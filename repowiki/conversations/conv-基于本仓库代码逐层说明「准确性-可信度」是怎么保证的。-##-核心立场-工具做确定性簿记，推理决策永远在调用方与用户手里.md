---
type: Conversation
title: "conversation 20260904T043937Z"
status: distilled
stale_after: 2026-12-03
generated: { by: codewiki/5.5.1, at: 2026-09-04T04:39:37Z }
captured_at: "2026-09-04T04:39:37Z"
content_hash: "sha256:1e2585abb690386c950153d257e13305ea592020c26af1b09dd5124f90a9f532"
friction_score: 45
friction_signals: "correction=2,interrupt=0,repeat=0,user_turns=5"
keep_raw: false
link_to: ""
source_session: "de00b15723c843da991a87678162c023"
turn_count: 27
---

# Conversation Transcript

user: 基于本仓库代码逐层说明「准确性/可信度」是怎么保证的。



## 核心立场



> **工具做确定性簿记，推理决策永远在调用方与用户手里；证据只驱动复核提醒，永不自动改写。**



`



## 五道防线



**1. 生成前：事实由静态分析产出，LLM 只负责表述**

`analyze_repo` 用 AST/符号表/路由抽取建组件图与依赖边，组件 ID 来自真实符号表；写文档时 Agent 通过 `read_code_components` 读真实源码区间。代码还按 `code_routing` 分级注入（business 全量源码 / boilerplate 仅签名 / infra 摘要），避免 token 压缩导致的臆造。



**2. 生成中：Evidence-Based 断言协议（反幻觉主手段）**



```41:49:codewiki/src/be/prompt_template.py

2. Rules WITHOUT direct code evidence MUST be marked as [candidate] with confidence ≤ 0.5.

3. Format in documentation as a "Business Constraints" section per component:

   - <rule statement> (confidence: 0.85)

     > Evidence: `<code quote>` — <reason>

   - [candidate] <rule statement> (confidence: 0.4)

     > No direct code evidence; requires developer confirmation



4. Do NOT fabricate evidence. If you cannot point to specific code that enforces the rule, mark it as [candidate].

```



**3. 落盘即锚定：内容哈希证据（借鉴 openwiki Grounded Claims）**

`stamp_evidence` 把 `repo://<path>#L<start>-<end>` + 该区间的 `sha256` 写进页面 frontmatter 的 `sources`；`write_doc_file` 在 `conventions.auto_evidence: true` 时自动打标（最多 8 个组件，`doc_writer.py:962-1010`）。用内容哈希而非 git SHA，跨分支/重写历史都稳定。



**4. 落盘后：lint_wiki 18 项一致性检查**



| 检查 | 作用 |

|---|---|

| `stale_evidence` | 重算哈希 → `stale`/`missing`/`unresolvable`，代码漂移就报复核（`wiki_lint.py:1004-1096`） |

| `unsupported_claims` | 无代码证据断言占比 >30% 告警（`:930-1001`） |

| `stale_refs` / `broken_links` / `overview_stale` | 引用了已消失组件、断链、总览与子模块不一致 |

| `okf_conformance` / `stale_notes` / `low_adoption` | 溯源字段合规、超复核期、高频召回零采纳（内容不 actionable） |

| `coverage` / `undocumented` / `isolated_components` | 覆盖缺口 |



**5. 生命周期闸门 + 检索期信号**

- 笔记默认 `draft`，`confirm_note` 才升 `stable` 并写 `verified: by: human:<id>`、续期 `stale_after`；`reject_note` 转 `deprecated`（`knowledge_loop.py:996-1058`）。本仓页面已带 `generated.by/at`、`status`、`verified`（如 `repowiki/wiki/modules/MCP_Cache.md:4-21`）。

- `stale_notes` 按 `stale_after` 滚动复核，近期被检索可豁免，并按「超期最久 + 最少被查」排复核优先级（`wiki_lint.py:1133-1257`）。

- 检索侧标注 `source_type`（`auto_generated` / `developer_note` / `ingested_source`）并给出消费建议；热度+采纳权重进排序；索引在 `git pull` 后与磁盘清单不符会自动重建，避免用陈旧索引回答（`index_freshness.py:1-19`）。



## 必须说清的边界（当前缺口）



1. **证据只提醒不改写**——漂移了还要人类复核，`stale_evidence` 不会自动修正文档。

2. **`unsupported_claims` 只扫带 `(confidence: x.xx)` 的行**（`_CONFIDENCE_RE`，`wiki_lint.py:925`）。没标置信度的断言完全不被检查，等于可绕过。

3. **置信度是 LLM 自评**，不是客观真值；`evidence` 引用也是模型摘的，未做机器校验。

