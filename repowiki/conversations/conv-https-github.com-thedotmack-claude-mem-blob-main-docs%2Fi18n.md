---
type: Conversation
title: "conversation 20260903T020026Z"
status: distilled
stale_after: 2026-12-02
generated: { by: codewiki/5.5.1, at: 2026-09-03T02:00:26Z }
captured_at: "2026-09-03T02:00:26Z"
content_hash: "sha256:c09f609e76dc5947c76ee31974897158517ac8ee4464c54b0443b4b61cc06da5"
friction_score: 5
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=5"
keep_raw: false
link_to: ""
source_session: "e5103b8c415d427a85016cf1c516344f"
turn_count: 24
---

# Conversation Transcript

user: https://github.com/thedotmack/claude-mem/blob/main/docs%2Fi18n%2FREADME.zh.md  调研该项目，看有什么值得我们项目借鉴的，生成调研报告
assistant: I'll start with the required task-memory flow.
user: <question>本会话是否需要关联一个进行中的任务？（当前有 5 条未蒸馏历史对话积压）</question>
<answers>
OpenWiki 竞品调研(task_id=OpenWiki-竞品调研 —— 本次为竞品调研，建议关联此项)
</answers>
</question_item>
</questions>
</question_answer>
assistant: codewiki MCP 服务器当前未连接，我先确认一下配置，同时并行抓取 claude-mem 的架构文档。
assistant: MCP 服务器未连接，稍后处理。先并行抓取剩余关键文档 + 了解本项目现状。
assistant: 信息收集完毕。现在生成调研报告。
assistant: 调研报告已生成：`docs/claude-mem-调研与借鉴分析.md`

## 需要先说明一件事

**任务关联流程未能完成** —— `codewiki` MCP 服务器当前未连接（`Server 'codewiki' not found or not connected`），因此 `set_session_task` / `get_task_context` / 补蒸馏都无法执行。你选的 `OpenWiki-竞品调研` 任务绑定、以及那 5 条积压对话的补蒸馏，需要 MCP 重连后再走。

## 报告核心结论

**两者是同一个问题的两个切面**：claude-mem 关心"这次会话记住了什么"（时间中心、零摩擦、无闸门）；CodeWiki 关心"项目知识如何沉淀评审"（结构中心、闸门、团队治理）。

**最有价值的可迁移思想，一句话**：*把检索成本显式化，把获取决策权交还给 Agent。*

### CodeWiki 其实已经有大半，不该妄自菲薄

| 能力 | 对比结果 |
|---|---|
| 分层检索 | CodeWiki **更细**：`query_wiki` 四模式（`overview`/`directory`/`detail`/`check`）vs claude-mem 三层 |
| 排序信号 | CodeWiki **更丰富**：BM25 + `authority` + `usage` heat 三重加权 vs 纯 FTS5 rank |
| 检索透明化 | CodeWiki **独有**：`matched_tokens` + `query_coverage.missing` |
| 注入预算 | CodeWiki **更可控**：`injection_budget.py` 可配置字符预算 + 降级不降可达性 |
| 多 IDE | CodeWiki **更通用**：`hooks.yaml` 家族归并 3 家族 10 智能体 |

### 真正的三个差距（P0，纯增量、合计不到一天）

1. **`est_tokens` 字段** —— 检索结果不告诉 Agent "展开这条要花多少"，Agent 只能盲目 `expand`。而 `injection_budget.py` 已经在用字符近似做预算判定，哲学已就位，只差暴露出去。
2. **`query_wiki(by_file=...)`** —— File Read Gate 的地基。`related_modules`/`related_components` 数据已在笔记 frontmatter 里，缺的只是反向检索出口。
3. **工作流写进工具描述** —— claude-mem 用永远可见的 `important_workflow` 工具把规则内建；CodeWiki 靠 AGENTS.md 文字约束，Agent 可能不读。

### 最激进的创新与我们的硬约束

**File Read Gate**（拦截 `Read`，用历史观察时间线替代全文读取，官方称省 95% token）建立在 `PreToolUse` 钩子上 —— 而 `hooks.yaml` 只声明了 `session_start`/`session_end`（Cursor 家族已经因此吃过降级亏）。建议先立一个可行性验证任务：CodeBuddy 是否支持 `PreToolUse`、能否表达 deny 语义。若不支持，P2-2 的 SessionStart 软闸门可拿到大部分收益且零侵入。

### 明确不建议借鉴

