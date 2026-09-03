# claude-mem 借鉴详细设计方案（P0 三项 + P1 一项）

> 来源：`docs/claude-mem-调研与借鉴分析.md`（2026-09-02，源码级调研，claude-mem v13.23.1 @ `f92996e`）
> 日期：2026-09-02 · Rev.2（拷问评审定稿，15 项裁决）· 2026-09-03 补 §十（P1/P2 遗留项评估结论）· 状态：**评审定稿** · 预计工作量：**3 人日**（P0-1 → P0-2 含 P1-4 → P0-3 收尾）
> 范围约束：
> - **不新增 MCP 工具**（沿用 `query_wiki` 现有参数面扩展）；
> - **不改评审闸门哲学**（`confirm_note` / `reject_note` 保留，ADR-0002 不变）；
> - **不改 Markdown 存储路线**（不迁 SQLite，结构化字段一律可选、缺失静默降级，不破坏既有 frontmatter 读取兼容性；往返不变量尚无实现，见 §2.6 前置缺口）；
> - **不引入新依赖**（无 tokenizer、无向量库、无常驻进程）；
> - 与已落地的新鲜度专项（F1/F2/F3）、检索透明化（T1）、使用热度（U1）互补不冲突。

> **Rev.2 变更摘要**（2026-09-02 拷问评审，15 项裁决全部定案）：实施顺序改为 P0-1 → P0-2（含 P1-4）→ P0-3 收尾；`advice` 字段统一为 `hint` 家族；P1-4 判据由 mtime 改为 **git 最后提交时间**（ADR-0003）；by_file 仅覆盖 notes、含 draft、query 为硬过滤、不写 usage heat 只写 telemetry；est_tokens 统一语义为"全篇展开成本"、不进 check 输出；新增遥测基线前置项（§6.4）；引用行号按源码逐项校正。

---

## 零、总览

### 0.1 要解决的两个真实缺陷

调研中实测本仓库语料：`notes/` 112 篇（平均 1,335 字符）、`wiki/` 51 篇（平均 5,410 字符，最大 27,534）、`raw/` 8 篇。在此规模上发现两个已存在的缺陷：

**缺陷一：注入预算与展开预算口径断裂**

```python
# wiki_search.py:626 —— snippet 截断到 300 字符
"snippet": (_extract_snippet(...))[:300],

# injection_budget.py:30 —— 总预算 1200 字符
_DEFAULT_BUDGET = {"search_result_chars": 1200, ...}
```

1200 ÷ 300 = **4 条**。默认 `max_results=10` 时，**后 6 条全部降级为单行指针**（`injection_budget.py:86-103`）。Agent 拿到 10 条里有 6 条是空壳，自然会转向 `expand=True`。

而 `expand` 走的是**完全不受该预算约束**的独立通道（`knowledge_loop.py:1725`）：

```python
max_chars = min(20000, max(500, int(arguments.get("max_chars", 3000))))
```

最坏情况 `expand=True, max_results=10, max_chars=20000` = 20 万字符 ≈ **5 万 tokens**，单次调用吃掉大半个上下文窗口。系统在前门严格控 1200 字符，后门敞开 20000 倍。

**缺陷二：无"这个文件有没有历史知识"的出口**

笔记 frontmatter 已有 `metadata.related_modules`（实测样本：`metadata.related_modules: [mcp, prompt_server]`），但**没有按文件维度反向检索的路径**。Agent 改 `codewiki/mcp/tools/wiki_search.py` 之前，无法得知"这个文件有 3 条历史决策笔记"。

### 0.2 项与依赖

| 编号 | 项 | 解决什么 | 工作量 | 依赖 |
|------|-----|---------|--------|------|
| **P0-1** | 检索成本可见性（`est_tokens`） | 缺陷一 | 0.5–1 人日 | 无 |
| **P0-2** | `by_file` 文件知识检索 | 缺陷二 | 1.5–2 人日 | 无 |
| **P0-3** | 工作流内建工具描述 | 让 `mode=check` 等已有设计真正被使用 | 0.2 人日 | 无 |
| **P1-4** | 对端新鲜度（git 提交时间判定，ADR-0003） | 消除 `stale_after` 的假阳性/假阴性 | 0.5 人日 | 随 P0-2 落地（共用文件映射） |
| ~~P1-2~~ | 笔记 `files` 结构化字段 | 提升 P0-2 匹配精度 | 0.5 人日 | **数据触发的条件项**（前置含 frontmatter writer，实估 1+ 人日），见 §10.1 |
| ~~P1-3~~ | 折叠视图（smart_outline 等价物） | 填补索引与全文之间的空档 | 3–4 人日 | **压置**（证据触发再议），见 §10.1 |

P1/P2 其余遗留项（P1-1/P1-5/P2-1'/P2-2/P2-3）的评估结论见 §十。

**实施顺序（Rev.2 定案）**：P0-1 → P0-2（含 P1-4）→ P0-3 收尾。理由：P0-3 要改写的 description 引用 `by_file` 与 `est_tokens`，必须等能力落地后一次写成——描述不存在的能力等于契约坏账。

### 0.3 借鉴来源与代码依据

