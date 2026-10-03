---
name: character-management
description: >-
  Creates and updates character profile files with relationships, traits,
  goals, and status (alive/dead/location). Use when the user asks to create a
  character, define a character's background/relationships, or mark a
  character as dead/changed status, e.g. "创建人物", "新增角色", "更新XX的人物设定",
  "这个角色死了".
---

# 人物管理

## 创建新人物

1. 先查 [`characters/_index.md`](../../../characters/_index.md) 确认该姓名尚未存在。
2. 若角色属于特定时代、文化、族群或语言体系，先查 [`references/naming-conventions.md`](../../../references/naming-conventions.md) 的命名规则；规则尚未建立时，先与作者确认并记录，不要临场随机换风格。
3. 按 [`references/entity-templates.md`](../../../references/entity-templates.md) 的人物模板在 `characters/` 下新建 `<姓名>.md`，尽量把用户给出的信息落到对应字段（外貌/性格/目标与动机/人物关系/剧情职能与出场触发/当前可推进矛盾/成长弧光）。尚未正式出场时，`first-appearance` 留空，不得用计划章号冒充已经发生的事实。缺省使用 `context-scope: standard`；只有作者明确把人物列为中长期方向名额、暂不准进入近期章节时，才使用 `direction-only`。
4. 若角色会跨章复现，把他加入或更新 [`plot/character-pipeline.md`](../../../plot/character-pipeline.md)：登记调度状态、进入触发、与现有人物的功能差异和下一次最小推进。一次性路人不进调度表。
5. 运行 `python3 scripts/story.py reindex` 让 [`characters/_index.md`](../../../characters/_index.md) 生效。

## 更新已有人物

直接编辑对应文件。若涉及**状态变化**（死亡、失踪、叛变等）：

- 更新该文件 frontmatter 的 `status`；若死亡，务必填 `death-chapter`（整数章号），否则 `scripts/story.py lint` 无法检测"死人复活"。
- 同步回写 [`continuity/state.md`](../../../continuity/state.md) 的人物状态表。

年龄字段只在这里解释一次：`age` 是当前叙事时点年龄，`age-at-first-appearance` 是首次出场的历史锚点，`age-as-of` 是当前年龄对应日期。年龄计算口径必须先在故事合同中确认；时间线跨过年龄变化节点时统一更新相关人物的 `age` 与 `age-as-of`。修订旧章时按旧章日期和首次出场锚点计算，禁止把当前年龄全局替换进旧正文。

人物的行动、关系、权限或认知发生有效变化时，同时更新 [`plot/character-pipeline.md`](../../../plot/character-pipeline.md) 的最近推进与下一次最小推进；单纯在场或被提及不算变化。

`characters/` 根目录保存稳定人物事实，但上下文温度由 `context-scope` 决定：

- `standard` 是章节任务可按相关性加载的普通档案；缺少字段时也按 `standard` 处理。
- `direction-only` 是方向冷档，只能由主 Codex 在计划模式做中长期方向规划时通过 `python3 scripts/story.py context --task direction --focus <人物>` 显式读取。普通 plan/write/revise/review、章节写作与改稿 Skill 均不展开；本 Skill 只负责建立、维护和转档，不主动把方向候选推荐进正文。
- 只有作者确认该人物进入未来三章后，才把 `direction-only` 转为 `standard`，随后才能进入章节控制卡。不得因为档案已经存在反向制造出场入口。
- 已经正式出场、只是暂时离开镜头的人不降为 `direction-only`；继续保持 `standard`，由本章相关性和预算决定是否加载。
- 方向冷档与 [`continuity/archive/characters/`](../../../continuity/archive/characters/) 的人物旧史不是一类东西：前者是尚未启用的未来方向，后者是已确认且结束的历史阶段。

普通 `standard` 档案只保存稳定设定、当前关系快照、仍未结束的认知/权限变化和下一步可推进矛盾：

- 不得在“人物关系”下按“第N章……”逐章追加流水；逐章事件已经由章节 frontmatter 与 [`plot/timeline.md`](../../../plot/timeline.md) 保存。
- 同一关系跨过多个情节点后，将旧条目合并成一句当前状态，例如“已从受命照料转为家中成员；仍不知道对方的真实身份”，而不是保留每一顿饭、每一次同行。
- 只有全部对应章节已经确认、阶段也已经结束时，才把历史证据按章号范围摘要到 [`continuity/archive/characters/`](../../../continuity/archive/characters/)；待审核章节与当前卷变化继续留在热档案。
- 需要修订旧章或复盘人物时，用 `scripts/story.py context --task revise --chapter <章号> --focus <人物>` 按需加载历史冷档案，不为了方便检索把旧史重新抄回普通档案。

## 人物关系一致性

创建/修改人物关系时，检查关联人物的文件是否也需要同步更新对方视角的关系描述（关系通常是双向但不必对称的）。人物档案保存各自当前认知与态度；会跨章反复对话的人物对，另在 [`continuity/relationships.md`](../../../continuity/relationships.md) 保存可执行的阶段声口：

- 不使用单一“好感度”数值。至少写明关系类型与阶段、A→B/B→A、私下与公开声口、亲近落点、冲突禁区和共享锚点。
- 关系升级时封闭旧行的章号范围，再新增下一阶段；不得用最新亲密程度覆盖旧章。
- 一次自然热络、礼貌亲近或单方面误判不等于关系升级。只有称呼权限、信任边界、共享秘密、责任或相处方式发生可复用变化时才更新关系卡。
- 修改完成后运行 `python3 scripts/story.py lint`，同一人物对的阶段范围不得重叠。

逐章实际经过、旁听者与钱物执行账写入 `continuity/scene-log.md` 对应章号段；人物档案、当前状态、地理和活跃悬念只存当前有效事实。规划中的候选路径不登记成已发生事实。
