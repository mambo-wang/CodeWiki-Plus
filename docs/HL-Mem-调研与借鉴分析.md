# HL-Mem 调研与借鉴分析（源码级）

> 调研日期：2026-09-11
> 调研对象：**lohr13/hl_mem** @ `aa5d0688`（v1.1.7，2026-09-09）——本地优先、证据驱动的 Agent 长期记忆系统。Python 3.12+ / SQLite WAL + FTS5 + 向量 BLOB / Apache-2.0。
> 对照对象：**CodeWiki-CN**（本仓库）。
> 调研方法：浅克隆源码（`.tmp/hl_mem`）后实读，与官方文档（README / `docs/architecture.md` / `docs/capability-matrix.md` / `docs/mcp.md`）交叉比对；两侧结论均落到 `文件:行号`。
> 规模实测：src 下 Python 约 53,517 行、测试文件 360 个、不可变 SQL 迁移 60 个（001–060）。
>
> **置信度声明**：机制与默认值均有源码证据。**HL-Mem 自报的量化晋级证据（precision 100%、Wilson 下界 ≥96%、143/143、37/37）未独立复核**，仅用于佐证"它把晋级写成可测数字"这一方法论，不作能力结论。

---

## 一、执行摘要

| 维度 | CodeWiki-CN | HL-Mem v1.1.7（代码实测） |
|------|-------------|--------------------------|
| 定位 | 项目级代码知识库（Markdown 为中心，git 版本化） | 单机 Agent 长期记忆系统（SQLite 为唯一权威存储） |
| 知识模型 | 模块文档 / 笔记（draft→stable）/ 场景 / doctrine / 任务记忆 | Event（不可变）→ Claim → Observation/Mental Model；另开 Experience 通道 |
| 时间模型 | 单轴：`stale_after` 复核期 + 按类型新鲜度窗口 | **双时间**：`valid_from/to` + `recorded_from/to` |
| 冲突治理 | **仅 prompt 约定**（矛盾写进 open-questions） | 案卷状态机 + 动作集 + revision/fingerprint CAS + 治理账本；自动模式默认 `l0_only` |
| 反馈去向 | 只进**排序**（heat 因子）+ `low_adoption` warning | 进**生命周期**（延长保留期），模式默认 `observe` |
| 来源权威 | 按 `note_type` + `status`；`raw/sources/` 按路径 −0.20 | 按声明来源类别（provenance 模式默认 `enforce`） |
| 曝光口径 | **召回即计 hit** | **只有被物化进 Context Packet 的条目**才获得曝光行 |
| 可答性 | `[unconfirmed]` 前缀 + `deprecated` 跳过 | `no_evidence`（硬弃答）/ `low_confidence`（软弃答）二分 |
| 删除 | 置 `deprecated`，文件保留，git 兜底 | tombstone sidecar 账本 + fail-closed 物理删除闭包 |
| 能力登记 | 无 | `docs/capability-matrix.md`：**37 条能力** × 成熟度 / 默认开关 / 降级行为 / 量化晋级标准 |
| 工具面 | 48 个 MCP 工具 | 7 个 MCP 工具（`memory_save/recall/get/correct/forget/explain/feedback`） |

**核心结论**

1. **两者是同一问题的两种解法，方法论高度互证。** HL-Mem 的 `domain/` 是纯函数、`application/` 持有事务边界、`ingest/admission.py` 是纯函数准入，依赖方向由脚本强制（`AGENTS.md:156-162`）——与本仓「工具做确定性簿记，推理在调用方」的 Team Doctrine 独立收敛到同一结论。**方向正确，不需摇摆。**

2. **本仓唯一的能力级缺口是「冲突没有身份」。** HL-Mem 把矛盾做成一等实体；本仓对矛盾只有一句 prompt 提醒（`note_consolidation.py:82-84`）。这是本轮第一优先建议。

3. **HL-Mem 最值得抄的是「默认保守」的纪律。** 危险能力默认值实测：`conflict.auto_mode=l0_only`（`config/models.py:534`）、`dedup.audit_only=True` 且 `dedup.llm_enabled=False`（`config/models.py:538,542`）、`feedback_lifecycle_mode=observe`（`config/lifecycle.py:246-249`）、`expired_cleanup_mode=observe`（`config/lifecycle.py:104-107`）、`state.latest_wins_mode=observe`（`config/models.py:506`）。**没有一项语义归并能力默认开启。**

