#!/usr/bin/env python3
"""Surface configured secret-bearing prose for a manual audience check."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "continuity" / "state.md"


def body_start(lines: list[str]) -> int:
    separators = [i for i, line in enumerate(lines) if line.strip() == "---"]
    return separators[2] + 1 if len(separators) >= 3 else 0


def split_terms(raw: str) -> list[str]:
    return [part.strip() for part in re.split(r"[、，,；;/]", raw) if part.strip()]


def terms_from_state() -> list[str]:
    """Read the optional 检索词 column under continuity/state.md knowledge rows."""
    if not STATE_PATH.is_file():
        return []
    lines = STATE_PATH.read_text(encoding="utf-8").splitlines()
    in_section = False
    table: list[str] = []
    for line in lines:
        if line.startswith("## "):
            in_section = line.strip() in {
                "## 关键知情范围",
                "## 知识状态（谁知道什么秘密）",
            }
            continue
        if in_section and line.strip().startswith("|"):
            table.append(line)
        elif in_section and table and line.strip():
            break
    if len(table) < 2:
        return []
    headers = [cell.strip() for cell in table[0].strip("|").split("|")]
    if "检索词" not in headers:
        return []
    index = headers.index("检索词")
    terms: list[str] = []
    for line in table[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == len(headers):
            terms.extend(split_terms(cells[index]))
    return terms


def audit(path: Path, terms: list[str]) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = body_start(lines)
    pattern = re.compile("|".join(re.escape(term) for term in terms)) if terms else None
    hits: list[tuple[int, list[str], str]] = []

    if pattern:
        for index, line in enumerate(lines[start:], start=start + 1):
            found = sorted(set(pattern.findall(line)))
            if found:
                hits.append((index, found, line.strip()))

    print(f"## {path}")
    if not terms:
        print("尚未配置敏感检索词；请在 continuity/state.md 的关键知情范围表填写“检索词”，或使用 --term。")
        print("仍须按实际受众检查信件、口信、题字、记录和公开台词。")
        return 0
    if not hits:
        print("未命中已配置敏感词；仍须按实际受众检查未收录的输出。")
        return 0

    for lineno, found, line in hits:
        print(f"{lineno}: [{', '.join(found)}] {line}")
    print("逐项标记：旁白／内心／私谈／公开台词／文本，以及实际听众或读者。")
    return len(hits)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按实际受众检查敏感信息输出")
    parser.add_argument("paths", nargs="+", type=Path, help="待检查的章节 Markdown")
    parser.add_argument("--term", action="append", default=[], help="额外敏感词，可重复")
    args = parser.parse_args(argv)

    missing = [path for path in args.paths if not path.is_file()]
    if missing:
        for path in missing:
            print(f"文件不存在：{path}", file=sys.stderr)
        return 2

    terms = sorted(set(terms_from_state() + args.term), key=lambda item: (-len(item), item))
    for path in args.paths:
        audit(path, terms)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
