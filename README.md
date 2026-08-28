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
| `.cursor/skills/` | 项目级写作工作流 |
| `.agents/skills/` | 指向 `.cursor/skills/` 的共享链接 |

## 常用命令

```bash
python3 scripts/story.py new-chapter 1 章节标题
python3 scripts/story.py wordcount --write
python3 scripts/story.py reindex
python3 scripts/story.py lint
python3 scripts/story.py confirm-chapter 1
python3 scripts/story.py compile --out manuscript.md
python3 scripts/story.py context --task plan --chapter 1
python3 scripts/story.py context-audit
python3 scripts/rules_audit.py
python3 -m unittest discover -s tests -v
```

`confirm-chapter` 只在作者明确确认后运行。不要手工编辑 `chapters/final/`。