4. **反馈必须能反噬生命周期，否则只是排序装饰。** 本仓已采齐 `hit/adopted/last_hit`（`retrieval.py:622-652`），但去向只有 heat；`low_adoption` 只发 warning（`wiki_lint.py:1339-1353`）。HL-Mem 让 usefulness 真正延长保留期，且**只在 `on` 模式生效**、**且被 `valid_to` 夹住**（`workers/ttl.py:37-43`）——延寿不得越过事实有效期。这个细节本仓可直接抄。

5. **它的重工程对 CodeWiki 是过度工程，明确排除。** tombstone 账本、双时间、CAS、decay 半衰期、60 个不可变迁移、事件流限流，都是"SQLite 单库 + 无版本控制"的自保手段；Markdown + git 已提供不可变历史、审计与回滚。判据见 §四。

---

## 二、文档与代码落差（方法论复核）

沿用本仓「竞品调研必须读源码」口径，先读文档再读代码，发现 1 处滞后：

| 项目 | 文档说法 | 代码实际 |
|------|---------|---------|
| 迁移数量 | `AGENTS.md:75` 写 "57 SQL migrations (001-057)" | **60 个**（`001_initial.sql` … `060_event_provenance.sql`，`storage/migrations/` 实测） |
| 迁移数量 | `docs/architecture.md` 写 "60 个不可变迁移 001–060" | 一致（架构文档是对的） |

另有文档自述瑕疵：`docs/capability-matrix.md` 小节标题写「六大特性」，表内实际 **7 条**——该矩阵为手维护。

**启示**：落差很小，但再次印证本仓既有 stable 笔记「借鉴调研先证伪」的姊妹结论——**他仓文档必须落到源码才算证据**。

---

## 三、机制真相（源码级）

### 3.1 写入管线：LLM 只做提取，其余全确定性

```
7 字段 compact LLM 提取 → AdmissionPolicy（纯函数准入）→ 完整 schema 后处理
→ fact_hash v2 精确去重 → conflict_key 确定性冲突解析 → observation-gated 时间关链
→ 灰区冲突 LLM 四路合并（默认关）→ 保守 near-copy 复用 → 嵌入 + 证据链接
→ 单一 BEGIN IMMEDIATE 事务提交
```

### 3.2 冲突治理（本仓唯一无对应物的能力）

- **案卷身份**：`(namespace, group_key, generation)` 下只有一个 open case 持有全部候选；状态机 `pending → auto_resolved/manual_required → resolved/rejected`。
- **CAS 不变量**：`workers/auto_resolve_conflicts.py:53-71` —— `BEGIN IMMEDIATE` 内**重读 revision 与 docket fingerprint**，不匹配即抛 `StaleConflictDecision`；mutation 与 ledger **同事务**。
- **动作集**：Pair = `keep_left / keep_right / coexist / reject`；Group = `select_candidate` + 破坏性 `reject_candidate`（需显式撤回确认），见 `:86-120`；**终态理由不可变**。
- **自动模式边界**：`domain/governance.py:236-237` `decide_l0`「按不可交换顺序执行六条确定性法条」；默认 `l0_only`——只有确定性规则能改 Claim，LLM 归并只写 `audit_only:<kind>`。
- **策略版本化**：`domain/governance.py:26` `CONFLICT_AUTO_POLICY_VERSION = "conflict-auto-v1"`，随 `DecisionEnvelope` 落账本。

### 3.3 反馈 → 生命周期：默认观察，开启即真实延长

`config/lifecycle.py:8` 定义 `FeedbackLifecycleMode = Literal["off","observe","on"]`，默认 `observe`（`:246-249`）。生效点 `workers/ttl.py:35-43`：

```python
base = expires_at
effective = base
if feedback_lifecycle_mode == "on" and row["bonus_days"] > 0:
    effective = base + timedelta(days=row["bonus_days"])
    if row["valid_to"]:
        effective = min(effective, valid_to)      # 延寿不得越过事实有效期
```

