#!/usr/bin/env python3
"""从当前模板仓库安全生成一个独立、无故事内容的小说项目。"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


SKILL_FILE = Path(__file__).resolve()
DEFAULT_SOURCE = SKILL_FILE.parents[3]
EXCLUDED_PREFIXES = (".git/", ".story-cache/", "packaging/")


def run(command, cwd, capture=False):
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=capture,
        check=False,
    )
    if result.returncode != 0:
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        raise RuntimeError(output or f"命令失败：{' '.join(map(str, command))}")
    return result.stdout if capture else ""


def source_files(source):
    output = run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        source,
        capture=True,
    )
    paths = []
    for raw in output.split("\0"):
        if not raw or raw.startswith(EXCLUDED_PREFIXES):
            continue
        path = source / raw
        if path.is_file() or path.is_symlink():
            paths.append(Path(raw))
    return paths


def copy_entry(source, staging, relative):
    source_path = source / relative
    target_path = staging / relative
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.is_symlink():
        os.symlink(os.readlink(source_path), target_path)
    else:
        shutil.copy2(source_path, target_path)


def set_project_mode(project):
    config_path = project / "novel-project.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["mode"] = "project"
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description="从已验证模板创建空白小说项目")
    parser.add_argument("target", help="新项目目录；必须不存在或为空")
    parser.add_argument("--source", help="模板仓库路径；默认使用本 Skill 所在仓库")
    parser.add_argument("--no-git", action="store_true", help="不初始化独立 Git 仓库")
    parser.add_argument("--commit", action="store_true", help="创建首个本地提交（隐含启用 Git）")
    parser.add_argument("--commit-message", default="chore: 初始化空白小说项目骨架")
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve() if args.source else DEFAULT_SOURCE
    target = Path(args.target).expanduser().resolve()
    if not (source / "novel-project.json").is_file() or not (source / "scripts" / "doctor.py").is_file():
        print(f"错误：{source} 不是可识别的小说模板源", file=sys.stderr)
        return 2
    if target == source or source in target.parents:
        print("错误：目标目录不能是模板源或其子目录", file=sys.stderr)
        return 2
    if target.exists() and any(target.iterdir()):
        print(f"错误：目标目录非空：{target}", file=sys.stderr)
        return 2
    if args.no_git and args.commit:
        print("错误：--commit 与 --no-git 不能同时使用", file=sys.stderr)
        return 2

    try:
        run([sys.executable, "scripts/doctor.py", "--template"], source)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f".{target.name}.bootstrap-", dir=target.parent) as temporary:
            staging = Path(temporary)
            files = source_files(source)
            for relative in files:
                copy_entry(source, staging, relative)
            run([sys.executable, "scripts/doctor.py", "--template"], staging)
            set_project_mode(staging)
            run([sys.executable, "scripts/doctor.py"], staging)

            if not args.no_git:
                run(["git", "init", "-b", "main"], staging)
                if args.commit:
                    run(["git", "add", "."], staging)
                    run(["git", "commit", "-m", args.commit_message], staging)

            if target.exists():
                target.rmdir()
            staging.replace(target)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(f"已创建：{target}")
    print(f"复制模板文件：{len(files)}")
    print(f"Git：{'未启用' if args.no_git else '已初始化'}")
    print(f"首个提交：{'已创建' if args.commit else '未创建'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
