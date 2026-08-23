# OpenViking 借鉴详细设计方案（P3 四项：声明式类型 · 遥测出口 · ReAct 提取 · 输入感知复核）

> 来源：`docs/OpenViking借鉴全景路线图.md` P3 档 V4–V7。V1–V3（P2 档）详细设计见 `docs/知识飞轮增强设计方案-P2三项.md`，本文不重复；V8/V9 属 P4 触发条件制，只到路线图粒度不做详设。
> 日期：2026-08-22 · 状态：**候选（评审中，未实施）** · 预计工作量：**4.5–5.5 人日**（四线独立，V6 建议 V4 之后）。
> 范围约束：沿用既有哲学——不新增 MCP 工具、能力长在现有工具上；零 LLM 依赖（V6 的 LLM 由调用方提供，与 distill 现状一致）；draft→confirm 闸门不动摇。
> 现状基线（详设依据，均为已核实源码事实）：freshness 窗口表在 `schema_generator.py` `_get_defaults()` 的 `conventions.freshness.by_type`（8 类硬编码）；lint 18 项检查含 `_check_stale_notes`（L918，判断级联 stale_after → metadata.date+类型窗 → 检索顺延豁免）；`telemetry.aggregate_usage(output_dir) -> {fp: {hits, last_hit}}`；adoption 落 `adoption_events` 表（`adoption.py`，capture_key 幂等）；distill 三模式（A 注入 llm 回调 / B 环境变量后台 / C prepare+submit），`_find_existing_note` 已做标题相似度查重。

---

## 一、V4：note_type 声明式收敛（schema 化）

### 1.1 问题

note_type 相关事实当前散在三处，历史上已产出一个 live bug：

| 事实 | 位置 1 | 位置 2 | 位置 3 |
|------|--------|--------|--------|
| 合法类型枚举 | `schema.yaml` conventions 段 | 各 handler 常量（`_ALL_CHECKS`、`PAGE_TYPE_DIRS`） | MCP `REGISTRY[name].schema.inputSchema` 枚举 |
| 类型窗口 | `schema_generator.py` `_get_defaults().freshness.by_type`（硬编码 8 类） | `repowiki/schema.yaml` 增量合并 | — |
| 晋升路由（pitfall→query/lesson→concept） | promote-note prompt（`prompts.py`） | — | — |

query_wiki type_filter 漏 "scenario" 的 bug 即枚举三处不同步所致。OpenViking 的借鉴点是**单一声明源**：12 类记忆全部声明在 YAML 模板里，handler 从表读。

### 1.2 设计：schema.yaml 内的权威段

在 conventions 段下新增 `note_types` 权威声明（schema.yaml 是唯一可配置载体，不新造文件）：

```yaml
conventions:
  note_types:
    pitfall:
      freshness_days: 180
      promote_to: query
      merge_fields: {body: append, related_modules: replace}   # V3 挂载点
    decision:
      freshness_days: 365
      promote_to: concept
      merge_fields: {body: append, related_modules: replace}
    # ... 其余类型同构；scenario 等现有类型一并入表
```

**生成与消费链**：

1. `schema_generator.py` `_get_defaults()` 的 `freshness.by_type` 改为从 `note_types` 表派生（保留旧键读取作向后兼容回退）——**模板、schema、生成器三处同步的老坑被结构消灭**，因为窗口只有一处定义。
2. 新增模块级校验函数 `validate_note_types(schema)`：核对 conventions.note_types 的键集合 ⊇ handler 实际接受集合，lint 启动时调用，不同步当场报错而非静默拒绝合法输入（正是 scenario bug 的防复发）。
3. promote 路由：`wiki_stats` 的 promotion_candidates 与 promote-note prompt 模板改为读 `promote_to` 字段（prompt 生成时做字符串替换），映射仍写进表作为默认。
4. **MCP inputSchema 枚举同步**：registry 注册时从 `note_types` 表生成 type_filter 枚举（注意坑：inputSchema 真身在 `REGISTRY[name].schema.inputSchema`，校验先于 handler）。首版接受"registry 在 server 启动时静态生成、表变更须重启"的约束——与 MCP server 需重启加载新 registry 的既有行为一致，不额外做动态刷新。

### 1.3 迁移

`scripts/migrate_note_types.py`（幂等，参照 migrate_freshness.py 模式）：读现有 freshness.by_type + promote prompt 映射，写入 note_types 表；跑两遍第二遍零 diff。存量 repowiki/schema.yaml 滞后于根模板属正常，增量更新合并，不强制批量迁移。

### 1.4 验收

表内声明的全部类型在 query_wiki type_filter 均可查询通过（scenario 回归用例）；从表删一个类型后 lint 报"handler 接受但表未声明"；freshness 窗口行为与迁移前逐条一致（既有 140+ 测试全绿）。