常驻 worker 进程（违背"工具不持模型"的 Doctrine）、Chroma 向量库（换可选收益引入 Python 依赖）、无闸门自动入库（与 `confirm_note` 直接冲突）、工具从 48 砍到 4（功能域不同，五大域是真实映射）。

---

两点需要你决定：

1. **MCP 重连后**，是否把这份调研的核心结论（`est_tokens` + `by_file` + 工作流内建）作为 `decision` 笔记归档？按 AGENTS.md 的规矩，需要你确认后我才会写。
2. 报告里 P0-1 到 P0-3 是纯增量改动，要我直接开工吗？
user: 你把他们代码克隆下来，深入读代码，调研得深入一些
assistant: 明白，我克隆源码来做代码级调研。
assistant: 版本是 **v13.23.1**（2026-09-01）——文档站描述的还是 v5.x，代码已大幅演进。并行深入探索。
assistant: 第一、二个子代理输出被截断，我直接读核心代码补充。
assistant: **重大发现**：MCP 工具实际是 19+ 个（文档说 4 个），且含 tree-sitter AST 代码搜索。继续深挖。
assistant: 存储层已重构为多租户团队模型，且用 tree-sitter 做代码符号搜索。继续读核心实现。
assistant: **关键反转发现**：File Read Gate 在 v13 已从"拒绝读取"改为"附加上下文"。核对 SessionStart 注入与语料库机制。
assistant: 材料齐了。基于代码实测重写报告 —— 文档与代码存在**重大落差**。
assistant: 代码克隆并读完了，报告已重写。`.tmp` 已被 `.gitignore:94`（`*.tmp`）覆盖，不会误提交。

## 版本真相：代码是 v13.23.1，文档站还停在 v5.x

读代码后发现文档站三处**系统性失真**（报告 §2 有对照表）：

| 项目 | 文档说 | 代码实际 |
|---|---|---|
| MCP 工具 | 4 个 | **19+ 个**（`mcp-server.ts:439-874`） |
| 数据表 | 4 张 | **9 张**（schema v33）+ Postgres 后端（v50） |
| File Read Gate | DENY 拒绝读取 | **`permissionDecision: 'allow'`** |

## 最重要的发现：他们自己废掉了"拦截读取"

这是本次调研价值最高的一条 —— 我上一版建议"争取 PreToolUse 做读取拦截"，**代码实测推翻了这个方向**。

```typescript
// src/cli/handlers/file-context.ts:186-192
return {
  hookSpecificOutput: {
    hookEventName: 'PreToolUse',
    additionalContext: timelines.join('\n\n---\n\n'),
    permissionDecision: 'allow',        // ← 不是 deny
  },
};
```

文案也从 `Read blocked: Choose the cheapest path` 改成了 `This file has prior observations — supplementary context follows. The Read result below is the full requested section.`

**含义**：v5 的"拒绝读文件、只给时间线"被放弃了，改为"照常读、旁边附上下文"。我们不必重走这段弯路。

## 剩下的内核反而更值得抄

剥离掉"拦截"外壳后，三个细节依然高价值：

**1. token 估算就是一行除法**（`timeline-formatting.ts:74-77`）
```typescript
export function estimateTokens(text: string | null): number {
  if (!text) return 0;
  return Math.ceil(text.length / 4);
}
```
只估 `obs.narrative` 一个字段。**P0-1 的门槛从"要引 tokenizer"降到了"一行除法"** —— `injection_budget.py` 本来就在用 `len()` 做字符预算，加个 `/4` 即可。

**2. 用文件 mtime 判定知识是否过期**（`file-context.ts:255-265`）
```typescript
if (fileMtimeMs >= newestObservationMs) return null;  // 文件在观察之后改过 → 不注入
```
对照我们的 `index_freshness.py`：`stale_after` 是基于**笔记创建时间**，claude-mem 是基于**被描述文件的真实修改时间**。3 个月前的笔记若文件没动过依然有效；昨天写的笔记若文件今早重构了也已失效。后者精确得多。

**3. 折叠视图**（`smart-file-read/parser.ts`，tree-sitter 27 语言）
`smart_search` / `smart_outline` / `smart_unfold` 提供"只要符号签名、函数体折叠、带 token 估算"的中间层 —— 这正是 CodeWiki 缺的一档：我们有 tree-sitter 分析器，但**没有这个消费形态**。

## 建议变更

