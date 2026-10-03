"""冷读流程的机械边界测试；不把这些测试当成小说语义审阅。"""

import io
import json
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from test_story_scaffold import load_story_module


class ChapterReviewTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.story = load_story_module()
        drafts = self.root / "chapters" / "drafts"
        drafts.mkdir(parents=True)
        self.chapter = drafts / "0001-test.md"
        self.original = "他抱走自己的毡。\n\n她把门关上了。"
        self.write_chapter(self.original)
        (self.root / "story.md").write_text("---\nstatus: active\n---\n", encoding="utf-8")
        self.rules = self.root / "style-guide.md"
        self.rules.write_text("正文质量规范。\n", encoding="utf-8")
        for name, value in {
            "ROOT": self.root,
            "CHAPTERS_DIR": self.root / "chapters",
            "CHAPTERS_DRAFTS_DIR": drafts,
            "CHAPTERS_FINAL_DIR": self.root / "chapters" / "final",
            "CHAPTERS_INDEX_PATH": self.root / "chapters" / "_index.md",
            "CHAPTER_CATALOG_PATH": self.root / ".story-cache" / "chapter-catalog-v1.json",
            "QUALITY_RULES": self.rules,
        }.items():
            self.stack.enter_context(mock.patch.object(self.story, name, value))
        self.record_path = self.root / ".story-cache" / "reviews" / "0001" / "record.json"

    def write_chapter(self, prose, status="draft", title="测试", extra=""):
        self.chapter.write_text(
            f"---\nchapter: 1\nvolume: 1\ntitle: {title}\nstatus: {status}\n"
            f"word-count: 0\n{extra}---\n\n## 本章控制卡\n\n隐藏的控制卡材料。\n\n---\n\n{prose}\n",
            encoding="utf-8",
        )

    def call(self, command, stage=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = getattr(self.story, f"cmd_{command}")(SimpleNamespace(chapter=1, stage=stage))
        return code, stdout.getvalue(), stderr.getvalue()

    def read_record(self):
        return json.loads(self.record_path.read_text(encoding="utf-8"))

    def save_record(self, record):
        self.record_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    def note(self, stage):
        record = self.read_record()
        record["stages"][stage]["notes"] = [
            {"quote": "她把门关上了。", "reason": "此处动作主体明确，动作承接上一段的离开。"}
        ]
        self.save_record(record)

    def finish_stage(self, stage):
        result = self.call("review_start", stage)
        self.assertEqual(result[0], 0, result)
        self.note(stage)
        result = self.call("review_finish", stage)
        self.assertEqual(result[0], 0, result)

    def finish_both(self):
        self.finish_stage("overall")
        self.finish_stage("language")

    def finding(self, decision="open", stage="overall", **changes):
        record = self.read_record()
        finding = {
            "stage": stage,
            "source_sha256": record["stages"][stage]["prose_sha256"],
            "quote": "他抱走自己的毡。",
            "problem": "这句缩略影响顺口程度。",
            "decision": decision,
            "replacement": "",
            "reason": "",
        }
        finding.update(changes)
        record["findings"].append(finding)
        self.save_record(record)

    def test_missing_record_blocks_check_and_confirm_without_writing(self):
        before = self.chapter.read_bytes()
        for command in ("review_check", "confirm_chapter", "ready_chapter"):
            with self.subTest(command=command):
                result = self.call(command)
                self.assertEqual(result[0], 1, result)
                self.assertIn("缺少冷读记录", result[2])
        self.assertEqual(self.chapter.read_bytes(), before)
        self.assertFalse(self.record_path.exists())
        self.assertFalse((self.root / "chapters" / "final").exists())

    def test_start_outputs_full_clean_prose_including_reader_notes(self):
        self.write_chapter(self.original + "\n\n---\n\n注：读者需要的资料。")
        before = self.chapter.read_bytes()
        code, output, _ = self.call("review_start", "overall")
        self.assertEqual(code, 0)
        self.assertIn(self.original, output)
        self.assertIn("注：读者需要的资料。", output)
        self.assertNotIn("隐藏的控制卡材料", output)
        self.assertNotIn("word-count:", output)
        self.assertEqual(self.chapter.read_bytes(), before)

    def test_language_cannot_start_before_overall_completes(self):
        self.assertEqual(self.call("review_start", "language")[0], 1)
        self.call("review_start", "overall")
        self.assertEqual(self.call("review_start", "language")[0], 1)

    def test_checkbox_without_evidence_does_not_complete(self):
        self.call("review_start", "overall")
        result = self.call("review_finish", "overall")
        self.assertEqual(result[0], 1)
        self.assertIn("缺少原句与判断依据", result[2])

    def test_evidence_must_exist_in_current_prose(self):
        self.call("review_start", "overall")
        self.note("overall")
        record = self.read_record()
        record["stages"]["overall"]["notes"][0]["quote"] = "隐藏的控制卡材料。"
        self.save_record(record)
        self.assertEqual(self.call("review_finish", "overall")[0], 1)

    def test_zero_findings_can_complete_both_stages(self):
        self.finish_both()
        before = self.chapter.read_bytes()
        self.assertEqual(self.call("review_check")[0], 0)
        self.assertEqual(self.read_record()["findings"], [])
        self.assertEqual(self.chapter.read_bytes(), before)

    def test_missing_second_stage_blocks_delivery(self):
        self.finish_stage("overall")
        self.assertEqual(self.call("review_check")[0], 1)

    def test_prose_change_invalidates_both_stages_and_confirm(self):
        self.finish_both()
        self.write_chapter(self.original.replace("毡。", "毡子。"))
        result = self.call("review_check")
        self.assertEqual(result[0], 1)
        self.assertIn("overall 记录已过期", result[2])
        self.assertIn("language 记录已过期", result[2])
        self.assertEqual(self.call("confirm_chapter")[0], 1)
        self.assertFalse((self.root / "chapters" / "final").exists())

    def test_change_during_read_cannot_be_sealed_as_old_version(self):
        self.call("review_start", "overall")
        self.note("overall")
        self.write_chapter(self.original + "\n\n门外又响了一声。")
        self.assertEqual(self.call("review_finish", "overall")[0], 1)

    def test_metadata_and_control_card_changes_do_not_invalidate_prose(self):
        self.finish_both()
        text = self.chapter.read_text(encoding="utf-8")
        text = text.replace("word-count: 0", "word-count: 20\nsummary: 摘要更新")
        text = text.replace("隐藏的控制卡材料。", "修改控制卡记录。")
        self.chapter.write_text(text, encoding="utf-8")
        self.assertEqual(self.call("review_check")[0], 0)

    def test_title_and_rules_changes_invalidate_checks(self):
        self.finish_both()
        self.write_chapter(self.original, title="另一个标题")
        self.assertEqual(self.call("review_check")[0], 1)
        self.write_chapter(self.original)
        self.rules.write_text("修订过的质量规范。", encoding="utf-8")
        self.assertEqual(self.call("review_check")[0], 1)

    def test_reader_footnote_change_invalidates_checks(self):
        self.finish_both()
        self.write_chapter(self.original + "\n\n---\n\n注：新资料。")
        self.assertEqual(self.call("review_check")[0], 1)

    def test_unresolved_finding_blocks_finish_and_survives_restart(self):
        self.call("review_start", "overall")
        self.note("overall")
        self.finding()
        self.assertEqual(self.call("review_finish", "overall")[0], 1)
        self.call("review_start", "overall")
        self.assertEqual(len(self.read_record()["findings"]), 1)
        self.assertTrue(self.read_record()["history"])

    def test_fixed_finding_retains_original_evidence_across_prose_versions(self):
        self.call("review_start", "overall")
        self.finding()
        original_hash = self.read_record()["findings"][0]["source_sha256"]
        replacement = "他抱走自己的毡子。"
        self.write_chapter(self.original.replace("他抱走自己的毡。", replacement))
        record = self.read_record()
        record["findings"][0].update(decision="fixed", replacement=replacement, reason="补全名词。")
        self.save_record(record)
        self.finish_both()
        self.assertEqual(self.call("review_check")[0], 0)
        self.assertEqual(self.read_record()["findings"][0]["source_sha256"], original_hash)

    def test_retained_finding_requires_reason_and_existing_quote(self):
        self.call("review_start", "overall")
        self.note("overall")
        self.finding(decision="retained")
        self.assertEqual(self.call("review_finish", "overall")[0], 1)
        record = self.read_record()
        record["findings"][0]["reason"] = "测试保留记录校验，不是实际文风判断。"
        self.save_record(record)
        self.assertEqual(self.call("review_finish", "overall")[0], 0)

    def test_false_fixed_claim_is_rejected(self):
        self.call("review_start", "overall")
        self.note("overall")
        self.finding(decision="fixed", replacement="根本不存在的改句。", reason="已修改。")
        self.assertEqual(self.call("review_finish", "overall")[0], 1)

    def test_existing_unrelated_sentence_is_not_proof_of_a_fix(self):
        self.call("review_start", "overall")
        self.note("overall")
        self.finding(decision="fixed", replacement="她把门关上了。", reason="声称已经修改。")
        result = self.call("review_finish", "overall")
        self.assertEqual(result[0], 1)
        self.assertIn("改句之外仍有原句", result[2])

    def test_deletion_claim_is_checked_against_actual_prose(self):
        self.call("review_start", "overall")
        self.note("overall")
        self.finding(decision="fixed", replacement="", reason="删除此句。")
        self.assertEqual(self.call("review_finish", "overall")[0], 1)
        self.write_chapter("她把门关上了。")
        self.finish_both()
        self.assertEqual(self.call("review_check")[0], 0)

    def test_post_finish_note_edit_invalidates_receipt(self):
        self.finish_both()
        record = self.read_record()
        record["stages"]["language"]["notes"][0]["reason"] = "改过的判断。"
        self.save_record(record)
        self.assertEqual(self.call("review_check")[0], 1)
        self.assertEqual(self.call("review_finish", "language")[0], 0)
        self.assertEqual(self.call("review_check")[0], 0)

    def test_restarting_overall_requires_language_again(self):
        self.finish_both()
        self.finish_stage("overall")
        self.assertNotIn("language", self.read_record()["stages"])
        self.assertEqual(self.call("review_check")[0], 1)

    def test_corrupt_record_is_not_silently_reset(self):
        self.call("review_start", "overall")
        for malformed in ("{", "null", "[]", '{"schema_version": 9}'):
            with self.subTest(malformed=malformed):
                self.record_path.write_text(malformed, encoding="utf-8")
                self.assertEqual(self.call("review_start", "overall")[0], 1)
                self.assertEqual(self.call("review_check")[0], 1)
                self.assertEqual(self.record_path.read_text(encoding="utf-8"), malformed)

    def test_tampered_or_missing_snapshot_blocks_check(self):
        self.finish_both()
        digest = self.read_record()["stages"]["overall"]["prose_sha256"]
        snapshot = self.record_path.parent / "snapshots" / f"{digest}.md"
        snapshot.write_text("被篡改的快照。", encoding="utf-8")
        self.assertEqual(self.call("review_check")[0], 1)
        snapshot.unlink()
        self.assertEqual(self.call("review_check")[0], 1)

    def test_invalid_source_hash_cannot_escape_snapshot_directory(self):
        self.call("review_start", "overall")
        self.note("overall")
        self.finding(decision="retained", source_sha256="../../outside", reason="测试。")
        self.assertEqual(self.call("review_finish", "overall")[0], 1)

    def test_ready_runs_lint_and_only_sets_pending_review(self):
        self.finish_both()
        with mock.patch.object(self.story, "cmd_lint", return_value=0) as lint:
            result = self.call("ready_chapter")
        self.assertEqual(result[0], 0, result)
        lint.assert_called_once()
        self.assertIn("status: 待审核", self.chapter.read_text(encoding="utf-8"))
        self.assertFalse((self.root / "chapters" / "final").exists())
        self.assertEqual(self.call("review_check")[0], 0)

    def test_lint_failure_does_not_mark_ready(self):
        self.finish_both()
        before = self.chapter.read_bytes()
        with mock.patch.object(self.story, "cmd_lint", return_value=1):
            self.assertEqual(self.call("ready_chapter")[0], 1)
        self.assertEqual(self.chapter.read_bytes(), before)

    def test_confirm_checks_records_before_export_and_ready_cannot_downgrade(self):
        self.finish_both()
        self.assertFalse((self.root / "chapters" / "final").exists())
        self.assertEqual(self.call("confirm_chapter")[0], 0)
        final = next((self.root / "chapters" / "final").rglob("*.md"))
        self.assertIn(self.original, final.read_text(encoding="utf-8"))
        before = self.chapter.read_bytes()
        with mock.patch.object(self.story, "cmd_lint", return_value=0):
            self.assertEqual(self.call("ready_chapter")[0], 1)
        self.assertEqual(self.chapter.read_bytes(), before)

    def test_duplicate_or_empty_target_is_rejected(self):
        duplicate = self.chapter.parent / "0001-duplicate.md"
        duplicate.write_bytes(self.chapter.read_bytes())
        self.assertEqual(self.call("review_start", "overall")[0], 1)
        duplicate.unlink()
        self.write_chapter("")
        self.assertEqual(self.call("review_start", "overall")[0], 1)


if __name__ == "__main__":
    unittest.main()