4. **本仓库自身没吃到这套保护**：`repowiki/schema.yaml` 里没有 `auto_evidence`（默认 false），wiki 目录下只有 13 个页面有 `sources` 且多为 `ingest_source` 的外部文档，模块页基本**没打代码证据锚点** → `stale_evidence` 对 CodeWiki-CN 自己的模块文档实际不生效。这是最值得补的一环。

5. `low_adoption` / `stale_notes` 依赖 telemetrY
user: <question>本会话是否关联到某个进行中的任务？</question>
<answers>
跳过(本次会话不做任务关联)
</answers>
</question_item>
</questions>
</question_answer>
assistant: 用户选择跳过任务关联，我直接开始。这个问题要求基于源码验证「准确性/可信度」的五道防线，我先并行摸底仓库结构并核验用户引用的文件。
assistant: 文件都存在，但注意 `knowledge_loop.py` 只有 2.46KB——用户引用的 996-1058 行不在这个文件里。先摸清真实代码位置。
assistant: `knowledge_loop.py` 是重构后的兼容门面，真正的 confirm/reject 逻辑已拆到 `note_lifecycle.py`——用户引用行号来自旧版文件，这点稍后说明。现在并行核验各引用点的真实实现。
assistant: 已确认 `prompt_template.py` 41-49、`doc_writer.py` auto_evidence、`stamp_evidence`、`index_freshness` 的实现都真实存在且与描述基本吻合。继续核验 `wiki_lint.py` 各检查项和 confirm/reject 生命周期，先定位符号行号再读区间。
assistant: 关键发现：`repowiki/schema.yaml:91` 其实是 `auto_evidence: true`（2026-09-04 生成），用户边界第 4 点「本仓库没开 auto_evidence」可能已过时——需要进一步核实。继续读 `wiki_lint.py` 关键实现并核对 sources 实际覆盖。
assistant: wiki 目录实际有 18 个带 `sources` 的文件（含 7 个模块页），与用户说的「13 个、模块页基本没打」不符。进一步区分哪些是带 `content_hash` 的真代码证据，同时读生命周期与哈希实现。
assistant: 现在仓库里已有 8 个模块页 + 1 个 scenario 带 `content_hash` 代码证据锚点，`schema.yaml` 也是 `auto_evidence: true`——用户边界第 4 点与当前仓库状态不符，需在回答中更正。继续读证据哈希实现、code_routing 分级注入和静态分析管线。
assistant: 核心证据链已清晰。现在补最后几块：`analyze_repo` 的静态分析入口、`read_code_components` 写盘机制、以及 code_routing 分级如何影响注入内容。
assistant: 最后读 `format_user_prompt` 中 code routing 如何决定注入内容的完整度。
assistant: 核心机制已基本核实。做最后一批定向确认：`_inject_evidence` 在写入链路的挂载点、`DependencyGraphBuilder` 是否真用 AST/符号表、检索侧 `source_type` 标注与 telemetry 降级。
assistant: 核验完毕。以下按你的框架逐层给出代码实证，并在末尾标注「与仓库现状有出入、需要更正」的点。

## 逐层核验：准确性/可信度保证机制

### 防线 1 — 生成前：事实由静态分析产出

`analyze_repo` 链路真实存在：`handle_analyze_repo` 委托 `DependencyGraphBuilder.build_dependency_graph`，而底层解析器是**确定性语法分析而非 LLM 抽取**——Python 用标准库 `ast.parse`，其余语言走 tree-sitter：

```1:16:codewiki/src/be/dependency_analyzer/analyzers/python.py
import ast
...
```
```535:535:codewiki/src/be/dependency_analyzer/analyzers/python.py
                tree = ast.parse(self.content)
```
`js/typescript/java/go/kotlin/php/c#/c/cpp` 各有 tree-sitter 解析器（`analyzers/*.py`）。组件 ID、`start_line/end_line`、依赖边都来自符号表结果；增量模式只重解析变更文件（`analysis.py:108-144`），未变组件从缓存复用。

`read_code_components` 的关键点是**回源读磁盘实时源码**：组件节点仅存 `file_path + 行区间`，内容按需从磁盘现读（`code_reader.py:18-32`），LLM 拿到的不是分析期的快照。

**一处出入**：`code_routing` 分级并非「business 全量 / boilerplate 仅签名 / infra 摘要」，实际判定是按**文件**粒度：

