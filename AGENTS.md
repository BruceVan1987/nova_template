# 项目地图

这是一个尚未初始化故事内容的长篇小说写作工作区。正文不是设定事实源；写作前必须读取结构化文件与定向上下文，不得凭对话记忆补设定，也不得另建一套重复目录。

## 协作原则

- 从原始需求和问题本质出发，不套用题材惯例或旧项目模板内容。
- 动机或目标不清楚且会改变作品方向时，先与作者讨论。
- 工具操作、资料读取和项目维护采用直接路径；正文的场景取舍与阅读体验服从作者要求和唯一质量规范。
- 遇到问题追根因；正文问题改正文，事实问题改事实源，流程问题才改工具。
- 工作汇报只保留会改变判断、写作或下一步行动的信息。

## 唯一事实源

| 内容 | 唯一入口 |
|---|---|
| 题材、人称、时态、基调、边界 | `story.md` |
| 人物事实与当前人物关系 | `characters/`；登记表为 `characters/_index.md` |
| 反复关系戏的阶段声口 | `continuity/relationships.md` |
| 当前人物、物品、秘密边界 | `continuity/state.md` |
| 地理方位与距离 | `worldbuilding/geography.md` |
| 大纲、分卷与日期 | `plot/`、`plot/timeline.md` |
| 活跃伏笔／悬念 | `continuity/promises/`、`continuity/questions/` |
| 已结束历史 | `continuity/archive/`，仅按关键词或显式焦点加载 |
| 专有名词 | `glossary/terms/` 与 `glossary/_index.md` |
| 逐章经过、旁听者与执行账 | `continuity/scene-log.md`（按章号取用，开写不载入） |
| 正文质量规则 | `references/style-guide.md`（唯一规范） |
| 可选声口锚点 | `references/voice-samples.md`（正文仍在已确认章节） |
| 草稿格式 | `references/chapter-template.md` |
| 命名与实体格式 | `references/naming-conventions.md`、`references/entity-templates.md` |

`chapters/drafts/<卷>/` 是章节元数据和正文的唯一编辑源。`chapters/final/<卷>/` 只能由 `python3 scripts/story.py confirm-chapter <章号>` 生成，禁止手工编辑、复制或改 status。

## 工作流路由

1. 新故事：`story-init`。
2. 规划大纲／故事线：`plot-structure`。
3. 写新章：`chapter-writing`，先用 `scripts/story.py context` 生成最小上下文包，再写控制卡与正文。
4. 只读审阅待审核草稿：项目级 `draft-reviewer`。
5. 按意见改稿、修连续性或修已确认章节：`revision-continuity`。
6. 用户明确确认章节：主 agent 按 `story-maintenance` 核验当前版本并确认；subagent 不得确认，纯确认不启动改稿。
7. 统计、索引和导出：`story-maintenance` 或 `scripts/story.py` 对应命令。
8. 剧情分支整体回滚：仅在作者明确授权回滚点后使用 `story-branch-rollback`。

章节正文的生成与改写是项目级串行临界区：任何时刻只能有一个正文执行者处理一章，不得把完整、局部或候选正文交给多个 subagent、任务或线程并行产出。唯一并行例外是 `chapter-writing` 定义的落笔前“关键角色立场推演”，其输出不得是可直接拼接或粘贴的正文。

## 维护原则

- 正文质量规则只写入 `references/style-guide.md`。Skill、常驻规则和 reviewer 只引用，不复制同义条目。
- 一次性偏好不升级为全局规则；跨章复发且作者确认可泛化的问题才进入唯一规范。
- 稳定可机械识别的问题写进脚本；依赖语境的判断留给语义审阅。
- 事实源只存当前状态；逐章经过写入 `continuity/scene-log.md` 或章节元数据，人物档案不积累逐章流水。
- 修改规则后运行 `python3 scripts/rules_audit.py`；修改脚本后运行测试、`lint` 和 `context-audit`。

## 草稿与确认边界

- 作者明确要求写指定章且所属单元方向已锁定时，自行完成控制卡、正文与交稿流程，交付为待审核；明确要求先看控制卡时提交后停止。
- 缺少单元方向、需要改变已锁定方向或新增尚未授权的外部视角时，先交作者决定。只推进已授权章数，完成授权末章后停止。

- 只要用户要求的是评估、审阅或报告，保持只读，不顺手改稿。
- 没有明显问题可以直接通过，不为审阅制造意见。
- 用户未明确确认前，章节保持 `draft` 或 `待审核`，不得生成或改写正稿。
- 写作或改稿交付按 [章节交稿检查流程](references/chapter-review-workflow.md) 分开整体与语言冷读；用 `ready-chapter` 核验当前版记录后置为待审核。只读审阅不写记录，记录就绪也不等于作者确认。

常驻流程约束见 [`.cursor/rules/novel-style.mdc`](.cursor/rules/novel-style.mdc)。
