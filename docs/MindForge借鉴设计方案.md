# MindForge 借鉴设计方案（四线：检索成本度量 · 截断 JSON 抢救 · frontmatter 血缘合并 · lint 健康度与缺失概念）

> 来源：`docs/MindForge-调研与借鉴分析.md` 借鉴清单 P1/P2 部分。
> 日期：2026-08-27 · 状态：**草案（待评审）** · 预计工作量：**6–8 人日**（四线，B/D1 先行一批，A/C 二批可并行）
> 前置约束：不新增 MCP 工具（沿用 P0 哲学——能力长在现有工具与数据上）；OKF frontmatter 顶层零新增键；**MindForge 为 BUSL-1.1 许可证（Source Available 非开源），本方案只借鉴设计思想，实现零代码抄写**，所有算法按本文描述自研。
> 形态前提（决定 A 线必须转化）：MindForge 是自带 LLM 的 Web 产品（后端统一 `_llm_complete_tracked` 封装所有调用）；CodeWiki 是无内嵌 LLM 的 MCP 工具链，LLM 在调用方（IDE Agent / distill Mode B 的环境变量构建）。因此 MindForge 的"AI 调用级审计日志"不能直接照搬，须转化为 CodeWiki 自己可测的确定性指标。

---

## 一、背景：两条已核实的事实基线

**事实一（增量更新现状，2026-08-27 核实源码）**：CodeWiki 的增量更新不是新建整页——`write_doc_file` 对已存在文件直接拒绝（doc_writer.py，"Use edit_doc_file to modify it"），唯一更新路径是 `edit_doc_file`（str_replace/insert/undo），frontmatter 补丁是 additive-only（`_patch_existing_frontmatter`：existing keys are never overridden or reordered），兜底是 `.meta/edit_history.json` 快照（20 条/文件）。**人工修改是"结构性保留"而非"语义性保留"**：LLM 可以合法地用一个大范围 `str_replace` 换掉恰好包含人工改动的段落，工具层不识别"这段是人改过的"。当前防线是围栏（禁止整页覆盖 + 事后 undo），不是管道（程序化合并）。

**事实二（lint 现状）**：`lint_wiki` 已有 18 项检查，全部是结构/一致性/时效类确定性规则；无跨页面"缺失概念"聚合检查（被多页引用却从未建页的目标）；无健康度聚合数字（grep 全仓无 health_score 实现）。telemetry 事件流只有 hit（检索命中）与 adopted（采纳）两类，无成本维度。

MindForge 恰好在这三个缺口上各有机制：enrich 的确定性血缘合并（sources/tags/links 由程序取并集，不信任 LLM 输出）、missing_concepts 检查（被 3+ 实体引用但无页面的概念，纯确定性实现）、健康度评分（100 − critical×2 − warning×1.5 − info×0.5，保底 10 分）与 AI 调用审计（token/时长/finish_reason 逐次记录）。本方案把这四个机制按 CodeWiki 的形态转化落地。

---

## 二、A 线：检索成本度量（"AI 调用审计"的 CodeWiki 转化）

### 2.1 为什么不能直接照搬、转化成什么

MindForge 审计的对象是 LLM 调用（它自己发起的）。CodeWiki 的主体路径里没有 LLM 调用可审计——LLM 调用发生在 IDE Agent 一侧，CodeWiki 不可见。但 CodeWiki 有一个自己完全可测的确定性指标：**每次 query_wiki 实际注入了多少内容**。这正对齐 Multi-Agent 成本文章调研已确认的结论（记忆存档 2026-08）："评测应测确定性指标（检索轮次/带入字节），端到端 A/B 噪声大于信号"。

"检索 vs 盲搜"的节省估算此前已被识别为 telemetry 的核心缺口（只有 hit_count，无法回答"这个知识库到底省了多少上下文"）。A 线补的就是这块。

### 2.2 采集：telemetry 新事件类型

落点 `telemetry.py`（现有 `record_hit` / `record_adopted` 同款模式，jsonl 事件流 + mtime 快照聚合）：

```python
def record_query(output_dir, query, results: int, injected_chars: int) -> None:
    # 事件 {"type": "query", "query": ..., "results": N, "injected_chars": M, "at": ISO}
```

- 埋点在 `wiki_search.py` 的查询入口（query_wiki 主路径），`injected_chars` 取本次返回各结果 snippet/content 字符数之和（expand=true 深读时按 max_chars 预算计实际注入量）；
- 查询是用户可见的高频操作，事件量可控（每会话量级 10–100），无膨胀风险；
- `mode=check`（轻量预检）不记录——它不注入内容。

