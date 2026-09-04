# 代码库架构评审：deepening 候选清单（2026-09-03）

> 评审方法：按近 60 次提交热点定向（`codewiki/mcp/tools/` 69 处、`codewiki/mcp/` 27 处、`codewiki/src/` 10 处），三路并行探索后按 deep module / seam / locality / leverage 词汇定级。五个候选，三个 Strong、一个 Worth exploring、一个 Speculative。
> 词汇约定：**module**（接口+实现的整体）、**interface**（调用方必须知道的一切）、**seam**（不改此地即可改行为的位置）、**shallow**（接口几乎和实现一样宽）、**deep**（小接口后面藏大量行为）。

## 候选总览

| # | 候选 | 强度 | 核心病灶 |
|---|------|------|---------|
| 1 | 拆开 wiki kernel：knowledge_loop.py | Strong | 2,974 行装 6 个工具族 |
| 2 | 抽出检索 kernel：wiki_search 偷 cache.py 私有 | Strong | 11 个私有 import 击穿 seam |
| 3 | 一个 frontmatter 层：读写一体 | Strong | 5 份手搓 parser、写侧无正主 |
| 4 | store.py 成为唯一写路径 | Worth exploring | 锁漏斗建成但 5 个卫星绕行 |
| 5 | 共享 helper 落座 store_bridge | Speculative | 兄弟模块偷 capture_conversation 私有 |

---

## #1 拆开 wiki kernel（Strong）

### 现状

`codewiki/mcp/tools/knowledge_loop.py`（2,974 行）单文件承载 6 个 MCP 工具族：

| 工具族 | 行号 | 内容 |
|--------|------|------|
| ingest_note | :506-765 | 笔记创建、文件名生成（`{date}-{slug}.md`）、手搓 frontmatter 组装 |
| note 生命周期 | :787-1236 | confirm/reject/batch_set_status、锁内 frontmatter 保留改写 |
| freshness 引擎 | :307-505 | 配置加载、窗口计算、`evaluate_note_freshness`、分布统计 |
| query_wiki | :1359-2413 | 5 种查询模式（overview/directory/detail/check/by_file）、过滤、图谱多跳 |
| stats / cold / promotion | :2444-2782 | wiki_stats、cold notes、promotion candidates |
| legacy keyword search | :2783-2938 | 旧版关键词检索 |

### 为什么值得合入

- **locality 约等于零**：ingest 的写路径、query 的读路径、freshness 判定混在同一 implementation 里。改任何一族都要打开同一个 3,000 行文件，diff 审查半径被迫放大到无关区域。
- **没有专门测试文件**：knowledge_loop 被 22 个测试模块顺带覆盖，没有自己的测试面；query 路径无法脱离文件其余部分独立测试。
- **deletion test 不过**：删掉这六族中的任何一族，复杂度会在别处原样重现——它是六个 module 的物理拼接，不是一个 deep module。
- **平行实现滋生**：`_apply_status_to_file`（:787）与 distill_conversation 的 `_apply_dedup_action`（distill_conversation.py:693-780）是两套并行的"锁内 frontmatter 保留正文改写器"。

### 方案

按工具族拆成 ingest / lifecycle / freshness / query / stats 五个 module；抽出一个 **NoteWriter** deep module（文件名生成 + frontmatter 写入 + wiki_index/BM25 刷新），ingest_note、distill_conversation、status 改写全部走它。distill 的平行改写器删除。

### 收益

- 每族改动集中一个文件（locality）
- NoteWriter 一个接口供 N 个写方复用（leverage）
- query 路径获得独立测试面
- 消掉 distill 的平行 status 改写器

### 风险与顺序

收益最大但风险也最大——query_wiki 是产品心脏，拆分动静大。**应在 #2 检索 kernel 立稳之后顺势推进**（query 模块拆出来直接落座新 kernel 之上，不用二次返工）。

---

## #2 抽出检索 kernel（Strong，首选）

### 现状

三层病灶，全部指向同一个根因——检索 kernel 没有自己的 interface：

1. **私有 import 击穿 seam**：`wiki_search.py:20-31` 从 cache.py import 11 个下划线函数（`_tokenize`、`_K1`、`_B`、`_extract_snippet`、`_doc_authority`、`compute_usage_heat`…）；`knowledge_loop.py:22,1824` 也偷 `_STOPWORDS` 和 `_tokenize`。
2. **cache.py 六种职责混装**（2,504 行）：BM25 文本 kernel（:206-554）、usage heat 遥测排序（:556-730）、component store + LRU（:733-826）、SQLite schema/路由/指纹/变更检测（:888-1703）、索引构建检索更新（:1704-2360）、链接图多跳（:2218-2460）。它同时是持久层和共享 kernel——interface（被 import 的私有面）与 implementation 一样宽。
3. **freshness 不变量三处平行维护**：`index_freshness.py:195`（三级磁盘检查）、`cache.py:2190`（`_refresh_index_built_at`）、`wiki_search.py:421-424`（手抄 mirror，注释自认是 AnalysisCache 逻辑的复制品）。且 `ensure_fresh` 每次查询被调两遍（handler `knowledge_loop.py:2098-2099` + `search` 内部 `wiki_search.py:523-525`）。

