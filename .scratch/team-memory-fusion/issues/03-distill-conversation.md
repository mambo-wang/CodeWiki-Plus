# 03 — T2: 新增 MCP 工具 distill_conversation（L0→L1 蒸馏）

**What to build:** 一次完整的"对话蒸馏"垂直切片——新增**无状态** `distill_conversation` MCP 工具:读取 `repowiki/raw/<session>.md`,把对话蒸馏为 L1 语义原子草稿 note(按现有 `note_type` 分类),经现有 `ingest_note` 以 `status='draft'` 写入,必须 `confirm_note` 后才进 `repowiki/notes/`。工具自身不持有 LLM——LLM 由调用方注入(推荐 IDE subagent 用 CodeBuddy 自带模型;或 BackgroundWorker 需 `MAIN_MODEL`/`LLM_BASE_URL`)。草稿 frontmatter 含 `origin: conversation` 与 `source_conversation` 引用。蒸馏是 LLM 重活,必须在后台异步执行、主线程不等待。蒸馏完成后在 02 未设 `keep_raw` 时 best-effort 删除对应 raw,防止暂存区膨胀。

**Blocked by:** 02 — T1: 新增 MCP 工具 capture_conversation（对话采集入口）(需 raw 落盘路径与 `keep_raw` 透传契约)。

**Status:** ready-for-agent

- [ ] 给定一段含明确决策/教训的 raw 对话,产出对应 `note_type` 的草稿 note。
- [ ] 草稿以 `status='draft'` 写入,未经 `confirm_note` 前不可被 `query_wiki` 作为正式笔记检索到。
- [ ] 每条草稿含 `origin: conversation` 与 `source_conversation` 引用。
- [ ] 闲聊/无意义内容不产生草稿(signal-dense)。
- [ ] 复用既有 `ingest_note` 持久化/索引路径,无第二套写入逻辑。
- [ ] 工具本身不持有 LLM 接线;LLM 由调用方注入(测试中可显式传入 stub/mock LLM 验证)。
- [ ] 02 未设 `keep_raw` 时,草稿全部确认/拒绝后 best-effort 清理对应 raw 文件。
- [ ] 有 LLM 提取的 golden-set 测试(防幻觉回归)与一条 handler 层测试。
