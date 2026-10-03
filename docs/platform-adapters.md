# 平台入口

规则与角色说明共用 `.cursor/skills/`、`.cursor/agents/` 和 `references/`。各平台文件只负责入口、工具权限与读取方式；更换平台不另立写作规则。

| 平台 | 入口 | 模型选择 |
|---|---|---|
| Cursor | `.cursor/skills/`、`.cursor/agents/` | 按会话配置 |
| Codex | `.agents/skills/` 链接、`.codex/agents/*.toml` | 本模板不固定模型或推理力度，按父会话与平台默认配置解析 |
| Devin | `.devin/agents/`、`.devin/rules/` | 本模板不固定模型，由平台默认子代理路由决定；不保证跟随父模型 |

Codex 的自定义入口包含 `name`、`description` 和 `developer_instructions`；审阅者设置只读沙箱，但会话的实时权限覆盖仍以平台为准。参见 [Codex 自定义代理文档](https://learn.chatgpt.com/docs/agent-configuration/subagents)。

Devin 的自定义代理采用 Markdown frontmatter。需要固定模型时，维护者在自己的项目入口配置 `model`，并核对当前平台支持。参见 [Devin 子代理文档](https://docs.devin.ai/cli/subagents)。

## 上下文交接

主执行者生成 `context --out` 文件，完整读取并检查后再委派。写手只读同一文件，不重新生成；必要时用终端分段读文件。整体首读和语言冷读分别只接收当前轮指定快照，不能同时提供控制卡、源稿或完整上下文包。

## Devin 写入护栏

`.devin/config.json` 列出生成正稿、快照和索引的文件写入禁止项；`.devin/hooks.v1.json` 的 PreToolUse hook 对 `write`、`edit`、`apply_patch`、`notebook_edit` 执行同一份清单。确认与回滚命令保留平台询问设置。个人覆盖使用已忽略的 `.devin/config.local.json`。

该 hook 只管匹配的文件工具，不拦截终端命令；自身错误按平台规则记录并放行。用 `/hooks` 检查是否加载。参见 [Devin hooks 文档](https://docs.devin.ai/cli/extensibility/hooks/overview)。仓库测试验证配置和 hook 输入输出，尚未在各平台真实会话里端到端试运行。
