# 长篇小说写作框架

版本 **2.0.0**。这是一个没有故事内容的 Markdown + Git 工作区：人物、世界、剧情和章节由作者在新项目中确定。模板提供事实分层、按任务装配上下文、草稿审阅记录和确认边界；题材与声口由 `story-init` 和 `story.md` 确定。

## 创建新项目

```bash
python3 packaging/novel-project-bootstrap/scripts/bootstrap_project.py /absolute/path/to/new-novel
```

目标目录必须不存在或为空。默认初始化独立 Git 仓库；需要首个提交时加 `--commit`，不需要 Git 时加 `--no-git`。脚本先检查源模板，在临时目录复制、检查，再落盘；不复制 `.git/`、`.story-cache/` 或包装 Skill。创建后运行目标项目的 `story-init`，确认故事合同后才开始建章。

也可以使用 GitHub Template Repository 创建独立仓库。已有小说的升级请按 [升级说明](docs/upgrading.md) 合并，不能用空模板覆盖内容文件。

## 文件分工

| 路径 | 用途 |
|---|---|
| `story.md` | 题材、视角、基调和作品边界 |
| `characters/`、`worldbuilding/`、`glossary/` | 人物、世界与名词的结构化事实 |
| `plot/`、`plot/timeline.md` | 大纲、单元方向、时间与消息排程 |
| `continuity/state.md` | 当前人物、物品和知情状态 |
| `continuity/relationships.md` | 按章节区间保存关系阶段与表达方式 |
| `continuity/scene-log.md` | 逐章经过、旁听者与执行账；开写不加载 |
| `continuity/promises/`、`questions/`、`archive/` | 活跃线索与定向读取的历史 |
| `chapters/drafts/` | 元数据、控制卡和正文的唯一编辑源 |
| `chapters/final/` | 作者确认后由脚本生成的纯正文 |
| `references/style-guide.md` | 正文质量的唯一规范，按作品要求调整 |
| `references/voice-samples.md` | 可选的已确认正文锚点；不复制另一份正文 |
| `novel-project.json` | 版本、字符预算、体积阈值与可选检查配置 |
| `.cursor/skills/`、`.cursor/agents/` | 共用工作流与角色说明 |

正文保存实际场面，写作时的设定与当前状态从结构化事实源取得；不能用旧聊天记忆补设定。流程检查与审阅记录不能证明小说质量，正文证据仍按唯一规范判断。

## 写章与交稿

作者明确要求写指定章且单元方向已锁定时，执行者自行完成控制卡与交稿流程；只要求先看卡时，在卡交付后停止。只推进已授权的章数。

```bash
python3 scripts/story.py new-chapter 1 章节标题
python3 scripts/story.py context --task plan --chapter 1 --out .story-cache/context/plan-1.md
# 填好本章控制卡、时间范围和逐幕安排后：
python3 scripts/story.py plan-check 1
python3 scripts/story.py context --task write --chapter 1 --out .story-cache/context/write-1.md
```

`new-chapter` 的第一个参数是卷号，章号自动生成。按 [完整读取协议](references/context-reading.md) 分段读完文件；生成回执不等于已读取。必须材料超预算时明确失败，不能略过后凭记忆写。正文由一个执行者串行处理；可选 `chapter-drafter` 接收保存的 write 包和目标章路径。

正文写完后按 [交稿流程](references/chapter-review-workflow.md) 分开整体首读、事实核对与语言冷读：

```bash
python3 scripts/story.py review-text 1
python3 scripts/story.py review-start 1 --stage overall
# 独立整体首读并按协议填写本轮 notes 和 findings
python3 scripts/story.py review-finish 1 --stage overall
python3 scripts/story.py context --task review --chapter 1 --out .story-cache/context/review-1.md
# 主执行者核对事实；若改正文，重开受影响的审阅轮
python3 scripts/story.py review-start 1 --stage language
# 独立语言冷读并按协议处置意见
python3 scripts/story.py review-finish 1 --stage language
python3 scripts/story.py review-check 1
python3 scripts/story.py ready-chapter 1
```

独立首读者只接收当前轮的精确正文快照与规范；控制卡、摘要、角色推演和预期结论不能进入隔离输入。记录与正文、标题及质量规范指纹绑定，修改后旧记录不能直接放行。`ready-chapter` 只置为待审核；作者明确确认后再运行：

```bash
python3 scripts/story.py confirm-chapter 1
```

不手工编辑正稿。纯确认不启动改稿；发现当前版问题时，报告后按新的修改授权处理。

## 可配置的检查

默认字符预算为 35000；在 `novel-project.json` 调整。`lint.name_shorthand` 默认空表，可按项目登记控制卡和事实材料中的单字简称；不扫描正文。

`lint.light_register.enabled` 和 `lint.bare_dialogue.enabled` 默认关闭。作者选择相应声口后可启用轻度书面词或纯对白段提醒；前者支持自定 `pattern`、提醒密度与交付阈值，语言轮可引用原句记录有理由的保留。详细用法见 [质量规范](references/style-guide.md#可配置的声口检查)。模板不固定各书的文体或冲突强度。

## 维护与验证

```bash
python3 scripts/story.py wordcount --write
python3 scripts/story.py reindex
python3 scripts/story.py stats
python3 scripts/story.py compile --out manuscript.md
python3 scripts/doctor.py --template
```

进入小说项目后运行不带 `--template` 的体检。doctor 包含语法、测试、lint、context-audit、rules-audit 和配置检查；模板模式另查是否混入故事内容。CI 配置 Python 3.9、3.11、3.13。

`.story-cache/` 不入库。元数据目录和任务包可以重建；`reviews/` 中的记录与快照应随工作区保留或备份，缺失时按协议重新审阅，不能补造完成标志。

平台入口见 [Cursor / Codex / Devin 适配说明](docs/platform-adapters.md)，版本变化见 [CHANGELOG](CHANGELOG.md)，既有项目合并见 [升级说明](docs/upgrading.md)。[扩展性评估](docs/scalability-assessment.md) 保留历史性能基线。

当前未添加许可证。
