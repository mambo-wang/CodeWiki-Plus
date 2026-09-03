# 重构方案：抽出检索 kernel（候选 #2）

> 目标形态：一个 deep module（检索 kernel）+ 两个 adapter（SQLite / legacy JSON）落座同一 interface；
> freshness 不变量收敛到一处；消灭 11 个跨文件私有 import。
> 全程行为不变：检索结果、排序、est_tokens 语义、三级回退顺序均不变。

## 一、现状与病灶

| 病灶 | 位置 |
|------|------|
| wiki_search 偷 import cache.py 的 11 个私有函数 | `wiki_search.py:20-31`（`_tokenize/_K1/_B/_extract_snippet/_doc_authority/…`） |
| knowledge_loop 也偷（`_tokenize`、`_STOPWORDS`） | `knowledge_loop.py:22, 1824` |
| cache.py 六种职责混装（2,504 行）：BM25 文本 kernel / usage heat / component store+LRU / SQLite schema+指纹 / 索引构建更新 / 链接图 | `cache.py:206-730, 733-826, 888-1703, 1704-2360, 2218-2460` |
| freshness 不变量三处平行维护 | `index_freshness.py:195` · `cache.py:2190 _refresh_index_built_at` · `wiki_search.py:421-424`（手抄 mirror） |
| `ensure_fresh` 每次查询调两遍 | handler（`knowledge_loop.py:2098-2099`）+ `wiki_search.search` 内部（`:523-525`） |

**registry.py 无需改动**：dispatch 按 `module:func` 字符串导入 handler，工具名与 handler 路径全不变，纯内部重构。

## 二、目标形态

```
codewiki/src/retrieval.py        ← 检索 kernel（deep module，纯逻辑，零 I/O 依赖面）
    tokenize(text) -> list[str]
    extract_snippet(content, query_tokens) -> str
    build_indexable_text(content, page_type) -> str
    load_ontology(output_dir) / expand_with_ontology(tokens, ontology)
    doc_authority(doc_key, source, content) -> float
    compute_usage_heat(...) / usage_context(...)
    STOPWORDS / K1 / B                      ← 私有名转正为公开常量

codewiki/mcp/tools/wiki_search.py ← seam 唯一所有者
    def search(output_dir, session, query, ...) -> list[SearchHit]
        1. ensure_fresh（唯一调用点）
        2. 选 adapter：session SQLite → standalone SQLite → legacy JSON
        3. 调 adapter.search()，补 est_tokens / cost 字段

    class SearchIndex(Protocol)             ← interface 立起来
        build(output_dir) -> dict
        search(query, *, scope, max_results, apply_authority,
               apply_usage, chars_per_token, ...) -> list[dict]
        update_file(output_dir, filepath)   ← 各自内部维护 freshness 基线

codewiki/mcp/cache.py            ← 瘦身为 persistence adapter
    AnalysisCache 实现 SearchIndex（SQLite 路径）
    ComponentMeta / LazyComponentStore / 指纹 / 路由 / 链接图留在原处
    文本 kernel 全部迁出
```

依赖方向变为 `mcp/tools → mcp/cache(persistence)` + `mcp/tools → src/retrieval(kernel)`，与仓内既有惯例（172 处 `mcp → src` import）一致。两个 adapter 是既存事实，seam 不是假设。

## 三、分阶段落地（每步独立提交、可单独回滚）

### Phase 0 — 基线固化（半天）

- 建固定 fixture wiki（含 notes/wiki/中文标题/ontology），golden 测试：`query_wiki` 全模式跑一遍，快照 top-k 顺序、分数、est_tokens。
- 两个路径都要 golden：SQLite 路径（带 session）与 legacy JSON 路径（无 DB）。
- 跑 pytest 全量 + `okf_regression_test.py` 留基线（注意本机已知环境约束：click 8.1.x、mcp<2）。

### Phase 1 — kernel 抽取：move, not copy（1 天）