`bonus_days` 来自 `memory_usefulness.retention_bonus_days`；参数 `feedback_bonus_every=3` / `feedback_bonus_days=14` / `feedback_bonus_cap_days=180`（`config/lifecycle.py:251-258`）。**两层约束让"反馈驱动"不会退化成"热度掩盖过期"。**

### 3.4 曝光口径：只有被交付的条目才算曝光

- `application/context_packet.py:197-199`：`RetrievalBundle` docstring 明确「不包含 feedback_id 或 delivery receipt」；`:219` 序列化处注释「wire payload 永不携带 feedback_id」。
- `:454-467`：只在 assembly/materialize 时为每个 item 生成 `feedback_id` 并写 exposure。即**物化 = 曝光 = 获得 feedback 行**。
- `api/routes/recall.py:114-122`：`/v1/internal/retrieval-feedback/injected` 在交付边界之后才标记 `injected`，**只标记不写 outcome**。

### 3.5 能力矩阵：把"能不能上线"变成可测问题

`docs/capability-matrix.md` = 37 条能力 × 4 列：成熟度（stable/beta/experimental）/ 默认模式 / 降级行为 / 量化晋级标准。抽样：

| 能力 | 成熟度 | 默认 | 晋级标准（摘） |
|---|---|---|---|
| 冲突处理 | stable | `l0_only`；LLM consolidation `off` | CAS/ledger/rollback 不变量全绿；语义审计零状态突变 |
| Near-copy dedup | beta | 确定性 review `on`；LLM `off`；`audit_only=true` | precision 100%、Wilson 下界 ≥96%、硬守卫违规 0 |
| 反馈驱动维护 | beta | `observe` | **离线证明生命周期收益且无错误延寿/衰减**，再考虑默认 `on` |
| 关系候选发现 | beta | `off` | proposal precision 达阈值、人工批准边保持证据闭环 |

后两列写的是"失败时退到什么"与"可复算的数字/不变量"，而非"效果好就上"。

---

## 四、逐项对照与判定（证伪优先）

| # | HL-Mem 候选 | 本仓现状（本次实读） | 判定 |
|---|---|---|---|
| C1 | 冲突案卷 + 动作集 + 人工裁决 | 冲突仅 prompt 约定（`note_consolidation.py:82-84`）；`reject_note` 只能置 deprecated（`note_lifecycle.py:93-123`）。**无 case 实体、无动作集、无裁决接口** | **absorbed** |
| C2 | 能力成熟度矩阵 | `docs/` 89 个 md，无此类登记表 | **absorbed** |
| C3 | 反馈驱动生命周期（延寿被 `valid_to` 夹住） | 信号已采齐（`retrieval.py:622-652`）但只进排序；`low_adoption` 只 warning（`wiki_lint.py:1212-1241,1339-1353`） | **absorbed** |
| C4 | 三态开关 `off/observe/enforce` + 保守默认 | 有零散影子机制（`[unconfirmed]` `note_query.py:1017-1018`、draft 降权 `retrieval.py:454`、lint 只报不改），**无统一约定** | **absorbed**（约定层） |
| C5 | 曝光口径 = 被物化条目 | `note_query.py:1248-1252`：**每个返回结果都记 hit**，且 fallback 到 title/path | **deferred** |
| C6 | 来源权威按 provenance 声明 | 按 `note_type`+`status`（`retrieval.py:445-457`）+ 路径（`raw/sources/` −0.20，`:476-477`） | **deferred** |
| C7 | 可答性二分 | 有 `[unconfirmed]` 软标注 + `deprecated` 跳过（`note_query.py:1014-1018`），未区分"无候选"与"弱候选" | **deferred** |
| C8 | 双时间模型 | 单轴 `stale_after` + `note_freshness` 窗口；确认时续期（`note_writer.py:209-222`） | **excluded** |
| C9 | tombstone 账本 + manifest v2 + 恢复回放 | `deprecated` 状态 + 文件保留 + git | **excluded** |
| C10 | CAS + 治理账本 + 60 个不可变迁移 | 无独立 DB；schema 由 `page_router.load_schema` 松加载 | **excluded** |
| C11 | decay 半衰期 / 多档 TTL / 归档清 embedding | 本仓 `decay` 仅指**图跳衰减**（`wiki_search.py:70`、`cache.py:1277,1748`）与检索分衰减；`TTL` 仅会话级 2h。**知识条目无衰减/归档** | **excluded** |
| C12 | Event 幂等摄入 + 分批窗口 + 抽取预算 | 输入是 Agent 主动调用的 `capture_conversation`/`distill_conversation`，非常驻事件流 | **excluded** |
| C13 | 7 字段紧凑抽取 + 上限告警不伪造 | Mode C 的 `submit` 契约已同构 | **excluded（已覆盖）** |
| C14 | 配置 fail-closed（未知键拒启动） | `schema.yaml` 缺失取默认、未知键宽容 | **deferred** |
| C15 | typed canonical entity + slot/tags | 本仓有 `repowiki/ontology.yaml` 本体表 | **excluded（部分重叠）** |
| C16 | 确定性时间关链三分支 | 无 | **excluded**（本仓无对应问题面） |

