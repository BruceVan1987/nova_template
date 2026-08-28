# 单章文件模板

本模板对应**草稿**文件，路径格式：`chapters/drafts/<卷文件夹>/<四位章号>-<标题>.md`，例如 `chapters/drafts/卷一/0001-初入云都.md`。用 `python3 scripts/story.py new-chapter <卷号> <标题>` 自动生成，不要手写文件名/路径。

草稿是唯一的元数据来源。等这一章被用户确认后，运行 `python3 scripts/story.py confirm-chapter <章号>` 会自动去掉下面的 frontmatter 和"本章控制卡"区块，把干净正文写到 `chapters/final/<卷文件夹>/` 下——那份正稿文件不需要、也不应该手工维护。

```markdown
---
schema-version: 1
chapter: 1
volume: 1
title: ""
pov: ""                  # 本章视角人物
status: draft            # draft（初稿）/ 待审核（写完等确认）/ 已确认（已用 confirm-chapter 生成正稿）
word-count: 0            # 由 scripts/story.py wordcount --write 自动填
characters: []           # 本章出场人物（姓名，需已在 characters/ 登记）
locations: []            # 本章涉及地点
objects: []              # 本章发生状态变化（换手/换地点）的关键物品名，需同步更新 continuity/state.md 的"最后更新章节"
mentions: []             # 本章仅"被提及"（非实际出场）的人物，用于合法区分"已死角色被追忆"与"复活穿帮"
summary: ""              # 一到两句话摘要，供后续章节写作时快速读取上下文，不读全文
state-changes: []        # 本章造成的状态变化，写完后同步回 continuity/state.md，例如："某角色 获得 某物品"
promises-planted: []     # 本章新埋下的伏笔，需同步登记进 continuity/promises/_index.md
promises-paid: []        # 本章回收的伏笔
---

<!-- 章节控制卡（beat outline），确认通过后保留在此处作为记录 -->
## 本章控制卡

- 普通愿望：人物这一章想得到什么日常结果
- 物件与动作：冲突落在哪件看得见、拿得动的东西或行为上
- 阻力／关系卡点：什么具体事物、人物或限制阻止愿望直接实现；关系章里谁的愿望卡住了谁
- 选择与代价：人物当场怎么选，具体损失什么
- 落点：人物以为什么已经解决；生活、声誉或关系实际留下了什么不可逆事实

---

正文正文正文……

<!-- 若正文依赖需要向读者交代的真实资料，章末最多加 3 条简短资料注；格式为“事实简述＋书名卷次／章节”，没有则省略此区块 -->
---

注：
1. ……
```
