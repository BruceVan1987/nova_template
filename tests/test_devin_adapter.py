import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORY = ROOT / "scripts" / "story.py"
DEVIN_AGENTS = ROOT / ".devin" / "agents"
CURSOR_AGENTS = ROOT / ".cursor" / "agents"
DEVIN_CONFIG = ROOT / ".devin" / "config.json"
DEVIN_HOOKS = ROOT / ".devin" / "hooks.v1.json"
WRITE_GUARD = ROOT / ".devin" / "hooks" / "guard_write_paths.py"


def load_story_module():
    name = "story_devin_adapter"
    spec = importlib.util.spec_from_file_location(name, STORY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def parse_agent(path):
    story = load_story_module()
    raw, body = story.split_frontmatter(path.read_text(encoding="utf-8"))
    return story.parse_frontmatter(raw), body


class DevinAdapterTests(unittest.TestCase):
    def test_devin_agents_point_to_canonical_specs(self):
        canonical = {path.stem: ".cursor/agents/{}.md".format(path.stem) for path in CURSOR_AGENTS.glob("*.md")}
        canonical["character-stance"] = ".cursor/skills/chapter-writing/references/character-stance.md"
        devin_stems = {path.stem for path in DEVIN_AGENTS.glob("*.md")}
        self.assertEqual(devin_stems, set(canonical))
        for path in DEVIN_AGENTS.glob("*.md"):
            frontmatter, body = parse_agent(path)
            self.assertEqual(frontmatter.get("name"), path.stem)
            self.assertNotIn("model", frontmatter)
            target = canonical[path.stem]
            self.assertIn("`{}`".format(target), body)
            self.assertTrue((ROOT / target).exists())

    def test_character_stance_is_read_only(self):
        frontmatter, _ = parse_agent(DEVIN_AGENTS / "character-stance.md")
        self.assertEqual(frontmatter.get("allowed-tools"), ["read"])

    def test_chapter_drafter_tools(self):
        frontmatter, _ = parse_agent(DEVIN_AGENTS / "chapter-drafter.md")
        self.assertEqual(frontmatter.get("allowed-tools"), ["read", "edit", "exec"])

    def test_draft_reviewer_cannot_edit(self):
        frontmatter, _ = parse_agent(DEVIN_AGENTS / "draft-reviewer.md")
        tools = frontmatter.get("allowed-tools") or []
        self.assertIn("read", tools)
        self.assertNotIn("edit", tools)

    def test_permissions_guard_final_snapshots_and_confirmation(self):
        config = json.loads(DEVIN_CONFIG.read_text(encoding="utf-8"))
        permissions = config["permissions"]
        self.assertIn("Write(chapters/final/**)", permissions["deny"])
        self.assertIn("Write(.story-cache/reviews/*/snapshots/**)", permissions["deny"])
        self.assertIn("Exec(python3 scripts/story.py confirm-chapter)", permissions["ask"])
        for entry in permissions.get("allow", []):
            self.assertNotIn("confirm-chapter", entry)

    def test_hooks_route_file_writes_through_guard(self):
        entries = json.loads(DEVIN_HOOKS.read_text(encoding="utf-8"))["PreToolUse"]
        guards = [entry for entry in entries if any(
            "guard_write_paths.py" in hook.get("command", "") for hook in entry["hooks"]
        )]
        self.assertEqual(len(guards), 1)
        matcher = guards[0]["matcher"]
        for tool in ("write", "edit", "apply_patch", "notebook_edit"):
            self.assertTrue(re.search(matcher, tool), tool)
        for tool in ("exec", "read", "grep"):
            self.assertFalse(re.search(matcher, tool), tool)


def run_guard(tool_name, tool_input):
    return subprocess.run(
        [sys.executable, str(WRITE_GUARD)],
        input=json.dumps({"tool_name": tool_name, "tool_input": tool_input}),
        text=True,
        capture_output=True,
        check=False,
    )


class WriteGuardTests(unittest.TestCase):
    def assertBlocked(self, tool_name, tool_input):
        result = run_guard(tool_name, tool_input)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["decision"], "block")

    def assertAllowed(self, tool_name, tool_input):
        result = run_guard(tool_name, tool_input)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_blocks_final_chapters_by_absolute_and_relative_path(self):
        self.assertBlocked("write", {"file_path": str(ROOT / "chapters/final/devin-probe.md"), "content": "x"})
        self.assertBlocked("edit", {"file_path": "chapters/final/卷一/0001-测试章节.md", "old_string": "a", "new_string": "b"})

    def test_blocks_review_snapshots_and_generated_indexes(self):
        self.assertBlocked("write", {"file_path": str(ROOT / ".story-cache/reviews/0011/snapshots/probe.md"), "content": "x"})
        self.assertBlocked("edit", {"file_path": str(ROOT / "plot/arcs/_index.md"), "old_string": "a", "new_string": "b"})

    def test_blocks_apply_patch_targets(self):
        patch = "*** Begin Patch\n*** Update File: chapters/final/卷一/0001-测试章节.md\n@@\n-a\n+b\n*** End Patch\n"
        self.assertBlocked("apply_patch", {"patch": patch})

    def test_blocks_patch_move_into_generated_tree(self):
        patch = "*** Begin Patch\n*** Update File: chapters/drafts/probe.md\n*** Move to: chapters/final/probe.md\n*** End Patch\n"
        self.assertBlocked("apply_patch", {"patch": patch})

    def test_allows_drafts_ledgers_review_records_and_outside_paths(self):
        self.assertAllowed("edit", {"file_path": str(ROOT / "chapters/drafts/卷一/0011-测试章节.md"), "old_string": "a", "new_string": "b"})
        self.assertAllowed("edit", {"file_path": str(ROOT / "continuity/promises/_index.md"), "old_string": "a", "new_string": "b"})
        self.assertAllowed("write", {"file_path": str(ROOT / ".story-cache/reviews/0011/record.json"), "content": "{}"})
        self.assertAllowed("write", {"file_path": "/tmp/devin-guard-probe.md", "content": "x"})
        self.assertAllowed("write", {"file_path": str(ROOT / "chapters/drafts/probe.md"), "content": "*** Update File: chapters/final/x.md"})
        self.assertAllowed("edit", {"old_string": "a", "new_string": "b"})


if __name__ == "__main__":
    unittest.main()
