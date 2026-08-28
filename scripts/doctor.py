#!/usr/bin/env python3
"""项目统一体检入口：语法、测试、一致性、上下文边界与模板洁净度。"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "novel-project.json"


def project_config_problems():
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"无法读取 novel-project.json: {exc}"]
    problems = []
    if config.get("schema_version") != 1:
        problems.append("schema_version 必须为当前支持的版本 1")
    if not isinstance(config.get("template_version"), str) or not config["template_version"].strip():
        problems.append("template_version 必须是非空字符串")
    if config.get("mode") not in {"template", "project"}:
        problems.append("mode 必须是 template 或 project")
    required_positive = {
        "context.default_max_chars": config.get("context", {}).get("default_max_chars"),
        "limits.core_total_bytes": config.get("limits", {}).get("core_total_bytes"),
    }
    for name, value in required_positive.items():
        if not isinstance(value, int) or value <= 0:
            problems.append(f"{name} 必须是正整数")
    return problems


def run_check(label, command):
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        print(f"[OK] {label}")
        return True
    print(f"[FAIL] {label}")
    output = (result.stdout + result.stderr).strip()
    if output:
        print(output)
    return False


def template_cleanliness_problems():
    problems = []
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"无法读取 novel-project.json: {exc}"]
    if config.get("schema_version") != 1:
        problems.append("novel-project.json 的 schema_version 必须为 1")
    if config.get("mode") != "template":
        problems.append("模板源的 novel-project.json mode 必须为 template")

    story_path = ROOT / "story.md"
    story = story_path.read_text(encoding="utf-8") if story_path.exists() else ""
    title = re.search(r'^title:\s*(?:"([^"]*)"|([^\n#]*))', story, re.MULTILINE)
    title_value = (title.group(1) if title and title.group(1) is not None else title.group(2) if title else "").strip()
    if title_value:
        problems.append("story.md 已有书名，不是干净模板")
    if not re.search(r"^status:\s*setup\s*$", story, re.MULTILINE):
        problems.append("story.md status 必须为 setup")

    content_patterns = (
        "chapters/drafts/**/*.md",
        "chapters/final/**/*.md",
        "characters/*.md",
        "worldbuilding/locations/*.md",
        "worldbuilding/systems/*.md",
        "worldbuilding/factions/*.md",
        "plot/arcs/*.md",
    )
    for pattern in content_patterns:
        for path in ROOT.glob(pattern):
            if path.name not in {"_index.md", "README.md"}:
                problems.append(f"模板中存在内容文件：{path.relative_to(ROOT)}")
    for path in (ROOT / "assets").rglob("*"):
        if path.is_file() and path.name != ".gitkeep":
            problems.append(f"模板中存在内容资源：{path.relative_to(ROOT)}")
    return problems


def main():
    parser = argparse.ArgumentParser(description="运行小说项目的统一体检")
    parser.add_argument("--template", action="store_true", help="额外检查仓库仍是无内容的模板源")
    args = parser.parse_args()

    scripts = sorted((ROOT / "scripts").glob("*.py"))
    checks = [
        ("Python 语法", [sys.executable, "-m", "py_compile", *map(str, scripts)]),
        ("单元测试", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("故事一致性", [sys.executable, "scripts/story.py", "lint"]),
        ("上下文边界", [sys.executable, "scripts/story.py", "context-audit"]),
        ("规则单一事实源", [sys.executable, "scripts/rules_audit.py"]),
    ]
    ok = True
    for label, command in checks:
        ok = run_check(label, command) and ok

    config_problems = project_config_problems()
    if config_problems:
        ok = False
        print("[FAIL] 项目配置")
        for problem in config_problems:
            print(f"- {problem}")
    else:
        print("[OK] 项目配置")

    if args.template:
        problems = template_cleanliness_problems()
        if problems:
            ok = False
            print("[FAIL] 模板洁净度")
            for problem in problems:
                print(f"- {problem}")
        else:
            print("[OK] 模板洁净度")

    if ok:
        print("体检通过。")
        return 0
    print("体检未通过。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
