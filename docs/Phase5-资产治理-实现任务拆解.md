# Phase 5 资产治理：实现任务拆解

> 对应 Roadmap Phase 5（5.1 资产置信分层 + 5.2 负反馈闭环）。
> 拆解日期：2026-08-21 · 状态：待排期
> 前置基础：L0-L3 记忆分层（已落地）、authority-aware 排序（`5de090f`，已落地）
> 总工作量估计：**8 个任务，约 10-14 人日**（不含评测）

---

## 依赖关系与实施批次

```
批次一（置信骨架）：
  T1 字段与流转 ──→ T2 排序集成 ──→ T3 检索露出
                                └──→ T4 统计分布
批次二（负反馈）：
  T5 误召回标记 ──→ T6 自动降权+复核清单 ──→ T8 负例反哺
批次三（新鲜度，可并行）：
  T7 新鲜度字段
```

批次一是批次二的前提（降权降的是 confidence）；T7 与任何批次无强依赖，可随时插入。

---

## 批次一：置信分层骨架

### T1：confidence_level 字段与状态流转

**目标**：资产获得显式置信维度，生命周期（status）与置信（confidence）成为两个正交维度。

**改动点**：
- `codewiki/mcp/tools/knowledge_loop.py`
  - `_apply_status_to_file`：新增可选参数 `extra_meta: dict`，YAML round-trip 时合并写入 `metadata`（confidence_level 放 metadata 折叠层，符合 OKF 生产者私有字段约定）
  - `handle_confirm_note`：确认时写 `confidence_level: weak`（confirmed 但无验证证据）；新增可选参数 `evidence`（`{test_ref?, commit_ref?, reviewed_by?}`）——携带任一证据则直接写 `strong` 并记录 `metadata.verification`
  - `handle_reject_note`：deprecated 资产同步写 `confidence_level: shadow`
- `codewiki/mcp/tools/note_consolidation.py` / `doctrine.py`：场景块与 doctrine 的 submit 写入默认 `confidence_level: weak`（产出即待验证）
- 存量迁移：`scripts/migrate_confidence.py`（幂等一次性脚本）——按现状态回填：stable→weak、draft→shadow、deprecated→shadow；scenario/doctrine 补 weak

**验收**：
- confirm_note 默认产出 weak，带 evidence 产出 strong（verification 留痕）
- 迁移脚本跑完，全部资产带 confidence_level；重复运行无副作用
- 测试：新增 `tests/test_confidence_lifecycle.py`（流转矩阵 + evidence 升级 + 幂等迁移）

**工作量**：2 人日

---

### T2：confidence 接入 authority 排序

**目标**：检索排序体现置信差异——strong 上浮、shadow 下沉。

**改动点**：
- `codewiki/mcp/cache.py`
  - `_CONFIDENCE_AUTHORITY = {"strong": +0.10, "weak": 0.0, "shadow": -0.30}`
  - `_doc_authority` 对 notes/scenarios/doctrine 读取 `metadata.confidence_level` 叠加（与现有 status gate 并存；clamp 0.7-1.3 不变）
  - raw/sources 的固定 -0.20 不变（未审阅第三方材料天然 shadow 语义）
- **关键不变量**：`distill_conversation._bm25_recall_candidates` 的 `apply_authority=False` 豁免保持——去重是相似度判断，不受置信影响（T1 迁移会把旧笔记降为 shadow，若去重被置信污染，冲突检测会漏报）

**验收**：
- 同查询下 strong 笔记排序高于内容同等相关的 shadow 笔记
- 去重召回候选不受 confidence 影响（回归现有两段式去重测试全绿）
- 测试：`tests/test_authority.py` 补 confidence 维度用例

**工作量**：1 人日 · **依赖**：T1

---

### T3：检索结果露出 confidence 与装配规则

**目标**：Agent 拿到结果时知道"什么能直接执行、什么只能参考"。

**改动点**：
- `codewiki/mcp/tools/knowledge_loop.py`
  - `handle_query_wiki` 结果条目增加 `confidence` 字段（读取模式同 `_note_source_ref`，frontmatter 解析）；新增参数 `include_shadow`（默认 false：shadow 资产只在你显式要的时候出现）
  - `handle_get_task_context` 的 related_notes 过滤：默认排除 shadow
- `_query_mode_overview`：doctrine 注入不变（doctrine 是 stable 前提下的最高层知识）；场景导航条目附带置信标记

**验收**：
- query_wiki 结果带 confidence 标注；默认不返回 shadow，`include_shadow=true` 时返回
- get_task_context 不再把 shadow 笔记带进任务上下文
- 测试：装配过滤用例

**工作量**：1.5 人日 · **依赖**：T1

---

### T4：wiki_stats 置信分布

**目标**：知识库健康度可观测——strong 占比是 Phase 5 的北极星指标（目标 >60%）。

**改动点**：
- `handle_wiki_stats`：新增 `confidence_distribution: {strong, weak, shadow}`（扫描 notes/ + scenarios/ frontmatter，缓存随 build_full_index 刷新）
- 顺带输出 `top_shadow_assets`（shadow 里被检索命中最多的前 5——它们是"该复核升级或该退役"的候选）

**验收**：wiki_stats 返回分布与 top_shadow_assets；lint 全绿
**工作量**：0.5 人日 · **依赖**：T1

---

## 批次二：负反馈闭环

### T5：flag_misrecall 误召回标记工具