```596:623:codewiki/src/be/prompt_template.py
        is_boilerplate = file_categories == {"boilerplate"}
        ...
        if is_boilerplate:
            # Abbreviated: signature-only for boilerplate (DTO/VO/Entity/Mapper)
            ...参数表（≤15 参数）
        else:
            # Full source for business/infra components
            ...整文件源码
```
即：**纯 boilerplate 文件 → 仅签名；business/infra/混合文件 → 全量源码**。另加 BFS 1-hop 依赖组件仅签名（≤15 条，`prompt_template.py:625-659`），提示语注明「use read_code_components for full source if needed」。不存在单独的「infra 摘要」档。

### 防线 2 — 生成中：Evidence-Based 断言协议

`prompt_template.py:41-49` 与你的摘录一致（`SYSTEM_PROMPT` 和 `LEAF_SYSTEM_PROMPT` 各有一份）。补充一点：`LEAF_SYSTEM_PROMPT` 从 121 行起有同样的规则块，覆盖子模块文档生成。

### 防线 3 — 落盘即锚定：内容哈希证据

`stamp_evidence`（`evidence.py`）与 `src/evidence.py` 数据模型完整：

```19:25:codewiki/src/evidence.py
_RESOURCE_RE = re.compile(r"^repo://(?P<path>[^#]+?)(?:#L(?P<start>\d+)(?:-L(?P<end>\d+))?)?$")
...
def _sha256(data: str) -> str:
    return _HASH_PREFIX + hashlib.sha256(data.encode("utf-8")).hexdigest()
```
- 条目形如 `repo://src/x.py#L10-L40` + `sha256:` 内容哈希；idempotent key = resource（`_merge_sources` 按 id 去重，哈希变了才更新）。
- 集中式多仓工作区会记录 `repo` 归属字段 + `evidence_roots` 候选根解析（`evidence.py:25-76`），避免 `repo://` 路径歧义。
- 自动打标挂载在 `write_doc_file` 主链路（`doc_writer.py:1504-1510` 调 `_inject_evidence`），上限 8 组件（`_MAX_AUTO_EVIDENCE`），**永不覆盖已存在的 `sources`**，失败 non-fatal。
- 用内容 sha256 而非 git SHA 的判断正确——`make_entry` 不带任何 commit 引用。

### 防线 4 — 落盘后：lint_wiki 检查

你引用的行号经核对基本准确（文件是当前版本的 `wiki_lint.py`）：

| 检查 | 实际位置 | 备注 |
|---|---|---|
| `_check_unsupported_claims` | `wiki_lint.py:930-1001` | 阈值 0.3 |
| `_CONFIDENCE_RE` | `wiki_lint.py:925` | 与描述一致 |
| `_check_stale_evidence` | `wiki_lint.py:1004-1096` | docstring 明写「never rewrites content」 |
| `_check_stale_notes` | `wiki_lint.py:1133-1257` | 排序 `(-overdue, last_hit)` 实现「超期最久+最少被查优先」 |
| `_check_low_adoption` | `wiki_lint.py:1260` | |
| `_check_stale_refs` / `_check_broken_links` / `_check_okf_conformance` | 294 / 366 / 1619 | |

`stale_evidence` 判定细节（`wiki_lint.py:1060-1069`）：多根解析时对每个 entry 逐个 root `verify_entry`，任一 `ok` 即通过；否则按 **stale > missing > unresolvable** 只报最可行动态。

### 防线 5 — 生命周期闸门 + 检索期信号

**行号过时需更正**：`knowledge_loop.py:996-1058` 引的是拆分前的大文件。该文件现为 2.4KB 兼容门面（docstring 明示 2026-09 拆分），confirm/reject 真实实现已移至 `note_lifecycle.py`：

```56:91:codewiki/mcp/tools/note_lifecycle.py
def handle_confirm_note(...):
    """Confirm a draft note, promoting it to stable (verified) domain knowledge.
    OKF v0.2: appends a ``verified`` entry (``human:<id>`` when ``by`` is
    passed, else ``codewiki/<version>``) and renews ``stale_after``.
    ...
    return _update_note_status(
        output_dir, note_file, "stable",
        verified_by=_okf_actor(arguments.get("by")),
        renew_stale_after=True, ...)
```
`handle_reject_note` 在 94 行，转 `deprecated`。`MCP_Cache.md:4-21` 的 frontmatter（`generated.by: codewiki/5.2.0` / `status: stable` / `verified: human:wangbao`）核对属实。

`index_freshness` 核对属实：三层检查（count → manifest → **mtime 采样 ≤8 个文件**，覆盖「pull 来被 confirm 的草稿」这类内容级变更），每 output_dir 60s 节流，stale 判定绕过节流立即重建搜索索引 + `index.md`；重建失败降级用旧索引并标记 `index_stale`，「self-healing must NEVER break search」。

检索侧标注确认在 `note_query.py:936-946`（`developer_note` / `ingested_source` / `auto_generated`）；usage-heat 排序消费 `telemetry.aggregate_usage`（`note_query.py:1208`）。

