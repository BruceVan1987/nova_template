---
name: worldbuilding
description: >-
  Builds and updates worldbuilding entries: locations, power/magic/tech
  systems, and factions. Use when the user asks to design a location, power
  system, magic system, or faction, e.g. "设计一个力量体系", "新建地点", "势力设定",
  "这个门派的规则是什么".
---

# 世界观构建

## 选择子目录

- 地点 → `worldbuilding/locations/`
- 力量体系/规则系统（修炼/魔法/科技/社会规则）→ `worldbuilding/systems/`
- 势力/组织 → `worldbuilding/factions/`

## 执行步骤

1. 先查对应子目录的 `_index.md` 和 [`worldbuilding/_index.md`](../../../worldbuilding/_index.md)，确认不与已有设定冲突或重名。
2. 按 [`references/entity-templates.md`](../../../references/entity-templates.md) 对应模板新建文件。
3. 力量体系类设定，务必写清楚"限制与代价"——这是避免后期为了剧情需要不断加能力导致体系崩坏的关键。
4. 新建地点时，若它跟已有地点有相对方位/距离，同步补进 [`worldbuilding/geography.md`](../../../worldbuilding/geography.md) 的关系表（而不是只写在地点文件的自然语言描述里，那样没法被 `lint` 校验）。
5. 运行 `python3 scripts/story.py reindex` 让对应 `_index.md` 生效，再跑 `python3 scripts/story.py lint` 确认没有引入地理方位矛盾。
6. 若新设定引入了专有名词（招式名、机构名等），补进 [`glossary/_index.md`](../../../glossary/_index.md)。
