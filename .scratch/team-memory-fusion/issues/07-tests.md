# 07 — T4: 端到端测试与提取质量 golden-set

**What to build:** 为整条对话→Wiki 链补测试护城河——(a) `capture_conversation` handler 测试(成功写 + 幂等);(b) `distill_conversation` handler 测试(给定 raw 产出正确 `note_type` 草稿);(c) 集成测试贯穿 02→03→`confirm_note`→`query_wiki`,验证草稿经确认后才可检索;`query_wiki` 能取回带 `origin: conversation` 的笔记;(d) golden-set:一小批已知 raw→预期提取,捕获 LLM 提取回归(幻觉/漏提)。遵循现有 `codewiki/mcp/tools/` 测试惯例,通过 MCP handler 表面测外部行为,fixtures 置于 `tests/`,不依赖外部实时 LLM。

**Blocked by:** 02 — T1: 新增 MCP 工具 capture_conversation（对话采集入口）, 03 — T2: 新增 MCP 工具 distill_conversation（L0→L1 蒸馏）, 04 — T3: 草稿去重（蒸馏前对 notes/ 检索）, 05 — T5: query_wiki 区分对话笔记与架构 Wiki(集成测试贯穿全链路,需各工具就绪)。

**Status:** ready-for-agent

- [ ] `capture_conversation` handler 测试覆盖成功写与幂等。
- [ ] `distill_conversation` handler 测试覆盖 note_type 正确性与 draft 状态。
- [ ] 一条端到端集成测试覆盖 采集→蒸馏→确认→检索。
- [ ] 至少 3 条 golden-set 样例验证提取质量。
- [ ] 全部测试可独立运行且不依赖外部实时 LLM(用 mock/stub 模型响应或固定 fixture)。
