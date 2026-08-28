---
name: story-init
description: >-
  Scaffolds a new web-novel project by interviewing the user about genre,
  protagonist, POV, tense, tone, update pace, and boundaries, then fills in
  story.md and creates the first volume outline and protagonist file. Use when
  the user says "开始新故事", "新建小说项目", "初始化故事", or story.md is
  still empty/placeholder and the user wants to start writing.
---

# 新故事初始化

## 何时使用

`story.md` 的 `title` 为空，或用户明确要求开始一个新故事。若 `story.md` 已经填过内容，先确认用户是要重新初始化（会覆盖现有设定）还是新开一卷（应改用 `plot-structure` skill）。

## 访谈问题

用 AskQuestion（若可用）或对话方式依次问清楚：

1. 题材/类型（如：都市异能、玄幻修真、悬疑推理、女频爱情……）
2. 主角是谁、核心冲突/目标是什么（一句话）
3. 人称与时态（默认建议：第三人称限知视角 + 现在时态叙述过去发生的事，即常见网文写法）
4. 基调与文风偏好（爽感为主/写实为主/幽默/沉重……）
5. 更新节奏与单章目标字数（决定 `target-chapter-length` 和 `update-pace`）
6. 禁忌/边界（绝对不能出现的设定或描写）

## 执行步骤

1. 把回答填进 [`story.md`](../../../story.md) 的 frontmatter（`title`/`genre`/`pov`/`tense`/`tone`/`target-chapter-length`/`update-pace`/`status: active`）与正文各节。
2. 按 [`references/entity-templates.md`](../../../references/entity-templates.md) 的人物模板，在 `characters/` 下创建主角文件。
3. 在 [`plot/_index.md`](../../../plot/_index.md) 的分卷表里新增第一卷一行；按 arc 模板在 `plot/arcs/` 下创建第一卷的 arc 文件（目标、关键节点粗纲）。
4. 把 [`novel-project.json`](../../../novel-project.json) 的 `mode` 从 `template` 改为 `project`；若作者给出了全书目标字数，也写入 `writing.target_total_words`，否则保持 `0`。
5. 运行 `python3 scripts/story.py reindex` 和 `python3 scripts/doctor.py`，让人物/arc 注册表生效并验证初始化结果。
6. 告知用户：现在可以说"写下一章"来触发 `chapter-writing`。