## 边界核对：哪些成立、哪些已过时

1. **证据只提醒不改写** ✅ 成立。`wiki_lint.py:1010` docstring + `src/evidence.py:8` 两处明示「drives a review reminder, never an automatic rewrite」；suggestion 只指引人工 re-verify + re-stamp。
2. **`unsupported_claims` 只扫 `(confidence: x.xx)` 行** ✅ 成立（`wiki_lint.py:961` 无置信度行直接 `continue`）。且注意它只检查「后续 2 行内有 `> Evidence:` 行」的**格式邻近性**，并不校验引用代码是否真实支撑断言——比你说的「可绕过」更松一层。
3. **置信度是 LLM 自评** ✅ 成立。prompt 让 LLM 自填 confidence，lint 不校验真假。
4. **「本仓库没吃到这套保护」❌ 已过时**。`repowiki/schema.yaml:91` 现为 `auto_evidence: true`（`generated_at: 2026-09-04`）。实测：
   - `repowiki/wiki/` 下有 **18 个**页面带 `sources:`（不止 13）；
   - 其中 **9 个带 `content_hash` 真代码证据锚点**：`MCP_Tools_Workspace`、`MCP_Tools_Quality`、`MCP_Tools_Knowledge`、`MCP_Tools_DocWriter`、`MCP_Cache`、`LLM_Backend`、`KnowledgeStore`、`AnalyzerUtils`（8 个模块页）+ `scenarios/任务记忆系统设计方法.md`。
   
   即 `stale_evidence` 对本仓模块文档**已生效**——这块缺口似乎在 2026-09-04 的 schema 重生成时补上了。若你基于更早的仓库状态得出此结论，建议以当前 HEAD 复查；若想进一步确认覆盖度，可跑 `lint_wiki checks=['stale_evidence']` 看实际告警。
5. **依赖 telemetry（后半句被截断）**：补完——`telemetry.enabled: true`（schema:190），且带 gitignored 本地降级目录 `.meta/telemetry-local/`（`telemetry.py:15,49`），`aggregate_usage` 两个目录都会聚合。即使关掉遥测，`low_adoption`/`stale_notes` 的逻辑不失效，只是数据变单机、不再跨成员共享。

## 一个未列出的隐式防线

`append_evidence_block` 与 `_merge_sources` 都走锁内读改写（`locked_rmw`，`evidence.py:146-197`），并发写不丢证据；`stale_notes` 的「近期被检索豁免」（`retrieval_defer_days`）由 telemetry 的 `last_hit` 驱动，属于检索反馈闭环——这些算是防线 3/5 的并发与时效细节，供你补充进说明。
user: <cb_summary>
This session is being continued from a previous conversation that was compacted to stay within the model context window.
Messages after this summary (if any) are the original recent turns. Tool results from before this summary were omitted.
If you need exact code, command output, or file contents from before compaction, re-read those files. Do not treat omitted tool bodies as still in context.

Earlier user requests:
- 基于本仓库代码逐层说明「准确性/可信度」是怎么保证的。
 
 ## 核心立场
 
 > **工具做确定性簿记，推理决策永远在调用方与用户手里；证据只驱动复核提醒，永不自动改写。**
 
 `
 
 ## 五道防线
 
 **1. 生成前：事实由静态分析产出，LLM 只负责表述**
 `analyze_repo` 用 AST/符号表/路由抽取建组件图与依赖边，组件 ID 来自真实符号表；写文档时 Agent 通过 `read_code_components` 读真实源码区间。代码还按 `code_routing` 分级注入（business 全量源码 / boilerplate 仅签名 / infra 摘要），避免 token 压缩导致的臆造。
 
 **2. 生成中：Evidence-Based 断言协议（反幻觉主手段）**
 
 ```41:49:codewiki/src/be/prompt_template.py
 2. Rules WITHOUT direct code evidence MUST be marked as [candidate] with confidence ≤ 0.5.
 3. Format in documentation as a "Business Constraints" section per component:
    - <rule statement> (confidence: 0.85)
      > Evidence: `<code quote>` — <reason>
    - [candidate] <rule statement> (confidence: 0.4)
      > No direct code evidence; requires developer confirmation
 
 4. Do N…
- <question_answer> <questions> <question_item id="q-0"> <question>本会话是否关联到某个进行中的任务？</question> <answers> 跳过(本次会话不做任务关联) </answers> </question_item> </questions> </question_answer>

