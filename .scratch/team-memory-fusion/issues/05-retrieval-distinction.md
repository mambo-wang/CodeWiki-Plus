# 05 — T5: query_wiki 区分对话笔记与架构 Wiki

**What to build:** 让 `query_wiki` 检索结果可区分来源——对话笔记(`origin: conversation`)与架构 Wiki 文档,并支持按来源过滤,且不破坏默认行为。复用现有 `query_wiki` 路径与 BM25 索引;结果项增加来自 note frontmatter 的 `origin` 元数据,新增可选来源过滤参数(默认不过滤,向后兼容)。

**Blocked by:** 03 — T2: 新增 MCP 工具 distill_conversation（L0→L1 蒸馏）(需 `origin: conversation` 草稿先落入 `notes/`)。

**Status:** ready-for-agent

- [ ] 对话笔记经 `confirm_note` 后,`query_wiki` 能检索到且结果含 `origin: conversation`。
- [ ] 新增的来源过滤参数按预期只返回对应来源结果。
- [ ] 不带过滤参数时,行为与改动前完全一致(向后兼容)。
- [ ] 有测试覆盖来源元数据透传与过滤。