### 2.3 聚合与节省估算

`aggregate_usage`（fold 全目录 jsonl 的既有模式）扩展产出：

```
total_queries, total_injected_chars, avg_chars_per_query,
blind_baseline_chars,   # 全库 wiki/**/*.md 总字符数（不含 .meta）
estimated_saving = 1 − total_injected_chars / (total_queries × blind_baseline_chars)
```

- 节省率的语义：N 次查询如果靠通读全库解决，需要 N × 全库字符；实际只注入了 total_injected_chars。这是**下界估算**（盲搜未必真读全库、检索也未必一次命中），文档与输出文案明确标注"估算"；
- token 换算不做硬编码换算比（中文/英文差异大），透出字符量原始值，换算留给消费方；
- **价值叙事落地**：`wiki_stats` 新增 `retrieval_value` 段（与 promotion_candidates 同款的数据段形态），让"知识库值不值"从 hit_count 的模糊信号升级为可展示的量化对比。

### 2.4 附带小项（可选）：distill Mode B 调用审计

CodeWiki 唯一内嵌 LLM 的路径是 `distill_conversation` Mode B（`_call`，从 MAIN_MODEL/LLM_BASE_URL 构建，distill_conversation.py L809）。对齐 MindForge 的审计纪律：

- `_call` 返回值从 `str` 扩为 `(text, meta)`，meta 捕获 provider 响应的 `usage`（OpenAI 兼容接口的 `data.usage`，缺省为空）、duration、finish_reason；
- 有 usage 时写 telemetry 事件 `{"type": "llm_call", "model": ..., "input_tokens": ..., "output_tokens": ..., "duration_ms": ..., "finish_reason": ...}`；
- 失败也记事件后 re-raise（MindForge 模式：成功失败均留痕）；
- 此项为 Mode B 专属（Mode A/C 的 LLM 在调用方，审计不到），标为可选实现，不阻塞主线。

### 2.5 边界

- 不改 retrieval_stats SQLite 表（查询事件进 telemetry jsonl，与 hit/adopted 同库不同事件类型，aggregate fold 天然兼容）；
- telemetry 开关（`conventions.telemetry`）沿用，关闭时零写入。

---

## 三、B 线：截断 JSON 抢救状态机

### 3.1 现状与缺口

`distill_conversation.py` 的 `_parse_llm_notes` / `_parse_llm_memories`（L823-873）是 CodeWiki 里唯一解析 LLM JSON 输出的两个函数。现有容错两层：剥 markdown 围栏 → `json.loads` 失败后**朴素括号截取**（`find("{")` 到 `rfind("}")`）。这个 fallback 只能处理"输出被围栏或前后噪声包裹"的情况；**尾部被 max_tokens 截断时无效**——截断的 JSON 数组/对象 rfind 仍能找到 `}` 但整体结构不完整，二次 loads 仍失败，函数返回 `[]`，**整次蒸馏产出归零**（Mode B 下浪费一次完整 LLM 调用）。

MindForge 在同一问题上用手写状态机（跟踪 depth / in_str / escape 三个状态）从残缺 JSON 中提取已完整的对象——数组被截断时，前 N 个完整元素全部救回，零额外 LLM 调用。其工程注释还记录了实测依据（规划输出 4096 tokens 时 3/4 次顶满截断；单页正文 4096 时约 7% 静默截断）。

### 3.2 设计：通用纯函数 + 双接入点

新模块 `codewiki/src/salvage_json.py`（纯函数，无 IO，无第三方依赖）：

```python
def salvage_complete_objects(text: str) -> list[dict]:
    """从可能截断的 LLM JSON 输出中提取所有已完整闭合的顶层对象。

    算法（自研，勿参考 MindForge 源码——BUSL-1.1）：
    单遍扫描字符流，维护 depth（括号嵌套深度）、in_string（是否在 "..." 内）、
    escape（前一字符是否为反斜杠）三个状态；
    - in_string 内的 { } [ ] 不计深度（MindForge 踩坑点：字符串里含 } 会毁掉朴素计数）；
    - 记录每个 depth==1 层完整闭合对象的 [start, end) 边界；
    - 顶层是 {...} 单对象且完整 → [obj]；顶层是 [...] 且被截断 → 数组内所有完整元素；
    - 任何元素不完整（扫描到文本末尾仍未闭合）→ 丢弃该元素，保留更早的完整元素。
    """
```

接入：`_parse_llm_notes` / `_parse_llm_memories` 的 `JSONDecodeError` 分支替换为 salvage 调用；成功救回时返回值附带 `salvaged=True` 标记（写入 distill 结果 JSON 的诊断字段，供 telemetry 与排障区分"完整解析"与"抢救产物"——抢救产物更可能缺尾部内容，需人工留意）。

