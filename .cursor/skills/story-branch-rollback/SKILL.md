---
name: story-branch-rollback
description: >-
  Safely rolls a web-novel project back to a chosen confirmed chapter, preserves
  the abandoned branch in Git, extracts reusable scene assets, and rebuilds all
  continuity sources before a replacement branch is written. Use for 剧情回滚、
  从某章重写、废案提取或分支重构. Do not use for ordinary single-chapter revision.
---

# 剧情分支回滚

这是破坏性较高的项目操作。执行前必须有用户对目标章号的明确授权，并把现有分支保存到 Git 引用。

## 不可破坏的边界

- `story.md`、各 `_index.md`、`continuity/`、人物档案与卷纲是正文之外的事实源；回滚不能只删章节。
- `chapters/final/` 仍然是派生物。新章只在 `drafts/` 写，用户确认后再用 `confirm-chapter` 生成正稿。
- 不建立平行的草稿/正稿目录保存废章；完整旧文由 Git 快照保存，工作树只保留可检索的素材卡。
- 不使用 `git reset --hard` 或 `git checkout -- .`。只删除经章号解析确认的目标文件，其他文件逐项语义重建。
- 若工作树在快照前已有用户改动，停止自动删除，先保全并报告重叠。

## 工作流

1. 记录 `git status --short`，确认回滚点草稿存在且是已确认章。
2. 以不会覆盖的名称建立备份分支，例如 `codex/archive/pre-rewrite-YYYYMMDD`，记录完整 commit id。
3. 运行 `scripts/rollback_chapters.py <目标章> --snapshot-ref <备份分支>` 预览将移除的草稿、正稿和晚出场人物；核对后加 `--apply`。
4. 删除前根据章节 frontmatter 、摘要与关键原文建立素材库。每张卡只保留：
   - 原章号/标题与 Git 快照；
   - 可复用的冲突或场面，而非原连续性；
   - 再启用前提；
   - 必须重写的地点、人物知情、资源与因果；
   - 禁止原样复用的问题。
5. 语义回滚事实源：
   - 删除首次出场晚于目标章的人物和地点档案；
   - 所有留存人物的当前位置、目标、关系阶段与知情范围回到目标章结束；
   - `continuity/state.md` 从目标章末重写，不从最新快照修补；
   - 把目标章之后才回收/解答的伏笔与悬念恢复为活跃，删除目标章之后才埋下的项；
   - 时间线、卷纲、角色调度表、地理、术语只保留已发生内容。
6. 运行 `reindex`、`lint`和 `context-audit`。上下文包中不得出现废弃分支的当前状态。
7. 重写分支首章时转入 `chapter-writing` 流程；它必须保持待审核，不与回滚操作一起自动确认。

## 完成证据

- `chapters/drafts/` 与 `chapters/final/` 不存在目标章之后的旧分支文件，新分支首章除外。
- 备份 Git 引用可读到旧章；素材库每项有重启用条件。
- `state.md` 的 `last-updated-chapter`、人物位置、物品最后更新章及活跃台账与新的最后一章一致。
- `python3 scripts/story.py lint` 无误，`context --task plan --chapter <下一章>` 不泄漏废案事实。

回滚时脚本按章号移除 `continuity/scene-log.md` 中晚于回滚点的段；跨越回滚点的段需要逐项语义重建，不把被废弃分支的经过留在当前上下文中。
