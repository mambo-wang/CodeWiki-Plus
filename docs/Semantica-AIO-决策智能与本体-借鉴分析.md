# 调研报告：Semantica 与 AIO 对 CodeWiki-CN 的借鉴分析

> 调研对象：`berkeleybop/artificial-intelligence-ontology`（AIO）与 `semantica-agi/semantica`
> 调研目标：评估其"上下文图 / 决策智能 / 本体"设计对 CodeWiki-CN 的借鉴价值，并给出可落地的增强方案
> 日期：2026-08-09

---

## 1. 背景与调研对象概览

| 项目 | 定位 | 核心产物 | 是否依赖 LLM | 存储形态 |
|---|---|---|---|---|
| **AIO** | AI/ML 领域静态本体 | OWL/OBO 本体文件 + SSSOM 跨本体映射 | 否 | 文件 |
| **Semantica** | 图原生 AI 基础设施（"开源 Palantir"） | Python 包 + RDF/LPG/向量多后端图 + MCP/REST/CLI | 抽取层依赖，推理层不依赖 | 可置换图数据库 |
| **CodeWiki-CN(我们)** | LLM Wiki 生成与检索工具链 | `repowiki/` 下 markdown + json + BM25 索引 | 是(capture/distill) | 文件系统 + BM25 |

**结论先行**：AIO 是"静态术语本体"，与 CodeWiki 已有 `ontology.yaml` 理念同源但领域不匹配，借鉴有限；**Semantica 的「决策即一等公民 + 因果链 + 先例检索 + 确定性推理」设计，恰好补齐 CodeWiki 当前最薄弱的一环（决策无溯源、检索只靠向量）**，是最值得借鉴的对象。

---

## 2. Semantica 的核心设计（深入）

### 2.1 端到端流水线
```
Sources → Ingest → Parse → Normalize → Split → Extract → Conflict/Dedup
   → KG → [Ontology · Reasoning · Provenance · Decisions] → Enriched KG
   → Vector Store + Polyglot Graph Store → Export / MCP / REST / CLI
```

### 2.2 Decision Intelligence 生命周期（关键）
每个决策是知识图谱中的**一等节点**，带完整数据结构（`docs/reference/context.md`）：
```python
@dataclass
class Decision:
    decision_id: str
    category: str          # 如 model_selection / vendor_selection
    scenario: str          # 场景描述
    reasoning: str         # 推理过程
    outcome: str           # 结果
    confidence: float      # 0.0-1.0
    decision_maker: str
    valid_from / valid_until: Optional[str]   # 双时态
    reasoning_embedding / node2vec_embedding   # 语义 + 结构嵌入
    metadata: Dict
```

生命周期五阶段（来自 `docs/guides/decision-intelligence.md`）：
1. **Record**：`record_decision()` → 生成嵌入 → 返回 decision_id
2. **Precedent Search**：`find_precedents()` 用**混合搜索（语义 0.7 + 图结构 0.3）**找历史相似决策
3. **Causal Linking**：`add_causal_relationship(src, tgt, "CAUSED"|"INFLUENCED")` 连成因果链，支持 `upstream`（追根因）/ `downstream`（追影响）
4. **Policy Gating**：`PolicyEngine.check_compliance()` 策略门禁，不合规可 `record_exception()` 留审计痕
5. **Explainability & Audit**：`trace_decision_explainability()` → 导出 W3C PROV-O 审计轨迹

### 2.3 三大可借鉴机制
- **决策溯源链**：决策不是"记一笔"，而是图节点 + 因果边，可 `get_causal_chain(direction, max_depth)` 多跳追踪。
- **先例检索**：新决策前先查 `find_precedents()`，保证跨次决策一致性。
- **确定性推理层**：图分析（PageRank/社区发现）、Datalog/SPARQL 规则推理**完全不依赖 LLM**，只有抽取层用 LLM。

---

## 3. CodeWiki-CN 现状对照

### 3.1 当前 decision note 的实际情况
通过 `distill_conversation.py` 与 `knowledge_loop.py` 的源码确认：
- decision 只是 `_VALID_NOTE_TYPES` 中的一种（`codewiki/mcp/tools/distill_conversation.py:48-51`），与 lesson/pitfall 平级，**没有任何专属字段**。
- `handle_ingest_note`（`knowledge_loop.py:253`）接收的字段为：`note_type, title, content, related_modules, related_components, severity, root_cause, source_ref, aliases, status` —— **没有 `decision_chain` / `precedents` / `confidence` / `category` 等决策专属字段**。
- 去重仅靠标题 Jaccard 相似度（`distill_conversation.py:229-281`），无语义相似度、无因果关系。
- `related_modules` 仅用于"自动匹配模块"，**未形成可多跳行走的关系图谱**。

### 3.2 query_wiki 的检索能力
`wiki_search.py:285-307` 已支持 `hop`（多跳）与 `decay`（衰减）参数，且 `ontology.yaml` 已声明 `relations`（节 3）支持"可多跳行走的图谱"——**架构上已为决策链预留了通道，只是 decision 数据里没有可连的边**。