| 本方案项 | claude-mem 源码依据 | 本方案对其的改造 |
|---------|-------------------|----------------|
| `est_tokens` | `src/shared/timeline-formatting.ts:74-77`（`Math.ceil(text.length/4)`）；`SearchManager.ts:229`（只估 `obs.narrative`） | 口径一致，但**扩展到响应级成本提示**（claude-mem 无此层） |
| `by_file` | `/api/observations/by-file`；特异性排序 `file-context.ts:69-86`（+2/+2/+1） | 保留排序思想；**去掉"拦截"外壳**（v13 已改 `permissionDecision: 'allow'`） |
| 对端新鲜度 | `file-context.ts:255-265`（`fileMtimeMs >= newestObservationMs → return null`） | 从"跳过注入"改为"标注可能过期"；**判据由 mtime 换为 git 最后提交时间**（ADR-0003，clone 场景 mtime 全量假阳性） |
| 工作流内建 | `mcp-server.ts:439-445`（`important_workflow` 永远可见） | 不新增工具，改写 `query_wiki` 的 description |

---

## 一、P0-1：检索成本可见性

### 1.1 设计目标

让 Agent 在**决定展开之前**就知道每条要花多少 token，把 `expand` 从"盲猜"变成"有预算的决策"。

### 1.2 估算口径

沿用 claude-mem 的实测口径，不引 tokenizer：

```python
def estimate_tokens(char_count: int, chars_per_token: int = 4) -> int:
    """Approximate LLM token count from character count.

    Calibrated for the mixed zh/en corpus this project targets: zh ~1.5
    tokens/char in real tokenizers, en ~0.25 — /4 sits close enough for a
    *decision hint* and is never used for billing or hard truncation.
    """
    if char_count <= 0:
        return 0
    return max(1, math.ceil(char_count / chars_per_token))
```

**为什么不用索引里已有的 `doc_len`**：`wiki_search.py:151` 的 `doc_len` 是 **jieba 分词后的词数**，与 LLM token 不同源（中文一词常对应 1–2 个 LLM token），且不含 frontmatter。用字符数 /4 口径更统一、与 `injection_budget.py` 的 `len()` 预算同构。

**为什么能零额外 IO**：两条检索路径为了抽 snippet 都**已经读了全文**——

- JSON fallback：`wiki_search.py:623` `(od / fk).read_text(...)`
- SQLite 主路径：`cache.py:2056` `_extract_snippet(raw, qts)[:300]`（其 `raw` 即全文）

因此只需在组装 entry 时顺手取 `len(raw)`。

**est_tokens 的统一语义（Rev.2 定案）**：无论出现在非 expand 检索结果还是 expand 结果中，`est_tokens` 一律表示**该篇全文的估算成本**（"展开这条要花多少"），不是"本次返回已花费"；expand 结果另以 `content_tokens` 表达实际返回量。字段名不随层级变化——一名一义，语义写进工具 description（"est_tokens = estimated cost of expanding that result in full"）。

### 1.3 改动点（精确位置）

**(1) `codewiki/mcp/tools/injection_budget.py`** —— 新增两个函数（该文件已负责"注入成本"语义，且 `knowledge_loop.py:2008` 已 import 它）：

```python
_DEFAULT_RETRIEVAL_COST = {
    "enabled": 1,
    "chars_per_token": 4,
    "expand_hint": 1,
}

def load_retrieval_cost(schema: Optional[dict]) -> Dict[str, int]:
    """Resolve retrieval-cost config (defaults → schema overrides)."""
    # 与 load_budget() 同构：conventions.retrieval_cost 覆盖默认值

def estimate_tokens(char_count: int, chars_per_token: int = 4) -> int:
    ...
```

**(2) `codewiki/mcp/tools/wiki_search.py:614-632`** —— JSON fallback 路径的 `out` 组装，entry 增加：

```python
out.append({
    "file": fk,
    "title": ...,
    "source": ...,
    "snippet": ...,
    "relevance_score": round(s, 4),
    "authority": round(auth, 2),
    "est_tokens": estimate_tokens(len(raw)),   # ← 新增
    "matched_tokens": ...,
    "usage": {...},
})
```

**(3) `codewiki/mcp/cache.py:2060-2073`** —— SQLite 主路径 entry，同样增加 `est_tokens`。
**(4) `codewiki/mcp/cache.py:2113-2129`** —— hop 图扩展 entry，同样增加（保证 hop>0 时字段不缺失，避免调用方 KeyError）。

> **实施注意**：`cache.py` 的 `search()` 需从调用方接收 `chars_per_token`。建议沿用既有模式——在 `wiki_search.search()` 里解析一次配置后透传，保持 `cache.py` 的 `search()` 签名新增一个可选关键字参数（`chars_per_token: int = 4`），默认值保证既有调用方（`distill` 去重召回等）行为不变。

**(5) `codewiki/mcp/tools/knowledge_loop.py:1834-1845`** —— expand 分支，增加 `content_tokens`（实际返回量，区别于 `est_tokens` 的全量估算）：

```python
if expand:
    full_text = file_path.read_text(...)
    entry["content"] = full_text[:max_chars].strip()
    entry["est_tokens"] = estimate_tokens(len(full_text))        # 全篇成本
    entry["content_tokens"] = estimate_tokens(len(entry["content"]))  # 本次实际返回
    if len(full_text) > max_chars:
        entry["content_truncated"] = True
        entry["content_budget"] = max_chars
```

**(6) `codewiki/mcp/tools/knowledge_loop.py:2017-2039`** —— 响应级成本提示（**claude-mem 没有这一层，是本方案的增强**）：