Earlier assistant notes (truncated):
- 用户选择跳过任务关联，我直接开始。这个问题要求基于源码验证「准确性/可信度」的五道防线，我先并行摸底仓库结构并核验用户引用的文件。
- 文件都存在，但注意 `knowledge_loop.py` 只有 2.46KB——用户引用的 996-1058 行不在这个文件里。先摸清真实代码位置。
- `knowledge_loop.py` 是重构后的兼容门面，真正的 confirm/reject 逻辑已拆到 `note_lifecycle.py`——用户引用行号来自旧版文件，这点稍后说明。现在并行核验各引用点的真实实现。
- 已确认 `prompt_template.py` 41-49、`doc_writer.py` auto_evidence、`stamp_evidence`、`index_freshness` 的实现都真实存在且与描述基本吻合。继续核验 `wiki_lint.py` 各检查项和 confirm/reject 生命周期，先定位符号行号再读区间。
- 关键发现：`repowiki/schema.yaml:91` 其实是 `auto_evidence: true`（2026-09-04 生成），用户边界第 4 点「本仓库没开 auto_evidence」可能已过时——需要进一步核实。继续读 `wiki_lint.py` 关键实现并核对 sources 实际覆盖。

Tools used before this summary: read_file × 9, search_file × 5, search_content × 4, list_dir × 3, ask_followup_question × 1
</cb_summary>

生成一篇文章说明CODEWIKI-pLUS是如何保证生成的代码WIKI、笔记等知识是准确的，如何做知识保鲜，如何识别知识过期或知识不对，如何更新过时的知识。导入的文档或生成的知识与已有知识冲突如何检测和识别、更新
assistant: 先补齐冲突检测相关机制的核验（这是文章必须覆盖、但前面尚未单独核实的一块），再动笔。
assistant: 冲突检测线索集中在 `note_merge.py`、`note_ingest.py`、`note_consolidation.py`、`wiki_lint.py`。并行读取关键实现。
assistant: 补最后几块证据：`superseded` 状态在检索侧的压制、`batch_set_status` 的状态机、`ingest_source` 的幂等/来源锚定。
assistant: 看 `_update_note_status` 状态机实现，确认 `superseded/deprecated` 语义与 stale_after 续期逻辑的细节。
assistant: 以下是基于仓库源码逐点核验后写成的文章。每处机制都标注了实现位置，可直接当文档用；需要落盘成 `.md` 文件告诉我目标路径即可。

---

# CodeWiki-Plus 知识可信度工程白皮书

> **一句话总结这套系统的立场：工具做确定性簿记，推理与决策永远在调用方与用户手里；证据只驱动复核提醒，永不自动改写。**
>
> 所有"对错"判断分两类：机器只对**可判定的不一致**负责（哈希不匹配、链接失效、状态词非法、复核期过期），语义层面的真假由**证据协议 + 人工双签名**把关。

## 一、知识如何保证准确：五道防线

### 防线 1 · 生成前：事实由静态分析产出，LLM 只负责表述

`analyze_repo` 不靠 LLM 抽取代码事实。它用语法分析器建组件图——Python 走标准库 `ast.parse`，其余语言走 tree-sitter：

```535:535:codewiki/src/be/dependency_analyzer/analyzers/python.py
                tree = ast.parse(self.content)
```
```6:15:codewiki/src/be/dependency_analyzer/analyzers/javascript.py
from tree_sitter import Parser, Language
import tree_sitter_javascript
...
```

组件 ID、代码行区间、依赖边全部来自真实符号表，且支持增量分析（只重解析变更文件，未变组件从缓存复用）。文档写作时，Agent 通过 `read_code_components` 取源码——组件节点只存 `file_path + 行区间`，**内容按需从磁盘现读**（`code_reader.py:18-32`），LLM 看到的永远是当前真实源码而非分析期快照。

同时，代码按 `code_routing` 分级注入，用确定性规则控制喂给 LLM 的代码量，避免上下文压缩导致的臆造：

```596:623:codewiki/src/be/prompt_template.py
        is_boilerplate = file_categories == {"boilerplate"}
        ...
        if is_boilerplate:
            # Abbreviated: signature-only for boilerplate (DTO/VO/Entity/Mapper)
        else:
            # Full source for business/infra components
```

纯数据类文件只给签名（参数表），业务/基础设施文件给全量源码，1-hop 依赖组件只给签名并注明「需全文用 read_code_components」(`prompt_template.py:625-659`)。

### 防线 2 · 生成中：Evidence-Based 断言协议（反幻觉主手段）

系统提示词强制每条业务规则带代码证据引用 + 置信度：

```41:49:codewiki/src/be/prompt_template.py
2. Rules WITHOUT direct code evidence MUST be marked as [candidate] with confidence ≤ 0.5.
3. Format in documentation as a "Business Constraints" section per component:
   - <rule statement> (confidence: 0.85)
     > Evidence: `<code quote>` — <reason>
   - [candidate] <rule statement> (confidence: 0.4)
     > No direct code evidence; requires developer confirmation
4. Do NOT fabricate evidence...
```