### 3.3 差距总结
| 能力 | Semantica | CodeWiki 现状 |
|---|---|---|
| 决策专属结构化字段 | ✅ 完整 dataclass | ❌ 仅通用 note 字段 |
| 决策因果链 / 多跳溯源 | ✅ `get_causal_chain` | ❌ 无 |
| 相似决策 / 先例检索 | ✅ 混合搜索 | ❌ 仅 BM25 全文 + 标题去重 |
| 双时态（valid/recorded） | ✅ | ❌ 仅 `stale_after` 保鲜期 |
| 确定性推理（不依赖 LLM） | ✅ Datalog/SPARQL | ⚠️ 部分（`ontology.yaml` relations 可走，未落地） |

---

## 4. 借鉴方案设计（可落地）

**原则**：复用 Semantica 的"决策即一等公民 + 因果链 + 先例检索"思想，**不引入图数据库**（保持 CodeWiki 文件系统 + BM25 的轻量模式），用 frontmatter 字段 + 现有 `ontology.yaml` relations/hop 机制实现。

### 4.1 增强 decision note 的 frontmatter schema
在 `repowiki/schema.yaml` 或笔记 frontmatter 约定中，为 decision 类型新增：

```yaml
# decision note 专属字段（建议新增）
decision_category: model_selection | tech_choice | api_design | ...   # 对应 Semantica category
scenario: "一句话描述决策场景"                                          # 对应 scenario
confidence: 0.91                                                      # 对应 confidence
decision_chain:                                                       # 对应 add_causal_relationship
  - type: INFLUENCED        # CAUSED | INFLUENCED | ENABLES | PRECEDES
    target: "<note_filename 或 note slug>"   # 上游/前置决策
impact_scope: [module_a, module_b]        # 对应 analyze_decision_impact，影响范围
valid_from: "2026-08-09"
valid_until: null                          # 双时态，null 表示至今有效
```

### 4.2 蒸馏 prompt 增强（`_DISTILL_SYSTEM`）
当前 prompt（`:55-81`）对 decision 只要求 `note_type + related_modules`，改为：
- 当 LLM 判定为 `decision` 时，**强制抽取** `decision_category / scenario / confidence / decision_chain（引用本次对话或历史中提及的前置决策） / impact_scope`。
- 新增指令："若对话中引用了之前做过的某个决策或受其影响，在 `decision_chain` 中指向该决策的 slug；若无法定位则标记 `todo: true` 占位"。

### 4.3 query_wiki 新增两种检索模式
复用现有 `hop`/`decay` 参数（`wiki_search.py:285`）：
- **决策溯源链**：`query_wiki(query="X 选型", mode="decision_chain")` → 沿 `decision_chain` 边多跳（上游追根因、下游追影响），利用已有 hop 机制。
- **相似决策 / 先例**：`query_wiki(query="LLM 选型", mode="precedent")` → 在 decision note 子集内做语义相似（现有 BM25 升级为带 `decision_category` 加权）。

### 4.4 复用 ontology.yaml 的 relations 固化因果
将 `decision_chain` 同步写入 `ontology.yaml` 的 `relations`（节 3），使 `query_wiki` 的 hop 多跳直接消费，**无需新存储层**。这正好呼应 `ontology.yaml` 已有的"管推理——构成可多跳行走的关系图谱"目标。

---

## 5. 取舍与风险

**值得做（高 ROI）**：
- §4.1 + §4.2 字段增强：改动小（只改 frontmatter 约定 + 蒸馏 prompt），直接获得"决策可溯源"。
- §4.3 precedent 检索：用现有 BM25 + category 加权即可，不引入新依赖。

**不必做（避免过度设计）**：
- 不引入 Neo4j/Oxigraph 等图数据库 —— CodeWiki 是开发辅助，非合规审计。
- 不实现 Semantica 的 W3C PROV-O 全链路审计、双时态快照、PolicyEngine 合规门禁 —— 超出 CodeWiki 范围。
- 确定性推理层（Datalog/SPARQL）：可长期借鉴 `ontology.yaml` relations 的多跳，但短期不必自建规则引擎。

**风险**：
- decision_chain 的 `target` 引用可能指向不存在的 note → 用 `ontology.yaml` 已有的 `todo: true` 占位机制兜底（`:85` 已有先例）。
- LLM 抽取的 `decision_chain` 可能不准 → 保持 `status: draft`，由 `confirm_note` 人工/agent 校验。

---

## 6. 结论

Semantica 最值得 CodeWiki 借鉴的是**"把决策当作带因果链和置信度的一等公民，并支持先例检索"**这一思想，而非其图数据库/合规审计的重型架构。CodeWiki 当前已具备 `ontology.yaml` relations + `query_wiki` hop 的"关系图谱"骨架，只差把 decision 数据**结构化并连成边**。建议按 §4.1–§4.3 做轻量增强，即可在不引入新依赖的前提下，补齐"决策无溯源、检索只靠向量"的短板。

---

## 附：参考来源

- AIO 仓库：https://github.com/berkeleybop/artificial-intelligence-ontology
- AIO 文档站：https://berkeleybop.github.io/artificial-intelligence-ontology/
- Semantica 仓库：https://github.com/semantica-agi/semantica
- Semantica 决策智能文档：`docs/guides/decision-intelligence.md`、`docs/reference/context.md`
- CodeWiki 现状源码：`codewiki/mcp/tools/distill_conversation.py`、`codewiki/mcp/tools/knowledge_loop.py`、`codewiki/mcp/tools/wiki_search.py`、`repowiki/schema.yaml`、`repowiki/ontology.yaml`
