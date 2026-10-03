"""时间线与章节必需材料的预算边界；不把机械检查当成正文时序审阅。"""

import io
import re
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from test_story_scaffold import ROOT, load_story_module
from act_plan_fixtures import VALID_ACT_PLAN


class ContextTimelineTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.story = load_story_module()
        for name, value in list(vars(self.story).items()):
            if isinstance(value, Path) and value.is_relative_to(ROOT):
                self.stack.enter_context(mock.patch.object(self.story, name, self.root / value.relative_to(ROOT)))
        for name, section in (("CONTEXT_CONFIG", "context"), ("LIMIT_CONFIG", "limits")):
            self.stack.enter_context(mock.patch.object(self.story, name, self.story.DEFAULT_PROJECT_CONFIG[section].copy()))

        self.write("story.md", "---\nstatus: active\n---\n\n## 一句话简介\n\n测试故事。\n")
        self.timeline_source = (
            "---\nschema-version: 1\nlast-updated-chapter: 1\n---\n\n# 故事时间线\n\n"
            "## 前史\n\n开篇前四年，甲离家。\n\n"
            "## 已发生\n\n第零日甲在门口，第一个来客只听见敲门。\n\n"
            "## 作者侧消息排程\n\n第一日送信，第二日才到，第三日回信；甲尚未获知。\n\n"
            "## 规划\n\n第四日见面，第五日才辨认敌人，第六日才能讲出前史；均尚未发生。\n"
        )
        self.timeline = self.write("plot/timeline.md", self.timeline_source)
        self.alias = self.root / "plot/time-link.md"
        self.alias.symlink_to(self.timeline)
        self.arc = self.write("plot/arcs/门口.md", (
            "---\nstatus: 进行中\nchapter-range: 0001-0010\n---\n\n"
            "# 门口\n\n甲先敲门，乙只能被提及，张丙将来才出现。\n"
        ))
        self.write("continuity/state.md", (
            "## 人物位置、目标与边界\n\n| 人物 | 位置 |\n|---|---|\n| 甲 | 门口 |\n\n"
            "## 活跃物品与文书\n\n| 物品 | 位置 |\n|---|---|\n| 包袱 | 甲手中 |\n\n"
            "## 关键知情范围\n\n| 人物 | 已知 |\n|---|---|\n| 甲 | 眼前的事 |\n"
        ))
        for name in ("甲", "乙", "张丙"):
            self.write(f"characters/{name}.md", f"---\nname: {name}\n---\n\n## 身份\n\n{name}的事实档案。\n")
        self.place = self.write("worldbuilding/locations/门口.md", "# 门口\n\n## 概况\n\n门口有一条窄沟。\n")
        self.write("references/style-guide.md", (
            "# 规范\n\n## 1. 基本声口\n\n白话。\n\n### 落笔前自检\n\n检查句子。\n\n"
            "## 2. 对话与人物关系\n\n有来有往。\n\n## 3. 限知、受众与场内连续性\n\n审阅顺序。\n\n"
            "## 5. 叙事发动机与节奏\n\n写场面。\n\n## 7. 交稿前五道门\n\n冷读。\n"
        ))
        for number, status in ((1, "已确认"), (2, "draft")):
            self.write(f"chapters/drafts/卷一/{number:04d}-测试.md", (
                f"---\nchapter: {number}\nvolume: 1\ntitle: 测试\nstatus: {status}\npov: 甲\n"
                "characters: [甲]\nmentions: [乙]\nobjects: [包袱]\nlocations: [门口]\nsummary: 敲门。\n"
                "---\n\n## 本章控制卡\n\n- 场面简报：甲先敲门，等回应后才进门。\n\n"
                + VALID_ACT_PLAN + "\n---\n\n他提起包袱。\n"
            ))
        self.write("references/voice-samples.md", (
            "# 默认声口样本\n\n## 测试样本\n\n- 章节：1\n- 起：他提起包袱。\n- 止：他提起包袱。\n"
        ))

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def build(self, task, chapter=2, **kwargs):
        return self.story.build_context(task, chapter, **kwargs)

    def source_candidates(self, candidates, path):
        return [candidate for candidate in candidates if candidate.path.resolve() == path.resolve()]

    def test_chapter_tasks_require_full_timeline_with_all_message_clocks(self):
        for task in ("plan", "write", "revise", "review"):
            with self.subTest(task=task):
                output, selected, omitted = self.build(task)
                timelines = self.source_candidates(selected, self.timeline)
                self.assertEqual(len(timelines), 1)
                self.assertEqual(timelines[0].priority, "P0")
                self.assertEqual(timelines[0].content, self.timeline_source)
                self.assertEqual(self.source_candidates(omitted, self.timeline), [])
                self.assertIn(self.timeline_source.rstrip(), output)
                for marker in ("开篇前四年", "第零日", "第一日送信", "第二日才到", "第三日回信", "均尚未发生"):
                    self.assertEqual(output.count(marker), 1)

    def test_include_aliases_do_not_duplicate_timeline_or_change_tail_order(self):
        includes = ["plot/timeline.md", str(self.timeline), "plot/../plot/timeline.md", "plot/time-link.md"]
        for task in ("plan", "write", "revise", "review"):
            with self.subTest(task=task):
                baseline, base_selected, _ = self.build(task)
                output, selected, omitted = self.build(task, includes=includes)
                timelines = self.source_candidates(selected, self.timeline)
                self.assertEqual(len(timelines), 1)
                self.assertIn("--include", timelines[0].reason)
                self.assertEqual(sum(c.size for c in selected), sum(c.size for c in base_selected))
                self.assertEqual(self.source_candidates(omitted, self.timeline), [])
                self.assertEqual(re.findall(r"^# \[P\d\] (.+)$", output, re.MULTILINE),
                                 re.findall(r"^# \[P\d\] (.+)$", baseline, re.MULTILINE))

    def test_required_sources_cannot_be_silently_omitted(self):
        for task in ("plan", "write", "revise", "review"):
            with self.subTest(task=task):
                _, selected, _ = self.build(task)
                required = sum(c.size for c in selected if c.priority == "P0")
                _, tight_selected, tight_omitted = self.build(task, max_chars=required)
                expected_paths = [self.timeline, self.root / "characters/甲.md"]
                if task != "write":
                    expected_paths.append(self.arc)
                if task != "plan":
                    expected_paths.extend([self.place, self.root / "references/style-guide.md"])
                for path in expected_paths:
                    self.assertTrue(self.source_candidates(tight_selected, path), path)
                    self.assertEqual(self.source_candidates(tight_omitted, path), [], path)
                with self.assertRaisesRegex(ValueError, "P0 必需上下文.*超过预算"):
                    self.build(task, max_chars=required - 1)
                # 仅被提及的乙仍可省略，不能用远期人物挤掉实际出场者。
                self.assertTrue(self.source_candidates(tight_omitted, self.root / "characters/乙.md"))

    def test_next_chapter_direct_profiles_required_mentions_remain_optional(self):
        _, selected, _ = self.build("plan", chapter=3)
        self.assertEqual(self.source_candidates(selected, self.root / "characters/甲.md")[0].priority, "P0")
        self.assertEqual(self.source_candidates(selected, self.root / "characters/乙.md")[0].priority, "P1")
        self.assertEqual(self.source_candidates(selected, self.root / "characters/张丙.md")[0].priority, "P2")

    def test_pov_profile_is_required_even_when_not_in_characters_list(self):
        chapter = self.root / "chapters/drafts/卷一/0002-测试.md"
        chapter.write_text(chapter.read_text(encoding="utf-8").replace("characters: [甲]", "characters: []"), encoding="utf-8")
        for task in ("plan", "write", "revise", "review"):
            with self.subTest(task=task):
                _, selected, _ = self.build(task)
                self.assertEqual(self.source_candidates(selected, self.root / "characters/甲.md")[0].priority, "P0")
        _, selected, _ = self.build("plan", chapter=3)
        self.assertEqual(self.source_candidates(selected, self.root / "characters/甲.md")[0].priority, "P0")

    def test_current_arc_explicit_include_is_deduplicated(self):
        for task in ("plan", "revise", "review"):
            with self.subTest(task=task):
                _, baseline, _ = self.build(task)
                _, selected, _ = self.build(task, includes=[str(self.arc), "plot/arcs/门口.md"])
                arcs = self.source_candidates(selected, self.arc)
                self.assertEqual(len(arcs), 1)
                self.assertIn("--include", arcs[0].reason)
                self.assertEqual(sum(c.size for c in selected), sum(c.size for c in baseline))
        _, default_write, _ = self.build("write")
        self.assertEqual(self.source_candidates(default_write, self.arc), [])
        _, explicit_write, _ = self.build("write", includes=[str(self.arc), "plot/arcs/门口.md"])
        self.assertEqual(len(self.source_candidates(explicit_write, self.arc)), 1)

    def test_missing_timeline_blocks_chapter_tasks_but_direction_remains_isolated(self):
        self.timeline.unlink()
        for task in ("plan", "write", "revise", "review"):
            with self.subTest(task=task), self.assertRaisesRegex(ValueError, "缺少必需时间线"):
                self.build(task)
        output, selected, omitted = self.build("direction")
        self.assertNotIn("故事时间线", output)
        self.assertNotIn("开篇前四年", output)
        self.assertEqual(self.source_candidates(selected + omitted, self.timeline), [])
        with self.assertRaisesRegex(ValueError, "不接受 --include"):
            self.build("direction", includes=["plot/timeline.md"])

    def test_context_audit_requires_actual_full_p0_timeline_in_every_chapter_task(self):
        original_build = self.story.build_context
        for task in ("plan", "write", "revise", "review"):
            for alteration in ("missing", "duplicate", "truncated", "optional"):
                def altered_build(*args, **kwargs):
                    output, selected, omitted = original_build(*args, **kwargs)
                    if args[0] == task:
                        timeline = self.source_candidates(selected, self.timeline)[0]
                        if alteration == "missing":
                            selected.remove(timeline)
                            omitted.append(timeline)
                        elif alteration == "duplicate":
                            selected.append(timeline)
                        elif alteration == "truncated":
                            timeline.content = timeline.content[:40]
                        else:
                            timeline.priority = "P1"
                    return output, selected, omitted

                with self.subTest(task=task, alteration=alteration), mock.patch.object(self.story, "build_context", side_effect=altered_build):
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        code = self.story.cmd_context_audit(SimpleNamespace())
                    self.assertEqual(code, 1, stdout.getvalue())
                    self.assertIn("故事时间线未作为完整 P0 源文恰好载入一次", stdout.getvalue())

    def test_context_audit_detects_missing_required_materials_without_omission_entries(self):
        original_build = self.story.build_context
        for task in ("plan", "write", "revise", "review"):
            required_paths = [self.root / "characters/甲.md"]
            if task != "write":
                required_paths.append(self.arc)
            if task != "plan":
                required_paths.append(self.place)
            for path in required_paths:
                for alteration in ("missing", "optional"):
                    def altered_build(*args, **kwargs):
                        output, selected, omitted = original_build(*args, **kwargs)
                        if args[0] == task:
                            source = self.source_candidates(selected, path)[0]
                            if alteration == "missing":
                                selected.remove(source)
                            else:
                                source.priority = "P1"
                        return output, selected, omitted

                    with self.subTest(task=task, path=path, alteration=alteration), mock.patch.object(self.story, "build_context", side_effect=altered_build):
                        stdout = io.StringIO()
                        with redirect_stdout(stdout):
                            code = self.story.cmd_context_audit(SimpleNamespace())
                        self.assertEqual(code, 1, stdout.getvalue())
                        self.assertIn("缺少 P0 章节必需资料", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