`SYSTEM_PROMPT` 与 `LEAF_SYSTEM_PROMPT` 各有一份，主/子模块文档生成同样约束。

### 防线 3 · 落盘即锚定：内容哈希证据

页面写入时，把 `repo://<相对路径>#L<起>-L<止>` 连同代码区间的 **sha256 内容哈希** 一起存进 frontmatter `sources`（`src/evidence.py:24-34`）。三个关键设计：

- **用内容哈希而非 git SHA**——跨分支、rebase、rewrite 都稳定，哈希对的是代码本身而不是提交历史；
- 集中式多仓工作区记录 `repo` 归属字段，配 `evidence_roots` 候选根解析，`repo://` 不会歧义；
- 自动打标是**可选项**（schema `conventions.auto_evidence`，本仓库已开启），挂在 `write_doc_file` 主链路（`doc_writer.py:1504-1510`），单页上限 8 个组件，**永不覆盖已有 `sources`**，失败不致命。

### 防线 4 · 落盘后：`lint_wiki` 一致性审计

近二十项检查（`wiki_lint.py:25-45`）持续扫描知识库，覆盖六类不一致（详见第三节）。

### 防线 5 · 写入确认闸门：机器生成 ≠ 正式知识

新写入的笔记默认 `draft`。只有 `confirm_note`（记录 `verified` 事件：`human:<id>` 或 `codewiki/<version>`，并续期 `stale_after`）才转正为 `stable`；`reject_note` 转 `deprecated`（`note_lifecycle.py:56-118`）。一份可信知识是"机器签名 + 人类签名"双签名的，例如本仓库：

```4:21:repowiki/wiki/modules/MCP_Cache.md
generated: { by: codewiki/5.2.0, at: ... }
status: stable
verified: human:wangbao
stale_after: 2027-02-22
```

## 二、知识保鲜：滚动复核期 + 索引保鲜 + 使用信号

### 1. 每篇知识都有一张"保质期"

`stale_after` 是**滚动的复核截止日**，在写入/确认时激活、每次确认续期。`_check_stale_notes` 明确以 `stale_after` 为判定基准，而不是创建时间（旧实现按 `metadata.date` 平铺阈值，确认笔记不改变陈旧度——已被废弃，见 `wiki_lint.py:1138-1157` 的注释）。

### 2. 判定级联

```1146:1156:codewiki/mcp/tools/wiki_lint.py
Judgment cascade per note (v2, via ``evaluate_note_freshness``):
  - due date = ``stale_after``; fallback when absent =
    ``metadata.date`` + the note's type window (legacy behaviour);
  - due date passed → warning「复核期已过」, unless the note was
    retrieved within ``retrieval_defer_days`` → deferred (activity
    exemption preserved);
  - otherwise fresh.
```

**活动豁免**：笔记若近期仍被检索命中（`last_hit` 来自遥测），说明它还在被使用，复核提醒自动顺延——知识保鲜不是一刀切定时器，而是与真实使用挂钩。

### 3. 索引保鲜，永不阻塞

`index_freshness` 在搜索前做三层新鲜度检查（文件计数 → manifest → mtime 采样 ≤8 文件），检出目录与索引不符（如 `git pull` 合并进来人工确认过的草稿）就自动重建索引 + `index.md`；重建失败则降级用旧索引并标记 `index_stale`。代码注释明示：**self-healing must NEVER break search**。

### 4. 检索反馈闭环

采纳声明（`usage.adopted_count`）给真正被用到的文档加权——采纳权重是单纯召回的 2 倍；长期高频召回却零采纳的笔记被 `low_adoption` 标记为"需要重写得更可操作"。知识保鲜的终点不是删除，是**让知识保持被需要的状态**。

## 三、识别知识过期或不对：机器可检的四类信号

