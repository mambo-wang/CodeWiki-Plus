# 06 — T6: IDE hook 自动采集对话（capture_conversation 自动触发）

**What to build:** 一次完整的"自动采集"垂直切片——在 IDE agent 运行环境中监听对话事件(用户消息提交/assistant 回复落库/会话结束),自动调用 02 的 `capture_conversation`,实现对话经验无感采集(手动触发之外的可选路径)。要求异步/非阻塞、可开关(默认关)、与 02 共用 `repowiki/raw/<session>.md` 且幂等。边界明确:自动采集层**只落 raw,不触发蒸馏**;蒸馏由 03 经 subagent/worker 后台执行。自动采集落下的 raw 同样适用 02 的清理策略,不额外持有副本。

**Blocked by:** 02 — T1: 新增 MCP 工具 capture_conversation（对话采集入口）(需 `capture_conversation` 工具先就绪)。

**Status:** ready-for-agent

- [ ] 开启自动采集后,一次对话结束能在 `repowiki/raw/` 生成对应 session 的 turns 文件。
- [ ] 关闭开关后,不发生任何自动写入。
- [ ] 自动写入为异步/非阻塞,不拖慢对话响应。
- [ ] 与手动调用 02 写入同一路径且幂等,不冲突。
- [ ] 有测试或冒烟验证覆盖"事件触发 → capture_conversation 被调用"。