| 编号 | 变化 |
|---|---|
| P0-1 `est_tokens` | **强化**，实现成本远低于预估 |
| P0-3 工具描述 | **修正**：不是全极简，是按重要性分层（工作流指引类极简，需精确调用的给完整 schema） |
| P1-3 折叠视图 | **新增**，高价值低门槛 |
| P1-4 mtime 对端新鲜度 | **新增** |
| P1-5 语料保留 filter 支持 rebuild | **新增**（`CorpusBuilder` 把 filter 随语料落盘，可增量刷新，对照我们的 Doctrine） |
| ~~P2-1 读取拦截~~ | **方向反转** → P2-1' 改为附加上下文 |
| P2-2 SessionStart 软闸门 | **优先级上调** —— 与 v13 实际做法同构，且无需 PreToolUse 支持 |

## 一处我们确实领先的（值得记下来）

多 IDE hook 适配：claude-mem 是**每平台一份 hooks.json + 一个 Installer 类**（Cursor / Antigravity / Windsurf / OpenCode 各一份，`build-hooks.js` 做逐字节校验）；我们的 `hooks.yaml` 是**家族归并 + 事件名候选数组 + `verified` 诚实标注**，加一个新智能体只需一行。**这项不该反向借鉴。**

另外顺带确认：claude-mem 已演化为商业化 SaaS（CMEM Pro / Stripe / PostHog / 配额守卫），其 `server/` + `supervisor/` + `workers/sync-hub/` 的复杂度是业务形态驱动的，不是记忆能力所需 —— 别被体量吓到，也别照搬。

---

两件事需要你定：

1. `d:\repos\CodeWiki-CN\.tmp\claude-mem`（1082 个文件）要删掉吗？已被 gitignore，留着方便后续追问细节。
2. 「**竞品调研必须克隆源码，文档会方向性失真**」这条经验，要不要沉淀成 Wiki 的 `lesson` 笔记？按规矩需你确认后我才写 —— 而且 codewiki MCP 仍未连接，得先解决连接问题。
user: 如果按照你的借鉴建议开发的话，对于我们项目的收益是什么
assistant: 收益要落到可验证的数字上，我先核实两个关键事实。
assistant: 先把基线量化清楚，收益才不是空话。我实测了本仓库语料规模：

| 语料 | 数量 | 平均字符 | 最大字符 |
|---|---|---|---|
| `notes/` | 112 篇 | 1,335（≈334 tok） | 5,199 |
| `wiki/` | 51 篇 | 5,410（≈1,353 tok） | 27,534（≈6,884 tok） |
| `raw/` | 8 篇 | — | — |

## 一、先看清现状的一个真实缺陷

读 `knowledge_loop.py:2002-2010` 时发现：**默认检索的 10 条结果里，实际只有 4 条带内容**。

原因是两个预算口径打架：

```python
# wiki_search.py:626 —— snippet 截断到 300 字符
"snippet": (_extract_snippet(...))[:300],

# injection_budget.py:30 —— 总预算 1200 字符
_DEFAULT_BUDGET = {"search_result_chars": 1200, ...}

# injection_budget.py:90 —— 累计超预算即降级
if used + len(snippet) <= budget:
```

1200 ÷ 300 = **4 条**。第 5 条起全部降级成 `description | score` 单行指针。也就是说 Agent 拿到 10 条结果，**60% 是空壳**。

而 `expand` 走的是另一条完全不受此约束的通道：

```python
max_chars = min(20000, max(500, int(arguments.get("max_chars", 3000))))
entry["content"] = full_text[:max_chars].strip()
```

**这里有个真正的盲区**：Agent 在索引阶段看到的是"10 条里 6 条没内容"，自然会倾向 `expand=True`；而 expand 一次能给到 10 × 20000 = 20 万字符 ≈ **5 万 tokens**，单次调用就吃掉大半个上下文窗口。系统在前门严格控制 1200 字符，后门却敞开着 20000 倍。

这就是 P0-1 的核心价值所在 —— 不是"锦上添花加个字段"，而是**把后门的代价暴露给决策者**。

## 二、逐项收益

### 确定性收益（可由现有代码推算）

| 项 | 现状 | 改后 | 收益 |
|---|---|---|---|
| **P0-1 `est_tokens`** | Agent 盲目 expand，最坏 5 万 tok；保守用 3000 则截断（wiki 平均 5410 字符，截掉 45%）需二次调用 | 索引阶段见成本，只展开 2–3 篇 | 最坏场景 **-90%**；保守场景 **-35%**，且消除二次调用 |
| **P0-2 `by_file`** | 改文件前无任何历史知识入口，只能全文 Read | 先查历史时间线（~370 tok）再决定 | 单次改文件 **省 5k–50k tok**；且能捞到历史决策/踩坑 |
| **P1-3 折叠视图** | 读文件全量 | 只要签名+行号 | 最大 wiki 文档 6,884 tok → 折叠后约 **-80%** |
| **P1-4 mtime 对端新鲜度** | `stale_after` 按笔记年龄判定，112 篇笔记会同时产生**假阳性**（老笔记但文件没动，仍有效却被判过期）和**假阴性**（新笔记但文件已重构，已失效却仍注入） | 比对目标文件 mtime | 消除两类误判，且**减少误导比省 token 更值钱** |