```python
**({"cost_hint": cost_hint} if cost_hint else {}),
```

`cost_hint` 结构：

```json
{
  "index_tokens": 812,
  "expand_all_tokens": 4820,
  "top3_tokens": 2100,
  "hint": "索引已返回 10 条（约 812 tokens）。展开前 3 条约 2100 tokens，全部展开约 4820 tokens。建议先按 est_tokens 挑最相关的再 expand。"
}
```

### 1.4 配置

`schema.yaml`（整体缺失走代码默认，不影响任何现有行为）：

```yaml
conventions:
  retrieval_cost:
    enabled: true          # false = 关闭，回到 legacy（结果无 est_tokens 字段）
    chars_per_token: 4     # 换算系数；中英混合语料的经验值
    expand_hint: true      # 是否在响应里给 cost_hint
```

### 1.5 兼容性核对

| 消费方 | 影响 |
|--------|------|
| `distill_conversation` 的去重召回（走 `search()` 且 `apply_authority=False`） | 新增字段，不读取 → 无影响 |
| `wiki_stats` / `telemetry` | 不读取结果条目 → 无影响 |
| `low_adoption` / `promotion` lint 检查 | 不读取 → 无影响 |
| 前端 WebApp | 不消费 query_wiki 结果 → 无影响 |
| 既有测试断言精确字段集 | 已核查（Rev.2）：默认检索结果条目**顶层字段集无精确断言**；有精确断言的是 usage 子字典（`test_query_transparency.py:230`、`test_usage_ranking.py:365`）与 check 模式条目（`test_query_transparency.py:86`）。est_tokens 不进 check 输出（见 §9），后者不受影响 |

---

## 二、P0-2：`by_file` 文件知识检索

### 2.1 设计目标

Agent 在读取/修改某个文件之前，能查到"这个文件有哪些历史知识"，并据此决定：够用了就不读全文、需要细节再展开。

### 2.2 接口设计

**参数**：新增 `by_file`（string，目标文件路径，相对 repo 根或绝对均可）。

**为什么不是新增 `mode="by_file"`**：`mode` 在现有代码里是**互斥的早返回分支**（`knowledge_loop.py:1749-1764`），而 `by_file` 是**过滤维度**，语义上应与 `scope` / `type_filter` 并列。且它可与默认 BM25 检索共存（`by_file` + `query` 同时给 → 在该文件的知识范围内做关键词过滤）。

**`required` 调整**（`registry.py:1162` 与 `knowledge_loop.py:1711`）：

```python
# 现状
if not query and mode not in ("overview", "directory", "detail"):
    return json.dumps({"error": "query is required."})

# 改为
if not query and not by_file and mode not in ("overview", "directory", "detail"):
    return json.dumps({"error": "query is required (or pass by_file)."})
```

**硬前提（Rev.2 核实）**：`registry.py:1162` 的 `"required": ["query"]` 是 **MCP 层 schema 校验，先于 handler 执行**——必须同步将 required 改为 `[]`（query 转可选），否则仅传 `by_file` 在 MCP 层就被拒绝，handler 的放宽形同虚设。勿效仿 `repo_path` / `origin_filter` 的 schema 未声明先例。

### 2.3 匹配逻辑（核心设计）

**覆盖范围（Rev.2 定案）：v1 仅覆盖 `notes/`，不含 `wiki/` 生成页。** by_file 回答的是"这个文件有哪些历史经验知识（决策/教训）"；生成页是机器对代码的结构描述，`read_code_components` 与默认 BM25 检索已覆盖该需求。混入时间线会稀释特异性排序的信噪比。

**v1 采用"路径段 → 模块名"映射，不新增索引。**

实测笔记 frontmatter 结构（`repowiki/notes/2026-08-03-*.md`）：

```yaml
metadata:
  date: 2026-08-03
  related_modules:
  - mcp
  - prompt_server
  related_components: []
  source_ref: ...
```

映射算法（`_query_mode_by_file` 内）：

```
1. 规范化目标路径：绝对路径 → 相对 repo 根；分隔符统一为 '/'
2. 提取路径段集合：
   codewiki/mcp/tools/wiki_search.py
   → {"codewiki", "mcp", "tools", "wiki_search.py", "wiki_search"}
3. 对每个候选笔记，读取 metadata.related_modules（列表）
4. 命中判定：模块名 ∈ 路径段集合
   related_modules: [mcp] 命中 "mcp" 段 → 匹配
5. 组件级：related_components 与路径段取交集（更高精度）
```

**为什么不用 `module_tree.json` 做精确映射**：`module_tree.json` 的 `components` 字段是**组件 ID 列表**（见 `knowledge_loop.py:2617-2626` 的 `_walk` 只读 `info.get("components", [])`），不含 `file_path`；要拿到"文件 → 组件 ID"需要再加载 `symbol_map.json`（`_load_symbol_map`，`knowledge_loop.py:183-221`），引入额外依赖与失败面。**路径段匹配虽然粗，但零依赖、零索引、覆盖 90% 场景**，且粗粒度在此处反而是优点——"mcp 目录下的文件"匹配"mcp 模块的知识"正是想要的语义。

### 2.4 特异性排序（移植 claude-mem `file-context.ts:69-86`）

