#!/usr/bin/env python3
"""Audit rule entrypoints after a writing-workflow refactor."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
QUALITY_RULES = ROOT / "references" / "style-guide.md"
RETIRED_RULE_FILES = (
    "references/human-review-rules.md",
    "references/anti-ai-taste-checklist.md",
    "references/hooks-and-pacing.md",
    "references/review-modules/dialogue-relationships.md",
    "references/review-modules/quantities-objects.md",
    "references/review-modules/scene-continuity.md",
)
RULE_ENTRYPOINTS = (
    ROOT / "AGENTS.md",
    ROOT / ".cursor" / "rules" / "novel-style.mdc",
    ROOT / ".cursor" / "skills" / "chapter-writing" / "SKILL.md",
    ROOT / ".cursor" / "skills" / "revision-continuity" / "SKILL.md",
    ROOT / ".cursor" / "skills" / "plot-structure" / "SKILL.md",
    ROOT / "references" / "draft-review-protocol.md",
    ROOT / ".cursor" / "agents" / "draft-reviewer.md",
    ROOT / ".codex" / "agents" / "draft-reviewer.toml",
    ROOT / "scripts" / "story.py",
)
MUST_REFERENCE_QUALITY_RULES = (
    ROOT / "AGENTS.md",
    ROOT / ".cursor" / "rules" / "novel-style.mdc",
    ROOT / ".cursor" / "skills" / "chapter-writing" / "SKILL.md",
    ROOT / ".cursor" / "skills" / "revision-continuity" / "SKILL.md",
    ROOT / ".cursor" / "skills" / "plot-structure" / "SKILL.md",
    ROOT / "references" / "draft-review-protocol.md",
    ROOT / "scripts" / "story.py",
)
CANONICAL_ONLY_PHRASES = (
    "现代网文大白话",
    "熟而写生",
    "分派—执行—汇报—验收",
    "眼中闪过一丝",
)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def latest_chapter() -> int | None:
    numbers = []
    for path in (ROOT / "chapters" / "drafts").glob("*/*.md"):
        match = re.match(r"(\d{4})-", path.name)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers) if numbers else None


def check_context(task: str, chapter: int) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "story.py"),
        "context",
        "--task",
        task,
        "--chapter",
        str(chapter),
        "--max-chars",
        "35000",
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    errors = []
    if result.returncode:
        errors.append(f"{task} 上下文生成失败：{result.stderr.strip() or result.stdout.strip()}")
        return errors
    count = result.stdout.count("· 写作质量规范 ·")
    if count != 1:
        errors.append(f"{task} 上下文应载入一次写作质量规范，实际 {count} 次")
    if task == "write":
        if "写作质量规范（开写视图）" not in result.stdout:
            errors.append("write 上下文未使用正向开写视图")
        if "· 当前 arc：" in result.stdout:
            errors.append("write 上下文不应载入整份卷纲")
        for boundary_material in (
            "## 禁忌/边界", "| 不得越界 |", "| 不得写成 |",
            "## 能力与硬边界", "## 记录边界", "冲突与禁止捷径",
        ):
            if boundary_material in result.stdout:
                errors.append(f"write 上下文提前载入边界答辩素材：{boundary_material}")
        for review_only in ("## 3. 限知、受众与场内连续性", "## 6. 高频 AI 痕迹", "## 7. 交稿前五道门"):
            if review_only in result.stdout:
                errors.append(f"write 上下文提前载入冷读内容：{review_only}")
    elif task in ("revise", "review") and "## 7. 交稿前五道门" not in result.stdout:
        errors.append(f"{task} 上下文缺少完整冷读规范")
    if "审阅专项：" in result.stdout:
        errors.append(f"{task} 上下文仍载入已废弃的审阅专项")
    return errors


def main() -> int:
    errors: list[str] = []

    if not QUALITY_RULES.is_file():
        errors.append("缺少 references/style-guide.md")
    elif len(QUALITY_RULES.read_bytes()) > 12000:
        errors.append("style-guide.md 超过 12000 字节，可能再次堆积同义规则")

    for retired in RETIRED_RULE_FILES:
        if (ROOT / retired).exists():
            errors.append(f"废弃规则文件仍存在：{retired}")

    for path in RULE_ENTRYPOINTS:
        if not path.is_file():
            errors.append(f"规则入口缺失：{rel(path)}")
            continue
        text = path.read_text(encoding="utf-8")
        for retired in RETIRED_RULE_FILES:
            if retired.split("/")[-1] in text:
                errors.append(f"{rel(path)} 仍引用 {retired}")

    for path in MUST_REFERENCE_QUALITY_RULES:
        if path.is_file() and "style-guide.md" not in path.read_text(encoding="utf-8"):
            errors.append(f"{rel(path)} 未引用唯一写作质量规范")

    for phrase in CANONICAL_ONLY_PHRASES:
        for path in RULE_ENTRYPOINTS:
            if path.is_file() and phrase in path.read_text(encoding="utf-8"):
                errors.append(f"{rel(path)} 复制了只应存在于 style-guide.md 的规则句：{phrase}")

    markdown_files = [
        ROOT / "AGENTS.md",
        ROOT / ".cursor" / "rules" / "novel-style.mdc",
        QUALITY_RULES,
        ROOT / "references" / "draft-review-protocol.md",
        *sorted((ROOT / ".cursor" / "skills").glob("*/SKILL.md")),
        ROOT / ".cursor" / "agents" / "draft-reviewer.md",
    ]
    for path in markdown_files:
        if not path.is_file():
            continue
        for raw_target in MARKDOWN_LINK_RE.findall(path.read_text(encoding="utf-8")):
            target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                errors.append(f"{rel(path)} 存在断链：{raw_target}")

    chapter = latest_chapter()
    if chapter is not None:
        for task in ("write", "revise", "review"):
            errors.extend(check_context(task, chapter))

    if errors:
        print("规则审计失败：")
        for error in errors:
            print(f"- {error}")
        return 1

    print("规则审计通过：")
    print("- 正文质量只有 references/style-guide.md 一个事实源")
    print("- write 只载正向开写视图，revise/review 载入完整冷读规范")
    print("- 旧规则文件与引用均已清除")
    print("- 本地 Markdown 链接有效")
    if chapter is not None:
        print(f"- 第{chapter}章 write/revise/review 上下文均只载入一次质量规范")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