实证代价：est_tokens 功能（提交 444c8ae）被迫横穿 4 个文件——config、cache.py 的 SQLite 路径、wiki_search 的 JSON 路径、handler 的 cost_hint；by_file 模式（6dad898）则干脆绕开 wiki_search/cache 另起炉灶，重复实现 frontmatter 解析。

### 为什么值得合入

- **seam 是既成事实**：SQLite 路径与 legacy JSON 路径两个 adapter 已经存在——不是假想 seam，只差把 interface 立起来。
- **迭代频率打在这里**：近两个月 est_tokens、by_file、成本可见性三次功能全部落在检索路径上，每次都付"横穿多文件"的税。kernel 立起后这类功能落一处、两个 adapter 自动继承（leverage）。
- **并发/一致性 bug 面**：三处平行 freshness 维护正是未来出 bug 的形态；收口后改一处、一处验证（locality）。
- **可测性质变**：BM25/分词/authority 变成 `src/retrieval.py` 纯函数，零 I/O 秒级单测；adapter 用同一契约测试参数化覆盖。测试面 = interface，不再伸手进 implementation。
- **顺手修两个实缺陷**：`ensure_fresh` 双重调用白付一次探测；`invalidate_schema_cache` 全仓零调用方（死代码确认）。

### 方案（已定稿，详见 [retrieval-kernel-refactor-plan.md](plans/retrieval-kernel-refactor-plan.md)）

四个独立提交的 phase，golden diff 硬闸保证检索结果零漂移，registry.py 零改动：

- **Phase 0 基线固化**（半天）：固定 fixture wiki，SQLite 与 JSON 两路径 golden 快照（top-k 顺序、分数、est_tokens）。
- **Phase 1 kernel 搬移**（1 天）：`cache.py:206-730` 文本 kernel 整体搬入 `src/retrieval.py`，私有名转正；3 个消费方 import 改指正主。
- **Phase 2 interface 立起 + freshness 收口**（1-2 天）：`SearchIndex` Protocol；`wiki_search.search` 成为 seam 唯一所有者（`ensure_fresh` 收口到此处，handler 重复调用删除）；手抄 mirror 删除，`built_at` 刷新成为 JSON adapter 的 implementation 细节。
- **Phase 3-4 by_file 落座 + 清理**（1 天）：by_file 改用 kernel + `src/frontmatter.parse_frontmatter`；删兼容 re-export，`from codewiki.mcp.cache import _` 归零。

已裁决决策（2026-09-03）：kernel 落 `src/retrieval.py`（mcp→src 既有方向）；`ensure_fresh` 唯一调用点在 `wiki_search.search` 入口；shim 不设过渡期；与 #1 不同期推进。

---

## #3 一个 frontmatter 层（Strong）

### 现状

frontmatter 的读取语义散在五个模块、写侧没有正主：

| 实现 | 位置 | 角色 |
|------|------|------|
| `_extract_frontmatter` | knowledge_loop.py:2939 | 读（手搓） |
| `_parse_frontmatter` + `_unquote_fm` | distill_conversation.py:340 | 读（手搓） |
| `_extract_fm` | task_manager.py:162 | 读（手搓） |
| 逐行扫描 | wiki_search.py:227 | 读（手搓） |
| `_parse_frontmatter_dict` | cache.py:265 | 读（手搓，第六份） |
| `parse_frontmatter` | src/frontmatter.py | 读（正主，readers absorb 全部 legacy 格式） |
| 序列化 writer | —— | **缺失** |

`store.py:171` 的 `Page.get` 注释自认"统一了昔日各手搓 parser 的语义"——统一发生过一次，但只覆盖了 store 内部。写侧全靠各处手拼 YAML 字符串。

### 为什么值得合入

- **已登记的前置缺口**：CONTEXT.md 明确记录 frontmatter 模块"只有读路径，序列化 writer 与 `parse(render(x)) == x` 往返不变量尚无实现，是 P1-2 `files` 字段落地的前置项"。本候选就是补齐它。
- **deletion test 强信号**：删掉五份手搓副本，复杂度集中到一处——每份都只是正主的近似。
- **往返不变量即测试面**：`parse(render(x)) == x` 一条断言锁住整个读写契约，五份近似各自没有这层保证。
- **写侧现状有实害**：手拼 YAML 出错只在运行时暴露（引号、多行值、转义）；ingest / distill / status 改写三处手拼格式必须人工保持一致。

### 方案

给 `src/frontmatter.py` 补 `render_frontmatter`，成为读写一体 deep module；五份读副本 + 各处手拼写全部改走它。保留一条永久约束：`conv-*.md` 的 `status`/`task_id` 保持顶层单行键（stdlib-only hook `.codebuddy/hooks/task_session_start.py` 逐行扫描，无法 import 本模块）。

### 收益

- 往返不变量成为测试面；legacy 格式吸收进一个 reader
- 解锁 P1-2 files 字段
- 手拼写点归零，frontmatter 损坏类 bug 的定位半径从五个文件缩到一个

---

