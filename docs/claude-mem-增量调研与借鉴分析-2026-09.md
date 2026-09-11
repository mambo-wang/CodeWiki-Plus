# claude-mem 增量调研与借鉴分析（2026-09-11）

> 增量对象：**thedotmack/claude-mem** @ `d095021d`（2026-09-10，`origin/HEAD`），本地克隆 `D:\repos\claude-mem`
> 基线：`docs/claude-mem-调研与借鉴分析.md`（2026-09-02，`f92996e` / v13.23.1）
> 视角：自上次借鉴以来，哪些新合入值得 CodeWiki 借鉴
>
> 调研方法：`git log --since=2026-09-02`（**36 个 commit**）+ CHANGELOG（13.24.0 / 13.24.1 / Unreleased）
> + 关键 diff 与新增源码实读 + 本仓代码对照。
> 他仓论断落到 `文件:行号`（相对 claude-mem 仓库根，`origin/HEAD` = `d095021d`）；本仓对照落到 CodeWiki 的 `文件:行号`。
>
> 处置规则沿用前两份增量调研：**先证伪再立项**——他仓新增 ≠ 本仓缺口；
> 涉及「有没有漏掉」的判断必须实测计数，不靠直觉；候选一律落 absorbed / deferred / excluded，**排除必填原因**。

---

## 0. 增量概览

| 项 | 上次（2026-09-02） | 本次（2026-09-11） |
|---|---|---|
| 版本 | v13.23.1 | v13.24.1（+ Unreleased 的 Grok Bot pilot） |
| 新增提交 | — | **36** |
| 主线工作 | 记忆压缩管线、渐进式披露三层 | **宿主分发形态拆为两个市场插件**（Cursor / Grok Bot）+ **工具调用明细落库（#3898）** + **技能调用遥测（#3960）** + CCS Align（内部上下文缓存对齐） |
| 记忆机制层变化 | — | **无**（观察生成 / 压缩 / 三层披露的工作流未动，只在第三层后追加了第 4 层「原始证据」） |

一句话：这 9 天 claude-mem 的力气花在**分发形态**与**用量可观测**上——他们现在要回答的问题从「记住了什么」变成了
「哪个技能被谁用了多少次、这次推理花了多少钱」。而我们上一次借鉴的正是记忆机制层（已落地），
本轮新增的两项都**依托他们独有的业务前提**（OpenRouter 计费、插件市场分发），故产出以证伪为主。

---

## 1. #3898 工具调用明细表 `tool_uses` — 机制精巧，但前提不成立

### 1.1 做法

原始的工具 I/O 此前没有持久落点：`pending_messages` 是生成队列，行被认领、摘要、删除，
一旦 observation 生成，原始 `tool_input` / `tool_response` 就没了（commit `fd0ecf02` message）。
新增 `tool_uses` 表（schema v51）作为**副索引（side index）**，从唯一的 ingest 收口点双写：

- DDL 与索引 — `src/services/sqlite/tool-uses.ts:174-202`
- 写入是 upsert：`ON CONFLICT(content_session_id, tool_use_id) DO UPDATE`，重放只补空字段不产生重复行 — 同文件 `:230-242`
- `observation_id` 只在仍为 NULL 时回填（`COALESCE`），**先认领的批次拥有该链接，后来的批次不得抢** — 同文件 `:279-306`
- 契约文档 — `RECEIPT-JOIN.md:83-109`（冻结 schema）、`:117-158`（读 API）、`:164-189`（caveats）

### 1.2 四条值得单独记下的工程不变量（与业务无关，可复用）

1. **权限分离，绝不混写**：`tool_uses` 只承载**身份与计数**，金额留在 OpenRouter 花费行，
   契约里写死「不要把 `cost_usd` / micros 放到 `tool_uses` 上当权威」— `RECEIPT-JOIN.md:5`、`:25`、`:69-73`
2. **递归自读保护**：写入器跳过自己的披露工具（`memory_*` 前缀 + `mcp__` 服务器段匹配，
   `search` / `timeline` / `get_observations` / `get_tool_uses`），否则「每调一次读工具，表就增长一次」— `tool-uses.ts:48-74`
3. **原始体只能按 id 取**：`POST /api/tool-uses/batch` **必须显式给 ids**，故意不提供全表翻页；
   `GET /api/tool-uses` 只返身份 + `tool_input_bytes` / `tool_response_bytes` 这类体积提示，永不返载荷 — `RECEIPT-JOIN.md:117-158`
4. **截断可辨认 + 哈希忠于原文**：载荷 64 KB 软截断并追加 `…[truncated: N bytes]` 标记，
   而 `content_hash` 基于**截断前**原文计算，因此两个共享前缀的超大载荷仍可区分 — `RECEIPT-JOIN.md:181-189`

