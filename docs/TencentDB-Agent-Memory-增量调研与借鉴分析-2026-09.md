# TencentDB-Agent-Memory 增量调研与借鉴分析（2026-09-10）

> 增量对象：**TencentCloud/TencentDB-Agent-Memory** @ `906b582`（2026-09-10，分支 `feat/server_team`），本地克隆 `D:\repos\TencentDB-Agent-Memory`
> 基线：`docs/TencentDB-Agent-Memory-记忆提取机制分析.md`（2026-08-16，v2.0.1-beta.2 @ `97f9465`）
> 视角：自上次借鉴以来，哪些新合入值得 CodeWiki 借鉴
>
> 调研方法：`git log 97f9465..origin/feat/server_team`（**17 个 commit**）+ CHANGELOG（2.0.1 / 2.0.2-beta.1）
> + 关键 diff 实读 + 本仓代码对照 + 探测脚本实测。
> 他仓论断落到 `文件:行号`（相对 TAM 仓库根，`origin/feat/server_team`）；本仓对照落到 CodeWiki 的 `文件:行号`。
>
> 处置规则沿用上一份增量调研（teamai-cli）：**先证伪再立项**——他仓新增 ≠ 本仓缺口；
> 涉及「有没有漏掉」的判断必须用探测脚本实测计数，不靠直觉。

---

## 0. 增量概览

| 项 | 上次（2026-08-16） | 本次（2026-09-10） |
|---|---|---|
| 版本 | v2.0.1-beta.2 | v2.0.2-beta.1 |
| 新增提交 | — | **17**（其中代码改动 8，文档/部署 9） |
| 主线工作 | L0–L3 分层记忆管线、Skill 沉淀 | **宿主适配广度**（OpenCode / dsh / Codex CLI / WorkBuddy / Pi）+ **服务端部署形态**（Mongo 后端、OAuth2、ClickHouse 埋点）+ **Proxy 会话注册健壮性修复** |
| 记忆机制层变化 | — | **无**（L0–L3 管线、SceneExtractor、PersonaTrigger 均未动） |

一句话：这 25 天 TAM 把力气花在**接入广度与服务器运维形态**上，记忆分层/提取机制本身零改动；
而我们上次借鉴的正是机制层（L2 场景聚合 → `consolidate_notes`、L3 → `refresh_doctrine`，均已落地）。
因此本次 **0 项采纳**，但有三处值得写下来的对照结论（§1），其中一处是交叉印证（§3）。

---

## 1. 同层面的三个真实代码改动与对照

### 1.1 #1131 task 从「必填门禁」降级为「可选业务维度」— 不借鉴（设计取向相反）

**他仓改动**（`0afa626`）：Proxy 原先要求 team + agent + task 三者齐全才注册会话，缺 task 一律 bypass，
导致「用户不会预先建任务」的场景**静默丢记忆**。改为：

- `MemoryProxy/src/session/preset.ts:115` — `res.canRegister = !!res.agentId && !res.hadMismatch;`
  （不再要求 `res.taskId`；stale/unknown task_id 也不再翻转 `hadMismatch`，见 `:101` 注释）
- `MemoryProxy/src/session/codebuddy/init.ts` — 删除 `if (!resolved.task_id) → bypass` 守卫；
  stale task 只 warn 不阻断（`:816` 起的 warn 分支）
- 内核依据：`MemoryCore/src/core/store/isolation.ts` — taskId 只是 L0/L1 过滤的**可选业务维度**，
  记忆主键是 `(team, user, agent, session)`，缺 task = 宽召回，不是失败

**本仓对照**：

- 任务本来就可选：会话开局弹框有「跳过（本次不做任务关联）」选项；未关联任务的对话**照样采集**
  （本次 `get_task_context` 显示 pending 中「未关联任务: 2 条」）。不存在静默丢弃。
- 未知 task_id：显式报错 `"Task '<id>' does not exist."` — `codewiki/mcp/tools/task_manager.py:619-622`，
  并有测试钉住 `tests/test_task_manager.py:140`。