**合计 16 项：4 absorbed / 5 deferred / 7 excluded。**

### deferred 与 excluded 的原因（必填）

**C5 曝光口径 — deferred**：HL-Mem 写法更干净，但本仓 `hit` 还承担**冷启动保护**（无记录即中性 1.0，见 `retrieval.py:516-517` 注释立场）。拆成 `retrieved`/`injected` 需先定义本仓的"注入判定点"（本仓无交付边界事件，上下文注入由 IDE 完成）。**前置条件：先有足够 `adopted` 样本。** 建议与 C3 同批评估。

**C6 provenance — deferred**：`raw/sources/` 是强约定目录，按路径 −0.20（`retrieval.py:476-477`）与 `external → low authority` 语义等价而成本更低。引入字段需改 OKF frontmatter schema 与全部写入路径，收益不足。**若将来出现"agent 自主蒸馏内容混入 `notes/`"的具体问题再立项。**

**C7 可答性二分 — deferred**：本仓 `query_wiki` 的读者本身就是 Agent，`[unconfirmed]` 已提供充分置信提示，且 `raw/` 不进检索已消除一大类低质候选。**降级处理：无结果时明确回"未检索到相关文档"，比新增枚举更划算。**

**C11 衰减/归档 — excluded**：本仓价值主张是"确定性排序、可解释"（全链路无 LLM 重排），半衰期会让排序无法用人话解释。已有更保守替代：`cold_penalty`（仅"曾热过且冷了"扣分，`retrieval.py:599-612`）+ `stale_after` + lint stale 检查。**保留负反馈的离散形态，不引入连续衰减。**

**C14 配置 fail-closed — deferred**：HL-Mem 的 `Settings` 是运行时契约，拒启动合理；本仓 `schema.yaml` 是随仓库分发的**约定模板**，用户可能自定义扩展，全局 fail-closed 会产生大量伪造失败。**可取的子集：只对关键字段（如 `conventions.usage_ranking.*`）校验类型与取值范围，非法值报错而非静默取默认。**

**C8/C9/C10/C12/C16 — excluded**：均为「SQLite 单库 + 无版本控制 + 常驻事件流」环境下的自保手段，本仓 git + 同步 MCP 工具 + 主动调用式输入，无对应问题面。

---

## 五、absorbed 项落地建议

### A1（最高优先）把「矛盾」做成一等对象

**目标**：两条笔记矛盾时能表达"这是一处待裁决冲突"，而非让 Agent 在 prompt 里自记一笔。

**最小实现（刻意降复杂度）**：
- 新增 `conflict` 页面类型（或 `notes/conflicts/<slug>.md`），frontmatter 携带 `claimants: [notes/a.md, notes/b.md]`、`group_key`、`status: open|resolved`、`resolution`、`resolved_by`、`resolved_at`。
- 新增 `flag_conflict`（创建）+ `adjudicate_conflict`（裁决，动作集沿用 `keep_a / keep_b / coexist / reject`）。
- **裁决复用现有原语**：`keep_a` 内部即"对 b 调 `reject_note` 并写明 reason"——`reject_note` 的 deprecated + reason 机制已存在（`note_lifecycle.py:93-123`），**不需要新建状态机**。
- **账本 = git**，不做独立 ledger；裁决写入 frontmatter 即留痕。
- **不做的部分**：CAS / fingerprint 并发控制（本仓单写者 + git）、自动裁决（本仓无 `conflict_key` 确定性底座）、`generation` 世代（文件系统足够）。
- **接入检索**：`open` 冲突双方在 `query_wiki` 结果中标注"存在未裁决冲突"，避免 Agent 只看到一半。
- **接入 lint**：`open` 冲突超期未裁决 → warning。