配套的披露层定位也很清醒：新增「Layer 4: Get Tool Uses (Raw Evidence)」，
并直接写「Never start here」——摘要不够时才准下钻，默认披露就不是渐进式披露而是更大的 transcript
— `docs/public/progressive-disclosure.mdx:264-268`、新增段 `:403-441`

### 1.3 本仓对照（证伪）

| 他仓前提 | 本仓事实 | 结论 |
|---|---|---|
| 有外部计费数据面（OpenRouter 花费行），需要把 $ 归因到工具 | 本仓无 LLM 花费数据面，token 由宿主/用户承担，资产是 markdown | 建表的主需求**不存在** |
| 需要 `COUNT(DISTINCT tool_use_id)` 做用量计数 | 本仓 `tool_digest.py` 只把工具调用**消化成文本行**写进 raw（`:195`、`:204`），无 tool_use_id 级身份 | 有差异，但计数需求待实测（见下） |
| 原始工具 I/O 需要能按 id 取回 | 本仓**原始 body 根本不落盘**，两级消化后只留摘要与 `[tool-error: …]` 行（`tool_digest.py:213-237`） | 要对齐等于**新开一个存储面** |
| 读工具会污染被观测数据 | 本仓 telemetry 只记 `hit` / `adopted` / `by_file` 三事件（`telemetry.py:20-21`、`:139`、`:190`、`:208`），**不记工具载荷** | 无此类风险，不变量 2 无对应面 |

唯一一条和本仓真有交集的，是**逐次工具调用的失败计数**：这正是上一轮 teamai-cli #336 留下的 deferred
（`docs/teamai-cli-增量调研与借鉴分析-2026-09.md:175`）——`[tool-error: …]` 行已在 raw 里，
但 `friction.py` 没有 per-call 计数。而那次的实测结论是**漏检率 0%（n=1，样本量不足，不构成证否）**。

> **连带发现（2026-09-11）：#336 那次实测的口径本身可能偏窄，需要在复测前先修正测量方法。**
> `[tool-error: …]` 行只由 `tool_digest` 产生，而它在本仓只有两个调用点——`codewiki/mcp/_ide_hook.py:268`
> 与 `codewiki/mcp/tools/capture_conversation.py:221`；session-end 的 transcript 补采集
> （`capture_session_end.py`）**不经过 `tool_digest`**，因此该通道覆盖的会话根本不会在 raw 里留下
> `[tool-error: …]` 行。
> 换言之，上次「8 条 raw 中仅 1 条含 tool-error」这个计数，测的是**通道覆盖面**而不是**漏检率**，
> 0% 的漏检率既可能因为没漏、也可能因为压根没采到。复测 #336 之前必须先回答
> 「工具失败信号在几条通道上被采集，各自覆盖多少会话」，否则换更大的样本也只是把同样的偏差放大。

**裁决：#3898 本体 → excluded**（需求侧不成立：无计费归因场景；计数侧缺口未实测）。
**其四条工程不变量 → deferred（留档）**：若将来 friction 真做 per-call 计数，
`tool-uses.ts` 的 upsert 语义、自读跳过、截断+原文哈希、按 id 取这四点是现成的参考实现，不必重新设计。

---

## 2. #3960 技能调用遥测 `skill_invoked` — 本仓唯一可能真缺口的候选

### 2.1 做法

统计**第一方技能**被谁、在哪个宿主上调用了，明确不采集参数、提示正文与第三方技能名
（commit `d095021d` message；`docs/public/telemetry.mdx:121-124`）：

- **封闭枚举，永不外传自由文本**：`FIRST_PARTY_SKILL_IDS` 是硬编码常量数组（21 个），
  `classifySkillId()` 归一化后不在枚举内一律折叠为 `{skill_id: 'other', skill_source: 'third_party'}`
  — `src/services/telemetry/skill-id.ts:12-33`、`:62-69`
- 归一化规则本身也是防泄漏的一部分：trim + 小写、去前导 `/`、`claude-mem:mem-search` 取最后一段，
  并注明「Never return the original string」— 同文件 `:52-61`
- 纯模块、无 I/O、永不抛异常 — 同文件 `:9`
- 遥测白名单只加三个键 `skill_id` / `skill_source` / `skill_trigger` — `src/services/telemetry/scrub.ts:188-194`
- 采集点放在既有分支里（命中 `Skill` 工具的 skip 分支），不新增捕获路径 — `src/services/worker/http/shared.ts:81-95`

### 2.2 本仓对照

