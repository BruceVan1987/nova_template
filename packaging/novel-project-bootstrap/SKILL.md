---
name: novel-project-bootstrap
description: >-
  Creates an independent, content-free long-form novel workspace from this
  repository's validated template, with optional Git initialization and first
  commit. Use when the user asks to create a new novel project, reuse this
  skeleton, or start another clean writing workspace without carrying over
  story content.
---

# 新小说项目引导

## 边界

- 本仓库是模板唯一真源；不要在 Skill 内维护第二份项目骨架。
- 目标目录必须不存在或为空。不要覆盖已有项目；已有项目升级按仓库的 `docs/upgrading.md` 合并，不使用本 Skill。
- 只复制模板文件，不复制 `.git/`、`.story-cache/` 或 `packaging/`。
- 初始化只创建空白工作区；作品内容交给目标项目里的 `story-init`。

## 执行

1. 若用户没有给出目标路径，且无法从当前上下文安全推断，先询问路径。
2. 运行：

   ```bash
   python3 <本 Skill 目录>/scripts/bootstrap_project.py <目标路径>
   ```

3. 用户明确要求首个提交时追加 `--commit`；不希望创建 Git 仓库时追加 `--no-git`。
4. 脚本会先验证模板源，在临时目录复制并体检，通过后才落到目标路径。
5. 报告目标绝对路径、是否初始化 Git、是否提交，以及下一步应运行 `story-init`。

若脚本报告模板源不干净，停止复制并修复模板源；不要绕过检查。
