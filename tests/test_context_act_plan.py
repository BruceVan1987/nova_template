"""逐幕计划的机械合同与真实装包；不把结构检查当成正文时序证明。"""

import importlib.util
import io
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest import mock

from act_plan_fixtures import VALID_ACT_PLAN
import test_context_timeline as timeline_fixture
from test_story_scaffold import ROOT


class ContextActPlanTests(unittest.TestCase):
    setUp = timeline_fixture.ContextTimelineTests.setUp
    write = timeline_fixture.ContextTimelineTests.write
    build = timeline_fixture.ContextTimelineTests.build
    source_candidates = timeline_fixture.ContextTimelineTests.source_candidates

    def card(self, acts=VALID_ACT_PLAN):
        return "## 本章控制卡\n\n- 场面简报：甲先敲门，等回应后才进门。\n\n" + acts + "\n---\n\n他提起包袱。\n"

    def set_card(self, acts=VALID_ACT_PLAN):
        path = self.root / "chapters/drafts/卷一/0002-测试.md"
        source = path.read_text(encoding="utf-8")
        path.write_text(source.split("## 本章控制卡", 1)[0] + self.card(acts), encoding="utf-8")
        return path

    def test_every_act_is_rendered_in_full_p0_write_card_and_existing_plan(self):
        path = self.set_card()
        for task, label in (("write", "目标章正向控制卡"), ("plan", "目标章控制卡")):
            with self.subTest(task=task):
                output, selected, omitted = self.build(task)
                cards = [candidate for candidate in selected if candidate.label == label]
                self.assertEqual(len(cards), 1)
                self.assertEqual(cards[0].priority, "P0")
                self.assertEqual(cards[0].path, path)
                self.assertIn(VALID_ACT_PLAN.rstrip(), cards[0].content)
                # 断言渲染的正文区块，不能仅凭纳入清单里的标签算成功。
                rendered = output.split(f"# [P0] {label}\n\n", 1)[1]
                self.assertIn(cards[0].content.rstrip(), rendered)
                self.assertNotIn("他提起包袱。", cards[0].content)
                self.assertFalse(any(candidate.label == label for candidate in omitted))
                required = sum(candidate.size for candidate in selected if candidate.priority == "P0")
                tight_output, _, _ = self.build(task, max_chars=required)
                self.assertIn(VALID_ACT_PLAN.rstrip(), tight_output)
                with self.assertRaisesRegex(ValueError, "P0 必需上下文.*超过预算"):
                    self.build(task, max_chars=required - 1)
        output, selected, _ = self.build("write")
        labels = [candidate.label for candidate in sorted(selected, key=lambda candidate: candidate.order)]
        self.assertEqual(labels[-4:], ["上章结尾原文", "目标章正向控制卡", "声口样本", "落笔前自检"])
        self.assertTrue(self.story._self_check_tail_ok(selected))

    def test_revise_full_source_retains_every_act_even_when_table_needs_repair(self):
        for acts in (VALID_ACT_PLAN, VALID_ACT_PLAN.replace("| 2 |", "| 9 |"), ""):
            with self.subTest(acts=acts):
                path = self.set_card(acts)
                output, _, _ = self.build("revise")
                rendered = output.split("# [TARGET] 目标章节全文\n\n", 1)[1]
                self.assertIn(path.read_text(encoding="utf-8").rstrip(), rendered)

    def test_write_missing_card_or_act_table_is_blocked_while_legacy_reads_work(self):
        with self.assertRaisesRegex(ValueError, "没有控制卡.*逐幕计划"):
            self.build("write", chapter=3)
        self.set_card("")
        with self.assertRaisesRegex(ValueError, "不可开写.*缺少「逐幕安排」"):
            self.build("write")
        for task in ("plan", "revise", "review"):
            with self.subTest(task=task):
                self.build(task)
        problems, warnings = self.story._skeleton_lint(self.story._load_chapters())
        self.assertFalse(any("逐幕" in item for item in problems + warnings))

    def test_empty_and_malformed_act_plan_never_opens_write(self):
        cases = {
            "missing_time": (VALID_ACT_PLAN.split("\n", 1)[1], "本章时间范围"),
            "empty_time": (VALID_ACT_PLAN.replace("第一日清晨到第一日午前。", ""), "本章时间范围"),
            "placeholder_time": (VALID_ACT_PLAN.replace("第一日清晨到第一日午前。", "TBD"), "本章时间范围"),
            "header_only": (VALID_ACT_PLAN.split("| 1 |", 1)[0], "至少一幕"),
            "wrong_header": (VALID_ACT_PLAN.replace("幕初状态", "开场"), "表头"),
            "separator": (VALID_ACT_PLAN.replace("|---|---|---|---|---|---|", "|---|---|---|---|---|bad|"), "分隔行"),
            "skipped_number": (VALID_ACT_PLAN.replace("| 2 |", "| 3 |"), "连续递增"),
            "duplicate_number": (VALID_ACT_PLAN.replace("| 2 |", "| 1 |"), "连续递增"),
            "missing_leading_pipe": (VALID_ACT_PLAN.replace("| 2 |", "2 |"), "破损表格行"),
            "fullwidth_leading_pipe": (VALID_ACT_PLAN.replace("| 2 |", "｜ 2 |"), "破损表格行"),
            "missing_cell": (VALID_ACT_PLAN.replace("无新增知情，乙仍未得知甲昨夜的去处。", ""), "第 2 幕"),
            "placeholder_cell": (VALID_ACT_PLAN.replace("无新增知情，乙仍未得知甲昨夜的去处。", "待填"), "第 2 幕"),
            "comment_cell": (VALID_ACT_PLAN.replace("无新增知情，乙仍未得知甲昨夜的去处。", "<!-- 待补 -->"), "第 2 幕"),
            "descriptive_placeholder": (VALID_ACT_PLAN.replace("无新增知情，乙仍未得知甲昨夜的去处。", "待填本幕信息"), "第 2 幕"),
            "duplicate_table": (VALID_ACT_PLAN + VALID_ACT_PLAN, "只能有一份"),
        }
        for name, (acts, error) in cases.items():
            with self.subTest(case=name):
                self.set_card(acts)
                self.assertIn(error, self.story.control_card_act_plan_error(self.card(acts)))
                with self.assertRaisesRegex(ValueError, error):
                    self.build("write")

    def test_one_act_and_no_new_knowledge_are_valid(self):
        acts = VALID_ACT_PLAN.split("| 2 |", 1)[0].replace(
            "乙在开门时才看见包袱破了，改变了赶人的打算。", "无新增知情。"
        )
        self.assertIsNone(self.story.control_card_act_plan_error(self.card(acts)))
        self.set_card(acts)
        self.build("write")

    def test_table_in_reader_prose_cannot_replace_control_card_table(self):
        body = self.card("") + VALID_ACT_PLAN
        self.assertIn("缺少「逐幕安排」", self.story.control_card_act_plan_error(body))

    def test_commented_out_card_or_act_table_cannot_satisfy_visible_plan(self):
        cases = (
            ("<!--\n" + self.card() + "\n-->", "缺少「逐幕安排」"),
            (self.card("<!--\n" + VALID_ACT_PLAN + "\n-->"), "缺少「逐幕安排」"),
            (self.card(VALID_ACT_PLAN.replace(
                "- 本章时间范围：第一日清晨到第一日午前。", "<!-- - 本章时间范围：第一日清晨到第一日午前。 -->"
            )), "本章时间范围"),
            (self.card("<!--\n" + VALID_ACT_PLAN), "HTML 注释"),
        )
        path = self.root / "chapters/drafts/卷一/0002-测试.md"
        prefix = path.read_text(encoding="utf-8").split("## 本章控制卡", 1)[0]
        for body, error in cases:
            with self.subTest(error=error):
                self.assertIn(error, self.story.control_card_act_plan_error(body))
                path.write_text(prefix + body, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, error):
                    self.build("write")
                # 初读改稿包仍可看到坏源文件，不能挡住修复所需的读取。
                output, _, _ = self.build("revise")
                self.assertIn(path.read_text(encoding="utf-8").rstrip(), output)

    def test_commented_candidate_rows_do_not_count_as_active_acts(self):
        commented = "<!--\n" + VALID_ACT_PLAN + "\n-->\n"
        self.assertIsNone(self.story.control_card_act_plan_error(self.card(commented + VALID_ACT_PLAN)))

    def test_plan_check_is_read_only_and_reports_structure_not_prose_correctness(self):
        self.set_card()
        def snapshot():
            return {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        before = snapshot()
        stdout = io.StringIO()
        with mock.patch.object(self.story, "_load_chapters", side_effect=AssertionError("不应写章节缓存")), redirect_stdout(stdout):
            self.assertEqual(self.story.cmd_plan_check(SimpleNamespace(chapter=2)), 0)
        self.assertIn("仍须按原文核对", stdout.getvalue())
        self.assertEqual(snapshot(), before)
        self.set_card("")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(self.story.cmd_plan_check(SimpleNamespace(chapter=2)), 1)
        self.assertIn("计划未就绪", stderr.getvalue())

    def test_ready_rejects_missing_act_plan_without_changing_historical_status(self):
        path = self.set_card("")
        original = path.read_bytes()
        stderr = io.StringIO()
        with mock.patch.object(self.story, "cmd_review_check", return_value=0), \
                mock.patch.object(self.story, "cmd_lint", return_value=0), \
                mock.patch.object(self.story, "_review_errors", return_value=[]), \
                mock.patch.object(self.story, "_reject_if_story_setup", return_value=False), redirect_stderr(stderr):
            self.assertEqual(self.story.cmd_ready_chapter(SimpleNamespace(chapter=2)), 1)
        self.assertIn("逐幕安排", stderr.getvalue())
        self.assertEqual(path.read_bytes(), original)

    def test_reader_only_export_never_leaks_the_act_plan(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(self.story.cmd_review_text(SimpleNamespace(chapter=2)), 0)
        text = stdout.getvalue()
        self.assertIn("他提起包袱。", text)
        for hidden in ("逐幕安排", "本章时间范围", "乙开门后才看见包袱", "乙递出空碗"):
            self.assertNotIn(hidden, text)

    def test_context_audit_detects_missing_or_truncated_actual_p0_card(self):
        original_build = self.story.build_context
        for alteration in ("missing", "optional", "truncated"):
            def altered_build(*args, **kwargs):
                output, selected, omitted = original_build(*args, **kwargs)
                if args[0] == "write":
                    card = next(candidate for candidate in selected if candidate.label == "目标章正向控制卡")
                    if alteration == "missing":
                        selected.remove(card)
                    elif alteration == "optional":
                        card.priority = "P1"
                    else:
                        card.content = card.content.split("| 2 |", 1)[0]
                return output, selected, omitted
            with self.subTest(alteration=alteration), mock.patch.object(self.story, "build_context", side_effect=altered_build):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    self.assertEqual(self.story.cmd_context_audit(SimpleNamespace()), 1)
                self.assertIn("完整逐幕控制卡", stdout.getvalue())

    def test_context_audit_reports_legacy_write_as_unready(self):
        self.set_card("")
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(self.story.cmd_context_audit(SimpleNamespace()), 1)
        self.assertIn("最近章写作包: 失败", stdout.getvalue())
        self.assertIn("缺少「逐幕安排」", stdout.getvalue())

    def test_rules_audit_only_accepts_the_specific_legacy_write_rejection(self):
        spec = importlib.util.spec_from_file_location("rules_audit_act_test", ROOT / "scripts/rules_audit.py")
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        self.set_card("")
        with mock.patch.object(audit, "ROOT", self.root):
            expected = "错误：第 2 章不可开写：控制卡缺少「逐幕安排」；先锁定逐幕计划，再生成写作包\n"
            cases = ((2, expected, "", True), (2, "缺少必需时间线", "", False), (0, "", "伪造的正常写作包", False))
            for code, stderr, stdout, accepted in cases:
                with self.subTest(code=code, stderr=stderr), mock.patch.object(audit.subprocess, "run", return_value=subprocess.CompletedProcess([], code, stdout=stdout, stderr=stderr)):
                    self.assertEqual(audit.check_context("write", 2) == [], accepted)

    def test_rules_audit_checks_actual_p0_card_content_instead_of_list_labels(self):
        spec = importlib.util.spec_from_file_location("rules_audit_render_test", ROOT / "scripts/rules_audit.py")
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        output, _, _ = self.build("write")
        second_act = VALID_ACT_PLAN.splitlines()[-1]
        cases = (
            (output, False),
            (output.replace(second_act + "\n", ""), True),
            (output.replace("# [P0] 目标章正向控制卡", "# [P1] 目标章正向控制卡"), True),
            (output.replace("# [P0] 目标章正向控制卡", "# [P0] 只有清单还在"), True),
        )
        with mock.patch.object(audit, "ROOT", self.root), mock.patch.object(audit, "QUALITY_RULES", self.root / "references/style-guide.md"):
            for rendered, malformed in cases:
                with self.subTest(malformed=malformed), mock.patch.object(audit.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout=rendered, stderr="")):
                    errors = audit.check_context("write", 2)
                    self.assertEqual(any("完整原样载入逐幕控制卡" in error for error in errors), malformed, errors)

    def context_args(self, out, **overrides):
        values = dict(task="write", chapter=2, focus=[], include=[], max_chars=self.story.CONTEXT_CONFIG["default_max_chars"], voice_chapter=None, out=out)
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_file_output_saves_the_complete_package_and_prints_only_its_path(self):
        expected, _, _ = self.build("write")
        stdout = io.StringIO()
        relative = ".story-cache/context-act-write.md"
        with redirect_stdout(stdout):
            self.assertEqual(self.story.cmd_context(self.context_args(relative)), 0)
        self.assertEqual((self.root / relative).read_text(encoding="utf-8"), expected)
        self.assertIn(VALID_ACT_PLAN.rstrip(), expected)
        self.assertEqual(stdout.getvalue(), f"已生成 {relative}\n")
        self.assertNotIn("逐幕安排", stdout.getvalue())

    def test_failed_package_generation_never_overwrites_the_previous_output(self):
        relative = ".story-cache/context-act-write.md"
        path = self.write(relative, "上一次完整写作包。\n")
        original = path.read_bytes()
        for invalid in ("budget", "missing_plan"):
            if invalid == "missing_plan":
                self.set_card("")
            stderr, stdout = io.StringIO(), io.StringIO()
            args = self.context_args(relative, max_chars=1 if invalid == "budget" else 80000)
            with self.subTest(invalid=invalid), redirect_stderr(stderr), redirect_stdout(stdout):
                self.assertEqual(self.story.cmd_context(args), 2)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(stdout.getvalue(), "")

    def test_interrupted_output_write_preserves_previous_file_and_cleans_temp(self):
        output, _, _ = self.build("write")
        relative = ".story-cache/context-act-write.md"
        path = self.write(relative, "上一次完整写作包。\n")
        original = path.read_bytes()
        real_named_temp = self.story.tempfile.NamedTemporaryFile

        def partial_write_then_fail(*args, **kwargs):
            handle = real_named_temp(*args, **kwargs)
            actual_write = handle.write
            def fail_write(text):
                actual_write(text[:len(text) // 2])
                handle.flush()
                raise OSError("模拟写盘中断")
            handle.write = fail_write
            return handle

        for failure in ("write", "replace"):
            patch = (
                mock.patch.object(self.story.tempfile, "NamedTemporaryFile", side_effect=partial_write_then_fail)
                if failure == "write" else mock.patch.object(self.story.Path, "replace", side_effect=OSError("模拟替换失败"))
            )
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(failure=failure), mock.patch.object(self.story, "build_context", return_value=(output, [], [])), \
                    patch, redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(self.story.cmd_context(self.context_args(relative)), 2)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("无法保存上下文包", stderr.getvalue())
            self.assertIn("模拟", stderr.getvalue())

    def test_context_file_output_is_restricted_to_resolved_cache_paths(self):
        outside = self.root / "outside"
        outside.mkdir()
        cache = self.root / ".story-cache"
        cache.mkdir(exist_ok=True)
        (cache / "outside-link").symlink_to(outside, target_is_directory=True)
        for relative in ("bad-package.md", ".story-cache/../bad-package.md", ".story-cache/outside-link/bad-package.md"):
            stderr = io.StringIO()
            with self.subTest(out=relative), redirect_stderr(stderr):
                self.assertEqual(self.story.cmd_context(self.context_args(relative)), 2)
            self.assertIn("--out 必须位于 .story-cache/ 内", stderr.getvalue())
        self.assertFalse((self.root / "bad-package.md").exists())
        self.assertFalse((outside / "bad-package.md").exists())

    def test_revise_same_chapter_snapshot_is_explicitly_not_an_act_entry_state(self):
        state = self.root / "continuity/state.md"
        original = state.read_text(encoding="utf-8")
        state.write_text("---\nlast-updated-chapter: 2\n---\n\n" + original, encoding="utf-8")
        output, selected, _ = self.build("revise")
        state_candidate = next(candidate for candidate in selected if candidate.label == "当前状态")
        self.assertIn("第2章末", state_candidate.content)
        self.assertIn("不能当成幕初状态", state_candidate.content)
        self.assertIn("目标章逐幕计划", output)
        _, review_selected, _ = self.build("review")
        review_state = next(candidate for candidate in review_selected if candidate.label == "当前状态")
        self.assertNotIn("时点警告", review_state.content)

    def test_rules_audit_rejects_workflow_commands_that_return_to_large_stdout(self):
        spec = importlib.util.spec_from_file_location("rules_audit_handoff_test", ROOT / "scripts/rules_audit.py")
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        command = "python3 scripts/story.py context --task write --chapter N"
        protocol = "参照 context-reading.md 分段完整读取。\n"
        cases = (
            (protocol + command + " --out .story-cache/context/write-N.md\n", None),
            (protocol + command + "\n", "--out"),
            (protocol + command + " --out .story-cache/context/write-N.md\n" + command + "\n", "--out"),
            (command + " --out .story-cache/context/write-N.md\n", "context-reading.md"),
        )
        with mock.patch.object(audit, "ROOT", self.root):
            for source, error in cases:
                with self.subTest(error=error):
                    path = self.write("workflow.md", source)
                    errors = audit.context_file_handoff_errors(path)
                    if error:
                        self.assertTrue(any(error in item for item in errors), errors)
                    else:
                        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
