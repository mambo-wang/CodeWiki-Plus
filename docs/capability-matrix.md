# CodeWiki 能力成熟度矩阵

> 基线：2026-09-12（develop）。所有「默认模式」取自代码静态默认值，非部署配置。
> 三态门控词汇（`off` / `observe` / `enforce`）见 `CONTEXT.md` glossary「tri-state gate」。
> 登记纪律：新增会改变知识内容或生命周期的能力必须登记本表，发布时更新（`CONTRIBUTING.md`）。
> 本表为手维护文档——HL-Mem 的同类矩阵已出现「标题六大、实际 7 条」漂移（`docs/HL-Mem-调研与借鉴分析.md` §八），登记时以代码为准，不接受转抄。

## 成熟度定义

- **stable**：默认主路径，契约与降级行为受回归测试保护。
- **beta**：可用且有保守默认值，需更多观察才能扩大自动化范围。
- **planned**：已立项未实施，登记防误当已生效。

## 检索与排序

| 能力 | 成熟度 | 默认模式 | 降级/边界行为 | 晋级标准 | 证据 |
|---|---|---|---|---|---|
| usage heat 排序 | stable | `enforce`（enabled=true，不可关） | 无记录中性 1.0；boost 封顶 0.15 | — | `codewiki/src/retrieval.py:523-533` |
| adopted 声明协议 | stable | 采集侧 `enforce`（自动提取） | 无声明但有搜索痕迹只打 adoption_nudge，不惩罚 | — | `codewiki/mcp/tools/adoption.py:6-33`、`capture_conversation.py:414-435` |
| authority 叠加（type×status×路径） | stable | `enforce` | 夹在 0.7-1.3 | — | `retrieval.py:445-461` |
| ontology 同义扩展 | beta | 存在 `ontology.yaml` 即生效（无独立开关） | 无文件即直通不展开 | 独立开关 + 评测收益 | `retrieval.py:281-299`、`wiki_search.py:678-680` |
| 图扩展（hop） | stable | `off`（hop=0），每跳衰减 0.5x | — | — | `wiki_search.py:69-70,591-592` |
| by_file 预检 | stable | `enforce`（默认开，max 15 条） | 只返回标题+est_tokens+status；**不计 usage-heat hit** | — | `note_query.py:493-500,604-613` |
| draft 笔记检索降权 | stable | `enforce`（-0.25，stable +0.05，deprecated -0.35） | — | — | `retrieval.py:453-457` |

## 知识生命周期

| 能力 | 成熟度 | 默认模式 | 降级/边界行为 | 晋级标准 | 证据 |
|---|---|---|---|---|---|
| 确认闸门（draft→stable） | stable | `enforce`（draft 不生效、带 `[unconfirmed]` 标注） | — | — | `note_query.py:1014-1018`、`note_lifecycle.py:56-92` |
| low_adoption 检查 | beta | `observe`（仅 warning） | 冷启动守卫：bundle 零 adopted 事件静默返回 | 升级为具体重写建议动作（Phase5 负反馈批次） | `wiki_lint.py:1267-1277,1342` |
| 反馈驱动生命周期（采纳延寿） | planned | 计划 `observe` 先行 | 延寿被笔记类型新鲜度上限夹住；保留冷启动守卫 | 离线证明「本应延长」分布无错误延寿，再议 enforce | `docs/HL-Mem-调研与借鉴分析.md` A3；公式 `feedback.py:36-37` |
| 冲突案卷（conflict case） | beta | `enforce`（手动声明，2026-09-12 落地；ADR-0007；不做自动发现） | 案卷不进检索语料、排除通用审计；query_wiki/by_file 命中 claimant 加 `open_conflict` 标注；open 超期（默认 14 天）lint warning | 真实使用中观察误报率与裁决流转时长，再议是否扩展 | ADR-0007、`conflict_case.py`、`tests/test_conflict_case.py` |
| memory recall（任务记忆检索） | beta | `enforce`（2026-09-12 落地；只读检索，无生命周期副作用） | 内存直算、零持久化；默认只搜本人（含本人 archive），他人须显式 `include_others`；legacy 文件可搜 | 观察 archive 命中率与真实召回需求，再议跨任务全局搜索 | `store.py` search_memories、`tests/test_task_memory_search.py` |
| 自动压缩驱动（compaction_action） | beta | `enforce`（compaction_due 时 get_task_context 携带派发指令；2026-09-12 落地，2026-10-09 由内联载荷 compaction_work 改为轻指令 + 异步子代理） | 主 Agent 只收指令不收条目正文（正文由子代理调 prepare 取，响应体积问题就此了结）；submit 由子代理显式发起，可逆（原文进 archive），ADR-0002 豁免确认闸门 | 真实使用观察子代理摘要质量与压缩频率（只在 red 派发） | `task_manager.py` `_compaction_action` / `_prepare_compaction_payload` |
| 置信分层（confidence_level） | beta | `enforce`（Phase5 T1，2026-09-13 落地：confirm 写 weak、evidence 升 strong、reject 降 shadow、ingest/consolidation 默认 weak） | draft 保持可见（[unconfirmed] 前缀），shadow 专用于 rejected/misrecalled；迁移脚本幂等回填 | strong 占比 >60%（北极星）；观察 evidence 使用率后再议强制证据 | `note_lifecycle.py`/`note_ingest.py`、`scripts/migrate_confidence.py` |
| 置信排序叠加 | beta | `enforce`（Phase5 T2：strong +0.10 / weak 0 / shadow −0.30，clamp 0.7-1.3 不变） | distill 去重召回 apply_authority=False 豁免保持（相似度不受置信污染） | 用真实语料验证排序体感，必要时调 clamp | `retrieval.py` `_CONFIDENCE_AUTHORITY`、`tests/test_confidence_lifecycle.py` |
| shadow 检索门控 | beta | `enforce`（Phase5 T3：query_wiki 默认滤 shadow，include_shadow 显式开启；task_context 排除 shadow） | by_file/mode=check 轻量路径暂不带门控（预检语义）；legacy 未标注资产不受影响 | 观察 shadow 误伤率，再议下潜到全部检索路径 | `note_query.py`、`tests/test_confidence_lifecycle.py` |
| outcome 采集（使用结果信号） | beta | `enforce`（2026-09-14 落地：report_outcome 遥测薄壳，doc+task_id 双挂，与 hit/adopted 同权免闸门；docs/负反馈与经验通道设计方案.md §三） | 采集侧无确认闸门（遥测非落盘知识，ADR-0002 同理）；task_id 尽力写（显式参数 > source_session_id 绑定）；adopted 关联只在同任务谱系内抄 key（跨任务不挂） | 消费全 observe（aggregate_usage success/failure + wiki_stats outcome_ratio + 负例反哺提示）；观察信号量攒够再议 disputed_assets lint | `outcome_report.py`、`telemetry.py` record_outcome、`tests/test_outcome_telemetry.py` |
| 负例反哺（negative_examples） | beta | `observe`（纯提示；2026-09-14 落地，设计文档 §四） | distill/consolidate prepare 携带近 30 天 failure outcome 的 {doc, note}（上限 5 条）+ 规避提示语；不改变任何提取/归纳行为 | 检索侧反哺（query_wiki 加 failure 标注）不实施——数据未攒够前不动消费端排序 | `distill_conversation.py` prepare、`note_consolidation.py` prepare、`telemetry.py` recent_outcome_failures |
| disputed_assets（消费预留） | planned | `off`（check 未实施；T6 观察化身后备，设计文档 §五） | 预留判据：failure ≥ 阈值（建议 2）且 success=0 且跨 ≥2 任务（独立失败才算数）；若未来升 enforce 走 confidence_level=shadow 通道 | outcome failure 数据攒够后再议是否实施 | 设计文档 §五 |

