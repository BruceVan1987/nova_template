#!/usr/bin/env python3
"""Audit rule entrypoints after a writing-workflow refactor."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
QUALITY_RULES = ROOT / "references" / "style-guide.md"
CHAPTER_WRITING_SKILL = ROOT / ".cursor" / "skills" / "chapter-writing" / "SKILL.md"
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
    ROOT / "references" / "chapter-review-workflow.md",
    ROOT / "references" / "context-reading.md",
    ROOT / ".cursor" / "agents" / "draft-reviewer.md",
    ROOT / ".codex" / "agents" / "draft-reviewer.toml",
    ROOT / ".cursor" / "agents" / "chapter-drafter.md",
    ROOT / ".codex" / "agents" / "chapter-drafter.toml",
    ROOT / "scripts" / "story.py",
)
# 防劣化：这些正向要求一旦被删，模型会退回“人人讲理、给台账写正文”的默认倾向。
REQUIRED_PHRASES = (
    (ROOT / "references/chapter-template.md", "场面简报", "控制卡缺场面简报"),
    (ROOT / "references/chapter-template.md", "本章时间范围", "控制卡缺时间范围"),
    (ROOT / "references/chapter-template.md", "### 逐幕安排", "控制卡缺逐幕表"),
    (CHAPTER_WRITING_SKILL, "plan-check", "锁卡后未核验计划结构"),
    (ROOT / ".cursor/skills/revision-continuity/SKILL.md", "plan-check", "改稿未核验计划结构"),
    (ROOT / "references/chapter-review-workflow.md", "language-only", "交稿缺独立语言轮"),
    (ROOT / "references/draft-review-protocol.md", "language-only", "审阅缺语言隔离模式"),
)
MUST_REFERENCE_QUALITY_RULES = (
    ROOT / "AGENTS.md",
    ROOT / ".cursor" / "rules" / "novel-style.mdc",
    ROOT / ".cursor" / "skills" / "chapter-writing" / "SKILL.md",
    ROOT / ".cursor" / "skills" / "revision-continuity" / "SKILL.md",
    ROOT / ".cursor" / "skills" / "plot-structure" / "SKILL.md",
    ROOT / "references" / "draft-review-protocol.md",
    ROOT / "references" / "chapter-review-workflow.md",
    ROOT / ".cursor" / "agents" / "chapter-drafter.md",
    ROOT / ".codex" / "agents" / "chapter-drafter.toml",
    ROOT / "scripts" / "story.py",
)
CANONICAL_ONLY_PHRASES = (
    "现代网文大白话",
    "熟而写生",
    "分派—执行—汇报—验收",
    "眼中闪过一丝",
    "人物不只在开口时存在",
)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SERIAL_CHAPTER_REQUIREMENTS = (
    ("单一正文执行者", re.compile(r"任何时刻只允许一个执行者.*章节正文")),
    ("不并行生成完整或局部候选正文", re.compile(r"禁止并行生成同一章的任何完整、局部或候选正文.*只选一份")),
    ("下章使用已回写状态", re.compile(r"第 N 章必须完成.*第 N\+1 章上下文")),
    ("并行仅限关键角色立场推演", re.compile(r"唯一并行例外.*关键角色立场推演")),
    ("角色推演不产出可拼接正文", re.compile(r"不得写完整场景.*可直接拼接的正文段落")),
    ("主执行者收拢后独自落笔", re.compile(r"等全部角色推演返回.*独自锁定控制卡并写正文")),
)
GLOBAL_SERIAL_CHAPTER_REQUIREMENTS = (
    ("项目级单一正文执行者", re.compile(r"章节正文的生成与改写是项目级串行临界区.*一个正文执行者")),
    ("项目级唯一并行例外", re.compile(r"唯一并行例外.*关键角色立场推演")),
    ("角色推演不可直接粘贴", re.compile(r"输出不得是可直接拼接或粘贴的正文")),
)
CONTEXT_FILE_HANDOFF_ENTRYPOINTS = (
    ROOT / ".cursor" / "skills" / "plot-structure" / "SKILL.md",
    ROOT / ".cursor" / "skills" / "chapter-writing" / "SKILL.md",
    ROOT / ".cursor" / "skills" / "revision-continuity" / "SKILL.md",
    ROOT / ".cursor" / "agents" / "chapter-drafter.md",
    ROOT / "references" / "draft-review-protocol.md",
)


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def latest_chapter() -> int | None:
    numbers = []
    for path in (ROOT / "chapters" / "drafts").glob("*/*.md"):
        match = re.match(r"(\d{4})-", path.name)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers) if numbers else None


def chapter_card_source(chapter: int):
    """读取唯一控制卡原文，供检查实际渲染正文区块。"""
    paths = list((ROOT / "chapters" / "drafts").glob(f"*/{chapter:04d}-*.md"))
    if len(paths) != 1:
        return None
    source = paths[0].read_text(encoding="utf-8")
    marker = "## 本章控制卡"
    if marker not in source:
        return None
    card = source.split(marker, 1)[1].split("\n---\n", 1)[0].strip()
    return paths[0], card


def legacy_write_card(chapter: int) -> bool:
    """仅识别真实旧控制卡；write 的任何其他失败仍为审计错误。"""
    source = chapter_card_source(chapter)
    if source is None:
        return False
    _, card = source
    return not re.search(r"^###\s+逐幕安排\s*$", card, re.MULTILINE)


def context_file_handoff_errors(path: Path) -> list[str]:
    if not path.is_file():
        return [f"上下文文件交接入口缺失：{rel(path)}"]
    source = path.read_text(encoding="utf-8")
    errors = []
    if "context-reading.md" not in source:
        errors.append(f"{rel(path)} 未引用上下文完整读取协议 context-reading.md")
    commands = re.findall(
        r"python3\s+scripts/story\.py\s+context\b([^\n`]*)",
        re.sub(r"\\\n\s*", " ", source),
    )
    if not commands or any("--out" not in command for command in commands):
        errors.append(f"{rel(path)} 的上下文命令必须用 --out 保存完整包后分段读取")
    return errors


def check_context(task: str, chapter: int, includes=()) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "story.py"),
        "context",
        "--task",
        task,
        "--chapter",
        str(chapter),
    ]
    for path in includes:
        command.extend(["--include", str(path)])
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    errors = []
    context_label = f"{task}（显式纳入规范）" if includes else task
    if task == "write" and legacy_write_card(chapter):
        expected = (
            f"错误：第 {chapter} 章不可开写：控制卡缺少「逐幕安排」；"
            "先锁定逐幕计划，再生成写作包"
        )
        if result.returncode == 2 and result.stderr.strip() == expected and not result.stdout.strip():
            return []
        errors.append(f"{context_label} 旧控制卡缺逐幕安排，应明确拒绝开写；实际未按该原因拒绝")
        return errors
    if result.returncode:
        errors.append(f"{context_label} 上下文生成失败：{result.stderr.strip() or result.stdout.strip()}")
        return errors
    # 只统计实际渲染的来源，不能靠标签，也不能把「因预算省略」清单算作已载入。
    # 「落笔前自检」尾块同样引规范原文，按块标签排除，不重复计入规范主块。
    count = sum(
        (ROOT / path).resolve() == QUALITY_RULES.resolve()
        for path in re.findall(r"^来源：`([^`]+)`；原因：", result.stdout, re.MULTILINE)
    )
    count -= sum(
        (ROOT / path).resolve() == QUALITY_RULES.resolve()
        for path in re.findall(
            r"^# \[P\d\] 落笔前自检\n\n来源：`([^`]+)`；原因：", result.stdout, re.MULTILINE
        )
    )
    expected_count = int(task in ("write", "revise", "review") or any(
        (ROOT / path).resolve() == QUALITY_RULES.resolve() for path in includes
    ))
    if count != expected_count:
        errors.append(f"{context_label} 上下文应载入 {expected_count} 次写作质量规范，实际 {count} 次")
    if task == "write":
        source = chapter_card_source(chapter)
        rendered_cards = list(re.finditer(
            r"^# \[P0\] 目标章正向控制卡\n\n来源：`([^`]+)`；原因：[^\n]*\n\n(.*?)(?=\n\n---\n\n# \[(?:P\d|TARGET)\] |\Z)",
            result.stdout, re.MULTILINE | re.DOTALL,
        ))
        rendered = rendered_cards[0] if len(rendered_cards) == 1 else None
        if not source or not rendered or (ROOT / rendered.group(1)).resolve() != source[0].resolve() or rendered.group(2).strip() != f"# 本章控制卡\n\n{source[1]}":
            errors.append("write 上下文未在实际 P0 正文区块完整原样载入逐幕控制卡")
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
        if "现场记录：" in result.stdout:
            errors.append("write 上下文不应载入逐章现场记录")
        if "### 落笔前自检" in result.stdout:
            errors.append("write 上下文的开写视图仍含「落笔前自检」小节；它只应作为包末清单出现")
    elif expected_count and task in ("plan", "revise", "review") and "## 7. 交稿前五道门" not in result.stdout:
        errors.append(f"{task} 上下文缺少完整冷读规范")
    blocks = re.findall(r"^# \[P\d\] (.+)$", result.stdout, re.MULTILINE)
    if task in ("write", "revise"):
        voice_labels = [label for label in blocks if label == "声口样本" or label.startswith("声口样章：")]
        if blocks[-1:] != ["落笔前自检"] or (voice_labels and blocks[-2:-1] != voice_labels):
            errors.append(
                f"{context_label} 包末必须是「落笔前自检」；配置声口样本时应紧邻其前，"
                f"实际为：{'、'.join(blocks[-2:]) if blocks else '（无）'}"
            )
    elif "落笔前自检" in blocks:
        errors.append(f"{context_label} 上下文不应载入「落笔前自检」尾块")
    if "审阅专项：" in result.stdout:
        errors.append(f"{task} 上下文仍载入已废弃的审阅专项")
    return errors


def main() -> int:
    errors: list[str] = []

    if not QUALITY_RULES.is_file():
        errors.append("缺少 references/style-guide.md")
    elif len(QUALITY_RULES.read_bytes()) > 16000:
        errors.append("style-guide.md 超过 16000 字节，可能再次堆积同义规则")

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

    if not CHAPTER_WRITING_SKILL.is_file():
        errors.append(f"章节写作 Skill 缺失：{rel(CHAPTER_WRITING_SKILL)}")
    else:
        chapter_skill_text = CHAPTER_WRITING_SKILL.read_text(encoding="utf-8")
        for label, pattern in SERIAL_CHAPTER_REQUIREMENTS:
            if not pattern.search(chapter_skill_text):
                errors.append(f"章节写作缺少串行不变量：{label}")

    agents_text = (ROOT / "AGENTS.md").read_text(encoding="utf-8") if (ROOT / "AGENTS.md").is_file() else ""
    for label, pattern in GLOBAL_SERIAL_CHAPTER_REQUIREMENTS:
        if not pattern.search(agents_text):
            errors.append(f"项目级章节串行规则缺失：{label}")

    for path, phrase, label in REQUIRED_PHRASES:
        if not path.is_file() or phrase not in path.read_text(encoding="utf-8"):
            errors.append(f"{rel(path)}：{label}（缺少「{phrase}」）")

    for path in CONTEXT_FILE_HANDOFF_ENTRYPOINTS:
        errors.extend(context_file_handoff_errors(path))

    for phrase in CANONICAL_ONLY_PHRASES:
        for path in RULE_ENTRYPOINTS:
            if path.is_file() and phrase in path.read_text(encoding="utf-8"):
                errors.append(f"{rel(path)} 复制了只应存在于 style-guide.md 的规则句：{phrase}")

    markdown_files = [
        ROOT / "AGENTS.md",
        ROOT / ".cursor" / "rules" / "novel-style.mdc",
        QUALITY_RULES,
        ROOT / "references" / "draft-review-protocol.md",
        ROOT / "references" / "chapter-review-workflow.md",
        ROOT / "references" / "context-reading.md",
        *sorted((ROOT / ".cursor" / "skills").glob("*/SKILL.md")),
        ROOT / ".cursor" / "agents" / "draft-reviewer.md",
        ROOT / ".cursor" / "agents" / "chapter-drafter.md",
        ROOT / "references" / "chapter-template.md",
        ROOT / "references" / "voice-samples.md",
        ROOT / "continuity" / "scene-log.md",
        ROOT / "story.md",
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
            errors.extend(check_context(task, chapter, (QUALITY_RULES, "references/../references/style-guide.md")))
        errors.extend(check_context("plan", chapter))
        errors.extend(check_context("plan", chapter, (QUALITY_RULES,)))

    if errors:
        print("规则审计失败：")
        for error in errors:
            print(f"- {error}")
        return 1

    print("规则审计通过：")
    print("- 正文质量只有 references/style-guide.md 一个事实源")
    print("- write 只载正向开写视图；write/revise 包末为可选「声口样本」接「落笔前自检」，revise/review 载入完整冷读规范")
    print("- 章节正文只能串行生成，并行仅限落笔前的关键角色立场推演")
    print("- 旧规则文件与引用均已清除")
    print("- 本地 Markdown 链接有效")
    print("- 规划、写章、改稿、写手与事实核对均用 --out 文件交接并引用完整读取协议")
    print("- 控制卡结构与独立审阅入口均在位；作品偏好由作者配置")
    if chapter is not None:
        if legacy_write_card(chapter):
            print(f"- 第{chapter}章旧控制卡缺逐幕安排，write 默认与显式纳入均明确拒绝；revise/review 仍可读取，plan 显式纳入全文")
        else:
            print(f"- 第{chapter}章 write/revise/review 默认及重复显式纳入均只载入一次质量规范（落笔前自检尾块不重复计数）；plan 显式纳入全文")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
