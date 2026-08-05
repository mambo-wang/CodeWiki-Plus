# 04 — T3: 草稿去重（蒸馏前对 notes/ 检索）

**What to build:** 在蒸馏链路中插入"先查重再落草稿"的一步,使对同一/相似对话反复蒸馏不会污染知识库。在 `distill_conversation`(03)产出草稿前,调用现有 `query_wiki` 在 `notes/` 中检索近重复项;命中则抑制(丢弃)或与既有 note 合并(追加 `source_conversation` 引用)。去重范围严格限定 `notes/`,避免与 `wiki/` 架构文档冲突。

**Blocked by:** 03 — T2: 新增 MCP 工具 distill_conversation（L0→L1 蒸馏）(在蒸馏流程中插入步骤)。

**Status:** ready-for-agent

- [ ] 对同一 raw 对话重复蒸馏,第二次不再产生重复草稿(被抑制或合并)。
- [ ] 与既有 `notes/` 中高度相似的 note 不重复创建。
- [ ] 去重范围限定在 `notes/`,不影响 `wiki/` 架构文档。
- [ ] 有测试覆盖"重复蒸馏不重复落库"。
