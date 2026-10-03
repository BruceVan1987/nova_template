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







    # ---- 现场记录 -------------------------------------------------------

    def test_scene_log_is_loaded_by_chapter_and_never_into_write(self):
        self.write("continuity/scene-log.md", (
            "# 现场记录\n\n## 0001 现场记录\n\n第一章旁听者：门房。\n\n"
            "## 0002—0003 现场记录\n\n第二章执行账：两枚。\n"
        ))
        review, _, _ = self.story.build_context("review", 2)
        self.assertIn("第二章执行账", review)
        self.assertNotIn("第一章旁听者", review)
        plan, selected, omitted = self.story.build_context("plan", 2)
        scene = [c for c in selected + omitted if c.label.startswith("现场记录")]
        self.assertEqual([(c.label, c.priority) for c in scene], [("现场记录：第1章", "P2")])
        write, _, _ = self.story.build_context("write", 2)
        self.assertNotIn("现场记录", write)

    # ---- 单字简称 -------------------------------------------------------



    # ---- 事实源日志化 -----------------------------------------------------

    def test_chapter_logs_in_fact_sources_are_problems_and_in_arcs_warnings(self):
        self.write("worldbuilding/geography.md", "# 地理\n\n### 0008实际核验的位置\n\n细节。\n")
        self.write("continuity/state.md", self.story.STATE_PATH.read_text(encoding="utf-8")
                   + "\n第九章现场受众：院门外车夫可能看见。\n")
        self.write("plot/arcs/测试.md", "---\nstatus: 进行中\n---\n\n## 第九章正式控制卡\n\n旧卡。\n")
        self.write("characters/乙.md", "---\nname: 乙\n---\n\n## 性格\n\n- 0004首次出场时认出甲。\n")
        self.write("characters/丙.md", "---\nname: 丙\n---\n\n## 当前状态\n\n截至0010第十日午后，他已能走动。\n")
        problems, warnings = self.story._skeleton_lint(self.story._load_chapters())
        joined = "\n".join(problems)
        self.assertIn("worldbuilding/geography.md", joined)
        self.assertIn("continuity/state.md", joined)
        self.assertIn("[人物档案日志化] characters/乙.md", joined)
        self.assertIn("[人物档案日志化] characters/丙.md", joined)
        self.assertTrue(any("plot/arcs/测试.md" in item for item in warnings), warnings)
        self.assertFalse(any("plot/arcs/测试.md" in item for item in problems))

    def test_current_state_headings_are_not_flagged(self):
        self.write("worldbuilding/geography.md", "# 地理\n\n## 石桥集内部（文学虚构）\n\n| a | b |\n")
        problems, warnings = self.story._skeleton_lint(self.story._load_chapters())
        self.assertEqual([p for p in problems if "日志化" in p], [])

    def test_character_log_detects_distinct_refs_but_not_single_or_range(self):
        self.write("characters/乙.md", (
            "---\nname: 乙\nfirst-appearance: \"0004\"\n---\n\n## 人物关系\n\n"
            "- **甲**：0009交付消息，0010又到酒肆。\n"
            "- **丙**：只在0011见过一次。\n"
            "- **丁**：0012-0016一直同行。\n"
            "- **戊**：第十二至十六章一直同行。\n"
        ))
        self.write("characters/丁.md", (
            "---\nname: 丁\nfirst-appearance: \"0004\"\n---\n\n## 人物关系\n\n"
            "- **甲**：只在0011见过一次。\n"
        ))
        problems, _ = self.story._skeleton_lint(self.story._load_chapters())
        flagged = [item for item in problems if "characters/乙.md" in item and "串联多个章号" in item]
        self.assertEqual(len(flagged), 1, flagged)
        self.assertIn("有 1 条", flagged[0])
        self.assertIn("0009交付消息，0010", flagged[0])
        self.assertFalse(any("characters/丁.md" in item for item in problems), problems)

    def test_character_log_normalizes_chinese_refs_and_does_not_duplicate_old_rule(self):
        self.write("characters/乙.md", "---\nname: 乙\n---\n\n## 人物关系\n\n- **甲**：第五章见面，第八章翻脸。\n")
        self.write("characters/丙.md", "---\nname: 丙\n---\n\n## 性格\n\n- 0009见面，0010翻脸。\n")
        problems, _ = self.story._skeleton_lint(self.story._load_chapters())
        chinese = [item for item in problems if "characters/乙.md" in item]
        self.assertEqual(len(chinese), 1, chinese)
        self.assertIn("串联多个章号", chinese[0])
        old_rule = [item for item in problems if "characters/丙.md" in item]
        self.assertEqual(len(old_rule), 1, old_rule)
        self.assertIn("以章号开头", old_rule[0])
        self.assertNotIn("串联多个章号", old_rule[0])

    def test_character_entry_length_warns_only_in_selected_sections(self):
        line_301 = "- " + "甲" * 299
        line_300 = "- " + "乙" * 298
        long_other = "- " + "丙" * 400
        long_current = "- " + "丁" * 299
        self.write("characters/乙.md", (
            f"---\nname: 乙\n---\n\n## 人物关系\n\n{line_301}\n{line_300}\n"
            f"\n## 性格\n\n{long_other}\n\n## 当前状态与知情\n\n{long_current}\n"
        ))
        _, warnings = self.story._skeleton_lint(self.story._load_chapters())
        flagged = [item for item in warnings if "[人物条目过长] characters/乙.md" in item]
        self.assertEqual(len(flagged), 2, flagged)
        relationship = [item for item in flagged if "「人物关系」" in item]
        self.assertEqual(len(relationship), 1, relationship)
        self.assertIn("有 1 条超过300字", relationship[0])
        self.assertFalse(any("性格" in item for item in flagged), flagged)
        self.assertTrue(any("「当前状态与知情」" in item for item in flagged), flagged)

    # ---- 控制卡简报与新章模板 --------------------------------------------






class RollbackSceneLogTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / ".cursor/skills/story-branch-rollback/scripts/rollback_chapters.py"
        spec = importlib.util.spec_from_file_location("rollback_under_test", path)
        self.rollback = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.rollback)

    def test_scene_log_sections_after_target_are_removed(self):
        text = (
            "# 现场记录\n\n说明。\n\n"
            "## 0009 现场记录\n\n九章。\n\n"
            "## 0010—0012 现场记录\n\n跨越。\n\n"
            "## 0011 现场记录\n\n十一章。\n\n"
            "## 0012 现场记录\n\n十二章。\n"
        )
        kept, removed, straddling = self.rollback.split_scene_log(text, 10)
        self.assertIn("九章", kept)
        self.assertIn("跨越", kept)
        self.assertNotIn("十一章", kept)
        self.assertNotIn("十二章", kept)
        self.assertEqual(removed, ["## 0011 现场记录", "## 0012 现场记录"])
        self.assertEqual(straddling, ["## 0010—0012 现场记录"])