P0-1 的收益推导（保守场景）：

```
现在：  expand=True, max_results=10, max_chars=3000
        = 30,000 字符 ≈ 7,500 tokens（其中 6 篇是噪音，且 wiki 被截断 45%）
改后：  索引 10 条约 800 tokens
        → 挑 3 篇展开 3 × 5,410 = 16,230 字符 ≈ 4,059 tokens
        = 约 4,859 tokens，且拿到的是完整内容
节省 35%，信息完整度反而上升
```

### 结构性收益（不改架构、但打开后续空间）

| 项 | 收益 |
|---|---|
| **P1-2 笔记结构化字段**（`facts`/`concepts`/`files`） | 现在笔记是自由 Markdown，检索只能全文匹配。有了 `files` 字段，P0-2 的 by_file 才有数据基础；有了 `concepts`，才能按概念聚类。**它是 P0-2 的前置依赖，不是独立功能** |
| **P1-5 Corpus filter 可 rebuild** | 现在 Doctrine 每次全量重算。记住"它是从哪些查询聚合来的"后，可增量刷新 —— 语料规模涨到 500 篇时，这个差异会从"几秒"变成"必须" |
| **P0-3 工作流写进工具描述** | 48 个工具里，Agent 不知道 `check` 模式存在（它不计入热度、不污染信号）。把这条写进 description，能减少"用默认检索当预检"造成的热度污染 —— **保护 `usage` 排序信号的数据质量** |

最后这条容易被忽略，但很重要：`query_mode_check` 的注释明确写了它是"轻量预检，不记录检索统计，避免污染 usage/heat 信号"（`knowledge_loop.py:1729-1735`）。**如果 Agent 不知道有这个模式，这个精心设计就是无效的**，而且真实检索信号会被预检稀释。P0-3 是让已有设计真正生效的成本最低的方式。

### 风险规避收益（最容易被低估的一项）

如果按**文档版**报告的建议去做 PreToolUse 读取拦截：

- 需验证 CodeBuddy 是否支持该事件、能否表达 deny 语义
- 需实现拦截逻辑 + 多级放行条件 + 逃生阀
- 需处理"记忆插件拒绝 IDE 读文件"带来的用户困惑

这是**数天工作量，且 claude-mem 已经用 v5→v13 的演进证明这条路最终会被放弃**。

代码实测把方向反转为"附加上下文"后，P2-2（SessionStart 软闸门）**完全不需要 PreToolUse 支持**，用现有 hook 通道就能拿到大部分收益。**规避的沉没成本 ≈ 数天，且避免了一次架构级的返工。**

## 三、汇总

| 维度 | 收益 | 确定性 |
|---|---|---|
| token 成本 | 单次检索 -35%（保守）至 -90%（最坏场景） | **高**（可由现有代码推算） |
| 检索精度 | 消除 mtime 误判的假阳性/假阴性 | **高**（逻辑确定，幅度待实测） |
| 已有设计生效 | `check` 模式被真正使用，保护 usage 信号 | **高** |
| 上下文完整度 | 从"10 条里 6 条空壳 + 截断 45%"到"按需取全文" | **高** |
| 后续扩展性 | by_file / 概念聚类 / Doctrine 增量刷新 有了数据地基 | **中**（依赖 P1-2 落地） |
| 避免返工 | 绕过已被证伪的拦截路线 | **高**（有 claude-mem 代码为证） |

## 四、需要说清楚的边界

**三点诚实提示：**

1. **-35%/-90% 是基于本仓库语料规模（112 笔记 / 51 文档，wiki 平均 5410 字符）的推算，不是实测。** 若用在更大的仓库（比如 wiki 平均 2 万字符），绝对值会放大，比例大致不变。真正落地后应该用 `telemetry.py` 的 retrieval_stats 做 A/B 对比。

2. **P1-2（结构化字段）收益最不确定，但它是 P0-2 的前置。** 它要求改 `frontmatter.py` 的写入路径，而那里有 `parse(render(x)) == x` 的往返不变量约束，改动风险高于其他项。如果不做 P1-2，P0-2 只能退化为"按 `related_modules` 粗粒度匹配"，收益打折。