**裁决：excluded。** 剩下的真实差异是 stale task 的处理方向：TAM 选「静默降级 + 宽召回」，
CodeWiki 选「显式报错」。本仓 Doctrine 明确「不静默失败」，且本仓 task_id 来自本地任务索引、
不存在跨服务 stale 语义，显式报错更优。这是**主动不同的设计**，不是缺口。

### 1.2 #1129 缓存未命中不再静默绕过 — 不借鉴（本仓无同类缺陷）

**他仓 bug**（`9cdfcf0`）：`SessionStore.getOrRecover()` 在绑定/缓存未命中时走 `tryHistoryScan`，
而 history scan 只认交互式选择的 **form marker**；header 身份的 agent（如 Pi）从不产生 form marker，
于是被无条件 bypass。又因 `getOrRecover` 跑在 `handleSessionInit` 之前，冷启动**完全拿不到记忆**。
修复：把 header 解析出的 `presetIdentity` 透传进 `RecoveryContext`
（`MemoryProxy/src/session/store.ts:65`），命中时直接 `return undefined` 跳过 history-scan
（`:690`），交由 `handleSessionInit` 的 headerAutoSelect 路径处理。

**本仓对照**：hook 侧的 fail-open 只影响「提示注入」这一层，**不阻断采集**——
`codewiki/hooks/task_session_start.py:122-166` 的 `_count_pending_raws` 在任何异常下返回 `{}`
并注明 "never breaks task binding"；陈旧索引条目也已就地跳过（`:146` "stale index entry"）。
即：我们退化的是**提示**，不是**记忆写入**；恰好避开了他们踩的坑。

**裁决：excluded（无缺陷可修）。**

### 1.3 #90a3d37 L0 写入前丢弃 harness 运行时快照 — 本仓已有等价机制（顺手补一行待裁决）

**他仓改动**：DSH 把运行环境快照作为独立 `role=user` 消息追加在真实提问之后，
而 L0 抽取器 `extractLatestUserMessage` 从后往前扫，于是把 harness 元数据当成用户提问写入 L0 并污染 L1。
修复：新增锚点 `MemoryProxy/src/common/user-query-extractor.ts:84` `DSH_RUNTIME_CONTEXT_PREFIX = "Current runtime context."`、
`:86` `isDshRuntimeContextSnapshot()`，在 `:106` **整条丢弃**。

**本仓等价机制已存在**：`codewiki/mcp/tools/capture_conversation.py:180-201`
`_FRAMEWORK_NOISE`（`(session bootstrap)`、`NO_REPLY`）+ `_FRAMEWORK_NOISE_PREFIXES`
（`A new session was started via`、`Pre-compaction memory flush`），宽松门 `_should_capture_l0` 落盘前过滤。

**实测（探测脚本 `probe_l0_noise.py`）**：扫描 79 个会话文件（conversations + raw），
命中候选噪词 24 个（30.4%），拆解后：

| 命中项 | 文件数 | 性质 |
|---|---|---|
| `@command://` | 19 | **误报**——用户真实引用命令文件（`@command://codewiki-…`），是内容不是噪声 |
| `<manually_attached_skills>` 块 | 8（10.1%） | **真噪声**：harness 注入的技能列表，但**附着在真实提问之前**（同一条 user 消息内） |
| `【项目定向】` 等旧版系统注入 | 1（1.3%） | **真噪声**（历史遗留，现版提示词已改） |

真噪声率 **11.4%**，低于 20% 阈值。且与 TAM 的 DSH 快照危害等级不同：
他们的噪声是**独立消息**→ 整条 L0 变成元数据；我们的噪声**与真实提问共存** → 只稀释，不致错。

**裁决：excluded（不作为借鉴项）。** 附一条顺手清理建议：把 `<manually_attached_skills` 加进
`_FRAMEWORK_NOISE_PREFIXES`（`capture_conversation.py:186-189`，一行），改用**前缀**而非整串集合，
因为它后面总是跟着真实提问，整条丢弃会误伤。**是否做由用户裁决，本轮不动代码。**

---

## 2. CHANGELOG 层面新能力的逐条处置

来源：`CHANGELOG.md` 的 2.0.1（2026-08-25）与 2.0.2-beta.1（2026-09-07）。

