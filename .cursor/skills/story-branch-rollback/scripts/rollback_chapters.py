#!/usr/bin/env python3
"""Preview or remove chapter drafts/finals after an authorized rollback point."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


CHAPTER_RE = re.compile(r"^chapter:\s*(\d+)\s*$", re.MULTILINE)
FINAL_RE = re.compile(r"^(\d{4})-")
FIRST_RE = re.compile(r'^first-appearance:\s*["\']?(\d+)["\']?\s*$', re.MULTILINE)
SCENE_HEADING_RE = re.compile(r"^##\s+(\d{4})(?:\s*[—–-]\s*(\d{4}))?")
VOICE_CHAPTER_RE = re.compile(r"^-\s*章节[：:]\s*(\d+)\s*$", re.MULTILINE)


def split_scene_log(text: str, target: int) -> tuple[str, list[str], list[str]]:
    """按章号切分现场记录。

    返回 (保留文本, 移除的段标题, 跨越回滚点、需人工语义审查的段标题)。
    起始章晚于回滚点的段属于废弃分支，整段移除；完整原文仍在备份 Git 引用里。
    """
    kept, removed, straddling = [], [], []
    dropping = False
    for line in text.splitlines():
        match = SCENE_HEADING_RE.match(line)
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else start
            dropping = start > target
            if dropping:
                removed.append(line)
                continue
            if end > target:
                straddling.append(line.strip())
        elif line.startswith("# "):
            dropping = False
        if not dropping:
            kept.append(line)
    return "\n".join(kept).rstrip() + "\n", [h.strip() for h in removed], straddling


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )


def chapter_number(path: Path) -> int | None:
    match = CHAPTER_RE.search(path.read_text(encoding="utf-8"))
    return int(match.group(1)) if match else None


def first_appearance(path: Path) -> int | None:
    match = FIRST_RE.search(path.read_text(encoding="utf-8"))
    return int(match.group(1)) if match else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=int)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--snapshot-ref", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    if not (root / "scripts/story.py").exists():
        parser.error("--root 不是小说项目根目录")

    target_matches = []
    old_drafts = []
    for path in sorted((root / "chapters/drafts").glob("*/*.md")):
        number = chapter_number(path)
        if number == args.target:
            target_matches.append(path)
        elif number is not None and number > args.target:
            old_drafts.append(path)
    if len(target_matches) != 1:
        parser.error(f"目标章必须唯一存在，当前命中 {len(target_matches)} 个")
    target_text = target_matches[0].read_text(encoding="utf-8")
    if "status: 已确认" not in target_text and 'status: "已确认"' not in target_text:
        parser.error("目标章尚未确认，拒绝以它作为回滚点")

    ref_check = git(root, "rev-parse", "--verify", args.snapshot_ref)
    if ref_check.returncode:
        parser.error("备份 Git 引用不存在")

    old_finals = []
    for path in sorted((root / "chapters/final").glob("*/*.md")):
        match = FINAL_RE.match(path.name)
        if match and int(match.group(1)) > args.target:
            old_finals.append(path)

    late_characters = []
    for path in sorted((root / "characters").glob("*.md")):
        if path.name == "_index.md":
            continue
        first = first_appearance(path)
        if first is not None and first > args.target:
            late_characters.append((first, path))

    print(f"回滚点: 第{args.target}章")
    print(f"备份: {args.snapshot_ref} -> {ref_check.stdout.strip()}")
    print(f"草稿待移除: {len(old_drafts)}")
    for path in old_drafts:
        print(f"  - {path.relative_to(root)}")
    print(f"正稿待移除: {len(old_finals)}")
    for path in old_finals:
        print(f"  - {path.relative_to(root)}")
    print(f"晚出场人物待语义审查: {len(late_characters)}")
    for first, path in late_characters:
        print(f"  - 第{first}章 {path.relative_to(root)}")

    scene_log = root / "continuity/scene-log.md"
    scene_kept, scene_removed, scene_straddling = (
        split_scene_log(scene_log.read_text(encoding="utf-8"), args.target)
        if scene_log.exists() else ("", [], [])
    )
    print(f"现场记录待移除段: {len(scene_removed)}")
    for heading in scene_removed:
        print(f"  - {heading}")
    for heading in scene_straddling:
        print(f"  ! 跨越回滚点，需人工删去回滚点之后的内容：{heading}")

    voice_file = root / "references/voice-samples.md"
    late_voices = [
        int(number) for number in VOICE_CHAPTER_RE.findall(voice_file.read_text(encoding="utf-8"))
        if int(number) > args.target
    ] if voice_file.exists() else []
    for number in late_voices:
        print(f"  ! 默认声口样本引用了第{number}章，回滚后必须换成回滚点以前的已确认章节")

    if not args.apply:
        print("仅预览；加 --apply 才移除章节文件。")
        return 0

    dirty = git(root, "status", "--porcelain")
    skill_prefixes = (
        "?? .cursor/skills/story-branch-rollback/",
        "?? .agents/skills/story-branch-rollback",
    )
    unexpected = [
        line for line in dirty.stdout.splitlines()
        if line and not line.startswith(skill_prefixes)
    ]
    if unexpected:
        print("拒绝执行：存在无关或未备份的工作树改动：", file=sys.stderr)
        print("\n".join(unexpected), file=sys.stderr)
        return 2

    for path in old_drafts + old_finals:
        path.unlink()
    if scene_removed:
        scene_log.write_text(scene_kept, encoding="utf-8")
    for directory in sorted(
        {path.parent for path in old_drafts + old_finals}, reverse=True
    ):
        if directory.exists() and not any(directory.iterdir()):
            directory.rmdir()
    print("已移除旧分支章节与现场记录段；人物与连续性仍须按 Skill 语义回滚。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