### 3.3 明确不接入的位置

- Mode C 的 `distilled_file` 侧信道：那是本地 Agent 写的文件，非 LLM 直出，截断概率低且有 JSON 校验拦截，不接；
- `batch_ingest` / `ingest_note`：内部无 LLM 调用；
- 嵌套深化（对 notes 数组内对象再截断抢救）：LLM 输出顶层就是 {notes, memories}，顶层完整即可，v1 不做递归抢救。

### 3.4 测试矩阵

单测构造截断样例（每类至少 2 例）：数组第 N 个对象中途截断（含对象首尾）、字符串内含 `}` 与转义 `\"` 的截断、frontmatter 噪声包裹 + 截断叠加、围栏未闭合、完全无法解析（返回 [] 不抛异常）。断言完整前缀元素被救回且顺序保持。现有 distill 全量测试不回归。

---

## 四、C 线：frontmatter 血缘字段确定性合并（enrich 的围栏内转化）

### 4.1 设计思想：从"围栏"到"围栏 + 管道"

CodeWiki 已有围栏（禁止整页覆盖、additive-only、undo 兜底，见 §一）。MindForge enrich 的启发不在"别新建页面"（已做到），而在**血缘字段由程序管**：它的 sources/tags/links 合并是确定性并集，LLM 只产正文。CodeWiki 已有一个程序管辖先例——`_resync_source_refs`：每次 edit 后重扫正文 `[^src:...]` 标注、程序化重写 frontmatter 的 source_refs/chunk_refs，**不信任 LLM 对这两个字段的任何改动**。C 线把这个模式扩展为通用的"血缘字段保护区"。

### 4.2 保护区定义与合并规则

v1 保护区：**tags、aliases**（source_refs/chunk_refs 已由 _resync 覆盖，纳入统一框架但不改行为）。选这两个的理由：它们是检索锚点——`missing_aliases` 检查、`wiki_index` 索引、`_collect_wiki_terms` 的 term 表都在消费；LLM str_replace 误删一个 tag/alias 会静默破坏可发现性，且不可观测（不报错、不 lint，直到检索召回率下降）。

规则（opt-in，schema 配置开启）：

```
conventions.frontmatter_merge:
  protected_fields: [tags, aliases]   # 空列表 = 关闭（默认）
```

`edit_doc_file`（str_replace/insert 均适用）写盘后的新钩子 `_merge_protected_fields`：

1. edit 前快照 frontmatter A，edit 后解析 frontmatter B；
2. 对每个受保护列表字段：`merged = union(A[f], B[f])`（保序：A 原序 + B 新增项追加）；
3. 若 `merged != B[f]`（即 B 删除了 A 有而 B 无的条目）→ 写回 merged，返回 JSON 附带：
   `"frontmatter_merge": {"field": "tags", "restored_items": ["被删条目"]}`；
4. **LLM 仍可新增**（新增 tags/aliases 合法通过，不受阻）；只有删除被程序拒绝。

语义：新增是 LLM 的职权（对应 MindForge "新标签提议"），删除须人显式操作（编辑 frontmatter 前先关保护，或直接改 schema 例外）——这正是 MindForge 词表治理"进词表须人批准"思想的**对偶形式**：我们管不了 LLM 往脑子里加什么，但能守住它删不掉既有锚点。

### 4.3 边界与被否方案

- **正文不保护区**：内容更新是 edit 的本职，保护正文等于冻结文档；
- `metadata.related_modules` 等：不进 v1（笔记归属由蒸馏写入，删除有正当场景——模块拆分），列观察项；
- undo 交互：合并发生在 write 之后，edit_history 存的是"合并前"快照，undo 恢复的正是合并前内容，链路自洽；
- **被否方案**：给 `write_doc_file` 加 `overwrite/enrich` 参数。否决理由：破坏"整页覆盖被禁止"的围栏语义；enrich 的正文生成在 CodeWiki 属于 Agent（LLM）职责，工具层只需守住血缘字段——职责切分与 MindForge"LLM 只产正文、元数据后端组装"一致。
- 落地纪律：本方案即 §五 P3"元数据后端组装"原则的机制化——文档约定（schema.yaml conventions 注释）与机制双写。

### 4.4 测试

在真实 repowiki 页面上回归：LLM 语义的 str_replace 删 tag → 恢复且返回 restored_items；新增 tag → 通过；insert 进正文含 frontmatter 改动 → 同规则；保护关闭时行为与现状完全一致（默认零变化）。

---

