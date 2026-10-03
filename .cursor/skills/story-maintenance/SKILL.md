---
name: story-maintenance
description: >-
  统计字数与进度、重建索引、导出稿件，或按作者明确授权确认章节。
---

# 项目维护

所有操作都通过 [`scripts/story.py`](../../../scripts/story.py) 完成，不要手写等价逻辑。

| 用户想要 | 运行 |
|---|---|
| 看进度（已有登记值） | `python3 scripts/story.py stats` |
| 统计当前正文字数（不写回） | `python3 scripts/story.py wordcount` |
| 明确要求刷新并写回字数 | `python3 scripts/story.py wordcount --write` |
| 重建各 `_index.md` | `python3 scripts/story.py reindex` |
| 一致性快速检查（死人复活/未登记人物/重复章号/伏笔遗忘/物品状态未同步/地理方位矛盾/正稿与草稿不同步/单字简称/事实源日志化/声口样本失效；draft 控制卡缺场面简报只提醒，交付时由 `ready-chapter` 拦截） | `python3 scripts/story.py lint` |
| 确认某章定稿 | 按下文“确认章节”核验当前版本并确认 |
| 导出完整稿件（只拼 `已确认` 章节的正稿） | `python3 scripts/story.py compile --out manuscript.md` |
| 拟单章控制卡或写新章 | 使用 `chapter-writing` |
| 生成定向任务上下文 | `python3 scripts/story.py context --task <plan\|write\|revise\|review> --chapter <章号> [--focus 关键词] --out .story-cache/context/<任务>-<章号>.md` |
| 审计常驻体积、归档边界和默认预算 | `python3 scripts/story.py context-audit` |

章节文件分两个区：`chapters/drafts/<卷>/` 是草稿（带 frontmatter，唯一元数据来源），`chapters/final/<卷>/` 是正稿（纯净正文，只能由 `confirm-chapter` 生成）。永远不要手工在 `final/` 下创建或编辑文件。

## 确认章节

仅主 agent 执行，并须有作者对目标章的明确确认。用 `python3 scripts/story.py review-check <章号>` 判断当前版记录是否就绪；本轮已经核验且相关内容未变时不重复检查。

- 记录就绪：运行 `python3 scripts/story.py confirm-chapter <章号>`；该命令也核验当前版记录。
- 记录缺失或过期：按 [章节交稿检查流程](../../../references/chapter-review-workflow.md) 先完成独立纯正文首读；随后主执行者运行 `python3 scripts/story.py context --task review --chapter <章号> --out .story-cache/context/review-<章号>.md`，使用项目默认字符预算，按[上下文完整读取协议](../../../references/context-reading.md)读完文件，补完事实核对，再按交稿流程完成独立语言轮与受众审计，无问题后按已有授权确认。
- 发现正文、标题问题或已有未处置问题：报告问题后停止；纯确认不授权改稿、改题、回写故事事实或处理其他章节。记录损坏或证据异常时保留原记录并报告，不覆盖成新记录。

## 汇报进度时

区分 `stats` 的登记值与 `wordcount` 的实时统计；查看进度或统计字数不自动写回。对照 [`story.md`](../../../story.md) 中已设定的目标节奏说明差距，没有目标时只汇报实际进度。

## lint 报错时

先判断是正文问题、事实源不同步还是误报。只读核查只报告；作者已授权修复时才修改相关内容，正文改稿进入 `revision-continuity`。不能删掉报错行了事，认定误报须说明依据。
