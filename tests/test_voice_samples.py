"""骨架防劣化：声口样本、现场记录、单字简称、事实源日志化与控制卡简报。

全部在临时小说中运行，不读真实章节与事实源。
"""

import importlib.util
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

CONFIRMED_PROSE = (
    "门开了一条缝。\n\n"
    "“谁？”里面的人问。\n\n"
    "“我。”他说，“再不开，我就睡你门口。”\n\n"
    "“睡吧，”她说，“明早扫地顺手把你扫走。”\n\n"
    "他笑了一声，膝盖却先软了。\n"
)


class SkeletonGuardTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.story = load_story_module()
        for name, value in list(vars(self.story).items()):
            if isinstance(value, Path) and value.is_relative_to(ROOT):
                self.stack.enter_context(mock.patch.object(self.story, name, self.root / value.relative_to(ROOT)))
        for name, section in (("CONTEXT_CONFIG", "context"), ("LIMIT_CONFIG", "limits"), ("LINT_CONFIG", "lint")):
            self.stack.enter_context(mock.patch.object(self.story, name, self.story.DEFAULT_PROJECT_CONFIG[section].copy()))

        self.write("story.md", "---\nstatus: active\n---\n\n## 一句话简介\n\n测试故事。\n")
        self.write("plot/timeline.md", "# 故事时间线\n\n第零日到门口，第一日才进门。\n")
        self.write("continuity/state.md", (
            "## 人物位置、目标与边界\n\n| 人物 | 位置 |\n|---|---|\n| 甲 | 门口 |\n\n"
            "## 活跃物品与文书\n\n| 物品 | 位置 |\n|---|---|\n| 包袱 | 甲手中 |\n\n"
            "## 关键知情范围\n\n| 人物 | 已知 |\n|---|---|\n| 甲 | 眼前的事 |\n"
        ))
        self.write("characters/甲.md", "---\nname: 甲\nrole: 主角\n---\n\n## 性格\n\n嘴硬。\n")
        self.write("references/style-guide.md", "# 规范\n\n## 1. 基本声口\n\n声口。\n")
        self.chapter(1, "已确认", "## 本章控制卡\n\n- 场面简报：甲敲门。\n", CONFIRMED_PROSE)
        self.chapter(2, "draft", "## 本章控制卡\n\n- 场面简报：甲进门后和乙为一碗水吵起来，乙先动手，停在碗摔碎。\n" + VALID_ACT_PLAN, "他进了门。\n")

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def chapter(self, number, status, card, prose, extra_fm=""):
        return self.write(f"chapters/drafts/卷一/{number:04d}-测试.md", (
            f"---\nchapter: {number}\nvolume: 1\ntitle: 测试\nstatus: {status}\n"
            f"characters: [甲]\nobjects: []\nlocations: []\nmentions: []\nsummary: 测试摘要\n{extra_fm}"
            f"---\n\n{card}\n---\n\n{prose}"
        ))

    def voice_file(self, start="门开了一条缝。", end="膝盖却先软了。", chapter=1):
        return self.write("references/voice-samples.md", (
            "# 默认声口样本\n\n## 熟人拌嘴\n\n"
            f"- 章节：{chapter}\n- 起：{start}\n- 止：{end}\n"
        ))

    def labels(self, output):
        return re.findall(r"^# \[P\d\] (.+)$", output, re.MULTILINE)

    # ---- 声口样本 -------------------------------------------------------

    def test_voice_samples_are_last_in_write_and_revise_only(self):
        self.voice_file()
        for task in ("write", "revise"):
            with self.subTest(task=task):
                output, selected, _ = self.story.build_context(task, 2)
                self.assertEqual(self.labels(output)[-1], "声口样本")
                self.assertIn("再不开，我就睡你门口", output)
        for task in ("plan", "review"):
            with self.subTest(task=task):
                output, _, _ = self.story.build_context(task, 2)
                self.assertNotIn("声口样本", self.labels(output))

    def test_write_tail_order_is_ending_then_card_then_voice(self):
        self.voice_file()
        output, _, _ = self.story.build_context("write", 2)
        self.assertEqual(self.labels(output)[-3:], ["上章结尾原文", "目标章正向控制卡", "声口样本"])

    def test_configured_sample_that_cannot_fit_fails_instead_of_returning_only_intro(self):
        self.voice_file()
        with self.assertRaisesRegex(ValueError, "超过样本预算"):
            self.story._default_voice_samples(self.story._load_chapters(), max_chars=10)

    def test_explicit_voice_chapter_replaces_default_sample(self):
        self.voice_file()
        output, _, _ = self.story.build_context("write", 2, voice_chapter=1)
        labels = self.labels(output)
        self.assertEqual(labels[-1], "声口样章：第1章")
        self.assertNotIn("声口样本", labels)

    def test_broken_anchor_is_reported_and_not_loaded(self):
        self.voice_file(end="这句正文里没有")
        chapters = self.story._load_chapters()
        problems, _ = self.story._skeleton_lint(chapters)
        self.assertTrue(any("声口样本失效" in item for item in problems), problems)
        output, _, _ = self.story.build_context("write", 2)
        self.assertNotIn("声口样本", self.labels(output))

    def test_voice_sample_must_come_from_confirmed_chapter(self):
        self.voice_file(start="他进了门。", end="他进了门。", chapter=2)
        problems, _ = self.story._skeleton_lint(self.story._load_chapters())
        self.assertTrue(any("尚未确认" in item for item in problems), problems)


    # ---- 现场记录 -------------------------------------------------------


    # ---- 单字简称 -------------------------------------------------------



    # ---- 事实源日志化 -----------------------------------------------------






    # ---- 控制卡简报与新章模板 --------------------------------------------






class EmptyVoiceTests(unittest.TestCase):
    def test_empty_template_voice_file_is_allowed(self):
        story = load_story_module()
        with tempfile.TemporaryDirectory() as directory:
            voice = Path(directory) / "voice-samples.md"
            voice.write_text("# 默认声口样本\n\n尚未配置。\n", encoding="utf-8")
            with mock.patch.object(story, "VOICE_SAMPLES_PATH", voice):
                self.assertEqual(story._voice_sample_entries(), [])
                self.assertEqual(story._voice_sample_excerpts([]), ([], []))