**验收**：能创建 → 能裁决 → 败者变 deprecated 且带 reason → 双方检索结果均带冲突标注 → 全程 git 可审计。

### A2 能力成熟度矩阵（`repowiki/capability-matrix.md`）

一张表：能力 / 成熟度（`stable|beta|experimental`）/ 默认开关 / 降级行为 / 晋级标准（可测数字或可测不变量）。首批登记对象：`low_adoption`（现仅 warning）、`usage heat` 三参数（`boost_cap`/`cold_penalty`/`adopted_weight`）、检索各通道（本体扩展、图扩展 hop 衰减、authority 叠加）、`lint_wiki` 各 check 的默认开关与阈值、采集 hook（默认关）、`distill_conversation` 三种 Mode。

**价值**：让"已实现但默认不开"变得可见，避免被误当已生效。成本仅一次编写 + 发布时更新。

### A3 反馈从「排序」走向「生命周期」（对应 Phase5）

信号侧零改动，只加动作：
1. **采纳加成保留期**（抄 `workers/ttl.py:37-43` 的双重夹紧）：`adopted_count` 达阈值 → 延长 `stale_after`，但**被该笔记类型的新鲜度上限夹住**。默认 `observe`：先只记录"本应延长多少天"，不改实际值。
2. **零采纳 → 重写候选动作**：对 `hit_count` 高、`adopted_count = 0`、且 `note_type != decision` 的笔记产出**具体重写建议**（现有 suggestion 为 i18n 文案，可升级为动作项）。
3. **保留冷启动守卫**：`_check_low_adoption` 已有"零 adopted 事件时不报任何 issue"的机制（`wiki_lint.py:1233-1236`），此纪律必须保留。

### A4 把三态开关写成约定

`off / observe / enforce` 三态命名 + "新能力默认 observe，用数据换 enforce"写进 Team Doctrine / `CONTRIBUTING.md`。成本近零，收益是让 A2 的矩阵有统一词汇。**注意**：本仓已有部分等价物（`[unconfirmed]`、`draft`、lint 只报不改），**不要重复造，只需统一命名**。

---

## 六、明确不借鉴

| 不借鉴项 | 原因 |
|---|---|
| 双时间模型（四字段） | 概念准确但写入门槛高；`stale_after` + git blame 已能回答"当时系统知道什么" |
| tombstone sidecar + manifest v2 + 恢复回放 | 无版本控制环境下的自保手段；git 天然提供不可变历史与回滚 |
| revision/fingerprint CAS + 治理账本 | 同上；本仓是单写者同步 MCP 工具，无并发竞争问题面 |
| 60 个不可变迁移 + migration runner | 无独立 DB 时的需要；本仓松加载已够 |
| decay 半衰期 / 多档 TTL / 归档清 embedding | 破坏确定性可解释性；`cold_penalty` + `stale_after` 是更廉价的离散替代 |
| Event 幂等摄入 + 分批窗口 + 抽取预算裁剪 | 本仓输入是主动调用，非常驻事件流 |
| provider 插件 allowlist + 宿主用量代理 | 本仓无第三方 provider 插件生态 |
| Experience 通道（Episode/Trace/Policy 归纳） | 与任务记忆 + 场景块职责部分重叠但形态不同；**值得单独立项评估，本轮不 absorb** |

---

## 七、附录：证据索引

### HL-Mem 侧（本次实读）

