# 可行性评估：融合 TencentDB Agent Memory 到 CodeWiki-CN

> 生成于 wayfinder 规划（`.scratch/team-memory-fusion/`）。调研对象：`D:/repos/Team-Agent-Memory`（TencentDB Agent Memory，MIT）。
> 本文只做**可行性 + 工作量**评估，不含实现。

## 一句话结论

**可行。** 推荐采用**借鉴式**（聚焦"对话 → Wiki/经验资产"提取），在 CodeWiki-CN 自身 Python 体系内复用 TAM 的记忆分层抽取思路，预计 **3–6 人周**完成 MVP，无需引入 Node 依赖或 TAM 服务。

## 调研对象能力盘点（TAM）

| 子项目 | 能力 | 对外接口 | CodeWiki-CN 是否已有 | 融合价值 |
|---|---|---|---|---|
| MemoryCore | L0-L3 记忆分层 + Skill + Asset + ACL | HTTP :8420 | 仅 L2 近似 | 高（分层抽取） |
| MemoryKnowledge | Wiki / CodeGraph 知识沉淀 | MCP | 有（codewiki/） | 低（重叠） |
| MemoryProxy | 透明把记忆注入 LLM 对话 | 代理 | 无 | 中 |
| MemoryPanel | Web UI | Web | 无 | 低（非核心） |
| sdk | TS / Py 调用面 | SDK | 无 | 中（桥接用） |

## CodeWiki-CN 现状与缺口

- 已有：LLM Wiki 生成（`codewiki/` → `repowiki/`）、`ingest_note` 知识流 + 人工确认飞轮、AGENTS.md 教训沉淀流程、MCP `codebase-memory`。
- **缺失**（TAM 的真正互补点）：①L0 对话级采集层；②L1 语义原子自动抽取；③L3 用户/团队画像；④Skill 资产体系；⑤透明代理注入；⑥多 Agent / ACL。
- 与 TAM **重叠**且无需重复：Wiki/CodeGraph 生成、`query_wiki` 检索。

## 三种融合形态对比

| 形态 | 可行性 | 工作量 | 与现状冲突 | 演进灵活 |
|---|---|---|---|---|
| 内置集成 | 中 | 2–4 人月 | 高（Node 依赖、存储模型差异、需补 L0/L3/ACL/Skill） | 低 |
| 桥接(MCP/SDK) | 高 | 2–4 人周 | 低 | 高 |
| **借鉴(对话→Wiki)** ✅ | 高 | **3–6 人周** | 低（纯 Python，复用现有笔记体系） | 高 |

**推荐：借鉴式（聚焦对话→Wiki 提取）。** 理由：保留 CodeWiki-CN Python 单体、复用 `ingest_note` 确认飞轮与 `repowiki/` 产出，避免 Node 依赖；只吸收 TAM 高价值切片——对话经验沉淀为可检索 Wiki。

## 数据模型映射（借鉴式视角）

| TAM 概念 | CodeWiki-CN 映射 | 成本 |
|---|---|---|
| L0 对话 turns | 新增对话采集入口 | 高（现状无采集链路） |
| L1 语义原子 | 复用 `ingest_note`(lesson/decision) + LLM 蒸馏 | 中 |
| L2 场景知识块 | 复用 `repowiki/` 文档生成，按场景聚类 | 低-中 |
| L3 画像 | 暂不纳入 MVP | — |
| Skill 资产 | 借鉴为"经验 note 可升级为 skill 建议" | 中 |
| ACL | 暂不纳入 MVP | — |

最大阻碍：L0 对话采集链路在 CodeWiki-CN 完全缺失（首要工程量）；L2 聚类与现有 CodeWiki 文档生成有重叠，需明确边界避免两套知识库。

## 工作量估算（借鉴式）

- **MVP（≈3 人周）**：①对话采集入口 → ②L0→L1 LLM 抽取管线 → ③L1→L2 场景聚类 + 自动建议 `ingest_note` → ④并入 `repowiki/` 可被 `query_wiki` 检索。
- **完整（3–6 人周）**：加 Skill 提炼建议、质量评测集、去重/边界治理。

## Top 风险与缓解

1. **对话采集链路缺失**：MVP 先只做"对话→经验 note"闭环（复用 `ingest_note` 确认），不上 L3/ACL。
2. **抽取质量/幻觉**：L0→L1 需评测集；结果一律走人工确认飞轮再落盘。
3. **重复造轮子**：L2 与现有 CodeWiki 生成重叠，明确"对话经验"专属知识库，不替代架构 Wiki。
4. **许可/演进**：仅借鉴设计不引入代码，许可风险低；跟踪 TAM 抽取范式更新。

## 建议下一步

若决定进入实现：用 `/to-spec` 把 MVP（对话采集 → L1 抽取 → `repowiki/` 经验笔记）写成 spec，再 `/triage` 拆 AFK 任务。