| 信号 | 检查 | 检出什么 | 机制 |
|---|---|---|---|
| **代码证据漂移** | `stale_evidence` | 文档引用的代码与磁盘现实不符 | 重算 `repo://` 区间哈希，逐条判定 `ok / stale / missing / unresolvable`（`src/evidence.py:107-119`），多根场景任一 root `ok` 即通过，多条目时按 `stale > missing > unresolvable` 报最可行动态 |
| **引用失效** | `stale_refs` / `broken_links` / `stale_sources` | wiki 内链目标消失/改名；外部导入源文档变更或撤回（`retract_source`） | 锚点映射比对；来源注册表（`source_registry.json`）跟踪 |
| **结构漂移** | `overview_stale` / `isolated_components` / `coverage` | 架构文档 vs 当前模块图不一致 | 模块树比对 |
| **声明缺证据** | `unsupported_claims` | 高置信度断言却没有 `Evidence:` 行 | 只扫带 `(confidence: x.xx)` 的规则行（`wiki_lint.py:961`），检查其后 2 行内是否有证据行 |
| **复核期到期** | `stale_notes` / `scenario_orphan` | 知识超期未复核；场景块长期无溯源无检索 | `stale_after` + 遥测 `last_hit` |
| **生命周期异常** | `superseded_pages` / `okf_conformance` | 被替换页面未归档；`status` 词非法 / 缺 `verified` / `stale_after` 已过期 | 状态机词汇表校验 |

**必须诚实标注的能力边界**：`unsupported_claims` 只做**格式邻近性**检查——"有 Evidence 行"不等于"引用真实支撑断言"。断言语义真假由防线 2 的证据协议约束、防线 5 的人工确认把关。机器不做语义裁判。

## 四、更新过时知识：提醒 → 人工裁决 → 确定性记账

`lint_wiki` 的每一个 issue 都带 `file / severity / message / suggestion`，但它**永不自动改写**——`stale_evidence` 的文档字符串明示「never rewrites content」，证据驱动的是人工复核提醒。更新出口有三条，全部由人决定：

1. **文档没跟上代码**（`stale_evidence` → `stale`）：人工基于 `read_code_components` 读当前真实源码 → 更新文档 → 重新 `stamp_evidence` 打上新哈希（哈希更新是显式动作，自动打标不覆盖已有 `sources`，避免静默改写证据）。
2. **知识不再适用 / 有新版本**：把旧文档标记 `status: superseded`（或 `deprecated`）+ `superseded_by: <新文档>` 显式指向新家。旧知识不会消失但会**退居二线**：检索侧读到 `superseded/deprecated` 直接把相关性砍半并附上 `superseded_by`（`note_query.py:1018-1044`），`lint` 的 `superseded_pages` 提醒归档清理。
3. **草稿待复核**：`confirm_note` 转正并续期，`reject_note` 转 `deprecated`。

每一次状态迁移都 append `verified` 事件（带确认人身份），审计链完整。批量场景用 `batch_set_status`（仅允许 `stable/deprecated`，支持 dry-run，`note_lifecycle.py:171-290`）。

## 五、冲突检测与消解：导入的知识撞上已有知识怎么办

冲突不是靠一次"查重"解决的，而是一整套**检出-标注-排序-消解**流程：

### 1. 导入去重（幂等，防噪音）

`ingest_note` 写盘前检查同名笔记：正文**完全相同** → 直接返回 `already_exists` 拒收，不产生噪音副本；正文**不同但撞了 slug** → 加 sha1 哈希后缀另存新文件（`note_ingest.py:301-317`），两条知识先共存，把"谁对"交给下游合并或人工。

### 2. 同主题草稿冗余 → 字段级预合并

`note_merge` 把同主题多条 draft 按字段策略预合并为**一条 draft**：标题/元信息取最新（`replace`），正文按树龄升序拼接并逐段带「合并自 `rel`」来源标记（`append`），tags 取并集（`union`），策略按笔记类型从权威表 `merge_fields_for` 读取（`note_merge.py:78-185`）。合并产物**仍是 draft**，过 `confirm_note` 闸门才转正；被合并的原稿由调用方在确认后标记 `superseded`——合并永远可追溯、永不绕过确认。

### 3. 同源会话重复捕获 → supersede 替换

`capture_conversation` 对同一 `source_session_id` 的重复捕获走 supersede 语义**替换旧 raw**（`repowiki/raw/` 不堆积），再配合第 1 节的幂等，同一段对话/文档反复导入不会产生知识副本。

### 4. 导入文档 vs 已有页面 → 来源锚定 + 变更跟踪

`ingest_source` 把外部文档复制进 `raw/sources/` 并在 `source_registry.json` 注册；若它关联了已有 wiki 页，则在页面 frontmatter 注入 `source_ref(s)` 与 OKF `sources` 条目（`source_ingest.py:173-247`）。此后页面与外部来源形成**可审计的引用关系**：来源文档一变更或撤回，`stale_sources` / `retract_source` 立即报警——"导入内容与页面说法冲突"被提前变成"你引用的源已经变了"。

### 5. 新旧知识语义冲突 → 显式替代，检索压制

第 4 节描述过：`superseded_by` 显式指认替代关系，检索降权 50% 并展示新家链接。冲突不是同时把两条真相摆给查询者，而是**让旧版本退位、给新版本让路**。

