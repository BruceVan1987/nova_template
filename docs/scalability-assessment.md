# 长篇扩展性评估

初次评估日期：2026-08-29。本文性能数字与外部对照保留为当时的历史基线，不代表 2.0.0 的重新测量。目标不是复制一套写作软件，而是判断这个 Markdown + Git 骨架在数百至上千章后，哪些机制会先失效。

## 结论

当前骨架的核心方向是对的：正文与设定是人类可读文件，草稿是唯一编辑源，正稿可重建，事实、状态、历史和写作规范分开，AI 上下文按任务与预算装配。它比“所有内容放一份大文档”更适合长期写作和版本控制。

原先真正的扩展瓶颈有四个：脚本反复读取全部正文、预算散落在代码里、人物/状态热区会随章节增长、项目只有一次性骨架而没有版本与统一体检。本轮已处理前三项的机制问题，并为第四项建立模板版本和验证入口。

本机用 1000 个约 3000 字的合成章节复测：首次重建元数据目录约 0.11 秒，再次复用约 0.07 秒，生成下一章计划上下文约 0.07 秒，全量 lint 约 0.11 秒。数字只代表当前机器和简单文本，但足以说明：磁盘扫描暂时不是主要痛点；真正要守住的是上下文相关性、热状态体积和可升级性。缓存的价值是让元数据任务不再随正文体积线性读取全部内容，而不是追求眼下几十毫秒的优化。

## 对照项目带来的判断

| 参考项目 | 值得借的机制 | 本项目的取舍 |
|---|---|---|
| [novelWriter](https://github.com/vkbo/novelWriter) | 小文档、元数据、交叉引用、项目搜索；近期版本也持续优化后台分块与缓存 | 保留纯文本事实源；新增章节元数据缓存。暂不引入 GUI 和专用文件格式 |
| [novelWriter manuscript build](https://github.com/vkbo/novelWriter/blob/main/docs/source/user_interface/manuscript.rst) | 从项目结构选择内容，并通过构建流程导出多种格式 | 继续让 `final/` 成为可重建产物；当前只导出 Markdown，多格式等真实发布需求出现后再加 |
| [Manuskript](https://github.com/olivierkes/manuskript) | 人物、世界、情节、场景卡和故事线分层 | 现有 `characters/`、`worldbuilding/`、`plot/arcs/` 已覆盖事实分层；不为“功能齐全”强加场景数据库 |
| [bibisco](https://github.com/andreafeccomandi/bibisco) | 章节/场景、修订、叙事线和时空社会设定 | 以 Git 承担修订历史，以 timeline/arc 承担叙事线；避免双重版本事实源 |
| [Obsidian Longform](https://github.com/kevboh/longform) | 明确的项目顺序、草稿分支、延迟字数统计、可组合编译步骤 | 章号 frontmatter 是当前顺序真源；新增元数据 `stats`。分支草稿继续交给 Git，编译管线以后按需求扩展 |

## 本轮落地

1. `novel-project.json` 集中维护上下文预算、热档上限、目标字数和模板版本，避免改一个阈值要找多处代码。
2. `.story-cache/chapter-catalog-v1.json` 只缓存章节 frontmatter。规划、索引、导出和进度统计先看元数据，真正需要正文时再加载单章。缓存被忽略且可随时删除重建。
3. `context-audit` 继续约束“热事实”体积；历史放冷档、显式焦点才召回。长篇后期的主要风险是上下文相关性，不是磁盘 I/O。
4. `scripts/doctor.py` 统一运行语法、测试、lint、上下文审计和规则单一事实源检查；`--template` 额外证明模板没有故事内容。
5. GitHub Actions 在 Python 3.9、3.11、3.13 上运行模板体检，防止模板本身悄悄腐化。
6. `template_version` 与 `schema_version` 为未来迁移提供可判断基线；现阶段没有自动升级既有项目，避免在没有真实迁移案例时发明脆弱框架。

## 仍然存在，但现在不该做的功能

- 多格式导出：等确定发布目标后，从 Markdown 中间稿生成 DOCX/EPUB/PDF；现在实现只会提前绑定样式。
- GUI 关系图和场景卡：现有 Markdown、索引和 `rg` 足够；只有检索成为实际阻力时再加结构化查询。
- 自动归档人物与伏笔：冷热迁移涉及叙事判断，工具应检测超限和缺口，不应擅自决定什么已经失效。
- 模板自动升级器：版本字段已具备；应等第一次真实 schema 变化时，用可回放迁移脚本实现，而不是先造空框架。

## 复用形态

主形态应是 GitHub Template Repository，因为它原样复制目录、文件和链接，并为新项目建立无关历史；这正符合“骨架相同、故事内容隔离”。GitHub 官方说明见 [Creating a template repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-template-repository)。

Skill 只负责本地、安全地调用这份模板：先证明源模板干净，在临时目录复制、再次体检，然后原子落盘；它不内嵌另一份骨架。这样不会出现“模板仓库修了 bug，Skill 里的旧副本却继续生成坏项目”的双真源问题。

CI 使用 GitHub 官方推荐的 `actions/setup-python`，参考 [Building and testing Python](https://docs.github.com/actions/automating-builds-and-tests/building-and-testing-python)。

## 2026-10-03 更新

2.0.0 保留元数据缓存与任务装包结构，补齐了真实写作中的交接和审阅边界：当前状态与逐章现场经过分开，控制卡逐幕原文完整入包，必需材料超预算报错，整体与语言审阅绑定当前版。声口样本和语言偏好按作品配置，空项目不携带旧作人物与规则。

升级既有项目采用[按文件职责合并](upgrading.md)，保留作品事实、正文、个性规则和未入库审阅证据；未实现自动升级器。本次以回归测试和真实 CLI 往返验证正确性，没有重跑上面的 1000 章性能基准。
