# 网文写作工作区

这是一个干净的 Markdown 长篇小说项目骨架。目前没有书名、题材、人物、世界观、剧情、章节或专属写作设定；下一步应先和作者讨论作品目标，再运行 `story-init` 写入首批事实源。

## 核心结构

| 路径 | 用途 |
|---|---|
| `story.md` | 全书最高优先级合同 |
| `characters/` | 人物档案 |
| `worldbuilding/` | 地点、规则系统、势力与地理关系 |
| `plot/` | 总纲、分卷、角色调度与时间线 |
| `continuity/` | 当前状态、关系声口、伏笔、悬念与历史归档 |
| `glossary/` | 专有名词 |
| `chapters/drafts/` | 带元数据和控制卡的唯一正文编辑源 |
| `chapters/final/` | 由脚本生成的已确认纯正文 |
| `references/` | 唯一写作规范、模板和审阅协议 |
| `scripts/` | 章节、上下文和一致性维护工具 |
| `novel-project.json` | 模板版本、上下文预算、体积阈值与全书目标配置 |
| `.cursor/skills/` | 项目级写作工作流 |
| `.agents/skills/` | 指向 `.cursor/skills/` 的共享链接 |

## 常用命令

```bash
python3 scripts/story.py new-chapter 1 章节标题
python3 scripts/story.py wordcount --write
python3 scripts/story.py catalog
python3 scripts/story.py stats
python3 scripts/story.py reindex
python3 scripts/story.py lint
python3 scripts/story.py confirm-chapter 1
python3 scripts/story.py compile --out manuscript.md
python3 scripts/story.py context --task plan --chapter 1
python3 scripts/story.py context-audit
python3 scripts/rules_audit.py
python3 -m unittest discover -s tests -v
python3 scripts/doctor.py
```

`confirm-chapter` 只在作者明确确认后运行。不要手工编辑 `chapters/final/`。

## 长篇扩展机制

- 章节正文始终是事实源；`.story-cache/` 只保存可删除、可重建的 frontmatter 目录。
- 规划、索引、进度和导出先读元数据，需要正文时才加载对应章节。
- 当前事实留在热状态；已结束的历史进入 `continuity/archive/`，只按显式焦点召回。
- 所有预算和体积阈值集中在 `novel-project.json`，不再散落在脚本中。
- 修改骨架后运行 `python3 scripts/doctor.py --template`；开始写作后运行不带 `--template` 的体检。

完整取舍与外部项目对照见 [`docs/scalability-assessment.md`](docs/scalability-assessment.md)。

## 作为模板复用

推荐把本仓库设为 GitHub Template Repository。由它创建的新仓库继承文件结构，但拥有独立历史，不会携带另一部小说的内容。

本地也可使用仓库内的薄 Skill：

```bash
python3 packaging/novel-project-bootstrap/scripts/bootstrap_project.py /absolute/path/to/new-novel
```

目标目录必须不存在或为空。默认初始化独立 Git 仓库；明确需要首个提交时追加 `--commit`，不需要 Git 时追加 `--no-git`。脚本不会复制 `.git/`、`.story-cache/` 或 Skill 包本身，并会在落盘前后运行体检。

若公开发布模板仓库，请先由维护者选择合适许可证；本骨架不替作者做许可证决定。