```python
def _specificity(note_fm: dict, path_segments: set, target_path: str) -> int:
    score = 0
    mods = set(note_fm.get("metadata", {}).get("related_modules") or [])
    comps = set(note_fm.get("metadata", {}).get("related_components") or [])
    files = set(note_fm.get("metadata", {}).get("files") or [])   # v1.5 可选字段

    if target_path in files:
        score += 3          # 精确命中（v1.5，需 P1-2 落地）
    if comps & path_segments:
        score += 2          # 组件级命中
    elif mods & path_segments:
        score += 1          # 模块级命中
    return score
```

claude-mem 原始规则是"文件被修改 +2 / 覆盖 ≤3 文件 +2 / ≤8 文件 +1"。**本方案改为按命中粒度分级**，原因：claude-mem 的 observation 有 `files_modified` 全量字段可算"覆盖文件数"，CodeWiki 笔记的 `related_modules` 不表达这个维度，硬套会失真。**保留其"越具体越靠前"的思想，替换其实现依据。**

**排序主键（Rev.2 定案）**：纯 `by_file` 时按 (specificity, date) 降序。实测 `related_components` 稀疏（抽查一篇 `[]`、一篇缺失），组件级 +2 在 v1 近乎死分支，但保留——零维护成本，且对 P1-2 `files` 字段前向兼容。

### 2.5 输出格式

对标 claude-mem 的时间线形态（`file-context.ts:118-134`），但适配 Markdown 笔记：

```json
{
  "query": "",
  "by_file": "codewiki/mcp/tools/wiki_search.py",
  "matched_modules": ["mcp"],
  "file_knowledge": {
    "total": 7,
    "returned": 5,
    "total_est_tokens": 1670,
    "timeline": [
      {
        "date": "2026-08-21",
        "file": "notes/2026-08-21-检索透明化.md",
        "title": "检索透明化：matched_tokens 与 query_coverage",
        "type": "decision",
        "status": "stable",
        "est_tokens": 334,
        "specificity": 1,
        "possibly_stale": false
      }
    ]
  },
  "hint": "该文件有 7 条历史知识（约 1670 tokens）。已按特异性返回前 5 条。够用即可开始；需要细节用 mode=detail 取单篇全文。"
}
```

**只给标题 + 成本 + 状态，不给正文** —— 这是渐进式披露的第 1 层，与现有 `mode=check` 的"只给标题不给 snippet"一脉相承。

**Rev.2 定案的三条输出语义**：

1. **命名**：顶层提示字段为 `hint`（原草案 `advice` 已废弃）——与既有 `aggregation_hint` 家族对齐，同一响应体系内不造近义新词。
2. **draft 口径**：时间线**含 draft 笔记**、`status` 如实显示，与默认 BM25 检索口径一致（draft 仅权威降权 -0.25，不过滤）——两个入口两种过滤策略会迫使 Agent 多记一条例外规则。
3. **信号纪律**：by_file 是读文件前的预检，**不写 usage heat**（与 `mode=check` 同纪律，防预检稀释深度消费信号），但**写 telemetry retrieval_stats**——验收 #8 需要 by_file 采纳率数据；两条管道各走各的。

**`by_file` + `query` 组合（Rev.2 定案）**：query 为**硬过滤**（不含关键词的条目直接出局），排序仍按 (specificity, date)。组合场景的调用意图是"收窄这个文件的知识范围"而非全局检索，specificity 是 by_file 的立身之本，不做 BM25 融合加权。

### 2.6 v1.5 可选增强：笔记 `files` 字段

若需要精确匹配（路径段匹配会把 `codewiki/mcp/` 下所有文件都算作 `mcp` 模块），在 `ingest_note` 的 frontmatter 写入中增加可选字段：

```yaml
metadata:
  related_modules: [mcp]
  files:                                    # 可选，v1 缺失时自动降级到模块级匹配
  - codewiki/mcp/tools/wiki_search.py
```

**硬约束**：必须可选、缺失时静默降级（不得报错）。**前置缺口（Rev.2 核实）**：`codewiki/src/frontmatter.py` 目前**只有读路径**（`parse_frontmatter` / `format_frontmatter_value`），无 render 序列化 writer——P1-2 落地前须先补 writer 并建立 `parse(render(x)) == x` 往返测试（详见 CONTEXT.md「frontmatter module」词条）。实施前先跑 `tests/okf_regression_test.py`。

### 2.7 配置

```yaml
conventions:
  file_knowledge:
    enabled: true
    max_results: 15          # 时间线条数上限（对齐 claude-mem 的 DISPLAY_LIMIT）
    stale_check: true        # 是否启用对端新鲜度标注（P1-4，git 提交时间判据，见 ADR-0003）
    min_module_depth: 1      # 路径段匹配时忽略的顶层段数（repo 名通常无语义）
```

---

## 三、P1-4：对端新鲜度（git 提交时间判定，ADR-0003）

### 3.1 与现有 `stale_after` 的关系

| | 现有 `stale_after` | 本项（git 提交时间判定，ADR-0003） |
|---|---|---|
| 判据 | 笔记**创建时间 + 类型窗口** | **被描述文件的最后一次 git 提交** vs 笔记时间 |
| 语义 | "这条笔记多大了" | "这条笔记描述的对象变没变" |
| 假阳性 | 3 个月前的笔记，文件没动过 → 误判过期 | 无 |
| 假阴性 | 昨天的笔记，文件今早重构 → 仍被注入 | 无 |

