---
name: plot-structure
description: >-
  Plans and updates the overall outline, volume (arc) breakdowns, and
  timeline. Use when the user asks to plan an outline, design a volume/arc,
  organize subplots, or check the timeline, e.g. "大纲", "分卷规划", "设计一条故事线",
  "梳理时间线".
---

# 大纲与故事线规划

## 层级

- [`plot/_index.md`](../../../plot/_index.md)：全书主线一句话 + 分卷表（手动维护，不是自动重建的注册表）。
- `plot/arcs/<名称>.md`：每条 arc（一卷或一条贯穿全书的主线/支线）的详细拆解，按 [`references/entity-templates.md`](../../../references/entity-templates.md) 的 arc 模板创建。
- [`plot/timeline.md`](../../../plot/timeline.md)：故事内时间线，用于核对"过了多久、谁在哪"。

## 执行步骤

1. 规划新的一卷/一条故事线前，先读 [`plot/arcs/_index.md`](../../../plot/arcs/_index.md)，并运行 `python3 scripts/story.py context --task plan --chapter <下一章> --max-chars 35000`。不得只凭对话摘要或 arc 列表规划。
2. 先确定本 arc 真正要改变的局面，再按 [`references/style-guide.md`](../../../references/style-guide.md) 的“叙事发动机与节奏”完成当前单元卡，不倒推章数。随后根据计划包选定核心人物；凡准备给具名人物安排选择、笑话、冲突或关系变化，必须先确认该人物热档已在包中，需要追溯旧关系时再用 `--focus`。
3. 涉及人质、诈谋、秘密资源或多方博弈时，关键机制锁定前先列对抗核验：各方实际知道什么、持有什么、想要什么、最怕什么、可以如何拒绝或反制。任一方必须忘记已知信息、凭空知道秘密或放弃明显更优解时，方案不成立。
4. 创建/更新 arc 文件：写入已经锁定的单元卡与粗粒度因果节点。还在讨论的试探性手段不得提前写入 `continuity/state.md` 或当作已发生事实。
5. 按 [`references/chapter-template.md`](../../../references/chapter-template.md) 拆章；缺项时依唯一质量规范并章、压成消息或更换入口。卷纲只记录将真正出现在场上的正向材料，不列逐章禁用项或验收边界。切换外部 POV 或更换全书默认发动机时，记录作者对该章的明确授权。声口或场面滋味已经漂移时，可用 `context --voice-chapter <已确认章号>` 定向载入一个样章，只参照 HOW。
6. 更新 [`plot/_index.md`](../../../plot/_index.md) 和对应 arc；涉及具体时点时同步 [`plot/timeline.md`](../../../plot/timeline.md)，最后运行 `python3 scripts/story.py reindex`。
