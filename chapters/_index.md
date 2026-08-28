---
schema-version: 1
---

# 章节登记表

由 `scripts/story.py reindex` / `wordcount --write` 自动重建。草稿在 `drafts/<卷>/`；`已确认` 状态的章节会在 `final/<卷>/` 下有对应正稿，正稿只能用 `scripts/story.py confirm-chapter <章号>` 生成，不要手工复制/编辑。

| 章号 | 卷 | 标题 | 字数 | 状态 | 摘要 | 草稿文件 |
|---|---|---|---|---|---|---|
| _(暂无)_ | | | | | | |

状态取值：`draft`（初稿，正在写/改）/ `待审核`（写完等待确认）/ `已确认`（已用 `confirm-chapter` 生成正稿）。