- **能力缺口真实存在**：本仓 telemetry 只有 `hit` / `adopted` / `by_file` 三类事件
  （`telemetry.py:20-21`），聚合也只折 `hit` / `adopted`（`:349-366`），**没有任何技能维度的事件**。
  技术路径也不通：技能由 IDE 从 `.codebuddy/skills/` 加载，不经过 MCP，本仓无法像他们那样在 ingest 收口点埋点。
- **可行性有替代路径**：本仓已有 UserPromptSubmit hook 通道与 raw 采集
  （`codewiki/mcp/_ide_hook.py`、`codewiki/mcp/tools/capture_conversation.py`），
  `/skill` 形态的触发在 user 消息里可见；成本是新增一个事件类型 + 一个封闭枚举，量级是几行。
- **但价值尚未被证明**：需要它的唯一理由是「回答 skill_creator 产出的技能到底有没有被触发」，
  而 `docs/plans/cli-capability-progressive-disclosure.md:92` 里 O6 关注的还是**检索** description 命中率，
  技能命中率尚未成为任何在办项的判定输入。

**裁决：deferred（待 skill_creator 验证阶段）**——不立项、不排期；
真要动手时，直接抄他们的**封闭枚举 + 折叠为 `other`** 这条隐私不变量，本仓 telemetry 基础设施（per-user JSONL + 锁 + 聚合 fold）已现成。

---

## 3. Grok Bot：无 hook 时退回 transcript watcher — 本仓已有同形态

CHANGELOG Unreleased 与 13.24.0：Grok Bot 没有宿主 hook，采集改走
`agent-transcripts/*/*.jsonl` 的 transcript watcher，并带 `platformSource=grok-bot`
（`CHANGELOG.md:9-14`、`:72-74`）。
这是「hook 不可用时的降级采集通道」，与本仓 `capture_session_end.py` 读宿主 transcript 的形态一致。

**裁决：excluded（已实现，非增量）。**

---

## 4. 13.24.1 事故：manifest 与构建产物不同步导致重启死循环 — 无对应面

`v13.24.0` 只改了 manifest 版本号、没重跑构建，提交的 `plugin/scripts/*.cjs` 仍是 13.23.1 字节。
而 `ensureWorkerRunning()` 拿插件缓存目录解析出的版本（13.24.0）与 worker 自报的
`__DEFAULT_PACKAGE_VERSION__`（13.23.1）比对，不一致就 SIGKILL 再 respawn——
**每次 hook 事件都把在途的 observer 一起带走**（`CHANGELOG.md:16-43`）。

本仓无 worker 版本自检/重启机制，无对应面。

**裁决：excluded（无对应面）。** 附一条给「发版本」任务的提醒：
凡「版本号常量」与「构建产物/运行时自报版本」两处真相的发布形态，都必须有**一致性校验**，
否则版本比对型守护进程会把不一致放大成重启风暴。

---

## 5. CCS Align（#3934–#3937）— 内部上下文缓存对齐

Phase 0 引入 worker 健康 + 三层拉取 + 原子 middle cache（`src/services/integrations/CcsAlignMiddleCache.ts`，369 行），
Phase 1 的 exclude marks 在**编译期**把规则从中层缓存里省略，Phase 2 处理 house → project → seat 的冲突走位。
这是 claude-mem 与宿主（Claude Code）上下文缓存的内部对齐机制，依赖他们的 worker 进程与插件缓存目录模型。

**裁决：excluded（形态不同，无对应面）。**

---

## 6. 借鉴处置表（2026-09-11）

| 合入 | 处置 | 原因 |
|---|---|---|
| #3898 `tool_uses` 明细表 | **excluded** | 建表主需求是 $ 归属（`RECEIPT-JOIN.md:5,69-73`），本仓无 LLM 花费数据面；计数侧缺口未实测 |
| #3898 的四条工程不变量（upsert / 自读跳过 / 截断+原文哈希 / 按 id 取） | **deferred（留档）** | 承接 teamai #336 的 deferred；若 friction 真做 per-call 计数，这是现成参考实现，不单独立项 |
| 渐进披露第 4 层（原始证据按需按 id 下钻） | **excluded** | 本仓原始工具 body 不落盘（`tool_digest.py:195-237`），对齐等于新开存储面，无需求驱动 |
| #3960 `skill_invoked` 技能遥测 | **deferred（待 skill_creator 验证）** | 能力缺口真实（telemetry 仅 hit/adopted/by_file），但技能命中率尚未成为任何在办项的判定输入 |
| Grok Bot transcript watcher | **excluded** | 本仓 `capture_session_end.py` 已是同形态 |
| 13.24.1 manifest/产物不同步事故 | **excluded（无对应面）→ 转提醒** | 本仓无 worker 版本比对重启；发布一致性校验一条留给「发版本」任务 |
| CCS Align 四阶段 | **excluded** | 宿主上下文缓存内部对齐，依赖 worker 与插件缓存模型，形态不同 |