## 五、D 线：lint 第 19 项 missing_concepts + health_score

### D1：missing_concepts（确定性，MindForge 检查的直接平移）

检查定义（severity: warning，与 missing_aliases 同级）：

```
判定对象：wiki/ 下所有页面正文中的链接目标（[[slug]] 与已转换的 [text](path).md 双形态）
触发条件：目标页面文件不存在，且引用它的不同源页面数 ≥ min_refs（默认 3）
报告条目：{name, referenced_by: [源页面列表], count}
message：Concept '<name>' is referenced by N pages but has no wiki page —
         高频被引用却从未建页的概念，建议为它补一篇 concept 页面
```

- **纯确定性**（MindForge 同款：不调 LLM，链接统计聚合）；与 `broken_links` 的边界：broken_links 报"任何死链"（含 1 次引用的笔误），missing_concepts 只报"高频缺页"（≥3 个不同源页面都指向它——笔误不会被 3 个页面共同指向，这是信号与噪声的分界）；
- 数据源复用 wiki_lint 既有的链接扫描基建（stale_refs/broken_links 已扫），新增的只是聚合视角；
- **硬约束（前科教训写死）**：`_ALL_CHECKS` 加 `"missing_concepts"` 必须与 `registry.py` 中 lint_wiki inputSchema 的 checks 枚举**同一提交同步**（type_filter 漏 scenario 的 live bug 前科：MCP 校验先于 handler，枚举不同步则合法输入被拒）；lint description 文案与 README（双语言版）检查项计数同步更新；同步断言已有测试先例可仿（test_consolidation_p2.py 的枚举同步测试）。
- 配置：`conventions.missing_concepts: {min_refs: 3}`。

### D2：health_score（lint 返回值携带）

`lint_wiki` 返回 JSON 顶层新增 `health_score` 字段（报告 markdown 头部同步展示）：

```
score = max(10, round(100 − critical×2 − warning×1.5 − info×0.5))
（无任何问题时 = 100；severity 计数来自本次 all_issues 汇总）
```

- 公式沿用 MindForge（加权思想无版权问题，权重比例体现"critical 是 warning 的 1.33 倍严重"）；保底 10 分避免"负分知识库"的展示荒谬；
- **v1 不落盘、不做趋势**：lint 每次独立执行，score 只在返回值与报告中出现。趋势线（每次 lint 分数写 telemetry 形成时间序列）与 `wiki_stats` 消费（需要 lint 结果落盘点）列 P3 观察项——等 A 线 telemetry 成熟后是自然延伸，避免 v1 同时引入存储 schema。

---

## 六、实施顺序与分批

| 批次 | 线 | 工作量 | 理由 |
|------|-----|--------|------|
| 一 | B（截断抢救） | 1 人日 | 纯函数独立可测，Mode B 蒸馏即时受益 |
| 一 | D1（missing_concepts） | 1 人日 | 确定性聚合 + 枚举同步，小而确定 |
| 二 | A（检索成本度量） | 2–3 人日 | telemetry 扩展 + wiki_stats 消费段；A4（Mode B 审计）可选 |
| 二 | C（frontmatter 血缘合并） | 2 人日 | edit 钩子 + opt-in 配置 + 真实页面回归 |
| 二 | D2（health_score） | 0.5 人日 | 纯汇总计算，随 D1 的 lint 改动顺带 |

验收：每线单测 + 全量 pytest（`-o addopts=""`）；B/D 线在本仓库自身 repowiki 上端到端验证（自举纪律）；C 线在真实页面做合并回归；提交按 feat/chore 分笔（仓库惯例）。

## 七、明确不做（借鉴的克制）

- **缺口探索工具（explore 三栏盘点）**：与 doctrine/场景导航定位重叠，且"全库盘点"是否被真实需要尚无数据支撑——列观察项，等 A 线 telemetry 能证明检索盲区后再立项；
- **语义冲突检测（LLM 辅助 lint）**：与"CodeWiki 无内嵌 LLM"原则冲突（唯一例外是 distill Mode B），不立项；MindForge 的 `[!conflict]` / `[!reinforce]` 文内标注语法可零成本引入 notes 模板建议（非检查项，仅约定），列为可选；
- **Web UI / 角色权限 / 图谱可视化 / 研究计划编排**：MindForge 的产品化路线与 CodeWiki"嵌入 Agent 工作流"的形态正交，不跟进；
- **元数据后端组装**：已是 CodeWiki 现状（`_build_okf_frontmatter` / `_inject_frontmatter` / `_patch_existing_frontmatter`），无需开发；C 线落地后作为机制纪律写入 schema.yaml conventions 注释即可。