**目标**：给"这条知识用错了"一个正式入口，误用事实留痕。

**改动点**：
- 新文件 `codewiki/mcp/tools/feedback.py`：`handle_flag_misrecall({asset, task_context?, reason})`
  - 写入资产 frontmatter：`metadata.misrecall = {count, last_at, last_reason, history: [{at, reason, task_context}...]}`（history 上限 10 条，防膨胀）
  - 同步 `update_file` 刷新索引（misrecall 本身暂不影响 authority，影响在 T6）
- `registry.py` 注册工具 schema

**验收**：重复标记同资产 count 递增、history 留痕；asset 不存在报清晰错误
**工作量**：1 人日

---

### T6：自动降权与待复核清单

**目标**：负反馈真正改变路由——"人的负反馈必须改变后续路由"（TAM 原则五）。

**改动点**：
- `codewiki/mcp/tools/feedback.py`：`_check_downgrade` —— misrecall count ≥ 阈值（`schema.yaml` `conventions.governance.misrecall_threshold`，默认 2）时：自动写 `confidence_level: shadow` + `metadata.misrecall.downgraded_at`；**只降 confidence 不动 status**（两个维度正交）
- 恢复路径：`confirm_note` 携带 evidence 时对 shadow 资产生效——升回 weak/strong 并清零 misrecall（复核即原谅，但留 history）
- `codewiki/mcp/tools/wiki_lint.py`：新增 `disputed_assets` 检查——列出 misrecall≥阈值或 confidence=shadow 且超过 30 天未复核的资产（warning），进入 `_ALL_CHECKS`（记得同步 registry.py 的 checks 枚举——本次验收期踩过的同步坑）

**验收**：
- 两次 flag 后资产自动变 shadow，检索排序下沉且默认装配不再带出
- confirm+evidence 恢复置信并清零计数
- lint disputed_assets 报出未复核清单
**工作量**：2 人日 · **依赖**：T5、T2

---

### T8：负例反哺（蒸馏/聚合提示）

**目标**：错误不止被降权，还要防止"换个马甲再来"。

**改动点**：
- `codewiki/mcp/tools/feedback.py`：`_misrecall_digest(output_dir, limit=5)` —— 汇总近期 misrecall 的 reason 摘要
- `distill_conversation(mode=prepare)` 与 `consolidate_notes(mode=prepare)` 响应增加 `negative_examples` 段：提示 Agent"以下模式曾被判为不适用/误用，提取时注意规避"
- （可选延伸）misrecall 达阈值时自动建议生成一条 pitfall 笔记（走 ingest_note draft，人工确认）——把负反馈本身变成知识

**验收**：prepare 响应带 negative_examples；内容与实际 misrecall 记录一致
**工作量**：1.5 人日 · **依赖**：T6

---

## 批次三：新鲜度

### T7：新鲜度字段与 stale 升级

> **已独立为专项**：见 [新鲜度机制设计方案](./新鲜度机制设计方案.md)（v2：零新增字段——去掉 valid_to，只激活 stale_after + 类型感知窗口 + 修复 lint 不读配置，拆为 F1-F3 共 2-3 人日，与置信分层解耦）。以下原始描述存档。

**目标**：过期判定从"按天龄粗判"升级为"按验证状态精判"。

**改动点**：
- frontmatter 新字段：`valid_from`（ingest/confirm 时写）、`valid_to`（可选，ingest_note 参数）、`last_verified_at`（confirm_note 时刷新，含复核场景）
- `codewiki/mcp/tools/wiki_lint.py` `_check_stale_notes` 判定顺序升级：valid_to 已过 → error；last_verified_at 超期（默认 180 天，schema 可配）→ warning；都没有 → 回退现有天龄逻辑
- `handle_confirm_note`：renew_stale_after 时同步写 last_verified_at

**验收**：带 valid_to 的资产过期即被 lint 报 error；confirm 刷新 last_verified_at 可推迟 stale
**工作量**：1.5 人日 · **依赖**：无

---

## 横向事项

| 事项 | 内容 |
|---|---|
| 配置 | schema.yaml 模板新增 `conventions.governance`（misrecall_threshold、shadow_review_days、verify_stale_days），参考 `conventions.aggregation` 的 read_config 模式 |
| 枚举同步 | 每次给 lint 加检查项，registry.py 的 checks 枚举必须同步（已有回归测试 `test_lint_wiki_schema_checks_enum_in_sync` 兜底） |
| 测试基线 | 全量套件当前 119 通过；每个任务交付时保持全绿 + 新增用例 |
| 文档 | 全部落地后：Roadmap Phase 5 状态更新；可写系列 5 文章（资产治理视角）；doctrine 刷新一次吸收新原则 |
| 评测锚点 | Roadmap 指标：strong 资产占比 >60%；负反馈后同查询重复误召回下降 ≥50%（需要真实使用积累数据，上线后观察） |

---

## 建议排期

1. **第一周**：T1 → T2 → T3/T4（批次一收官，置信分层可用）
2. **第二周**：T5 → T6 → T7（负反馈闭环 + 新鲜度）
3. **第三周前半**：T8 + 全量回归 + 文档收尾

风险点：T1 的存量迁移是唯一触碰存量数据的操作，先在分支跑迁移脚本 + 全量测试 + lint 三重验证再合入；authority clamp（0.7-1.3）在叠加 confidence 后是否仍够用，T2 需用真实语料验证排序体感，必要时调 clamp 而非调单项权重。
