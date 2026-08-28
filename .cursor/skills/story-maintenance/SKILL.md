---
name: story-maintenance
description: >-
  Runs deterministic project maintenance via scripts/story.py: word counts,
  progress reports, rebuilding registries, and exporting the manuscript. Use
  when the user asks for word count stats, writing progress, to rebuild
  indexes, or to export/compile the manuscript, e.g. "统计字数", "看看进度",
  "重建索引", "导出成稿".
---

# 项目维护

所有操作都通过 [`scripts/story.py`](../../../scripts/story.py) 完成，不要手写等价逻辑。

| 用户想要 | 运行 |
|---|---|
| 看字数/进度 | `python3 scripts/story.py wordcount --write` |
| 重建各 `_index.md` | `python3 scripts/story.py reindex` |
| 一致性快速检查（死人复活/未登记人物/重复章号/伏笔遗忘/物品状态未同步/地理方位矛盾/正稿与草稿不同步） | `python3 scripts/story.py lint` |
| 确认某章定稿（草稿去头生成正稿，`status` 改为 `已确认`） | `python3 scripts/story.py confirm-chapter <章号>` |
| 导出完整稿件（只拼 `已确认` 章节的正稿） | `python3 scripts/story.py compile --out manuscript.md` |
| 新建下一章草稿骨架（不确定用哪个 skill 时的兜底） | `python3 scripts/story.py new-chapter <卷号> <标题>` |
| 生成定向任务上下文 | `python3 scripts/story.py context --task <plan\|write\|revise\|review> --chapter <章号> [--focus 关键词]` |
| 审计常驻体积、归档边界和默认预算 | `python3 scripts/story.py context-audit` |

章节文件分两个区：`chapters/drafts/<卷>/` 是草稿（带 frontmatter，唯一元数据来源），`chapters/final/<卷>/` 是正稿（纯净正文，只能由 `confirm-chapter` 生成）。永远不要手工在 `final/` 下创建或编辑文件。

## 汇报进度时

统计字数后，对照 [`story.md`](../../../story.md) 的 `update-pace` 字段，告诉用户当前总字数、章节数、距离目标节奏的差距，而不只是甩一堆数字。

## lint 报错时

不要自己删掉报错行了事。逐条判断：是正文写错了（回去改正文/frontmatter），还是登记表/状态机没同步（补登记）。只有确认是误报时才可以忽略，并告知用户原因。
