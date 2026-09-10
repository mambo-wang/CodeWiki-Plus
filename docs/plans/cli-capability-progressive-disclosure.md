# Plan: CLI 能力增强——用渐进式披露替换 MCP 工具定义常驻

> **Status**: deferred | **Date**: 2026-09-10 | **Origin**: 用户提出「CLI 能力弱、没和 MCP 对齐，增强后智能体用起来更省 token」→ grill-me 追问四轮
>
> **暂缓原因**：全部收益测算均为估算，唯一实测数据（88,727 字符载荷）尚未换算成 IDE 真实注入量。用户决定先归档、拿到实测再动。
> **恢复条件**：见文末「恢复条件」。

## Problem

用户诉求的原始表述是「CLI 能力比较弱，没有和 MCP 对齐」。追问后发现真正的痛点不在能力数量，而在 **MCP 工具定义的常驻 token 开销**。

### 现状（已核实）

| 面 | 规模 | 位置 |
|---|---|---|
| MCP 工具 | **49 个** | 单一事实源 `codewiki/mcp/registry.py:58`（`REGISTRY`），分发 `registry.py:2967`，`server.py:106-111` 只做转发 |
| CLI 动词 | **12 个**（8 顶层 + 4 `config` 子） | `codewiki/cli/main.py:11-49`、`cli/commands/config.py` |

**唯一实测数据**：`get_all_tools()` 返回的 `tools/list` 载荷 = **88,727 字符 / 49 个工具**（本机 `python -c` 实测）。按 2.5–4 字符/token 粗估 ≈ **22k–35k token**。

关键性质：MCP 工具定义**每个 API 请求都要发一次**，与 agent 当轮是否真的调用 MCP 无关。

### 与之对比的 CLI 侧成本

- `codewiki --help` 输出 = **915 字符**（实测）≈ 300 token
- CLI 复用 handler 已有先例：`cli/commands/query.py:160` 直接调 `handle_query_wiki`；`cli/commands/migrate_team_layout.py:30` 直接导 tools 模块
- 已定调：`docs/Hook多智能体支持设计方案.md:176`「CLI 是 handler 的投影层，不实现第二套检索」—**本方案沿用，不再讨论**

### CLI 侧两个真实缺口（已复核）

1. **无 `--json`**：全仓仅 `cli/commands/config.py:287` 一处
2. **`est_tokens` 未渲染**：MCP 侧有（`registry.py:1056`），CLI 的 `_render_result_block`（`cli/commands/query.py:55-84`）完全没有 → 走 CLI 的 agent 看不见展开成本

## 核心认知：收益来源是「常驻」不是「输出」

设计树跑完四轮后收敛出的一条：**只要 codewiki MCP server 在会话里是启用的，工具定义就每轮常驻，与 agent 用 CLI 还是 MCP 无关。**

因此「完善 CLI」本身**不产生任何 token 收益**——它只是让「关掉 MCP」这件事变得可行。收益来自让那 22k–35k 不再进入上下文。

达成手段有两条（第 2 条由用户提出，优于我最初的第 1 条）：

| | 手段 | 常驻成本 | 备注 |
|---|---|---|---|
| A | 收缩 MCP 暴露面到 core ~12 个 | ~6–8k token | 需给 `ToolDef` 新增分组维度 + `server.py:106` 加过滤；**注意 `registry.py:50` 的 `mode` 是执行模式（`main_thread`/`thread`/`async`，见 `registry.py:8-10`），不能当分组钩子** |
| B | 渐进式披露（skill/command）+ MCP 按需关闭 | **~100 词/skill metadata** | 用户提出。**常驻比 A 低两个数量级** |

## 三层模型（待确认）

> **披露层**（skill/command，~100 词常驻）→ **执行层**（CLI）→ **后端**（MCP，可开关）

三层拆开后，「CLI 对齐 MCP」这个原始诉求被重新表述为：**让 CLI 能完整执行 skill 里承诺的动作**，而不是补齐 49 个命令。

### IDE 侧已有开关（本机核实）

| 开关 | 位置 | 粒度 | 当前值 |
|---|---|---|---|
| MCP server 禁用 | `~/.codebuddy/mcp.json:27-34` | 整 server | codewiki = `disabled: false`；另 4 个 server = `true` |
| MCP 单工具禁用 | `~/.codebuddy/mcp-disabled-tools.json:2` `disabledTools: {}` | 单工具 | 空 |
| Skill 禁用 | SKILL.md frontmatter `disable: false` | 单个 | — |
| Command 仅手动触发 | command frontmatter `disable-model-invocation: true` | 单个 | — |

**这意味着路径 B 不需要改一行 registry——机制已原生存在。**

## 已 settle 的决策

