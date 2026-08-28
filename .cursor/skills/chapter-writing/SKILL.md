---
name: chapter-writing
description: >-
  Drafts the next chapter (or a specific chapter) through an outline-first
  workflow that loads bounded story context, writes prose, updates continuity,
  and validates the result. Use for “写下一章”“继续写”“写第N章”或连续写数章。
---

# 章节写作

本 Skill 只规定执行顺序。正文质量统一服从 [`references/style-guide.md`](../../../references/style-guide.md)，不得在此另建一套文风清单。

## 1. 取得最小上下文

```bash
python3 scripts/story.py context --task plan --chapter <章号> --max-chars 35000
python3 scripts/story.py context --task write --chapter <章号> --max-chars 35000
```

- 先完整读取 `plan` 包。确定人物与线索后，再生成并完整读取 `write` 包；其中只载入唯一质量规范的“开写视图”，用来确定声口、关系和场景发动，不提前载入冷读禁线。
- 新章包必须包含 `continuity/state.md` 的当前状态、关键知情范围、上章结尾原文、直接承接人物热档和当前 arc。缺项先修上下文脚本，不用记忆补。
- 信件、口信、案卷和远程生活汇报中的写信人、被具体描写者也算事实依赖人物；若被预算省略，用一个或多个 `--focus <人物>` 重新生成。
- 两名复现人物会有三轮以上对白、私信或关系动作时，包内必须有目标章适用的 `P0 关系声口卡`。长期关系缺卡时先补 `continuity/relationships.md`；一次性关系不强建。
- 承接伏笔或悬念时，按台账章号定向回读首次出现原文及必要前后段，列内部清单：`线索 → 原始章节 → 本章仅提及／推进／回收`。找不到原文，不把推测写成事实。
- 近期正文已经声口漂移，或多人关系戏容易写成公事对白时，可从作者已经认可的正文中选一章真正接近目标滋味的已确认章节，用 `--voice-chapter <章号>` 重新生成 `plan`／`write` 包。一次只选一章，样章只约束 HOW，不提供目标章事实。
- 只在明确缺口时用 `--focus` 或 `--include`；禁止通读全书。跨元日时按人物年龄锚点统一更新存活人物，旧章年龄仍按旧时点计算。

## 2. 锁定章节控制卡

- 先从当前 arc 读取所属单元卡。缺少单元方向时先回到 `plot-structure`，不靠单章控制卡临时拼出路线；当前单元已锁定 WHAT 时，只讨论场景、视角和节奏等 HOW。
- 控制卡使用 [`references/chapter-template.md`](../../../references/chapter-template.md)，只写正向场景材料。不要列“本章不写什么”“谁不知道什么”“不能怎样解决”等验收边界；这些内容只在写后冷读时核对。
- 发动部件缺失时停止开写，回到章纲并章、压缩或更换入口。控制卡的答案只用于组织动作，正文不得逐项证明计划已经被遵守。
- 只有程序、说明、赶路或既知结果复核而无不可逆变化的内容，优先并入相邻章，不靠新增误会或人物撑篇幅。
- 检查最近两章主要发动机；连续两章已经同构时，第三章必须换入口、主场动作和焦点欲望。切换外部 POV 或更换全书默认发动机时，控制卡须记录作者对本章的明确授权。
- 除非用户明确授权连续写多章，控制卡确认后才写正文。连续写时每章仍保留独立控制卡和完整校验。

## 3. 创建并写作

```bash
python3 scripts/story.py new-chapter <卷号> <标题>
```

1. 填入控制卡，在 `chapters/drafts/` 写正文；不手工编号，不碰 `chapters/final/`。
2. 每个重要场景落笔前只列焦点人物、当下愿望、手边物件和接下来会发生的动作；让既有事实静默决定角色能说什么，不写成边界说明。
3. 私密频道与公开场景切换时，用现场动作自然标出声音是否外放；不在开写阶段逐项做受众验收。
4. 角色调度表是候选入口，不是待办清单。每章最多引入一名需要长期记忆的具名角色；新长期人物先用 `character-management` 建最小档案，再 `--focus` 后写。
5. 关系、秘密、保护或高风险位置优先给新同伴时，核对长期亲属、师徒和稳定助手是否会注意；差别合理也要有正文条件或反应。
6. 正文依赖真实资料且读者确需知道时，章末最多放三条简短资料注；原创设定不加资料注。

## 4. 交稿前检查

正文完成后，先生成并完整读取冷读包：

```bash
python3 scripts/story.py context --task review --chapter <章号> --max-chars 35000
```

此时才加载完整质量规范、当前知情范围与禁线。暂时不看控制卡、摘要和台账，把正文从头到尾连续读一遍，做一次去 AI 味冷读：若人物姓名遮掉后对白可互换，或整章能还原成会议纪要／任务清单，先重排承载场景，不以补动作和换同义词交差。随后完整执行写作质量规范的“五道门”，并运行：

```bash
python3 scripts/audience_audit.py chapters/drafts/<卷>/<章节>.md
```

逐项把命中行标为旁白、内心、私密频道、公开台词或可经手文本，写明实际受众。零命中不等于自动通过，仍要检查未收录关键词的信件和公开输出。

若发现正文确有信息缺口，补能改变人物理解或行动的事实；若只是规范要求已经满足，不追加“没有／不是／不代表”的验收总结。修改承载方式或场景因果，不在 Skill 中寻找另一套同义规则。

## 5. 回写事实

- 填好 frontmatter 的人物、地点、物品、提及、摘要、状态变化和伏笔字段。
- 人物／物品／秘密变化同步 `continuity/state.md`；伏笔与悬念同步各自 `_index.md`；术语同步 `glossary`；方位同步 `worldbuilding/geography.md`。
- 新人物首次有效行动，或旧人物的行动、关系、权限、认知变化时，更新人物档案与 `plot/character-pipeline.md`。单纯在场不算推进。
- 关系阶段、公开／私下语域、亲密许可或稳定冲突方式改变时，在 `continuity/relationships.md` 关闭旧区间、新增阶段；纯措辞增温不改事实卡。

## 6. 校验与交付

```bash
python3 scripts/story.py wordcount --write
python3 scripts/story.py lint
```

修清错误后把草稿 status 置为 `待审核`。只有用户明确确认，才运行 `python3 scripts/story.py confirm-chapter <章号>`。

连续写多章时，每章完整重复上述流程，并维护本轮内部跨章表：日期、人物位置、物品、知识与权限。不能等整批写完再一次性补状态。
