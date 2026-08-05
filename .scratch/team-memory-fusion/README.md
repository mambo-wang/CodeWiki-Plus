# Wayfinder effort: 融合 TencentDB Agent Memory 能力到 CodeWiki-CN

> Local-markdown issue tracker (gh CLI not installed in this environment).
> Map = this file's map body below; tickets = sibling `<ticket-n>.md` files.
> Claiming a ticket = rename its `status: unclaimed` to `status: claimed-by-<you>`.

## Destination

产出一份**可行性评估 + 工作量估算**报告，判断把 TencentDB Agent Memory（D:/repos/Team-Agent-Memory）的记忆/经验沉淀与可检索能力融合进 CodeWiki-CN 是否可行、以何种形态融合、各档工作量与风险。融合的具体形态（内置 / 桥接 / 借鉴）作为评估结论的一部分给出，不在此阶段落地实现。

## Notes

- 调研对象为外部仓库 `D:/repos/Team-Agent-Memory`（TencentDB Agent Memory）。
- 当前项目：`D:/repos/CodeWiki-CN`（Python 为主，已含 `codewiki/` LLM Wiki 生成、MCP `codebase-memory`）。
- 工单类型：`research` 由 /research 子代理并行解决；`grilling` 需与用户对话确认。
- 评估原则：先确认能力边界与兼容性，再谈融合形态与工作量。

## Decisions so far

- [01 能力盘点](01-capability-inventory.md) — TAM = TencentDB Agent Memory (MIT, Node≥22.16 + Py SDK)；含 MemoryCore(L0-L3/Skill/Asset/ACL, :8420 HTTP)、MemoryKnowledge(Wiki/CodeGraph MCP)、MemoryProxy(透明注入)、MemoryPanel、SDK。
- [02 现状与缺口](02-cw-capability-inventory.md) — CodeWiki-CN 已有 Wiki 生成 + ingest_note 知识流 + AGENTS.md 教训流；**缺失** L0-L3/Skill/透明注入/多Agent/ACL；无 update_memory 工具。
- [03 技术栈兼容](03-stack-compat.md) — 依赖不冲突、可并排 Docker、HTTP+MCP 互通；但 Node vs Python 与存储(文件 vs SQLite/TCVDB)需适配。桥接形态成本最低。
- [04 融合形态](04-fusion-shapes.md) — 用户决策：**借鉴式（聚焦对话→Wiki 提取）**，非泛化内置/桥接；推荐形态定调。
- [05 数据模型映射](05-data-model-mapping.md) — L0/L3/ACL/Skill 在 CodeWiki-CN 缺失；桥接零映射成本，内置需从零建 L0/L3/ACL。
- [06 工作量风险](06-effort-risk.md) — 借鉴式 3–6 人周（MVP≈3 人周）；Top 风险=对话采集缺失+抽取幻觉+知识库重叠。
- [07 可行性报告](07-feasibility-report.md) — 落盘 [`docs/team-memory-fusion-feasibility.md`](../../docs/team-memory-fusion-feasibility.md)。**结论：可行，推荐借鉴式，3–6 人周。**
- [SPEC 对话→Wiki(MVP)](SPEC-conversation-to-wiki.md) — 已发布为 `ready-for-agent` 规格；复用知识飞轮，新增 `capture_conversation` + `distill_conversation` 两个 MCP 工具。

## Triage 拆分（/triage 输出）

SPEC 已切分为 5 个 `ready-for-agent` 子任务 + 1 个 `needs-info` 决策项（追踪器为本地 markdown，因环境无 `gh`）：

- [T0 触发方式](T0-trigger-decision.md) — `resolved`：用户选 **both** —— 手动命令(主) + IDE hook(可选，见 T6)。不阻塞工具实现。
- [T1 capture_conversation](T1-capture-conversation.md) — `done`：新增 MCP 工具，落盘 raw 对话到 repowiki/raw/（幂等去重 + 不进 query_wiki）。
- [T2 distill_conversation](T2-distill-conversation.md) — `ready-for-agent`：无状态 LLM 蒸馏 L0→L1 语义原子草稿，LLM 由调用方注入，走现有确认门。
- [T3 去重](T3-dedup.md) — `ready-for-agent`：蒸馏前对 notes/ 近重复检索抑制。
- [T4 测试](T4-tests.md) — `ready-for-agent`：handler 层 + 端到端 + 提取 golden-set。
- [T5 检索区分](T5-retrieval-distinction.md) — `ready-for-agent`：query_wiki 暴露 origin 并支持来源过滤。
- [T6 IDE hook 自动采集](T6-ide-hook.md) — `ready-for-agent`：监听对话事件自动调 capture_conversation；可开关、异步、依赖 T1。

## Published tickets（/to-tickets 输出）

已规范化发布到 [`issues/`](issues/) 目录，按依赖顺序编号（blockers 在前），本地 markdown 单票单文件：

| # | Ticket | Blocked by | Status |
|---|--------|-----------|--------|
| [01](issues/01-trigger-decision.md) | T0 触发方式(both) | — | resolved |
| [02](issues/02-capture-conversation.md) | T1 capture_conversation | — | done |
| [03](issues/03-distill-conversation.md) | T2 distill_conversation | 02 | ready-for-agent |
| [04](issues/04-dedup.md) | T3 去重 | 03 | ready-for-agent |
| [05](issues/05-retrieval-distinction.md) | T5 检索区分 | 03 | ready-for-agent |
| [06](issues/06-ide-hook.md) | T6 IDE hook 自动采集 | 02 | ready-for-agent |
| [07](issues/07-tests.md) | T4 端到端测试+golden-set | 02,03,04,05 | ready-for-agent |

> 注：T4 在编号中置于 07（按依赖顺序最后发布），因集成测试需贯穿全链路。

## Not yet specified

- 融合后是否需要保留 Team-Agent-Memory 的 Web 面板（MemoryPanel）还是仅后端能力。
- 是否需要支持多 Agent / 多 Team 的协作与 ACL（取决于融合形态）。

## Out of scope

- 不在本次实现任何融合代码；只产出评估结论。
- 不评估 Team-Agent-Memory 的商业许可 / 商标问题（仅 MIT 许可已知）。