---

## 二、V5：遥测出口标准化（metrics 文本输出）

### 2.1 设计：只借 exporter 形态，不起服务

现状 `telemetry.aggregate_usage` 已产出 `{fp: {hits, last_hit}}`，adoption 有 `load_adoption_counts`——数据齐全，缺的是**标准格式的出口**。方案：`wiki_stats` 工具新增 `metrics: true` 参数（或独立子命令形态，实现取一），输出 Prometheus 文本格式（`text/plain; version=0.0.4`）到 stdout：

```
# HELP codewiki_note_hits_total Cumulative retrieval hits per note
# TYPE codewiki_note_hits_total counter
codewiki_note_hits_total{note="notes/pitfall-port-conflict.md"} 14
codewiki_note_adopted_total{note="notes/pitfall-port-conflict.md"} 3
codewiki_note_last_hit_timestamp_seconds{note="..."} 1786194673
# 汇总量
codewiki_notes_total{status="stable"} 62
codewiki_notes_total{status="draft"} 5
codewiki_adoption_events_total 87
codewiki_low_adoption_notes 2      # lint 第 17 项的计数口径复用
```

**边界**：latency 类指标现状无采集（BM25 检索快到不值得埋点），不为此加计时——OpenViking 的 latency 指标源于其向量检索场景，我们的瓶颈不在检索。exporter 每次调用即时聚合现有库（usage_map 已有缓存失效机制，bump mtime 即失效），无新增持久化、无常驻进程。

### 2.2 消费场景

单人：`wiki_stats metrics=true | grep` 直接看冷热；团队（未来）：Prometheus 抓取落盘文件或经脚本桥接。此项本质是给 P1-U 线的遥测数据开一扇标准门，为将来团队化预留，不预建基建。

### 2.3 验收

输出可被 promtool（若可用）或格式正则校验通过；hits/adopted 数值与 adoption.py / telemetry.aggregate_usage 直查一致；无检索记录的空库输出全零指标不报错。

---

## 三、V6：提取循环两轮化（distill v2）

### 3.1 问题与借法

现状 distill 是**单轮**：LLM 一次性从 transcript 产出 notes+memories，看不到库内已有笔记。OpenViking extract_loop 是带工具的 ReAct 循环（限 3 迭代）。全量 ReAct 化工程重（工具调度、迭代控制、防跑偏）；首版只做**两轮固定结构**——这是 ReAct 的最小有效子集：

```
Round 1（现状不变）：transcript → 候选 notes/memories JSON
Round 2（新增）  ：候选 × 库内现有笔记 → 修订指令 JSON
                  每条候选二选一：
                  { "action": "new" }                          # 库内无近邻，按原样出 draft
                  { "action": "merge", "into": "<note-id>",   # 有近邻，出合并建议
                    "fields": {...V3 策略} }
```

### 3.2 Round 2 的近邻检索

不引 embedding。`distill_conversation.py` 已有 `_find_existing_note`（标题 token 相似度）——扩展为双信号：标题相似度 + `_title_tokens` 交集投 BM25 一次（top-5）。候选笔记带 related_modules 的，同 module 笔记召回加权（复用检索 authority 权重的既有管道，dedup 豁免路径）。这条近邻检索**在蒸馏方进程内执行**（Mode A/B 的 distill 侧），不走 MCP 往返。

### 3.3 三模式的落点

- **Mode A**（注入 llm 回调）：Round 2 即第二次 `await llm(...)`，prompt 附 Round 1 候选 + 近邻笔记摘要（L0 abstract——V1 的直接受益者：近邻上下文用 abstract 而非全文，token 省一个量级）。
- **Mode B**（后台）：同 A，只是后台执行。
- **Mode C**（prepare+submit）：`prepare` 返回物新增 `neighbors` 段（每个候选的 top-3 近邻 note_id+abstract），IDE Agent 提取时自行判断 new/merge，`submit` 带回修订指令。**纯 MCP JSON 可走，不破坏 Mode C 的无状态约束**。

### 3.4 与 V3/V4 的组合

merge 建议的字段策略从 V4 的 `merge_fields` 表读（默认 append 正文/replace 元信息），人确认时看到的已是预合并 draft——V3 的 consolidate 管线无需变更，V6 的 merge 建议走 V3 同一条预合并代码路径，两线共享 `note_consolidation` 的字段策略实现。

### 3.5 明确不做

不做自由工具调用（LLM 自主决定查什么）——固定两轮足够覆盖"提取时看到库现状"的核心收益，自由 ReAct 的防跑偏成本不成比例；不做自动执行 merge——修订指令产出 draft/合并建议，闸门前不落任何 stable。

