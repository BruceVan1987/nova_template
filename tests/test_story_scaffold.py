import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORY = ROOT / "scripts" / "story.py"
AUDIENCE_AUDIT = ROOT / "scripts" / "audience_audit.py"
RULES_AUDIT = ROOT / "scripts" / "rules_audit.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(STORY), *map(str, args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class EmptyScaffoldTests(unittest.TestCase):
    def test_shared_skills_are_symlinks(self):
        cursor_names = sorted(path.name for path in (ROOT / ".cursor" / "skills").iterdir())
        agent_names = sorted(path.name for path in (ROOT / ".agents" / "skills").iterdir())
        self.assertEqual(agent_names, cursor_names)
        for name in agent_names:
            self.assertTrue((ROOT / ".agents" / "skills" / name).is_symlink())

    def test_lint_accepts_empty_scaffold(self):
        result = run("lint")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("未发现问题", result.stdout)

    def test_context_audit_accepts_empty_scaffold(self):
        result = run("context-audit")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("核心常驻包合计", result.stdout)
        self.assertIn("暂无迁移基线", result.stdout)

    def test_plan_context_is_bounded_and_has_story_contract(self):
        result = run("context", "--task", "plan", "--chapter", 1, "--max-chars", 35000)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("故事硬约束", result.stdout)
        self.assertIn("story.md", result.stdout)

    def test_direction_context_uses_candidate_pool(self):
        result = run("context", "--task", "direction", "--max-chars", 35000)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("方向冷人物候选", result.stdout)

    def test_include_cannot_escape_project(self):
        result = run(
            "context", "--task", "plan", "--chapter", 1,
            "--include", "/etc/hosts",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("只能读取项目内文件", result.stderr)

    def test_rules_audit_accepts_single_quality_source(self):
        result = subprocess.run(
            [sys.executable, str(RULES_AUDIT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("只有 references/style-guide.md 一个事实源", result.stdout)

    def test_audience_audit_accepts_explicit_terms(self):
        with tempfile.TemporaryDirectory() as directory:
            chapter = Path(directory) / "chapter.md"
            chapter.write_text(
                "---\nchapter: 1\n---\n\n## 本章控制卡\n\n---\n\n“机密代号不能公开。”\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(AUDIENCE_AUDIT), str(chapter), "--term", "机密代号"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[机密代号]", result.stdout)


if __name__ == "__main__":
    unittest.main()
