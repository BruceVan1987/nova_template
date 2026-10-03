#!/usr/bin/env python3
"""Devin PreToolUse 写入护栏。

文件工具写入前，按 .devin/config.json（及 config.local.json）里的 Write(...) 禁止规则拦截。
此 hook 对文件工具重复执行同一份禁止清单；是否加载由平台和会话设置决定。
只管文件工具；confirm-chapter、reindex 等终端命令不经过这里。脚本自身出错时以非 2
退出码结束，Devin 只记录不拦截，不会误伤正常编辑。
"""

import json
import os
import re
import sys
import unicodedata
from pathlib import Path


def _nfc(text):
    return unicodedata.normalize("NFC", text)


ROOT = Path(__file__).resolve().parents[2]
ROOT_TEXT = _nfc(os.path.realpath(str(ROOT)))
CONFIG_FILES = (ROOT / ".devin" / "config.json", ROOT / ".devin" / "config.local.json")
PATCH_FILE_RE = re.compile(
    r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+?)\s*$", re.MULTILINE
)


def deny_patterns():
    patterns = []
    for path in CONFIG_FILES:
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for entry in data.get("permissions", {}).get("deny", []):
            match = re.fullmatch(r"Write\((.+)\)", entry.strip())
            if match:
                patterns.append(_nfc(match.group(1).strip()))
    return patterns


def glob_to_regex(pattern):
    parts = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            parts.append(".*")
            i += 2
        elif pattern[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(parts))


def is_denied(relative, pattern):
    if not any(ch in pattern for ch in "*?"):
        base = pattern.rstrip("/")
        return relative == base or relative.startswith(base + "/")
    return bool(glob_to_regex(pattern).fullmatch(relative))


def candidate_paths(tool_name, tool_input):
    found = []
    for key, value in tool_input.items():
        if not isinstance(value, str):
            continue
        if key.endswith("path"):
            found.append(value)
        elif tool_name == "apply_patch":
            found.extend(PATCH_FILE_RE.findall(value))
    return found


def relative_to_root(raw):
    path = os.path.expanduser(raw)
    if not os.path.isabs(path):
        path = os.path.join(ROOT_TEXT, path)
    resolved = _nfc(os.path.realpath(path))
    prefix = ROOT_TEXT + os.sep
    if not resolved.startswith(prefix):
        return None
    return resolved[len(prefix):].replace(os.sep, "/")


def main():
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    patterns = deny_patterns()
    for raw in candidate_paths(payload.get("tool_name", ""), tool_input):
        relative = relative_to_root(raw)
        if relative is None:
            continue
        for pattern in patterns:
            if is_denied(relative, pattern):
                reason = (
                    "{} 命中 .devin/config.json 的 Write({}) 禁止规则。"
                    "正稿只能由 confirm-chapter 生成，自动索引用 reindex 或 wordcount --write 重建，"
                    "冷读快照不得改动。".format(relative, pattern)
                )
                print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
                print(reason, file=sys.stderr)
                return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
