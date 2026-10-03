---
trigger: always_on
---

# 缓存文件访问

主执行者先用 `context --out .story-cache/<任务文件>.md` 保存完整包。写手收到章号、目标草稿和该文件路径；不自行重建包。文件工具无法访问缓存时，经终端读取同一文件，按 `references/context-reading.md` 分段核对完整性。

审阅者只读 `review-start` 输出的精确快照路径。主执行者按共享协议填写记录；若需终端写 JSON，只改当前轮 `notes` 与顶层 `findings`，不改指纹、快照、历史或完成标志，随后运行 `review-finish`。