**两者互补，不替换**：`stale_after` 继续管"笔记是否该复核"，`possibly_stale` 标注管"这条知识对当前文件是否仍然成立"。

### 3.2 设计（Rev.2：判据改为 git 最后提交时间，ADR-0003）

```python
def _file_staleness(note_date: str, target_path: Path, buffer_days: int = 1) -> Optional[bool]:
    """True = 目标文件在笔记之后有过代码提交，知识可能已过期。"""
    try:
        note_dt = datetime.fromisoformat(note_date)
        commit_dt = _last_commit_time(target_path)   # git log -1 --format=%cI -- <path>
        if commit_dt is None:
            return None
        return commit_dt > note_dt + timedelta(days=buffer_days)
    except (OSError, ValueError):
        return None      # 拿不到就不知道，不猜
```

输出为 `possibly_stale: true|false|null`。**null 不是失败**——文件未被 git 跟踪、git 不可用、笔记无日期时，诚实返回"不知道"，比猜测更安全。

### 3.3 实施要点

- **笔记日期来源**：frontmatter 的 `metadata.date`（实测样本有）。缺失时回退到 `generated.at`，再缺失则 `null`。
- **mtime 判据已否决（ADR-0003）**：git clone 出来的工作树所有文件 mtime 均为 clone 时刻，比任何上月笔记都新一个多月——全量假阳性，原方案的 1 天缓冲治的是边界噪声不是量级差。假阳性率高的标注会被 Agent 学会忽略，还连坐损害 `stale_after` 攒下的新鲜度语义信誉。
- **未提交改动的假阴性**：工作树有未提交改动时"最后一次提交"早于实际修改，可能漏标。保守方向可接受——把不确定的知识当新鲜，比把好知识全标过期的破坏性小。
- **成本**：每次 by_file 查询对命中条目（≤ `max_results=15`）各一次 `git log -1` 子进程调用，仅在 by_file 路径发生，不进默认检索热路径。

---

## 四、P0-3：工作流内建工具描述

### 4.1 问题

`mode=check` 是一个精心设计但**大概率没被使用**的分支。其注释明确写了价值（`knowledge_loop.py:1750-1764` 一带）：

> Lightweight relevance pre-check: top score + titles only, no snippets, **no retrieval-stats recording (a pre-check is not a real consumption event and must not pollute usage/heat signals)**.

但 `registry.py:1135-1148` 的 description 里，它只是四个 enum 值里的一句话。Agent 不知道它的存在，于是用默认检索当预检 → **真实检索的 usage 信号被预检稀释** → 排序质量下降。

同理，48 个工具的 Agent 不会主动发现 `expand` 的成本风险。

### 4.2 改动

改写 `registry.py:1030-1042` 的 `query_wiki` description，把三层策略更新为四层，并显式点出成本与信号纪律。**以下为 Rev.2 定稿文案，实施时逐字使用**：

```
Search across generated documentation and ingested notes.

RETRIEVAL STRATEGY (cheapest first):
1) mode=check — titles only, no snippets. Use FIRST to decide whether a full
   search is worth the tokens. Does NOT pollute usage/heat ranking signals.
2) BM25 search (default) — returns snippets + est_tokens per result.
   est_tokens = estimated cost of expanding that result in full.
3) by_file=<path> — file-scoped knowledge timeline (ingested notes only):
   titles + est_tokens + status, no bodies, sorted by specificity. Check it
   before reading or editing a file to surface prior decisions and lessons.
   Add query=<keyword> to hard-filter within that file's knowledge.
4) expand=true — full page content (up to max_chars, default 3000, max 20000).
   LAST RESORT. Check est_tokens first: 10 results at max_chars=20000 is ~50k
   tokens. Prefer expanding only the 2-3 results you actually need.

Supports filtering by page type (type_filter), scope, repo (centralized layout),
and task_id. Graph expansion (hop=1-3) follows wikilinks with 0.5x decay per hop.
Best for: why decisions were made, lessons learned, architecture rationale.
For code implementation details (function signatures, call chains), use grep instead.
```

同步更新 `expand` / `max_chars` / `check` / 新增 `by_file` 各自的参数 description。

### 4.3 为什么值得单独做（0.2 人日）

这是**让已有设计真正生效的最低成本手段**。CodeWiki 的 `usage` heat 排序（U1）、`check` 模式的信号隔离，都是已投入实现成本但依赖 Agent 自觉才能生效的设计。工具描述是唯一"调用时强制可见"的通道。

---

## 五、P1-3：折叠视图（单独排期）

### 5.1 借鉴点

claude-mem 的 `smart_outline` / `smart_unfold`（`src/services/smart-file-read/parser.ts`，tree-sitter 27 语言）提供"符号签名 + 行号、函数体折叠、带 token 估算"的中间层，填补索引与全文之间的空档。

### 5.2 CodeWiki 的先天优势

CodeWiki **已有 tree-sitter 依赖分析与符号表**（`DependencyAnalyzer`，10 语言），缺的只是"折叠视图"这个消费形态。

### 5.3 设计草案（不在本次实施范围）