| 结论 | 证据 |
|---|---|
| 冲突自动模式默认 `l0_only` | `src/hl_mem/config/models.py:534` |
| L0 六条确定性法条 | `src/hl_mem/domain/governance.py:236-237` |
| 冲突策略版本常量 | `src/hl_mem/domain/governance.py:26` |
| CAS：revision + fingerprint，mutation 与 ledger 同事务 | `src/hl_mem/workers/auto_resolve_conflicts.py:53-104` |
| 冲突动作集 | `src/hl_mem/workers/auto_resolve_conflicts.py:86-120` |
| dedup 默认 audit-only、LLM 关闭 | `src/hl_mem/config/models.py:538,542` |
| 反馈模式默认 `observe` | `src/hl_mem/config/lifecycle.py:246-249` |
| 反馈加成生效点（被 `valid_to` 夹住） | `src/hl_mem/workers/ttl.py:35-43` |
| 反馈加成参数 | `src/hl_mem/config/lifecycle.py:251-258` |
| 过期清理默认 `observe` | `src/hl_mem/config/lifecycle.py:104-107` |
| `latest_wins_mode` 默认 `observe` | `src/hl_mem/config/models.py:506` |
| provenance 模式默认 `enforce` | `src/hl_mem/config/models.py:501` |
| Bundle 不携带 feedback_id | `src/hl_mem/application/context_packet.py:197-199, 219` |
| 物化时才分配 feedback_id 并写 exposure | `src/hl_mem/application/context_packet.py:454-467` |
| `/injected` 只标记不写 outcome | `src/hl_mem/api/routes/recall.py:114-138` |
| 60 个不可变迁移 | `src/hl_mem/storage/migrations/001_initial.sql` … `060_event_provenance.sql` |
| 能力矩阵 37 条 | `docs/capability-matrix.md` |
| MCP 七工具 | `docs/mcp.md` §4.1 |
| 文档滞后（57 vs 60） | `AGENTS.md:75` vs `storage/migrations/` 实测 |

### CodeWiki-CN 侧（本次实读）

| 本仓结论 | 证据 |
|---|---|
| 采纳声明协议（HTML 注释） | `codewiki/mcp/tools/adoption.py:32-35` |
| 采纳事件持久化 / 聚合 | `codewiki/mcp/tools/adoption.py:142-199` |
| `low_adoption` check 注册 | `codewiki/mcp/tools/wiki_lint.py:53-54` |
| `_check_low_adoption` 阈值（5/0/60）+ 冷启动守卫 | `codewiki/mcp/tools/wiki_lint.py:1212-1241` |
| `low_adoption` issue 仅 warning | `codewiki/mcp/tools/wiki_lint.py:1339-1353` |
| confidence / evidence 标记扫描 | `codewiki/mcp/tools/wiki_lint.py:926-941` |
| note_type + status 权威偏移 | `codewiki/src/retrieval.py:445-457` |
| 路径权威（`raw/sources/` −0.20） | `codewiki/src/retrieval.py:476-477` |
| 召回即记 hit | `codewiki/mcp/tools/note_query.py:1248-1252` |
| `record_hit` 同日合并写入 | `codewiki/mcp/tools/telemetry.py:139-143` |
| heat 参数（`adopted_weight=0.06` 为召回 2×） | `codewiki/src/retrieval.py:528-533` |
| `compute_usage_heat`（含 cold_penalty） | `codewiki/src/retrieval.py:565-612` |
| usage 聚合加载 | `codewiki/src/retrieval.py:622-652` |
| 冲突仅 prompt 约定 | `codewiki/mcp/tools/note_consolidation.py:82-84` |
| 血缘 `consolidated_into` ⇄ `source_notes` | `codewiki/mcp/tools/note_consolidation.py:19-26` |
| `confirm_note` 确认 + 续期 | `codewiki/mcp/tools/note_lifecycle.py:56-92` |
| `reject_note` 置 deprecated + reason | `codewiki/mcp/tools/note_lifecycle.py:93-123` |
| `stale_after` 续期 | `codewiki/mcp/tools/note_writer.py:209-222` |
| 新鲜度窗口 | `codewiki/mcp/tools/note_freshness.py:26,76,94` |
| draft 标注 `[unconfirmed]` | `codewiki/mcp/tools/note_query.py:1014-1018` |
| 知识条目无 decay/TTL | `decay` 仅见于 `codewiki/mcp/tools/wiki_search.py:70`、`codewiki/mcp/cache.py:1277,1748` |