3. **这些收益里，最值钱的其实不是省 token，是减少误导。** P1-4 消除的"假阴性"（文件已重构但旧笔记仍被注入）会让 Agent 基于过时信息做决策 —— 这个代价远超几千 token。同理 P0-2 让 Agent 改文件时能看到"上次在这里踩过什么坑"。**token 是可度量的，误判的代价不是。**

---

要不要我把 P0-1 和 P0-2 直接落地？P0-1 改动面很小（`wiki_search.py` 结果组装 + `knowledge_loop.py` 响应拼装 + `registry.py` description），且纯增量、不改任何现有契约。做完后可以用 `tests/` 里现有的 wiki_search 测试直接验证无回归。
user: 生成详细设计方案
assistant: 先看现有设计方案的格式规范与关键实现细节。
assistant: 需要确认 SQLite 检索路径的返回结构，才能让 P0-1 的设计对两条路径都成立。
assistant: 实现依据齐了（两条检索路径都会读全文，可零额外 IO 拿长度）。生成设计方案。
assistant: 设计方案已生成：`docs/claude-mem借鉴详细设计方案.md`（格式对齐现有 `知识飞轮增强设计方案-P0三项.md`）。

## 方案范围

| 项 | 工作量 | 状态 |
|---|---|---|
| P0-1 检索成本可见性 | 0.5–1 人日 | 本次实施 |
| P0-2 `by_file` 文件知识检索 | 1.5–2 人日 | 本次实施 |
| P0-3 工作流内建工具描述 | 0.2 人日 | 本次实施 |
| P1-4 mtime 对端新鲜度 | 0.5 人日 | 随 P0-2 落地 |
| P1-2 笔记 `files` 字段 | 0.5 人日 | v1.5 可选 |
| P1-3 折叠视图 | 3–4 人日 | 单独排期 |

**合计 3–4 人日**。全部有独立配置开关，置 `false` 即回 legacy，无需回滚代码。

## 几个关键设计决策

**1. `est_tokens` 能零额外 IO** —— 核实了两条检索路径为了抽 snippet 都**已读全文**（`wiki_search.py:623`、`cache.py:2056`），顺手取 `len(raw)` 即可。口径用 `len/4`，与 `injection_budget.py` 现有的 `len()` 预算同构，不引 tokenizer。

**2. `by_file` 用路径段匹配，不建索引** —— 我原本打算用 `module_tree.json` 做"文件→模块"精确映射，但核对后发现它的 `components` 只是 **ID 列表、不含 `file_path`**（`knowledge_loop.py:2588-2595` 的 `_walk` 只读 `get("components", [])`），要精确映射得再加载 `symbol_map.json`，多一个失败面。路径段匹配虽粗，但零依赖，且"mcp 目录下的文件匹配 mcp 模块的笔记"本来就是想要的语义。

**3. 特异性排序改造而非照搬** —— claude-mem 是"文件被修改 +2 / 覆盖 ≤3 文件 +2"，依据是它有 `files_modified` 全量字段能算"覆盖文件数"。CodeWiki 的 `related_modules` 不表达这个维度，硬套会失真，改成按**命中粒度**分级（精确 3 / 组件 2 / 模块 1）。

**4. mtime 有个坑要处理** —— repowiki 若是 git clone 来的，**所有文件 mtime 都是 clone 时刻**，会导致全量假阳性。方案里加了 1 天缓冲 + 拿不到就返回 `null`（不猜）。

## 一个需要你拍板的点

**P1-3 折叠视图的接入方式**（§5.3 列了三个方案）：

- **A**：新增 MCP 工具 `read_code_outline` —— 工具数 48→49，与"不新增工具"约束冲突
- **B**：`query_wiki` 的 `mode="outline"` —— 职责扩散
- **C**（我倾向）：`read_code_components` 加 `format="outline"` 参数 —— 复用既有工具，不增工具数，语义自洽

## 另一个提醒

方案 §8 的验收标准第 8 条我写了**收益必须实测而非采信估算** —— 上次回复里的"-35% 至 -90%"是基于语料规模的推算。落地后应该用 `telemetry.py` 的 retrieval_stats 对比改动前后的「单次 query_wiki 平均返回字符数」和「expand 调用占比」，拿真实数据验证。

---

要开始实施吗？建议从 **P0-3** 起手（0.2 人日、单文件改动、零依赖），先跑通全量测试确认基线，再进 P0-1 / P0-2。