- 新模块 `codewiki/mcp/tools/code_outline.py`，复用 `codewiki/src/be/dependency_analyzer/` 的解析结果；
- 输出形态（`CodeSymbol` 对标 claude-mem）：`{name, kind, signature, line_start, line_end, parent, children, token_estimate}`；
- 接入方式二选一，需评审决定：
  - **方案 A**：新增 MCP 工具 `read_code_outline`（缺点：工具数 48 → 49，与"不新增工具"约束冲突）；
  - **方案 B**：作为 `query_wiki` 的 `mode="outline"`（缺点：`query_wiki` 职责扩散）；
  - **倾向方案 C**：作为 `read_code_components` 的 `format="outline"` 参数扩展——复用既有工具，不增工具数，语义自洽。
- 工作量 3–4 人日，含语言覆盖测试。

---

## 六、测试计划

### 6.1 新增测试文件

`tests/test_claude_mem_borrowings.py`（命名对齐既有 `test_openviking_borrowings.py`）。

### 6.2 用例清单

**P0-1（约 12 项）**
| # | 用例 | 断言 |
|---|------|------|
| 1 | `estimate_tokens(0)` / 负数 | 返回 0 |
| 2 | `estimate_tokens(1000)` | 250 |
| 3 | 中文字符（len 按字符不按字节） | 与 `len(text)/4` 一致，非 UTF-8 字节数 |
| 4 | JSON fallback 路径结果含 `est_tokens` | 字段存在且 > 0 |
| 5 | SQLite 主路径结果含 `est_tokens` | 字段存在且 > 0 |
| 6 | `hop=2` 时扩展结果也含 `est_tokens` | 无 KeyError（`cache.py:2113-2129` 改动验证） |
| 7 | `expand=true` 时同时含 `est_tokens` 与 `content_tokens` | 两者存在；后者 ≤ 前者 |
| 8 | `content_truncated=true` 时 `content_tokens < est_tokens` | 严格小于 |
| 9 | `retrieval_cost.enabled=false` | 结果无 `est_tokens`，其余字段不变 |
| 10 | `chars_per_token=2` 配置生效 | token 数翻倍 |
| 11 | `cost_hint.expand_all_tokens` = 各条 `est_tokens` 之和 | 数值一致 |
| 12 | 既有断言字段集的测试全部通过（回归） | 无 KeyError / 无字段集不匹配 |

