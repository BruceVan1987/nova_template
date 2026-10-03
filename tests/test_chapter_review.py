"""冷读流程的机械边界测试；不把这些测试当成小说语义审阅。"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from test_story_scaffold import load_story_module
VALID_ACT_PLAN = ""


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
            f"word-count: 0\n{extra}---\n\n## 本章控制卡\n\n- 场面简报：甲想进门讨口热水，乙憋着昨夜的火不肯开门，停在门闩落下那一声。\n\n"
            + VALID_ACT_PLAN + f"\n隐藏的控制卡材料。\n\n---\n\n{prose}\n",
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

    def test_review_text_outputs_only_title_prose_and_reader_notes(self):
        prose = self.original + "\n\n---\n\n注：\n1. 读者需要的资料。"
        for status in ("draft", "待审核"):
            with self.subTest(status=status):
                self.write_chapter(prose, status=status, extra="summary: 隐藏的摘要\n")
                code, output, error = self.call("review_text")
                self.assertEqual(code, 0, error)
                self.assertEqual(output, f"# 第1章 测试\n\n{prose}\n")
                self.assertEqual(error, "")
                for hidden in ("控制卡", "summary:", "隐藏的摘要", "word-count:", "status:"):
                    self.assertNotIn(hidden, output)

    def test_review_text_removes_work_comments_before_locating_separator(self):
        prose = "他抱走自己的毡。<!-- 行内工作注释 -->\n\n她把门关上了。"
        self.write_chapter(prose + "\n\n<!-- 章末工作注释 -->\n---\n\n注：读者资料。")
        text = self.chapter.read_text(encoding="utf-8").replace(
            "## 本章控制卡", "<!-- 控制卡工作注释\n---\n不能当作正文分隔\n-->\n## 本章控制卡"
        )
        self.chapter.write_text(text, encoding="utf-8")
        code, output, error = self.call("review_text")
        self.assertEqual(code, 0, error)
        self.assertIn(self.original, output)
        self.assertIn("注：读者资料。", output)
        for hidden in ("<!--", "工作注释", "不能当作正文分隔", "隐藏的控制卡材料"):
            self.assertNotIn(hidden, output)

    def test_review_text_rejects_missing_or_comment_only_separator(self):
        for replacement in ("\n\n", "\n\n<!--\n---\n-->\n\n"):
            with self.subTest(replacement=replacement):
                self.write_chapter(self.original)
                text = self.chapter.read_text(encoding="utf-8").replace(
                    "隐藏的控制卡材料。\n\n---\n\n", "隐藏的控制卡材料。" + replacement
                )
                self.chapter.write_text(text, encoding="utf-8")
                code, output, error = self.call("review_text")
                self.assertEqual(code, 1)
                self.assertEqual(output, "")
                self.assertIn("缺少控制卡与正文之间的 --- 分隔", error)

    def test_review_text_rejects_malformed_chapter_without_partial_output(self):
        self.write_chapter(self.original)
        original = self.chapter.read_text(encoding="utf-8")
        malformed = {
            "frontmatter_missing": original.split("---\n", 2)[-1],
            "frontmatter_unclosed": original.replace("word-count: 0\n---\n", "word-count: 0\n"),
            "frontmatter_invalid": original.replace("word-count: 0", "not a metadata field"),
            "frontmatter_duplicate": original.replace("word-count: 0", "title: 重复标题"),
            "title_missing": original.replace("title: 测试\n", ""),
            "title_not_scalar": original.replace("title: 测试", "title: [多个, 标题]"),
            "card_missing": original.replace("## 本章控制卡", "## 其他内容"),
            "card_after_separator": original.replace(self.original, "## 本章控制卡\n\n泄漏的计划。"),
            "comment_unclosed": original + "\n<!-- 未闭合工作注释",
            "comment_close_only": original + "\n-->",
        }
        for name, text in malformed.items():
            with self.subTest(name=name):
                self.chapter.write_text(text, encoding="utf-8")
                code, output, error = self.call("review_text")
                self.assertEqual(code, 1)
                self.assertEqual(output, "")
                self.assertIn("[读者正文导出失败]", error)

    def test_review_text_rejects_confirmed_unknown_status_empty_or_duplicate(self):
        for status in ("已确认", "unknown"):
            with self.subTest(status=status):
                self.write_chapter(self.original, status=status)
                code, output, error = self.call("review_text")
                self.assertEqual(code, 1)
                self.assertEqual(output, "")
                self.assertIn("修订检查" if status == "已确认" else "仅用于", error)
        for prose in ("", "<!-- 只有工作注释 -->", "注：只有资料注。"):
            with self.subTest(prose=prose):
                self.write_chapter(prose)
                code, output, error = self.call("review_text")
                self.assertEqual(code, 1)
                self.assertEqual(output, "")
                self.assertIn("没有正文", error)
        self.write_chapter(self.original)
        duplicate = self.chapter.parent / "0001-duplicate.md"
        duplicate.write_bytes(self.chapter.read_bytes())
        code, output, error = self.call("review_text")
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("实际找到 2 份", error)

    def test_review_text_does_not_create_or_modify_any_files_or_cache(self):
        def snapshot():
            return {
                path.relative_to(self.root).as_posix(): (
                    path.read_bytes() if path.is_file() else None, path.stat().st_mtime_ns
                )
                for path in self.root.rglob("*")
            }

        for cached in (False, True):
            with self.subTest(cached=cached):
                if cached:
                    self.finish_both()
                    context = self.root / ".story-cache" / "existing-context.md"
                    context.write_text("现有上下文包。", encoding="utf-8")
                before = snapshot()
                with mock.patch.object(self.story, "_load_chapters", side_effect=AssertionError("cache loader")), \
                        mock.patch.object(self.story, "_atomic_write_text", side_effect=AssertionError("write")), \
                        mock.patch.object(self.story, "cmd_context", side_effect=AssertionError("context")):
                    result = self.call("review_text")
                self.assertEqual(result[0], 0, result)
                self.assertEqual(snapshot(), before)
                if not cached:
                    self.assertFalse((self.root / ".story-cache").exists())

    def test_review_text_cli_routes_to_readonly_export(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["story.py", "review-text", "1"]), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as exit_result:
                self.story.main()
        self.assertEqual(exit_result.exception.code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), f"# 第1章 测试\n\n{self.original}\n")
        self.assertFalse((self.root / ".story-cache").exists())

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
