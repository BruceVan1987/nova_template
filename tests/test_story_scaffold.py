import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
STORY = ROOT / "scripts" / "story.py"
AUDIENCE_AUDIT = ROOT / "scripts" / "audience_audit.py"
RULES_AUDIT = ROOT / "scripts" / "rules_audit.py"
CONFIG = ROOT / "novel-project.json"
# 空骨架用例只在模板仓库里成立；进入项目模式后，真实内容的健康度直接由
# `story.py lint` 与 `story.py context-audit` 检查，不在单元测试里假装仓库为空。
PROJECT_MODE = json.loads(CONFIG.read_text(encoding="utf-8")).get("mode") == "project"
SCAFFOLD_ONLY = unittest.skipIf(PROJECT_MODE, "项目模式：真实内容改由 lint / context-audit 命令检查")


def load_story_module():
    name = "story_under_test"
    spec = importlib.util.spec_from_file_location(name, STORY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(*args):
    return subprocess.run(
        [sys.executable, str(STORY), *map(str, args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class EmptyScaffoldTests(unittest.TestCase):
    def test_project_config_centralizes_scaling_limits(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(config["schema_version"], 1)
        self.assertIn(config["mode"], {"template", "project"})
        self.assertGreater(config["context"]["default_max_chars"], 0)
        self.assertGreater(config["limits"]["core_total_bytes"], 0)

    def test_shared_skills_are_symlinks(self):
        cursor_names = sorted(path.name for path in (ROOT / ".cursor" / "skills").iterdir())
        agent_names = sorted(path.name for path in (ROOT / ".agents" / "skills").iterdir())
        self.assertEqual(agent_names, cursor_names)
        for name in agent_names:
            self.assertTrue((ROOT / ".agents" / "skills" / name).is_symlink())

    @SCAFFOLD_ONLY
    def test_lint_accepts_empty_scaffold(self):
        result = run("lint")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("未发现问题", result.stdout)

    @SCAFFOLD_ONLY
    def test_context_audit_accepts_empty_scaffold(self):
        result = run("context-audit")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("核心常驻包合计", result.stdout)
        self.assertIn("暂无迁移基线", result.stdout)

    @SCAFFOLD_ONLY
    def test_catalog_and_stats_accept_empty_scaffold(self):
        first = run("catalog", "--refresh")
        second = run("catalog")
        stats = run("stats")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(stats.returncode, 0, stats.stdout + stats.stderr)
        self.assertIn("0 章", stats.stdout)

    def test_chapter_catalog_reuses_unchanged_frontmatter(self):
        story = load_story_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            drafts = root / "chapters" / "drafts" / "volume-01"
            drafts.mkdir(parents=True)
            chapter = drafts / "0001-test.md"
            chapter.write_text(
                "---\nchapter: 1\nvolume: 1\ntitle: test\nstatus: draft\nword-count: 4\n---\n\n正文内容\n",
                encoding="utf-8",
            )
            cache = root / ".story-cache" / "chapter-catalog-v1.json"
            with mock.patch.object(story, "ROOT", root), \
                    mock.patch.object(story, "CHAPTERS_DRAFTS_DIR", root / "chapters" / "drafts"), \
                    mock.patch.object(story, "CHAPTER_CATALOG_PATH", cache):
                chapters, first = story._load_chapters(full=False, with_stats=True)
                _, second = story._load_chapters(full=False, with_stats=True)
            self.assertEqual(first["refreshed"], 1)
            self.assertEqual(second["reused"], 1)
            self.assertIsNone(chapters[0]["body"])

    def test_plan_context_is_bounded_and_has_story_contract(self):
        result = run("context", "--task", "plan", "--chapter", 1)
        self.assertEqual(result.returncode, 0, result.stderr)
        budget = json.loads(CONFIG.read_text(encoding="utf-8"))["context"]["default_max_chars"]
        self.assertIn(f"/{budget} 字符", result.stdout)
        self.assertIn("故事硬约束", result.stdout)
        self.assertIn("story.md", result.stdout)

    def test_setup_blocks_mutating_writing_entrypoints(self):
        story = load_story_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "story.md").write_text(
                "---\nstatus: setup\n---\n\n# 故事圣经\n",
                encoding="utf-8",
            )
            drafts = root / "chapters" / "drafts"
            stderr = io.StringIO()
            with mock.patch.object(story, "ROOT", root), \
                    mock.patch.object(story, "CHAPTERS_DRAFTS_DIR", drafts), \
                    redirect_stderr(stderr):
                new_result = story.cmd_new_chapter(SimpleNamespace(volume="1", title="test"))
                confirm_result = story.cmd_confirm_chapter(SimpleNamespace(chapter=1))

            self.assertEqual(new_result, 2)
            self.assertEqual(confirm_result, 2)
            self.assertFalse(drafts.exists())
            self.assertIn("故事尚未初始化", stderr.getvalue())

    def test_setup_blocks_write_and_revise_but_allows_review_context(self):
        story = load_story_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "story.md").write_text(
                "---\nstatus: setup\n---\n\n# 故事圣经\n",
                encoding="utf-8",
            )
            base = {
                "chapter": 1,
                "focus": [],
                "include": [],
                "max_chars": 35000,
                "voice_chapter": None,
                "out": None,
            }
            stderr = io.StringIO()
            stdout = io.StringIO()
            with mock.patch.object(story, "ROOT", root), \
                    mock.patch.object(story, "build_context", return_value=("review package", [], [])), \
                    redirect_stderr(stderr), redirect_stdout(stdout):
                write_result = story.cmd_context(SimpleNamespace(task="write", **base))
                revise_result = story.cmd_context(SimpleNamespace(task="revise", **base))
                review_result = story.cmd_context(SimpleNamespace(task="review", **base))

            self.assertEqual(write_result, 2)
            self.assertEqual(revise_result, 2)
            self.assertEqual(review_result, 0)
            self.assertIn("故事尚未初始化", stderr.getvalue())
            self.assertEqual(stdout.getvalue(), "review package")

    def test_write_story_core_includes_voice_contract(self):
        story = load_story_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "story.md").write_text(
                "---\nstatus: active\n---\n\n"
                "# 故事圣经\n\n## 一句话简介\n\n一句话。\n\n"
                "## 核心冲突\n\n冲突。\n\n## 基调与文风\n\n现代白话。\n",
                encoding="utf-8",
            )
            with mock.patch.object(story, "ROOT", root):
                view = story._story_core("write")
        self.assertIn("## 基调与文风", view)
        self.assertIn("现代白话", view)

    def test_write_quality_view_contains_executable_prose_contract(self):
        story = load_story_module()
        view = story._quality_rules_view("write")
        self.assertIn("现代标准汉语句法", view)
        self.assertIn("省略号只表示真正的迟疑", view)
        self.assertIn("人物不只在开口时存在", view)
        self.assertIn("情绪释放服从处境", view)
        self.assertIn("控制卡、章纲和状态文件只提供因果", view)
        self.assertNotIn("## 6. 高频 AI 痕迹", view)
        self.assertNotIn("落笔前自检", view)

    def test_prose_lint_separates_hard_leaks_from_style_risks(self):
        story = load_story_module()
        body = (
            "## 本章控制卡\n\n- 推进主线\n\n---\n\n"
            "他觉得这段话正好用来推进主线。\n\n"
            "少顷，他闻言一怔，遂向门外走去。\n\n"
            "---\n\n注：本章控制卡不属于正文。\n"
        )
        issues = story.find_prose_style_issues(body)
        warnings = story.find_prose_style_warnings(body)
        self.assertEqual([item[1] for item in issues], ["工作台措辞穿帮"])
        self.assertEqual([item[1] for item in warnings], ["半文半白密度风险"])

    def test_prose_style_warnings_cover_ellipsis_and_short_sentence_density(self):
        story = load_story_module()
        body = (
            "---\n\n"
            "“我……”他看着门。“你……算了……我……不说了……”\n\n"
            "他醒了。天黑了。门开了。人走了。灯也灭了。\n"
        )
        categories = [item[1] for item in story.find_prose_style_warnings(body)]
        self.assertIn("省略号密度风险", categories)
        self.assertIn("短句堆叠风险", categories)

    def test_single_archaic_word_is_not_a_lint_failure_or_warning(self):
        story = load_story_module()
        body = "---\n\n他遂跟着队伍进了城。\n"
        self.assertEqual(story.find_prose_style_issues(body), [])
        self.assertEqual(story.find_prose_style_warnings(body), [])




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
        self.assertIn("章节正文只能串行生成", result.stdout)

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