### 3.6 验收

构造"库内已有同主题笔记 + 新 transcript 再提一条"场景：v2 输出 merge 建议引用正确 note_id；无近邻场景输出 new 与 v1 行为一致；Mode C 的 prepare/submit JSON 往返不丢修订指令。

---

## 四、V7：新鲜度输入感知复核（freshness v3 前半）

### 4.1 借鉴点

OpenViking 冒泡规则：父摘要消费子项 L0 正文，**输入未变即停止传播**——复核的触发依据是"实际输入是否变化"，时间窗只是兜底。现状 `_check_stale_notes` 已有两信号（stale_after 时间窗、检索顺延豁免），本线加第三个：**输入触发提前复核**。

### 4.2 输入的定义

note 的"输入"= 其声明依赖的上游文档，两个现成来源：

1. `related_modules` frontmatter 字段（多数笔记有）→ 对应 `wiki/modules/*.md` 的内容 hash；
2. `ingest_source` 溯源（source_ingest 写入的来源文件路径，若有）→ 源文件 mtime。

**触发规则**：note 满足以下任一即进 pending 复核（报 lint warning「上游输入已变化」），不受 stale_after 是否到期限制：

- related_modules 指向的 module 文档内容 hash ≠ 笔记 ingest/confirm 时记录的 hash（新 frontmatter 键 `metadata.upstream_hash`，**写 metadata 嵌套段**——OKF 顶层白名单不含新键的历史坑，与 promoted_to 同理）；
- 溯源源文件 mtime 晚于笔记最近 confirm 时间。

### 4.3 实现落点

全部在 `_check_stale_notes` 内加分支，零新检查项（lint 项数不变，README/registry 文案不用再对账）：

1. 判断级联改为四层：输入变化 → 提前复核；stale_after 到期 → 复核期已过；检索顺延 → defer；否则 fresh。
2. hash 记录时机：ingest_note 与 confirm_note 落盘时计算并写 `metadata.upstream_hash`（related_modules 为空则跳过该信号）；缺该键的存量笔记静默跳过输入检查——不回填（迁移成本大于收益，随下次 confirm 自然补齐）。
3. 排序口径（U2 既有：overdue desc, last_hit asc）中"输入变化"优先级置顶——输入变了的笔记比单纯过期的更值得先看。

### 4.4 明确不做

不做 OpenViking 式"向上冒泡"（module 文档变化时连坐其全部笔记）——related_modules 显式声明的依赖边足够，隐式连坐误报率高；不做删除信号（上游删除暂不触发，broken_links 检查已覆盖链接失效场景）。

### 4.5 验收

修改 module 文档后 lint，其 related_modules 指向该文档的笔记出现在 pending 列表首位；hash 未变的相邻笔记不受影响；存量无 upstream_hash 笔记零报错零行为变化；`python -m pytest tests/ -o addopts=""` 全绿。

---

## 五、任务拆解与顺序

| # | 任务 | 线 | 依赖 | 量 |
|---|------|----|------|----|
| 1 | note_types 表 + 派生 freshness.by_type + validate_note_types + 迁移脚本 | V4 | 无 | 1 人日 |
| 2 | registry inputSchema 枚举从表生成（重启生效） | V4 | #1 | 0.5 人日（并入 #1 验收） |
| 3 | wiki_stats metrics 输出（Prometheus 文本） | V5 | 无 | 1 人日 |
| 4 | Round 2 近邻检索 + 三模式落点 + merge 建议接 V3 管线 | V6 | V3、V4（merge_fields）、V1（abstract） | 2–3 人日 |
| 5 | upstream_hash 写入 + _check_stale_notes 输入分支 | V7 | 无 | 0.5 人日 |

串行建议 V7 → V4 → V5 → V6（V7 最小且独立，先行练手；V6 吃 V1/V3/V4 三项的产出，殿后）。并行则 1/3/5 三线同启，4 待 V4。

## 六、风险与不做的事

**风险**：V4 迁移若与存量 schema.yaml 的 freshness.by_type 冲突，回退链须保证旧键优先级明确（表 > 旧键 > 硬编码默认，写入文档）；V6 Round 2 增加一次 LLM 调用，Mode B 后台任务时长约翻倍——蒸馏本就是异步重活，可接受，但须在 task_tracker 透出两阶段进度；V7 的 related_modules 指向不存在的 module 时（历史数据常见）静默跳过，不与 broken_links 检查重复报警。

**明确不做**（路线图第八节八项之外，本档新增三条）：不做自由 ReAct 工具调度（V6 固定两轮）；不做向上冒泡连坐复核（V7 只走显式依赖边）；不做 latency 埋点与常驻 exporter 服务（V5 按需输出）。