**P0-2（约 14 项）**
| # | 用例 | 断言 |
|---|------|------|
| 13 | `by_file` 命中含 `mcp` 段的笔记 | 返回非空 |
| 14 | 目标文件无相关知识 | `total=0`，`timeline` 为空数组（非 error） |
| 15 | 路径分隔符 `\` 与 `/` 等价 | 结果一致 |
| 16 | 绝对路径与相对路径等价 | 结果一致 |
| 17 | 特异性排序：组件级命中排在模块级之前 | 顺序正确 |
| 18 | `max_results` 截断生效 | 条数符合配置 |
| 19 | `by_file` + `query` 组合 | 范围内再做关键词过滤 |
| 20 | 仅 `by_file` 无 `query` | 不报 "query is required" |
| 21 | `by_file` 缺失且 `query` 缺失且 `mode` 为空 | 仍报 "query is required" |
| 22 | v1.5 `files` 字段精确命中 | specificity 得 3 分 |
| 23 | 笔记无 `metadata.related_modules` | 静默跳过，不抛异常 |
| 24 | 笔记 frontmatter 损坏 | 跳过该文件，不影响其他 |
| 25 | `file_knowledge.enabled=false` | 退回 legacy 行为 |
| 26 | 时间线输出不含正文（只标题+成本） | 无 `content` / `snippet` 字段 |

**P1-4（约 5 项，Rev.2 判据换为 git 提交时间）**
| # | 用例 | 断言 |
|---|------|------|
| 27 | 文件最后提交晚于笔记日期 + 1 天 → `possibly_stale: true` | — |
| 28 | 最后提交早于笔记日期 → `false` | — |
| 29 | 1 天缓冲：提交仅晚几小时 → 仍为 `false` | 边界不抖动 |
| 30 | 目标文件未被 git 跟踪 / git 不可用 → `null` | 不是 `true` 也不是报错 |
| 31 | 笔记无日期字段 → `null` | — |

**P0-3（约 3 项）**
| # | 用例 | 断言 |
|---|------|------|
| 32 | `query_wiki` schema description 含 `mode=check` 优先提示 | 字符串断言 |
| 33 | description 含 expand 成本警告 | 字符串断言 |
| 34 | 所有工具 schema 可正常序列化（回归） | `tools/list` 不报错 |

**Rev.2 追加用例**

| # | 用例 | 断言 |
|---|------|------|
| 35 | `by_file` + `query` 组合：query 硬过滤 | 不含关键词条目出局；排序仍按 (specificity, date) |
| 36 | `by_file` 不写 usage heat | 调用前后笔记 usage 计数不变 |
| 37 | `by_file` 写 telemetry | retrieval_stats 记录该次调用 |
| 38 | `wiki/` 生成页不出现在时间线 | timeline 全部来自 `notes/` |
| 39 | draft 笔记包含在时间线 | `status` 如实为 draft |

### 6.3 全量回归

```bash
python -m pytest tests/ -q
```

重点关注既有断言字段集的测试：`test_query_transparency.py`、`test_usage_ranking.py`、`test_authority_p0.py`、`test_query_repo_filter.py`、`okf_regression_test.py`。

### 6.4 遥测基线（前置项，Rev.2 新增）

合入前必须先采集基线，否则验收 #8 永远只能是体感：

1. 构造 12 条固定查询集：4 条高频历史查询风格（决策/教训检索）+ 4 条 by_file 场景（对典型源文件路径）+ 4 条 check/expand 混合。
2. 基线快照存 `docs/retrieval-baseline.json`（每条查询的返回字符数、expand 调用占比），附一段说明。
3. 合入后同查询集复跑 diff 对比。查询集是测量仪器不是知识，不进 repowiki。

---

## 七、风险与回滚

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 既有测试断言了精确字段集，`est_tokens` 导致失败 | 中 | 低 | 实施第一步先跑全量测试定位；失败则调整断言而非放弃字段 |
| `cache.py` 的 `search()` 增加参数影响其他调用方 | 低 | 中 | 用默认关键字参数，既有调用零改动 |
| `by_file` 路径段匹配过粗，噪声多 | 中 | 中 | 配置 `max_results` 上限 15；v1.5 引入 `files` 精确字段后可降级噪声 |
| `by_file` 与 `mode=detail`/`overview` 组合时语义冲突 | 低 | 低 | 明确优先级：`mode` 早返回分支优先，`by_file` 仅在默认 BM25 路径生效，并在 description 写明 |
| git 子进程调用开销（by_file 每命中条目一次 `git log -1`） | 低 | 低 | 仅 by_file 路径触发，≤15 次/查询；超预算可按 commit 去重缓存 |
| 遥测基线未采集即合入 | 中 | 中 | §6.4 前置项：合入前先跑固定查询集快照 |
| by_file 扫描 112 篇笔记的 IO 开销 | 低 | 低 | 112 个 frontmatter 解析，实测应在 50ms 内；若超预算可缓存 |

**回滚**：三项均有独立配置开关（`retrieval_cost.enabled` / `file_knowledge.enabled` / `file_knowledge.stale_check`），置 `false` 即回到 legacy 行为，无需回滚代码。P0-3 的 description 改写在 `registry.py` 单点，独立 revert。

---

## 八、验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| 1 | 默认检索结果每条带 `est_tokens` | 对本仓库 repowiki 实跑 `query_wiki` |
| 2 | `expand=true` 时能预知成本 | `cost_hint.expand_all_tokens` 与实际展开量一致 |
| 3 | 改文件前能查到历史知识 | `query_wiki(by_file="codewiki/mcp/tools/wiki_search.py")` 返回非空时间线 |
| 4 | 时间线不给正文 | 输出无 `content` / `snippet` 字段 |
| 5 | `mode=check` 出现在工具描述首位策略 | `tools/list` 抓 description 确认 |
| 6 | 全量测试通过 | `python -m pytest tests/ -q` 全绿 |
| 7 | 关闭开关回到 legacy | 三个开关置 false，字段消失、行为不变 |
| 8 | **收益可度量** | 用 `telemetry.py` 的 retrieval_stats 对比**合入前采集的固定查询集基线**（§6.4，`docs/retrieval-baseline.json`）：单次 query_wiki 的平均返回字符数、`expand` 调用占比、`by_file` 采纳率 |

第 8 项是本方案的**关键验收**：调研中估算的"-35%（保守）至 -90%（最坏场景）"是推算值，落地后必须用真实遥测数据验证，而非采信估算。

---

## 九、与既有专项的关系

| 已有能力 | 关系 |
|---------|------|
| `injection_budget`（注入预算降级） | **互补**：它管 snippet 层 1200 字符，本方案管 expand 层成本可见性。两者口径统一于 `len()` /4 |
| `mode=check`（检索透明化 T1） | **P0-3 让它被真正使用**；est_tokens **不进** check 输出——check 保持 3 字段最小面，`test_query_transparency.py:86` 精确字段集断言不动（Rev.2 定案） |
| `usage` heat 排序（U1） | P0-3 通过引导 `check` 模式**保护该信号的数据质量** |
| `stale_after` 新鲜度（F1/F2/F3） | P1-4 是对端补充，不替换 |
| `query_coverage.missing` | 与 `est_tokens` 同属"让输出更诚实"家族，输出结构并列 |
| Doctrine / 场景聚合 | P1-5（保留 filter 支持 rebuild）见 §十 |

---

## 十、P1/P2 遗留项评估结论（2026-09-03 补充）

> 本节收录 Rev.2 定稿时未裁决的遗留项（P1-1/P1-2/P1-3/P1-5/P2-1'/P2-2/P2-3）的处置结论。
> 总原则：**P2 档全部是 P0 三项或团队化的下游，没有"现在就该动"的项**——先做 P0、拿遥测数据再决策。

### 10.1 P1 档

| 项 | 结论 | 触发条件 / 理由 |
|----|------|----------------|
| **P1-4** 对端新鲜度 | **已定案，随 P0-2 落地** | 判据 git 提交时间（ADR-0003），不在待决清单 |
| **P1-2** 笔记 `files` 字段 | **值得做，但现在不做——数据触发的条件项** | P0-2 上线 → 跑约一个月看 by_file 命中分布 → 噪声确实伤排序才立项。**成本修正**：`frontmatter.py` 只有读路径，无 render 序列化 writer——实际工作量 = 补 writer + 往返测试 + 加字段，约 1 人日以上（原表 0.5 人日不含 writer 前置） |
| **P1-3** 折叠视图 | **不做，压到证据出现再议** | ①3–4 人日 = P0 三项总和，边际增量不明确（`read_code_components` 已部分覆盖）；②违背"不新增工具"约束（方案 C 是打擦边）；③收益方向错位——P0 系列省的是**知识检索** token（expand 后门），折叠视图省的是**读代码** token，后者是 grep/Read 的地盘。重新评估的触发信号：遥测显示 Agent 频繁整读超大文件（如 27K 字符 wiki 页或千行源码） |
| **P1-5** Doctrine 聚合 filter | **不动** | 仅是调研备忘，无独立立项理由；等 Doctrine 场景聚合真正有性能压力再说 |
| P1-1 `mode="timeline"` | **不采纳**（调研报告原有项） | 本方案 §2.5 的时间线已作为 by_file 的输出形态落地，独立 timeline 模式与 by_file 重叠 |

### 10.2 P2 档

| 项 | 结论 | 触发条件 / 理由 |
|----|------|----------------|
| **P2-2** SessionStart 软闸门 | **三项里最值得，排在 P0 三项之后** | 调研报告已"优先级上调"，理由成立：无需新钩子、成本低、与 claude-mem v13 实际做法同构。与 P0-3 是同一问题两面——description 管"调用时可见"，SessionStart 注入管"开工前可见"（有 wiki、N 条笔记、近期关键决策）。对本仓，AGENTS.md 已承担该角色；对 PyPI 下游用户是普惠能力。**成本口径提醒**："低"是单 IDE 口径，全生态铺开要乘以 IDE 数 |
| **P2-3** 遥测脱敏白名单 | **值得，但绑在团队化第二刀前后做** | 单人仓无隐私问题；团队化 git 同步开启后，成员"谁在读什么"画像会随 push 进共享远端，届时脱敏（或把 telemetry 去入库化，对齐团队化"派生文件不入库"原则）是前置必修。**已发现的待修 bug**：`repowiki/.meta/telemetry/Administrator.jsonl.tmp.19748` 原子写临时文件被误提交进 git——归入此项的第一个小修（gitignore 或修写路径） |
| **P2-1'** PreToolUse 附加上下文 | **悬空项——先半天 spike 验证钩子能力，再议立项** | 方向反转正确（claude-mem 从 DENY 到 ALLOW 的弯路不必重走）。真实价值是消灭 P0-2 最大风险：把 by_file 从"Agent 主动调"变成"读文件时自动带"。但成本"高"的实质是**多 IDE 碎片化**——CodeBuddy 是否支持 PreToolUse 未验证，QwenWork 无钩子形态。节奏：P0-3 description 引导上线 → 看遥测 by_file 采纳率 → 引导不足、采纳率难看时先 spike 验证 CodeBuddy PreToolUse，再决定。采纳率数据出来前不立项 |
| ~~P2-1~~ 读取拦截（DENY） | **永久否决** | claude-mem 自己已从 DENY 改 ALLOW（`file-context.ts:190`），最强反证，不必重走弯路 |

### 10.3 排序

P0 三项（本方案范围）→ P2-2（SessionStart 注入）→ P2-3（绑团队化第二刀）→ P1-2（数据触发）→ P2-1'（spike 触发）；P1-3 / P1-5 / P1-1 压置。

---

## 附：改动文件清单

| 文件 | 改动 | 项 |
|------|------|-----|
| `codewiki/mcp/tools/injection_budget.py` | 新增 `estimate_tokens()` / `load_retrieval_cost()` | P0-1 |
| `codewiki/mcp/tools/wiki_search.py:614-632` | entry 加 `est_tokens`（JSON fallback 路径） | P0-1 |
| `codewiki/mcp/cache.py:2060-2073` | entry 加 `est_tokens`（SQLite 主路径） | P0-1 |
| `codewiki/mcp/cache.py:2113-2129` | entry 加 `est_tokens`（hop 扩展路径） | P0-1 |
| `codewiki/mcp/cache.py:1888-1903` | `search()` 新增 `chars_per_token` 可选参数 | P0-1 |
| `codewiki/mcp/tools/knowledge_loop.py:1834-1845` | expand 分支加 `content_tokens` | P0-1 |
| `codewiki/mcp/tools/knowledge_loop.py:1711` | `query` 必填校验放宽（`by_file` 情形） | P0-2 |
| `codewiki/mcp/tools/knowledge_loop.py:1749-1764` | 新增 `_query_mode_by_file` 分支（mode 早返回区之后、默认 BM25 路径之前） | P0-2 |
| `codewiki/mcp/tools/knowledge_loop.py:2017-2039` | 响应加 `cost_hint` / `file_knowledge` | P0-1/P0-2 |
| `codewiki/mcp/registry.py:1030-1163` | `query_wiki` description 改写 + `by_file` 参数 | P0-2/P0-3 |
| `codewiki/mcp/registry.py:1162` | `"required": ["query"]` → `[]`（MCP 层校验，by_file 硬前提） | P0-2 |
| `schema.yaml` | 新增 `conventions.retrieval_cost` / `conventions.file_knowledge` | 全部 |
| `docs/retrieval-baseline.json` | 新增（遥测基线快照，合入前采集） | 前置 |
| `tests/test_claude_mem_borrowings.py` | 新增（约 34 项用例） | 全部 |
