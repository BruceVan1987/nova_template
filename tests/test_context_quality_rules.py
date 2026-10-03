"""用隔离小说 fixture 检查唯一规范的阶段视图、优先级与审计。"""

import importlib.util
import io
import re
import shutil
import subprocess
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from test_story_scaffold import ROOT, STORY, load_story_module
from act_plan_fixtures import VALID_ACT_PLAN


class ContextQualityRulesTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.story = load_story_module()
        # 所有路径都转到临时小说，避免使用真实章节和当前事实档案。
        for name, value in list(vars(self.story).items()):
            if isinstance(value, Path) and value.is_relative_to(ROOT):
                self.stack.enter_context(mock.patch.object(self.story, name, self.root / value.relative_to(ROOT)))
        for name, section in (("CONTEXT_CONFIG", "context"), ("LIMIT_CONFIG", "limits")):
            self.stack.enter_context(mock.patch.object(self.story, name, self.story.DEFAULT_PROJECT_CONFIG[section].copy()))

        self.write("story.md", "---\nstatus: active\n---\n\n## 一句话简介\n\n测试故事。\n")
        self.write("plot/timeline.md", "# 故事时间线\n\n第零日到门口，第一日才进门。\n")
        self.write("continuity/state.md", (
            "## 人物位置、目标与边界\n\n| 人物 | 位置 |\n|---|---|\n| 甲 | 门口 |\n\n"
            "## 活跃物品与文书\n\n| 物品 | 位置 |\n|---|---|\n| 包袱 | 甲手中 |\n\n"
            "## 关键知情范围\n\n| 人物 | 已知 |\n|---|---|\n| 甲 | 眼前的事 |\n"
        ))
        self.write("characters/甲.md", "---\nname: 甲\nrole: 主角\n---\n\n## 身份\n\n测试人物。\n")
        for number, status in ((1, "已确认"), (2, "draft")):
            self.write(f"chapters/drafts/卷一/{number:04d}-测试.md", (
                f"---\nchapter: {number}\nvolume: 1\ntitle: 测试\nstatus: {status}\n"
                "characters: [甲]\nobjects: [包袱]\nlocations: []\nmentions: []\nsummary: 测试摘要\n"
                "---\n\n## 本章控制卡\n\n测试控制卡。\n\n"
                + VALID_ACT_PLAN + "\n---\n\n他提起包袱。\n"
            ))
        self.quality_source = (
            "# 测试规范\n\n"
            "## 1. 基本声口\n\n正向声口标记。\n\n"
            "### 落笔前自检\n\n自检清单标记-轻度书面词。\n\n"
            "## 2. 对话与人物关系\n\n正向对话标记。\n\n"
            "## 3. 限知、受众与场内连续性\n\n冷读限知标记。\n\n"
            "## 4. 事实\n\n冷读事实标记。\n\n"
            "## 5. 叙事发动机与节奏\n\n正向节奏标记。\n\n"
            "## 6. 高频 AI 痕迹\n\n冷读痕迹标记。\n\n"
            "## 7. 交稿前五道门\n\n冷读交稿标记。\n"
        )
        self.rules = self.write("references/style-guide.md", self.quality_source)
        self.write("references/voice-samples.md", (
            "# 默认声口样本\n\n## 测试样本\n\n"
            "- 章节：1\n- 起：他提起包袱。\n- 止：他提起包袱。\n"
        ))
        self.alias = self.root / "references/quality-link.md"
        self.alias.symlink_to(self.rules)
        (self.root / "scripts").mkdir()
        shutil.copy2(STORY, self.root / "scripts/story.py")

        spec = importlib.util.spec_from_file_location("rules_audit_quality_test", ROOT / "scripts/rules_audit.py")
        self.audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.audit)
        self.stack.enter_context(mock.patch.object(self.audit, "ROOT", self.root))
        self.stack.enter_context(mock.patch.object(self.audit, "QUALITY_RULES", self.rules))

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def build(self, task, **kwargs):
        return self.story.build_context(task, 2, **kwargs)

    def quality_candidates(self, candidates):
        # 「落笔前自检」尾块同样引规范路径，但是独立清单，不算规范主块。
        return [
            candidate for candidate in candidates
            if candidate.path.resolve() == self.rules.resolve() and candidate.label != "落笔前自检"
        ]

    def assert_quality_view(self, task, output, selected, omitted, priority):
        quality = self.quality_candidates(selected)
        self.assertEqual(len(quality), 1)
        self.assertEqual(self.quality_candidates(omitted), [])
        self.assertEqual(quality[0].priority, priority)
        blocks = re.findall(r"^# \[P\d\] (.+)$", output, re.MULTILINE)
        self.assertEqual(blocks.count("写作质量规范"), 1)
        for marker in ("正向声口标记", "正向对话标记", "正向节奏标记"):
            self.assertEqual(output.count(marker), 1)
        if task == "write":
            self.assertIn("写作质量规范（开写视图）", quality[0].content)
            for marker in ("冷读限知标记", "冷读事实标记", "冷读痕迹标记", "冷读交稿标记"):
                self.assertNotIn(marker, output)
        else:
            self.assertEqual(quality[0].content, self.quality_source)

    def test_default_prose_tasks_require_one_stage_view(self):
        for task in ("write", "revise", "review"):
            with self.subTest(task=task):
                self.assert_quality_view(task, *self.build(task), "P0")

    def test_include_aliases_promote_one_stage_view_to_p0(self):
        includes_cases = (
            ["references/style-guide.md"],
            ["references/style-guide.md", "references/style-guide.md"],
            [str(self.rules)],
            ["references/../references/./style-guide.md"],
            ["references/quality-link.md"],
            ["references/quality-link.md", str(self.rules), "./references/style-guide.md"],
        )
        for task in ("write", "revise", "review"):
            for includes in includes_cases:
                with self.subTest(task=task, includes=includes):
                    result = self.build(task, includes=includes)
                    self.assert_quality_view(task, *result, "P0")
                    self.assertIn("--include", self.quality_candidates(result[1])[0].reason)

    def test_tight_budget_counts_promoted_view_once_and_cannot_omit_it(self):
        for task in ("write", "revise", "review"):
            with self.subTest(task=task):
                _, default_selected, _ = self.build(task)
                base_required = sum(candidate.size for candidate in default_selected if candidate.priority == "P0")
                self.assert_quality_view(task, *self.build(task, max_chars=base_required), "P0")
                with self.assertRaisesRegex(ValueError, "P0 必需上下文.*超过预算"):
                    self.build(task, max_chars=base_required - 1)

                includes = ["references/style-guide.md", str(self.alias), str(self.rules)]
                _, promoted, _ = self.build(task, includes=includes)
                required = sum(candidate.size for candidate in promoted if candidate.priority == "P0")
                self.assertEqual(required, base_required)
                self.assert_quality_view(task, *self.build(task, includes=includes, max_chars=required), "P0")
                with self.assertRaisesRegex(ValueError, "P0 必需上下文.*超过预算"):
                    self.build(task, includes=includes, max_chars=required - 1)

    def test_plan_has_no_default_rules_and_explicitly_includes_full_rules(self):
        _, selected, omitted = self.build("plan")
        self.assertEqual(self.quality_candidates(selected + omitted), [])
        includes = ["references/style-guide.md", str(self.alias), str(self.rules)]
        self.assert_quality_view("plan", *self.build("plan", includes=includes), "P0")

    def test_non_rule_chapter_retains_voice_ending_and_explicit_full_view(self):
        chapter = self.root / "chapters/drafts/卷一/0001-测试.md"
        _, selected, _ = self.build("write", voice_chapter=1, includes=[str(chapter)])
        views = [candidate for candidate in selected if candidate.path.resolve() == chapter.resolve()]
        self.assertEqual(len(views), 3)
        self.assertEqual({candidate.label for candidate in views}, {
            "声口样章：第1章", "上章结尾原文", "强制纳入：chapters/drafts/卷一/0001-测试.md",
        })
        self.assertEqual(len({candidate.content for candidate in views}), 3)

    def test_focus_alias_cannot_reintroduce_full_rules_into_write(self):
        alias = self.root / "worldbuilding/locations/规范入口.md"
        alias.parent.mkdir(parents=True)
        alias.symlink_to(self.rules)
        self.assert_quality_view("write", *self.build("write", focuses=["规范入口"]), "P0")

    def test_rules_audit_checks_actual_default_and_explicit_contexts(self):
        for task in ("write", "revise", "review", "plan"):
            for includes in ([], [str(self.rules), str(self.alias)]):
                with self.subTest(task=task, includes=includes):
                    self.assertEqual(self.audit.check_context(task, 2, includes), [])

    def test_rules_audit_counts_resolved_sources_not_labels_or_omissions(self):
        output, _, _ = self.build("review")
        renamed = output.replace("写作质量规范", "另一入口")
        alias_source = "来源：`references/quality-link.md`；原因：另一入口\n"
        missing = renamed.replace("来源：`references/style-guide.md`；原因：", "来源：`story.md`；原因：")
        cases = ((renamed, None), (renamed + alias_source, "实际 2 次"), (missing, "实际 0 次"))
        for rendered, error in cases:
            with self.subTest(error=error):
                result = subprocess.CompletedProcess([], 0, stdout=rendered, stderr="")
                with mock.patch.object(self.audit.subprocess, "run", return_value=result):
                    errors = self.audit.check_context("review", 2)
                if error:
                    self.assertTrue(any(error in item for item in errors), errors)
                else:
                    self.assertEqual(errors, [])

    def test_rules_audit_uses_project_default_budget(self):
        output, _, _ = self.build("review")
        result = subprocess.CompletedProcess([], 0, stdout=output, stderr="")
        with mock.patch.object(self.audit.subprocess, "run", return_value=result) as run:
            self.assertEqual(self.audit.check_context("review", 2), [])
        self.assertNotIn("--max-chars", run.call_args.args[0])

    def test_write_and_revise_end_with_self_check_tail_block(self):
        for task in ("write", "revise"):
            with self.subTest(task=task):
                output, _, _ = self.build(task)
                blocks = re.findall(r"^# \[P\d\] (.+)$", output, re.MULTILINE)
                self.assertEqual(blocks[-2:], ["声口样本", "落笔前自检"])
                self.assertIn("自检清单标记-轻度书面词", output)
        output, selected, _ = self.build("write")
        main = [c for c in selected if c.label == "写作质量规范"]
        self.assertEqual(len(main), 1)
        self.assertNotIn("落笔前自检", main[0].content)
        self.assertNotIn("### 落笔前自检", output)

    def test_plan_and_review_have_no_self_check_tail_block(self):
        for task in ("plan", "review"):
            with self.subTest(task=task):
                output, _, _ = self.build(task)
                blocks = re.findall(r"^# \[P\d\] (.+)$", output, re.MULTILINE)
                self.assertNotIn("落笔前自检", blocks)
        # review 载入完整规范，原文里的落笔前自检小节仍在主块内。
        output, _, _ = self.build("review")
        self.assertIn("### 落笔前自检", output)
        self.assertIn("自检清单标记-轻度书面词", output)

    def test_main_rules_block_still_renders_once_with_include(self):
        for task in ("write", "revise"):
            with self.subTest(task=task):
                output, _, _ = self.build(task, includes=["references/style-guide.md"])
                blocks = re.findall(r"^# \[P\d\] (.+)$", output, re.MULTILINE)
                self.assertEqual(blocks.count("写作质量规范"), 1)
                self.assertEqual(blocks.count("落笔前自检"), 1)

    def test_context_audit_counts_resolved_paths_regardless_of_label(self):
        original_build = self.story.build_context
        for duplicate in (False, True):
            def altered_build(*args, **kwargs):
                output, selected, omitted = original_build(*args, **kwargs)
                quality = self.quality_candidates(selected)
                if quality:
                    quality[0].label = "另一规范入口"
                    if duplicate:
                        selected.append(self.story.ContextCandidate("P1", "重复入口", self.alias, "重复内容", "测试"))
                return output, selected, omitted

            with self.subTest(duplicate=duplicate), mock.patch.object(self.story, "build_context", side_effect=altered_build):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    code = self.story.cmd_context_audit(SimpleNamespace())
                self.assertEqual(code, int(duplicate), stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