### 6. 散乱笔记 vs 场景沉淀 → UPDATE 优先

`consolidate_notes`（L2）把碎片化确认笔记整合进 `wiki/scenarios/` 场景块时，强制策略是：**默认 UPDATE 不是 CREATE**；CREATE 前必须至少读 2 个最相似场景文件、确认新知识确实无处安放（`note_consolidation.py:56-60`）；容量上限 ≤15，产出去重（`created/updated/merged/deleted` 白名单动作）。

### 7. 最终裁判永远是人

所有"消解"工具的共性约束（`note_merge.py:6-8`、`note_consolidation.py:24-26`）：**合并产物一律 draft、须过确认闸门；原稿的退役由人显式调用，工具不自行改写或删除任何知识**。

## 六、一句话总结这套信任模型

> 静态分析给事实、证据协议约束表述、内容哈希钉住引用、lint 检出漂移、状态机管生命周期、遥测驱动保鲜与排序、人类双签名放行——CodeWiki-Plus 保证的不是"知识永远不会错"，而是**错的代价最低**：任何一条知识的代码出处、生成者、确认者、复核截止日、被谁取代都可查；任何过时或冲突都会在检索和复核提醒中被标记出来，而改写和定论的权利始终留在人手里。

---

文章中的机制均核验自当前 `develop` 分支源码。如需落盘为仓库文档，告诉我路径（例如 `docs/` 或 `repowiki/wiki/`），我可以按仓库页面规范生成 frontmatter 后写入。
user: <cb_summary>
This session is being continued from a previous conversation that was compacted to stay within the model context window.
Messages after this summary (if any) are the original recent turns. Tool results from before this summary were omitted.
If you need exact code, command output, or file contents from before compaction, re-read those files. Do not treat omitted tool bodies as still in context.

Earlier user requests:
- 生成一篇文章说明CODEWIKI-pLUS是如何保证生成的代码WIKI、笔记等知识是准确的，如何做知识保鲜，如何识别知识过期或知识不对，如何更新过时的知识。导入的文档或生成的知识与已有知识冲突如何检测和识别、更新

Earlier assistant notes (truncated):
- 先补齐冲突检测相关机制的核验（这是文章必须覆盖、但前面尚未单独核实的一块），再动笔。
- 冲突检测线索集中在 `note_merge.py`、`note_ingest.py`、`note_consolidation.py`、`wiki_lint.py`。并行读取关键实现。

Tools used before this summary: search_content × 4, read_file × 3
</cb_summary>

放到dOCS/aRTICLES目录，我要用来发公众号
assistant: `docs/articles/` 已存在。看看现有文章的风格（命名、是否带 frontmatter），好对齐格式。
assistant: 看一下现有系列文章的风格与命名（标题、frontmatter、公众号排版习惯），对齐格式。
assistant: 风格确认：系列文章、无 frontmatter、`> 导语` 引用块开头。系列最大编号是 10，这篇作为系列 11 落盘。原文偏工程引证（大段 `file:line` 引用块），公众号不适合，我会按系列风格重写成可读文本，保留技术术语的准确度。
assistant: 已写入 `docs/articles/CodeWiki-Plus系列11：机器写的Wiki凭什么可信——证据、保鲜与冲突消解.md`

针对公众号场景做的调整：

1. **编号续上系列**：`docs/articles/` 现有系列 2–10，这篇作为**系列 11**，文件名与标题一致。
2. **去掉源码引用块**：上一条回复里大量 ``file:line`` 式代码引证改为叙述化表达（术语仍准确：`stale_after`、`repo://`、`superseded_by`、`[candidate]` 等保留）。
3. **沿用系列排版惯例**：`> 导语` 引用块开篇承上启下，正文分节（引子 → 生成/落盘/确认闸门/保鲜/检出/冲突 → 结尾），用表格盘点 lint 信号。
4. **核心立场贯穿**：导语与结尾都点明"工具做确定性簿记，推理与决策永远在人手里；证据只驱动复核提醒，永不自动改写"。
5. **补了一段诚实边界**（第五节末）：机器只检"可判定不一致"，语义对错由人裁决——这类话术公众号读者很买账，也符合源码实际。

需要我调整标题（比如想要更"公众号爆款"的标题）、压缩到 3000 字左右的短版，或者导出成 `.docx` 方便粘贴排版，说一声即可。
user: 在放个文档到DOCS目录下，保留源码引用块，这个文档偏技术，给开发者和智能体阅读
assistant: 我先重新读取相关源码以确保引用块准确（前一轮的核验内容已被压缩丢失）。先定位关键实现文件。
assistant: 这是一篇偏技术的深度文档，需要准确的源码引用。我先并行读取核心实现文件来确认行号与行为。