## #4 store.py 成为唯一写路径（Worth exploring）

### 现状

锁漏斗 `codewiki/src/store.py`（`atomic_write` :92 / `locked` :109，sidecar `.lck` 保证 `os.replace` 在 Windows 合法 / `locked_write` :123 / `locked_rmw` :135，底层 `locks.py:65` 线程+OS 双层）是本仓已建成的 deep interface，提交 9c04222 收口过 4 个裸写点。但仍有 5 处卫星绕行：

| 卫星 | 位置 | 问题 |
|------|------|------|
| `task_manager._atomic_replace_with_retry` | task_manager.py:188 | 与 store.py:80 **逐字重复**；压缩归档写入（:995-1004）用它且**不带 sidecar 锁**——同用户双进程竞态窗口 |
| `aggregation_state` | aggregation_state.py:84 | 同惯用法另一份 |
| `page_manifest` | page_manifest.py:82 | 同上 |
| `wiki_search` | wiki_search.py:200 | 同上 |
| `doctrine` | doctrine.py:313 | 同上 |

### 为什么值得合入

- **行为不变、纯收口**：不引入新设计，只是让已有的 deep interface 真正成为唯一写路径。风险最低的候选。
- **修一个真实竞态**：task_manager 压缩归档无锁写入是现存缺陷，不是理论问题（per-user 文件所有权缓解了跨用户场景，同用户双进程未覆盖）。
- **locality**：并发正确性一处验证——`test_phase2_concurrency.py` 的 13 个锁漏斗测试直接复用为新收口点的保证。
- **与 ADR-0001/0002 不冲突**：任务记忆保持 Markdown、直写落盘均不变。

### 方案

删 `_atomic_replace_with_retry`，压缩归档改走 `locked_rmw`；其余四处卫星原子写逐个并入漏斗。半天到一天工作量。

---

## #5 共享 helper 落座 store_bridge（Speculative）

### 现状

- `store_bridge.py:34` 的 `_resolve_output_dir` 是正主（注释自述"统一昔日重复副本"），但重复仍存于 capture_conversation.py:152、source_ingest.py:56、note_consolidation.py:332、distill_conversation.py:199，`knowledge_loop.py:1970-1989` 内联三步回退，`task_manager.py:64` **import 兄弟模块的私有函数** `capture_conversation._resolve_output_dir`。
- distill 同样偷 `capture_conversation._slugify` 与 `pending_raws_by_task`；`_slugify` 在 knowledge_loop.py:116 与 capture_conversation.py:119 各有一份。
- `capture_conversation.pending_raws_by_task`（:321-323）是 `KnowledgeStore` 的薄转发，注释自认保留它"是为了那些从此模块 import 的模块"——模块图的历史路由盖过了设计路由。

### 为什么（暂时只值 Speculative）

- 病灶真实（seam 位置错了：通用 helper 住在 capture_conversation 的 implementation 里），但收益上限低于前四个：删 5 份解析副本，无行为收益、无测试面收益。
- **前置依赖**：#1 拆 knowledge_loop 时必然触碰 `knowledge_loop.py:1970` 的内联回退；#3 动 frontmatter 时也顺路。**应搭 #1/#3 的车做**，单独提 PR 性价比不高。

### 方案（搭车执行）

`_resolve_output_dir`、`_slugify`、`pending_raws_by_task` 迁入 store_bridge（后者本就是 KnowledgeStore 薄转发），兄弟 import 改指正主，私有名转正。

---

## 推进顺序建议

> **落地状态（2026-09-04 更新）**：五个候选全部完成合入（#2/#3/#4 commit
> 03ab32e..f09f30e；#5 commit f4c8802；#1 commit 206dbd4），golden 基线全程
> 零漂移，pytest 779 通过，smoke 132 通过。
> 实施中的两个额外收获：golden 基线抓回一次搬移事故（`_ontology_cache`
> 定义被正则吞掉，6 快照分数漂移，测试全绿也拦不住）；`parse_frontmatter`
> 升级吸收 YAML 流式集合与 `verified:` 映射列表（修复晋升年龄回退失效）。
> CONTEXT.md 已补 retrieval kernel / SearchIndex adapter 词条，frontmatter
> module 词条更新为读写一体。

1. **#2 检索 kernel**（✅ 已完成）：产品心脏 + 迭代频率最高 + seam 已是既成事实。
2. **#3 frontmatter 层**（✅ 已完成）：独立可做，且是 P1-2 前置项。
3. **#4 唯一写路径**（✅ 已完成）：风险最低，修真实竞态。
4. **#1 拆 knowledge_loop**（✅ 已完成，搭 #5）：六个工具族落座独立 module，NoteWriter deep module 抽出，knowledge_loop.py 降为兼容 facade，registry 路径改指真实 module。
5. 全程 registry.py 零改动（dispatch 按 `module:func` 字符串导入 handler），工具名与对外行为不变。

## 词汇沉淀

落地后按 domain-modeling 惯例在 CONTEXT.md 补词条：**retrieval kernel**（#2）、**SearchIndex adapter**（#2）、**NoteWriter**（#1）、**frontmatter round-trip invariant**（#3）。