## 采集与蒸馏

| 能力 | 成熟度 | 默认模式 | 降级/边界行为 | 晋级标准 | 证据 |
|---|---|---|---|---|---|
| IDE 采集 hook | beta | `off`（环境变量或 `--enable` 开启） | 只采集不蒸馏；fail-open | — | `codewiki/mcp/_ide_hook.py:22-26,67-71,470-479` |
| distill Mode A（llm 回调） | stable | 显式选择 | — | — | `distill_conversation.py:9-27` |
| distill Mode B（后台 LLM） | beta | 显式选择（环境变量构建） | 缺环境变量报错 | — | `distill_conversation.py:871-891` |
| distill Mode C（IDE Agent 自当 LLM） | stable | 显式选择（prepare/submit） | 大载荷走 `distilled_file` 文件侧通道 | — | `distill_conversation.py:1638,1733-1734` |
| keep_raw（蒸馏后保留原文） | stable | `off`（默认删 raw） | — | — | `capture_conversation.py:326,366` |

## 归并与治理

| 能力 | 成熟度 | 默认模式 | 降级/边界行为 | 晋级标准 | 证据 |
|---|---|---|---|---|---|
| consolidate_notes | stable | 仅手动触发 | disposition 三值（absorbed/excluded/deferred），UPDATE>CREATE 协议 | — | `note_consolidation.py:411-413,50-54,582-639` |
| skill 两区制生命周期 | beta | 草稿区索引但 `query_wiki` 永不召回；install 为独立用户动作 | draft skill 不生效 | — | `skill_creator.py:35-38,689-745`、`wiki_search.py:706-710` |

## lint_wiki 检查项（25 项，默认 `checks=["all"]`）

error 级：`stale_refs` `broken_links` `okf_conformance` `scenario_capacity`（超容）`skill_sections` `skill_lint`（六类）。
warning 级：`undocumented`（依赖数≥5）`orphan_pages` `stale_sources` `overview_stale` `unsupported_claims`（阈值 0.3）`stale_evidence` `stale_notes` `low_adoption`（5/0/60 + last_hit 60 天窗口）`layout_violations` `team_layout_gitignore` `open_conflicts`（ADR-0007，超期窗口默认 14 天，schema.yaml `lint.open_conflict_max_age_days` 可调）。
info 级：`cycles` `coverage` `isolated_components` `no_outlinks` `missing_aliases` `superseded_pages` `note_clusters`（≥3）`scenario_orphan`。

证据：`codewiki/mcp/tools/wiki_lint.py:25-59,2270-2274`；阈值见各 check 实现行号（事实清单 2026-09-12，2026-09-12 复核更新至 25 项）。
历史注记：2026-09-12 首次登记时 registry 描述写「22 checks」实际 24 项——已在本轮修复（描述与枚举均同步 25）。

---

> 采集口径：2026-09-12 子代理源码扫描 + 主 Agent 抽核。本表不追求全量登记，只登记「已实现但默认不开」与「会改变知识内容/生命周期」的能力；stable 且无门控的基础能力仅列检索排序首行示例。
