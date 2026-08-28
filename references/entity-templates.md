# 条目文件模板

各类条目（人物/地点/体系/势力/故事线）的新建文件模板集中放在这里，而不是放在各 `_index.md` 里，因为 `_index.md` 的表格部分会被 `scripts/story.py reindex` / `wordcount --write` 整体覆盖重建。

## 人物 — `characters/<姓名>.md`

```markdown
---
schema-version: 1
name: ""
aliases: []
age:                 # 当前叙事时点年龄；计算口径先在故事合同中确认
age-at-first-appearance:  # 首次出场时年龄，历史锚点，不随剧情推进修改
age-as-of: ""        # 当前 age 对应时点，如“故事纪年二年八月（0108）”
role: ""              # 主角/配角/反派/路人
reference-terms: []   # 正文可唯一指向此人的职务、亲属称呼或固定称谓
context-scope: standard # standard=章节任务可按相关性加载；direction-only=只供方向规划显式读取；缺省按 standard
first-appearance: ""  # 章节号，如 0001
status: alive         # alive/dead/unknown
death-chapter:         # 若 status: dead，填死亡发生的章号（整数），供 lint 检查"死人复活"
---

## 外貌

## 性格

## 目标与动机

## 人物关系

<!-- 这里只写当前关系事实与人物单向理解，不逐章追加经历。对反复承载关系戏的人物对，还须在 continuity/relationships.md 登记双向声口阶段：A→B、B→A、公开/私下语域、亲近落点、冲突与禁止捷径、共享锚点及适用章节。已确认且结束的人物阶段史移入 continuity/archive/characters/<姓名>.md；关系声口旧行保留章节区间，供旧章修订。 -->

## 剧情职能与出场触发

## 当前可推进矛盾

## 成长弧光（本卷/全书）
```

## 地点 — `worldbuilding/locations/<名称>.md`

```markdown
---
schema-version: 1
name: ""
region: ""
---

## 概况

## 与主线的关系

## 环境细节（供正文描写引用，保持前后一致）
```

新建地点后，如果它跟其他已有地点有相对方位/距离关系，必须补进 [`worldbuilding/geography.md`](../worldbuilding/geography.md) 的关系表——不要只在这个文件的“概况”里用自然语言描述方位，那样无法被 `scripts/story.py lint` 校验。

## 力量体系 / 规则系统 — `worldbuilding/systems/<名称>.md`

```markdown
---
schema-version: 1
name: ""
---

## 分级/规则

## 限制与代价

## 与主角能力线的关系（避免中途破坏平衡）
```

## 势力 / 组织 — `worldbuilding/factions/<名称>.md`

```markdown
---
schema-version: 1
name: ""
stance: ""
---

## 核心人物

## 目标

## 与其他势力的关系
```

## 故事线（Arc） — `plot/arcs/<名称>.md`

```markdown
---
schema-version: 1
name: ""
type: ""          # 主线/支线
status: ""        # 未开始/进行中/已完结
chapter-range: ""  # 如 0001-0030
---

## 目标（本 arc 要解决什么）

## 当前单元（三句话；约三至五章但不倒推章数，可按需重复）

- 结束时，生活／名声／关系变成什么：
- 这条链从哪件物品、传闻或关系长出来：
- 外部危机最早在哪个场面敲门，会撞到什么既有事实：

## 关键节点（beat by beat，粗粒度即可，细节留给写章节时展开）

1.
2.
3.

## 与其他 arc 的交叉点
```

## 章节 — `chapters/<四位章号>-<标题>.md`

用 `python3 scripts/story.py new-chapter <卷号> <标题>` 自动生成，无需手写。模板见 [`chapter-template.md`](chapter-template.md)。