**净结果**：候选 7 项，**0 采纳、2 deferred（均为「若将来做 X 则照抄」的留档）、5 excluded**。
本轮价值同样在**证伪**：确认 claude-mem 的新增能力依托「计费归因 + 插件市场分发」两个本仓没有的前提，
同时给 friction per-call 计数留下了一份可照抄的 schema 契约。

---

## 附 A：11 个借鉴项目的增量全景（2026-09-11 扫描）

扫描方式：本地克隆 `git fetch` 后 `git rev-list --count --since=<上次调研基线> origin/HEAD`。
基线取各自调研文档标注的调研日期；`llm_wiki` 调研文档未标日期，按保守的 2026-07-01 计。

| 项目 | 上次调研 | 新增提交 | 主线方向（抽样） | 队列 |
|---|---|---|---|---|
| codebase-memory-mcp | 2026-07-25 | **1182** | C 引擎 / AST 与图谱 | 量大，需先按 diffstat 过滤 |
| semantica | 2026-08-09 | **682** | 图原生基础设施 | 中 |
| WeKnora | 2026-07-21 | **588** | 外部文档管理、健康检查 | 中（我们借鉴过文档健康检查） |
| OpenViking | 2026-08-21 | **268** | 宿主适配、任务/插件、recall 与采集协议 | **高**（#4858 输入过滤、#4900 跨宿主 turn 捕获、#4779 队列自愈、#4906 recall 装配，与采集/注入同层） |
| llm_wiki | ~2026-07 | 183 | v0.6.9→0.6.11，deep research 批处理、按 source 过滤 | 低（形态为桌面应用） |
| claude-mem | 2026-09-02 | 36 | 分发形态、用量可观测 | **本轮已完成** |
| openwiki | 2026-08-31 | 34 | 依赖现代化、自维护 wiki 文档、指纹与托管块 | 中（#859 指纹忽略 Windows ctime 漂移、#777/#841 AGENTS.md 托管块，与新鲜度/注入同层） |
| RepoWiki | 2026-07-29 | 23 | — | 低 |
| MindForge | 2026-08-27 | **0** | 无新合入 | 跳过 |
| wikiskill | 2026-09-02 | **0** | 无新合入 | 跳过 |
| artificial-intelligence-ontology | 2026-08-09 | **0** | 无新合入 | 跳过 |

**建议下一轮顺序**：OpenViking（268，与采集/注入管线同层，候选密度最高）→ openwiki（34，两处与新鲜度/AGENTS.md 直接相关）→ WeKnora（588，文档健康检查）。

---

## 附 B：下一轮两项的预检结论（对照已做，未展开）

扫描全景时顺手做了两条对照，结论先落下，免得下一轮重复证伪：

| 他仓 | 做法 | 本仓事实 | 预检结论 |
|---|---|---|---|
| OpenViking #4724 `fix(plugins): treat camelCase isError as an error tool result`（`98f24e16`） | 三个宿主插件的 `toolStatus()` 原本只认 `is_error`，漏掉 AI SDK / transcript 形态的 `isError`，补齐为 `is_error \|\| isError \|\| state.isError \|\| error \|\| state.error`（`examples/*/scripts/shared/capture-utils.mjs:155`） | 本仓 `tool_digest.py:213` 只读 `block.get("is_error")`，但作用对象是 **hook payload 的 content blocks**（`_ide_hook.py:268`、`capture_conversation.py:221`），测试固定为 `is_error`（`tests/test_ide_hook_capture.py:779`）；另有文本指纹兜底 `_looks_like_error`（`:152-187`、`:225`） | **excluded（数据面不同）**；前瞻提醒：若将来新增 transcript 直读通道，必须同时认 `isError`，否则错误信号整条静默 |
| openwiki #859 `fix: ignore windows ctime drift while fingerprinting`（`1b84ea8`） | 同一性回退检查去掉 `ctimeNs`——Windows 上 `lstat()` 与 `FileHandle.stat()` 之间 ctime 会漂移，导致未变更文件被判为已变更（`src/agent/utils.ts:660-668`） | 本仓指纹全部基于**内容**：`doc_similarity.compute_fingerprint`（`codewiki/src/doc_similarity.py:109`）、`page_manifest.compute_source_fingerprint`（`codewiki/mcp/tools/page_manifest.py:104`），不参与 stat 元数据 | **excluded（无对应面）** |

> 落盘分工：本文是「正在想的事」（调研事实 + 处置 + 待办队列），存 `docs/`；
> 若将来某项被实测推翻并落地，应以 note 形式沉淀到 `repowiki/notes/`。
