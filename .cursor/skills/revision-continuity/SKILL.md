---
name: revision-continuity
description: >-
  Revises draft or confirmed chapters, fixes continuity and prose problems,
  updates structured story state, and validates the result. Use for 按意见改稿、
  修复一致性、去AI味重写或用户确认定稿。Opinion-only review of an unconfirmed
  draft goes to the read-only draft-reviewer.
---

# 改稿与连续性修复

本 Skill 只规定执行顺序。所有正文质量判断统一服从 [`references/style-guide.md`](../../../references/style-guide.md)，不得在此复制检查清单。

## 1. 先确定事实边界

```bash
python3 scripts/story.py lint
python3 scripts/story.py context --task revise --chapter <章号> --max-chars 35000
```

- 完整读取目标章和上下文包；包内必须有 `P0 当前状态`、关键知情范围，并且只能载入一次写作质量规范。缺项先修脚本，不另开规范文件补读第二遍。
- 若提示当前快照晚于目标章，只把它用于长期禁区；目标章当时的位置、伤情、物品与知识以该章、时间线和截至该章的归档为准，不能倒灌未来。
- 修改涉及旧伏笔、方位、亲属、具体数量或关系阶段时，用 `--focus`／`--include` 定向补入原始证据；伏笔必须回读首次出现原文。
- 信件、口信、案卷与远程汇报中的写信人和被具体描写者也属于事实依赖人物，档案被省略时先补入。

## 2. 修根因，不扩张改动

先判断反馈属于哪一层：

1. 句子、动作或场面问题：只改正文相关段。
2. 人物能力、亲属、关系或声口事实变化：同步人物档案／关系卡。
3. 位置、物品、秘密、日期、伏笔或悬念：同步连续性文件。
4. 结构性无聊、人物工具化或认知前提错误：重排叙事发动机或压缩章数，不能只换措辞。
5. 跨章复发且作者确认可泛化：才修改唯一质量规范；稳定可识别的问题优先写脚本。

保留作者已经打磨的句子和无关段落。关系增温只纠正已经亲近却写得生硬的部分，不为整齐反向清理一般关系的自然热络；除非出现泄密、越权或明确连续性硬伤。

## 3. 冷读与受众审计

修改后脱离用户意见，至少冷读修改段前后三段，并执行写作质量规范的“五道门”。所有改稿章都运行：

```bash
python3 scripts/audience_audit.py <目标章>
```

每条命中按真实受众分类。脚本没有命中时，仍检查信件、口信、公开对白、题字与案卷；“对方听不懂”不是保密理由。

若修复一处后改变了后文指代、数量、物品位置、人物知情或关系反应，继续改到闭合，不能只保证用户选中的那一行单独成立。

## 4. 同步与验证

- 只编辑 `chapters/drafts/`；已确认章也先改草稿。
- 字数变化后运行 `wordcount --write`；事实变化同步 state、timeline、人物、关系、伏笔／悬念与术语。
- 运行 `python3 scripts/story.py lint`，修清与本次改动相关的问题。
- 用户尚未确认时保持草稿／待审核。用户明确确认后运行 `python3 scripts/story.py confirm-chapter <章号>`；已确认旧章改动后也必须重跑该命令刷新正稿。
- 最后只汇报改了什么、验证结果和仍需用户决定的事项，不整章重贴正文。