| 新能力 | 本仓现状 | 处置 |
|---|---|---|
| MongoDB 存储后端（可选，默认 sqlite） | ADR-0001 钉死 markdown 存储；切换后端不迁数据 | excluded（形态不同，且我们无服务端数据面） |
| OAuth2 对接企业 OA 登录 | 无服务端、无账号体系 | excluded |
| ClickHouse 埋点 + 数据分析页 | 已有 `.meta/telemetry/` 埋点 | excluded |
| 异常技能数据**自动修复**、旧资产兼容 | 技能走 draft/confirm 三态，自动修复会绕过确认闸门 | excluded（Doctrine：绝不静默确认） |
| 新建技能立即可被检索、无搜索盲区 | 无持久索引，技能靠文件扫描匹配（`codewiki/src/skill_match.py:1-30`），新建即生效；ADR-0004 只索引草稿区元数据 | excluded（架构不同，不存在索引滞后） |
| 团队/Agent 选择列表完整展示、不再漏选 | 本仓同日已修：`0c9fc2e`「SessionStart 任务关联只弹一个框，一框列全部进行中任务」 | excluded（已解决，见 §3 交叉印证） |
| 对话内创建/更新任务、一键重置绑定 | 弹框内置「新建任务…（直接输入名称）」，`create_task` 已覆盖 | excluded |
| 会话绑定持久化、重启不丢 | `.meta/task_bindings/<session>.json` 落盘持久化 | excluded |
| 新宿主适配器（OpenCode / dsh / Codex CLI / WorkBuddy / Pi） | hook 已覆盖 5 宿主（`task_session_start.py:90-98` 的 CODEBUDDY/QODER/GEMINI/TRAE/CLAUDE `*_PROJECT_DIR`） | excluded（广度扩展，非能力缺口） |
| 修「记忆召回为空」「检索降级不生效」 | 本仓刚处理过三类静默降级（笔记 2026-09-10-知识管线三类静默降级…） | excluded（已覆盖） |

---

## 3. 交叉印证：同一个坑，两边独立收敛

TAM 2.0.2-beta.1「团队 / Agent 选择列表完整展示，团队较多时不再漏选」
与 CodeWiki `0c9fc2e`（2026-09-10，同日）「任务关联只弹一个框，一框列全部进行中任务」是**同一类问题**：
多选列表在条目变多时被 UI 层截断/拆框，用户选不到后半截。两边在互不知情的情况下各自收敛到
「一框列全」。这条不是借鉴，是对本仓该修复的**独立佐证**——说明这是多宿主 harness 的共性约束。

---

## 4. 结论

| 指标 | 结果 |
|---|---|
| 增量提交 | 17（代码 8 / 文档部署 9） |
| 候选项 | 10（代码 3 + CHANGELOG 7，去重后） |
| **采纳** | **0** |
| excluded | 10（均有本仓等价实现或设计取向相反） |
| 顺手清理（待用户裁决） | 1：`<manually_attached_skills` 加入噪声前缀表 |
| deferred | 0 |

**判断**：TAM 本轮是「广度 + 运维」迭代，对 CodeWiki（本地 MCP + markdown + 无服务端）没有机制层新东西可搬。
上次借鉴的机制层（L2/L3）已落地为 `consolidate_notes` / `refresh_doctrine`，本轮无需追加。

**下次复检建议**：盯 `MemoryCore/src/core/` 与 `MemoryProxy/src/tdai/` 下的 L1/L2 提取器改动；
宿主适配与部署类 commit 可直接跳过。

---

## 附：本轮用到的证伪手段（可复用）

1. `git log <基线>..origin/<分支>` 取增量，先按 diffstat 过滤掉纯文档/部署 commit；
2. 对每个候选先 grep 本仓同语义实现（注意命名差异：noise/噪声、bypass/降级、binding/关联）；
3. 涉及「有没有漏掉」的判断写探测脚本实测计数（本轮 `probe_l0_noise.py`：79 文件 → 真噪声 11.4%）；
4. 结论里区分「已实现」「设计取向不同」「无缺陷可修」三种 excluded 原因，不混写为「不需要」。