- 新建 `codewiki/src/retrieval.py`，把 `cache.py:206-730` 的文本 kernel（tokenize/snippet/ontology/authority/indexable_text/usage_heat/usage_context + `_K1/_B/_STOPWORDS`）**整体搬移**，私有名转正。
- `cache.py` 顶部留过渡 re-export：`from codewiki.src.retrieval import tokenize as _tokenize, ...`（兼容 shim，标 deprecated 注释）。
- 立即改三个消费方：`wiki_search.py:20-31`、`knowledge_loop.py:22`、`knowledge_loop.py:1824` → 改 import kernel 公开名。
- 验证：pytest + okf_regression 结果与 Phase 0 基线逐字段 diff。

### Phase 2 — interface 立起 + freshness 收口（1-2 天）

- 定义 `SearchIndex` Protocol（签名 = 现 `AnalysisCache.search` 契约，含 `apply_authority/apply_usage/chars_per_token`）。
- `wiki_search.py` 重构为 seam 所有者：
  - `ensure_fresh` 收敛到 `search()` 入口唯一调用；删 `knowledge_loop.py:2098-2099` 的 handler 侧重复调用（`has_search_index` 守卫一并下沉）。
  - 三级回退逻辑集中为一个 `_select_adapter(output_dir, session)`。
- freshness 三处收敛为一处不变量，各 adapter 内部自维护基线：
  - SQLite：`AnalysisCache.update_search_doc` 内部 `_refresh_index_built_at`（不变，已是内部）。
  - JSON：`wiki_search.py:415-424` 的手抄 mirror 注释块删除——`built_at` 刷新成为 JSON adapter `update_file` 的 implementation 细节。
- 契约测试参数化跑两个 adapter（同一组用例断言同一行为）。
- 验证：golden diff 不变；`test_index_freshness.py` / `test_freshness.py` 全绿。

### Phase 3 — by_file 落座（半天）

- `knowledge_loop._query_mode_by_file`（:1773 起）：改用 kernel `tokenize` + `src/frontmatter.parse_frontmatter`，删掉它自己的 frontmatter 逐行扫描与 `cache._tokenize` import。

### Phase 4 — 清理（半天）

- 删 `cache.py` 的兼容 re-export；`grep -rn "from codewiki.mcp.cache import _"` 归零。
- 顺手删死代码：`page_router.invalidate_schema_cache`（全仓零调用方）——不在本次范围只做记录，不混入本 PR。

## 四、测试策略：replace, don't layer

- **kernel**：纯函数测试，脱离 SQLite/文件系统（tokenize 中文分词、snippet、authority、ontology 展开）。
- **adapter**：同一契约测试套参数化两个 adapter——`test_authority_p0.py`、`test_usage_ranking.py`、`test_query_transparency.py` 现有的"伸手进内部"式测试逐步改为走 `wiki_search.search` interface。
- **回归底线**：Phase 0 golden 逐字段 diff，任何分数漂移即红灯。

## 五、风险与回滚

| 风险 | 缓解 |
|------|------|
| 分数/排序意外漂移 | golden diff 硬闸；BM25 常量随 kernel 整体搬移，数值不变 |
| 双 `ensure_fresh` 删除后时序变化 | ensure_fresh 幂等（tier-3 mtime 采样），删一次调用只省一次探测；golden + freshness 测试覆盖 |
| 进程级 schema 缓存干扰测试 | 沿用既有约定：`schema.yaml` 必须在首次查询前落盘（`_schema_with` 模式） |
| 回滚 | 四个 phase 独立提交，任一 phase 可单独 revert |

## 六、决策点（已定稿 2026-09-03）

1. **kernel 落位**：✅ `src/retrieval.py`。
2. **`ensure_fresh` 唯一调用点**：✅ `wiki_search.search` 入口；handler 侧调用与 `has_search_index` 守卫一并下沉。
3. **兼容 shim**：✅ 不设过渡期，Phase 4 同 PR 删除（仓内消费方 3 处已同期改完）。
4. **与候选 #1 的关系**：✅ 不同期。本方案先行；query 模块拆分（候选 #1）后续直接落座新 kernel 之上。

## 七、产出后的沉淀动作

- 落地后在 `CONTEXT.md` 词汇表补 **retrieval kernel** / **SearchIndex adapter** 词条（domain-modeling）。
- 若决策点 2/3 有 load-bearing 否决理由，记 ADR 防止未来评审重提。
