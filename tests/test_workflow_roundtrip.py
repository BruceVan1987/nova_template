"""在临时空白工作区验证真实 CLI 交接；合成文本不代表语义审阅通过。"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from act_plan_fixtures import VALID_ACT_PLAN
from test_story_scaffold import ROOT, load_story_module


class WorkflowRoundtripTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ("scripts", "references"):
            shutil.copytree(ROOT / name, self.root / name, ignore=shutil.ignore_patterns("__pycache__"))
        config = load_story_module().DEFAULT_PROJECT_CONFIG.copy()
        config["mode"] = "project"
        self.write("novel-project.json", json.dumps(config))
        self.write("references/voice-samples.md", "# 默认声口样本\n\n尚未配置。\n")
        self.write("story.md", "---\nstatus: active\n---\n\n## 一句话简介\n\n仅用于 CLI 测试。\n")
        self.write("plot/timeline.md", "# 时间线\n\n第一日清晨到午前。\n")
        self.write("continuity/state.md", (
            "## 人物位置、目标与边界\n\n| 人物 | 位置 |\n|---|---|\n| 甲 | 门外 |\n| 乙 | 屋内 |\n\n"
            "## 活跃物品与文书\n\n| 物品／文书 | 最后更新章节 |\n|---|---|\n\n"
            "## 关键知情范围\n\n| 人物 | 已知 |\n|---|---|\n| 甲 | 门口的事 |\n| 乙 | 有人敲门 |\n"
        ))
        self.write("continuity/relationships.md", (
            "| 人物A | 人物B | 适用章节 | 类型与阶段 | 私下／日常声口 | 公开／正式声口 | 冲突与禁止捷径 |\n"
            "|---|---|---|---|---|---|---|\n"
        ))
        for name in ("甲", "乙"):
            self.write(f"characters/{name}.md", f"---\nname: {name}\nrole: 配角\nstatus: alive\n---\n\n## 性格\n\n只用于临时测试。\n")

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def cli(self, *args, code=0):
        result = subprocess.run([sys.executable, "scripts/story.py", *map(str, args)], cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def stage(self, stage):
        output = self.cli("review-start", 1, "--stage", stage).stdout
        self.assertNotIn("隐藏的控制卡", output)
        record_path = self.root / ".story-cache/reviews/0001/record.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["stages"][stage]["notes"] = [{"quote": "乙把门关上了。", "reason": "测试记录绑定所引原句；此理由不充当语义评审。"}]
        record_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        self.cli("review-finish", 1, "--stage", stage)

    def test_first_chapter_reaches_pending_then_explicit_confirmation(self):
        self.cli("new-chapter", 1, "测试章节")
        chapter = next((self.root / "chapters/drafts").glob("*/*.md"))
        self.cli("plan-check", 1, code=1)
        rejected = self.cli("context", "--task", "write", "--chapter", 1, "--out", ".story-cache/write.md", code=2)
        self.assertIn("不可开写", rejected.stderr)
        self.assertFalse((self.root / ".story-cache/write.md").exists())

        text = chapter.read_text(encoding="utf-8")
        header = text.split("## 本章控制卡", 1)[0].replace('pov: ""', 'pov: 甲').replace('characters: []', 'characters: [甲, 乙]')
        prose = "甲抱走了自己的包袱。\n\n乙把门关上了。\n"
        chapter.write_text(header + "## 本章控制卡\n\n- 场面简报：甲敲门，乙开门后递出空碗，甲离开后门又关上了。\n\n" + VALID_ACT_PLAN + "\n隐藏的控制卡。\n\n---\n\n" + prose, encoding="utf-8")
        self.cli("plan-check", 1)
        receipt = self.cli("context", "--task", "write", "--chapter", 1, "--out", ".story-cache/write.md").stdout
        self.assertNotIn("逐幕安排", receipt)
        package = (self.root / ".story-cache/write.md").read_text(encoding="utf-8")
        self.assertIn(VALID_ACT_PLAN.rstrip(), package)
        self.assertIn("落笔前自检", package)
        self.assertNotIn("# [P0] 声口样本", package)

        exported = self.cli("review-text", 1).stdout
        self.assertIn(prose, exported)
        self.assertNotIn("隐藏的控制卡", exported)
        self.assertNotIn("pov:", exported)
        self.cli("ready-chapter", 1, code=1)
        self.stage("overall")
        self.stage("language")
        self.cli("review-check", 1)
        self.cli("ready-chapter", 1)
        self.assertIn("status: 待审核", chapter.read_text(encoding="utf-8"))
        self.assertFalse(list((self.root / "chapters/final").glob("*/*.md")))
        self.cli("confirm-chapter", 1)
        final = next((self.root / "chapters/final").glob("*/*.md")).read_text(encoding="utf-8")
        self.assertIn(prose, final)
        self.assertNotIn("隐藏的控制卡", final)
        self.cli("lint")
        self.cli("stats")
        self.cli("compile", "--out", "manuscript.md")
        self.assertIn(prose, (self.root / "manuscript.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