| # | 决策 | 依据 |
|---|---|---|
| D1 | CLI 是 handler 的投影层，不实现第二套业务逻辑 | `docs/Hook多智能体支持设计方案.md:176` |
| D2 | 收益来源是「MCP 工具定义常驻」，不是输出体积、不是往返次数 | 本轮分析 |
| D3 | 收缩暴露面**不是**唯一手段；渐进式披露是独立且更优的手段 | 用户反驳，我接受 |
| D4 | 不做「49 个 skill 一对一映射」给 agent 用；给人用的 command 可以 1:1 且全部 `disable-model-invocation` | 见下「被排除的候选」 |

## 被排除的候选（Doctrine：候选必有去向，排除必填原因）

| 候选 | 去向 | 原因 |
|---|---|---|
| 手写 49 个 CLI 子命令 | **excluded** | 双份维护，每加一个 MCP 工具要改两处（handler+registry+CLI=三处），违反「单点收敛」。必然腐化 |
| 49 个 skill 一对一映射 MCP 工具 | **excluded** | ① 常驻不是 0：49 × 100 词 ≈ 4,900 词 ≈ 7–15k token（中文 token 化更差），与路径 A 打平甚至更贵；② skill 只注入指令不执行，等于用「模型自己拼命令行字符串」替换「schema 校验的结构化调用」，撞 Doctrine「不绕过 dispatch/schema 校验直连 handler」；③ 49 个语义相近 description 互相竞争，误触发是乘法风险；④ 放弃 skill 相对 MCP 的唯一增量价值——工作流粒度 |
| 把命令清单写进 `AGENTS.md` | **excluded** | 等于把 schema 换马甲常驻，正好抵消收益 |
| 解决 CLI 冷启动 / 无 shell 环境 | **deferred** | MCP 继续兜底，两者并存而非替代 |
| 第二个「全量 MCP server」按需连接 | **excluded** | 工具定义换地方常驻，自欺欺人 |

## 未 settle（恢复时从这里接续）

| # | 问题 | 我的推荐 |
|---|---|---|
| O1 | 三层模型是否接受 | 接受 |
| O2 | 默认会话里 codewiki MCP 开还是关 | **先「开 + `disabledTools` 精禁到 ~10 个」过渡**，拿 telemetry 后再定；一刀切关掉会同时丢 schema 校验 |
| O3 | 披露粒度：1 个大 skill / 按域 5–8 个 / 薄 skill + `references/` | **1 个薄 skill（能力索引）+ 按域 `references/`**；body 有 <5k 词硬上限，49 个能力装不进一个 skill |
| O4 | skill/command 是否从 `registry.py` 自动生成 | **生成**，与 CLI 投影共用一个生成器——否则 MCP/CLI/skill 三份手写真相必然腐化 |
| O5 | 工作流 skill 怎么切 | 按管线阶段切（采集/蒸馏/归档/治理/检索）；按频次切会导致边界随新工具反复重划 |
| O6 | 是否实测 description 命中率（造 20 条 query） | 要。这是路径 B 唯一真正的风险点，且可测 |

## 未验证项（全部数字的可信度边界）

- **22k–35k token 是估算**，不是 IDE 实测注入量。IDE 可能截断、改写或缓存工具定义
- **「~100 词/skill metadata」来自 CodeBuddy Skills 官方文档**，中文语境下的真实 token 数未测
- **`disable-model-invocation` / `disable` 的行为来自 `/docs/zh/cli/slash-commands`（CodeBuddy Code 分支）**，IDE 端未独立验证
- 项目当前**没有 `.codebuddy/commands/`** 目录（只有 `skills/`），加 command 需新建

## 恢复条件

1. 跑 `/context all` 拿到 MCP 那一块的真实 token 分布（本会话用户跑了但输出未进入上下文）
2. 或做端到端 A/B：同一任务跑两遍（MCP 开 vs `mcp.json:34` 设 `disabled: true` + 薄 skill 引导 CLI），用 `/cost` 比 input token
3. **判定线**：若 A/B 差值接近 22k–35k/轮 → 路径 B 收益成立，继续推 O1–O6；若差值仅 2–3k → **整个前提推翻，收手不做**

## 相关文件

- `docs/Hook多智能体支持设计方案.md:130-176` — H4 CLI 检索设计、CLI 投影层定调
- `docs/teamai-cli-调研与借鉴分析.md`、`docs/teamai-cli-增量调研与借鉴分析-2026-09.md` — 既有 CLI 调研
- `repowiki/wiki/modules/CLI.md`、`CLI_Commands.md`、`CLI_Adapter.md`、`CLI_Config.md`
- `repowiki/notes/2026-09-05-query-wiki-p0-改进四项定案...md:36,38` — est_tokens 的真实价值
