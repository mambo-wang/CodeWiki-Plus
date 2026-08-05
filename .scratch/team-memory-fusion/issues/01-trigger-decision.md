# 01 — T0: capture_conversation / distill_conversation 触发方式（IDE hook + 手动命令）

**What to build:** 确定对话→Wiki 提取链的触发形态,并锁定为 **both**:(a) 手动命令触发——用户/Session 结束时显式调用 `capture_conversation`(主路径,无 IDE 依赖);(b) 可选 IDE hook 自动采集——监听对话事件自动调用 `capture_conversation`(见 06)。决策已 resolved,不阻塞工具实现,但为其余 ticket 提供约束边界。

**Blocked by:** None — can start immediately.

**Status:** resolved

- [ ] 手动命令触发形态已写入 spec(T1 工具的自然使用方式)。
- [ ] IDE hook 自动采集作为独立 ticket(06)拆分,依赖 T1 完成。
- [ ] T1–T5 工具实现不受触发方式影响,可并行开工。
- [ ] 蒸馏始终走 subagent/BackgroundWorker 后台路径,不在 hook 内联执行。
