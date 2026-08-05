# 02 — T1: 新增 MCP 工具 capture_conversation（对话采集入口）

**What to build:** 一次完整的"对话采集"垂直切片——新增 `capture_conversation` MCP 工具,把一次 Agent 对话的原始 turns(含 session id、timestamp、actor 标签)以 Markdown 幂等写入 `repowiki/raw/<session>.md`,并注册到现有 MCP server。该工具是整条链路的采集入口,落下的 raw 供 03 蒸馏消费。同时落实 raw 生命周期约束:raw 为暂存区、不进 `query_wiki` 检索、提供 `keep_raw` 开关(默认 False)与可配置保留上限(默认 7 天),蒸馏完成后由 03 清理。

**Blocked by:** None — can start immediately.

**Status:** done

- [x] 新增 `codewiki/mcp/tools/capture_conversation.py`：`handle_capture_conversation` 把 turns(role+content)以 Markdown 幂等写入 `repowiki/raw/conv-<UTCstamp>[-<link_to>].md`,含 frontmatter(actor/timestamp/content_hash/turn_count/link_to/keep_raw/status=pending)。
- [x] 幂等去重：按 turns+link_to 的 sha256 content_hash 检测,重复调用返回 `status=duplicate`,不写第二份。
- [x] 工具返回 `stored_at`(raw_path 相对路径)、`conversation_id`、`turn_count`、`content_hash`、`link_to`、`keep_raw`,可被 `distill_conversation` 直接消费。
- [x] 已在 `codewiki/mcp/registry.py` 注册( `name=capture_conversation`, `mode="thread"`),可通过 handler 表面调用。
- [x] handler 层 + 端到端测试见 `tests/smoke_test_mcp.py` `[17] capture_conversation`(9 项断言全部 PASS),含去重与 `query_wiki` 不索引 raw。
- [x] `keep_raw` 默认 False,仅作为元数据透传(实际清理由 T2 实现)。
- [x] raw 落入 `repowiki/raw/`(非 `raw/sources/`),`query_wiki` 索引与 `okf_conformance` lint 均不扫描该目录,满足"暂存区不进检索/不膨胀"约束。

**实现备注：**
- 同时将 `conversation` 入参支持 `list[turn]` 与 `{"turns": [...]}` 两种形态。
- `repowiki/raw/` 为暂存区,不在 `RAW_SOURCES_DIR` 下,因此不会被 `wiki_lint` 的 okf_conformance 扫描,也不会进入 BM25/SQLite 索引。
- 下一步：T2(T3/T5/T6 依赖本 ticket)实现无状态 LLM 蒸馏。
