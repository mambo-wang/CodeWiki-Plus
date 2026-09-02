# claude-mem 调研与借鉴分析（源码级）

> 调研日期：2026-09-02
> 调研对象：**thedotmack/claude-mem** @ `f92996e`（v13.23.1，2026-09-01）——为 AI 编程助手构建的跨会话持久化记忆系统，TypeScript + Bun + SQLite，Apache-2.0。
> 对照对象：**CodeWiki-CN**（本仓库）。
>
> **调研方法**：浅克隆完整源码（`d:\repos\CodeWiki-CN\.tmp\claude-mem`，1082 个文件）后逐文件实读，而非依赖官方文档站。所有机制描述均落到**具体文件路径 + 行号 + 代码原文**，凡代码与官方文档冲突处，以代码为准并在 §2 单列。CodeWiki 侧基于本仓库源码实读对照。
>
> **置信度声明**：机制描述均有源码证据；claude-mem 官方自述的"10x token 节省"等量化数字未独立验证，仅作量级参考。CodeWiki 工具数（48）由 `registry.py` 实读统计。

---

## 一、执行摘要（TL;DR）

| 维度 | CodeWiki-CN | claude-mem v13（代码实测） |
|------|-------------|--------------------------|
| 版本/定位 | 项目级代码知识库（文档为中心） | **v13.23.1**，已从"个人记忆插件"演化为**商业化团队知识 SaaS**（CMEM Pro / Stripe / PostHog / 订阅配额） |
| 存储 | Markdown 文件为主 + SQLite 检索索引 | **SQLite 多租户 schema v33**（9 张表含 `teams`/`api_keys`/`audit_log`）+ Postgres 云端后端（schema v50） |
| 知识模型 | 模块文档 / 笔记 / 任务记忆（Markdown） | `memory_items` 单表统一（kind: observation/summary/prompt/manual）+ `memory_sources` 独立溯源表 |
| 检索 | BM25 + jieba + authority + usage heat + 图多跳 | FTS5（`porter unicode61`）+ Chroma 向量（可选）+ Postgres GIN tsvector |
| MCP 工具 | 48 个 | **19+ 个**（文档站声称 4 个，已严重滞后） |
| Hook 事件 | `session_start` / `session_end`（`hooks.yaml` 家族归并，3 家族 10 智能体） | Setup + SessionStart + UserPromptSubmit + **PreToolUse** + PostToolUse + Stop（**无 SessionEnd**）；每平台一份 hooks.json，由脚本生成校验 |
| 代码理解 | tree-sitter AST（依赖图/调用图，10 语言） | **tree-sitter AST（27 语言）** —— `smart_search` / `smart_outline` / `smart_unfold` |
| 读文件策略 | 无 | **File Read Gate：v13 已从"拒绝读取"改为"附加上下文"**（详见 §4） |
| LLM 依赖 | 无状态工具 + LLM 外置（prepare→推理→submit） | 有状态常驻 worker（Bun 进程）内跑 Claude Agent SDK |
| 质量闸门 | `draft → confirm_note → stable`（ADR-0002） | **无内容评审闸门**（全仓库 confirm/draft 匹配均为安装态/会话态/同步态，非内容评审） |

### 六条核心结论

1. **文档站已严重滞后于代码（v5.x 文档 vs v13.x 代码），以文档为依据的调研会得出系统性错误结论。** 工具数（声称 4，实际 19+）、数据表（声称 4 张，实际 9 张 + Postgres）、File Read Gate 行为（声称 DENY，实际 ALLOW）三处关键描述全部失真。**这是本次调研方法论上最大的收获：竞品调研必须读源码。**

2. **claude-mem 自己废掉了 File Read Gate 的"拦截"语义** —— 这是本项目最有价值的**负面证据**。v5 的 `Read blocked` + `permissionDecision: deny` 在 v13 变成了 `permissionDecision: 'allow'` + "The Read result below is the full requested section"。§4 给出完整代码证据。**CodeWiki 计划中的 P2-1（争取 PreToolUse 做读取拦截）应当重新评估——行业实践已经证明拦截是错的，附加上下文才是对的。**

3. **`est_tokens` 的实现简单到只有一行 `Math.ceil(text.length / 4)`**（`src/shared/timeline-formatting.ts:74-77`），而且只估算观察正文一个字段。这把"成本可见"的门槛从"要引 tokenizer"降到了"一行除法"，是本次调研**性价比最高的可移植项**。

4. **用文件 mtime 判定历史知识是否仍然有效**，比时间窗更精确（`src/cli/handlers/file-context.ts:255-265`）：若目标文件的修改时间晚于最新观察时间，说明知识已过期，直接跳过注入。CodeWiki 的 `stale_after` 是基于笔记创建时间，没有对端（被描述对象）的新鲜度信号。

5. **`memory_items` 单表统一 + `memory_sources` 溯源表的数据建模方式**，对 CodeWiki 正在进行的「统一知识存储层（KnowledgeStore 动词式门面）」有直接参照价值——用 `kind` 枚举统一异构知识单元，用独立溯源表保留出处，比"每种知识一张表"更易扩展。

6. **商业化架构（server/ + supervisor/ + workers/sync-hub/ + Postgres）是业务驱动的，不是知识管理本身所需**，CodeWiki 不应照搬。可借鉴的是它从单机走向团队时数据模型的演进路径，而非它的部署形态。

---

## 二、文档与代码的落差（方法论警示）

调研初期先读了官方文档站（`docs.claude-mem.ai`）7 篇文档，随后克隆源码比对，**发现三处关键失真**：

| 项目 | 文档站（v5.x）说法 | 代码实际（v13.23.1） | 证据 |
|------|------------------|-------------------|------|
| MCP 工具数 | 4 个（`important_workflow` / `search` / `timeline` / `get_observations`），"2718 行 → 312 行，-88%" | **19+ 个**，`mcp-server.ts` 982 行。含 `smart_search`/`smart_outline`/`smart_unfold`、5 个 `observation_*`（走 Postgres GIN）、6 个 `*_corpus` | `src/servers/mcp-server.ts:439-874` |
| 数据表 | 4 张（`sdk_sessions`/`observations`/`session_summaries`/`user_prompts`） | **9 张**（`projects`/`teams`/`team_members`/`server_sessions`/`agent_events`/`memory_items`/`memory_sources`/`api_keys`/`audit_log`），schema v33；另有 Postgres 后端 schema v50 | `src/storage/sqlite/schema.ts:5-151`；CHANGELOG v13.22.0 提及 "schema version 50" |
| File Read Gate | "DENY read with timeline"，拒绝消息 `Read blocked:` | **`permissionDecision: 'allow'`**，文案改为 "This file has prior observations — supplementary context follows. The Read result below is the full requested section." | `src/cli/handlers/file-context.ts:120, 186-192` |

此外，文档站的钩子清单（`introduction.mdx:69`）写的是 `SessionStart, UserPromptSubmit, PostToolUse, Summary (Stop), SessionEnd` —— **漏了 PreToolUse、多了 SessionEnd**。代码中 `SessionEnd` 钩子根本不存在，`src/services/integrations/AntigravityCliHooksInstaller.ts:63-65` 明确注释：

> `SessionEnd is deliberately excluded: 'session-complete' has no handler in src/cli/handlers/index.ts`

**教训**：竞品调研若停留在 README / 官网，得到的是**产品叙事**而非**工程事实**。本项目后续调研（含已有的 OpenViking / teamai-cli / MindForge 系列）建议统一采用"克隆 + 实读"的口径，并在报告中显式标注版本 commit。

---

## 三、代码实测：架构真相

### 3.1 模块地图与规模

```
claude-mem/
├── src/
│   ├── cli/          # hook 处理器（context / session-init / observation /
│   │                 #   summarize / file-edit / file-context / user-message）
│   │                 #   + adapters（claude / codex / antigravity-cli 平台适配）
│   ├── hooks/        # hook 入口
│   ├── services/
│   │   ├── sqlite/           # SessionStore(2887行) / SessionSearch + FTS5
│   │   ├── worker/           # worker-service(1412行) / SearchManager(1024行)
│   │   │   ├── agents/       # ResponseProcessor（观察生成）
│   │   │   ├── http/routes/  # SessionRoutes / CorpusRoutes / ViewerRoutes
│   │   │   ├── knowledge/    # CorpusBuilder / CorpusRenderer / CorpusStore
│   │   │   └── search/       # SearchOrchestrator + strategies/ChromaSearchStrategy
│   │   ├── smart-file-read/  # parser.ts(810行, tree-sitter) / search.ts
│   │   ├── sync/             # CloudSync / SyncApply / ChromaSync / ChromaMcpManager
│   │   ├── integrations/     # 各 IDE hooks 安装器（Cursor/Antigravity/Windsurf…）
│   │   └── telemetry/        # PostHog + scrub（脱敏白名单）
│   ├── server/       # 云端后端：Postgres routes(1964行) / jobs / generation
│   ├── servers/      # mcp-server.ts(982行)
│   ├── storage/      # sqlite/schema.ts + postgres/schema.ts
│   ├── supervisor/   # process-registry.ts(705行) 进程监管
│   └── ui/viewer/    # React Viewer + SSE
├── workers/sync-hub/ # Cloudflare Worker（云端同步）
├── plugin/           # 分发产物（server-service.cjs 10045行 等）
├── openclaw/         # OpenClaw 集成（985行）
├── ragtime/          # 独立 Apache-2.0 子项目
└── scripts/          # build-hooks.js(710行) 等
```

规模：约 1082 个文件（浅克隆），TS 源码主体在 `src/` 与 `workers/`，另有大量构建产物（`plugin/scripts/*.cjs`）。

**注意 `src/server/` + `workers/sync-hub/` + `src/supervisor/` 这三块的体量**：它们服务于云端同步与商业化（团队、API Key、审计日志、作业队列、进程监管），与"记忆管理"本身无关。评估借鉴价值时应把这层剥离。

### 3.2 存储层：从四表到多租户团队模型

`src/storage/sqlite/schema.ts` 顶部声明 `SERVER_STORAGE_SCHEMA_VERSION = 33`，`SERVER_OWNED_TABLES` 列出 9 张表。核心是 `memory_items` —— **单表统一所有知识单元**：

```sql
-- src/storage/sqlite/schema.ts:85-105
CREATE TABLE IF NOT EXISTS memory_items (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  server_session_id TEXT,
  legacy_observation_id INTEGER,          -- 迁移兼容列
  kind TEXT NOT NULL CHECK(kind IN ('observation','summary','prompt','manual')),
  type TEXT NOT NULL,
  title TEXT, subtitle TEXT, text TEXT, narrative TEXT,
  facts TEXT NOT NULL DEFAULT '[]',       -- JSON 数组
  concepts TEXT NOT NULL DEFAULT '[]',    -- JSON 数组
  files_read TEXT NOT NULL DEFAULT '[]',  -- JSON 数组
  files_modified TEXT NOT NULL DEFAULT '[]',
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at_epoch INTEGER NOT NULL,
  updated_at_epoch INTEGER NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
  FOREIGN KEY(server_session_id) REFERENCES server_sessions(id) ON DELETE SET NULL
);
```

三个设计要点：

1. **`kind` 枚举统一异构知识** —— observation / summary / prompt / manual 共用一个表结构，避免"每种知识一张表"导致的检索联合查询复杂度。对比 CodeWiki：wiki 文档、notes 笔记、raw 原始对话是三套目录 + 三套读取逻辑（`_read_doc` / `_read_note` / raw 直读，见 `wiki_search.py:209-224`）。

2. **`memory_sources` 独立溯源表**（`:107-117`）—— `source_type` 枚举（`observation`/`session_summary`/`user_prompt`/`manual`/`import`）+ `legacy_table`/`legacy_id`/`source_uri`。把"内容"与"出处"解耦，一条知识可有多个来源。对 CodeWiki 的参照：当前 `source_ref` 是写在笔记 frontmatter 里的单值字符串，升级为独立溯源实体后可支持"一条笔记源自 3 次对话"的场景。

3. **FTS5 使用 `porter unicode61` 分词**（`:170-181`）：
   ```sql
   CREATE VIRTUAL TABLE IF NOT EXISTS memory_items_fts USING fts5(
     memory_item_id UNINDEXED, project_id UNINDEXED,
     title, subtitle, text, narrative, facts, concepts,
     tokenize='porter unicode61'
   );
   ```
   `porter` 是英文词干提取器 —— **对中文无效**。这是 claude-mem 面向英文生态的取舍；CodeWiki 的 jieba 分词在中文场景下更合适，这一点我们不必跟随。

本地（legacy）侧仍是四表 + FTS5 触发器，`SessionSearch.ts:65-74` 的**能力探测写法值得学习**：

```typescript
private isFts5Available(): boolean {
  try {
    this.db.run('CREATE VIRTUAL TABLE _fts5_probe USING fts5(test_column)');
    this.db.run('DROP TABLE _fts5_probe');   // 建了探针表立即 DROP
    return true;
  } catch (error) {
    logger.debug('DB', 'FTS5 probe failed — FTS5 unavailable on this platform', ...);
    return false;
  }
}
```

FTS5 不可用时降级到 ChromaDB 与 LIKE 查询（`:49-52`、`:61`）。**"探测 + 优雅降级"而不是假设环境具备** —— 这与 CodeWiki 的 SQLite/JSON 双路径回退（`wiki_search.py` 的 session 缓存 → 独立 SQLite → 遗留 JSON 三级回退）是同一种工程自觉，双方都做对了。

### 3.3 检索层：三条链路并存

| 链路 | 实现 | 场景 |
|------|------|------|
| 本地关键词 | FTS5 虚表 + 触发器（`SessionSearch.ts`） | 单机默认 |
| 本地语义 | Chroma 向量（`services/sync/ChromaSync.ts` 1067 行 + `ChromaMcpManager.ts` 1360 行） | 可选，需 Python/uv |
| 云端 | Postgres GIN tsvector（`observation_search` 工具描述原文：*"using the server's GIN tsvector index (Phase 1)"*） | Server runtime |

`SearchManager.ts`（1024 行）负责格式化三层工作流的输出。注意**工具数与代码量的关系反转**：文档吹嘘的"9→4 工具、2718→312 行"已成历史，v13 的 `mcp-server.ts` 是 982 行、19+ 工具。原因不难推断：商业化后端（Postgres）与代码智能（tree-sitter）两条新线都带来了新工具。**"工具精简"不是终态，是某个阶段的选择。**

### 3.4 MCP 工具真实清单（19+）

`src/servers/mcp-server.ts:439-874`：

**A. 记忆三层工作流组（与文档一致）**
| 工具 | description 原文要点 |
|------|--------------------|
| `important_workflow` | *"3-LAYER WORKFLOW (ALWAYS FOLLOW): 1. search(query) → Get index with IDs (~50-100 tokens/result) 2. timeline(anchor=ID) → Get context 3. get_observations([IDs]) → Fetch full details ONLY for filtered IDs. NEVER fetch full details without filtering first. 10x token savings."* |
| `search` | Step 1，参数 query/limit/project/platformSource/type/obs_type/dateStart/dateEnd/offset/orderBy |
| `timeline` | Step 2，参数 anchor 或 query、depth_before、depth_after |
| `get_observations` | Step 3，参数 ids（必填数组） |
| `session_start_context` | 渲染与目标 hook 注入完全一致的 SessionStart 上下文（调试用） |

**B. 代码智能组（tree-sitter，文档未提）**
| 工具 | description 原文要点 |
|------|--------------------|
| `smart_search` | *"Search codebase for symbols, functions, classes using tree-sitter AST parsing. Returns folded structural views with token counts."* |
| `smart_outline` | *"Get structural outline of a file — shows all symbols with signatures but bodies folded. Much cheaper than reading the full file."* |
| `smart_unfold` | *"Expand a specific symbol (function, class, method) from a file. Returns the full source code of just that symbol."* |

**C. 云端 server 组（Postgres，文档未提）**
`observation_add` / `observation_record_event` / `observation_search` / `observation_context` / `observation_generation_status` —— 五个工具 description 均标注 "Server runtime only"。

**D. 知识语料库组（文档未提）**
`build_corpus` / `list_corpora` / `prime_corpus` / `query_corpus` / `rebuild_corpus` / `reprime_corpus`（详见 §5.2）。

**注意 schema 写法**：`important_workflow` / `list_corpora` 等用 `properties: {}` + `additionalProperties: true`（省 token），但 `search` / `timeline` / `get_observations` / `smart_*` 都是**完整详尽的参数定义**（`mcp-server.ts:476-560`、`669-778`）。这说明文档里"schema 全部极简化"也是过度美化的叙述——实际是**按工具重要性分层**：工作流指引类极简，需要精确调用的给完整 schema。

### 3.5 Hooks：真实注册清单

`plugin/hooks/hooks.json` 实际注册（由 `scripts/build-hooks.js:83-115` 生成并逐字节校验）：

| 事件 | matcher | 命令 | 超时 | async |
|------|---------|------|------|-------|
| Setup | `*` | `version-check.js` | 300s | 否 |
| SessionStart | `startup\|clear\|compact` | ① `worker-service.cjs start` ② `hook claude-code context` | 60s | 否 |
| UserPromptSubmit | — | `hook claude-code session-init` | 60s | 否 |
| PostToolUse | `*` | `hook claude-code observation` | 120s | **true** |
| **PreToolUse** | **`Read`** | `hook claude-code file-context` | 60s | **true** |
| Stop | — | `hook claude-code summarize` | 120s | **true** |

**没有 SessionEnd**（已由 `AntigravityCliHooksInstaller.ts:63-65` 注释佐证）。

**多 IDE 适配方式 —— 与 CodeWiki 的关键对照：**

| | claude-mem | CodeWiki-CN |
|---|---|---|
| 组织方式 | **每平台一份 hooks.json**（`plugin/hooks/hooks.json`、`codex-hooks.json`）+ 各 `integrations/*Installer.ts` 里散落的事件映射 | **一份 `hooks.yaml`**，家族（claude/cursor/codex）+ 事件名候选数组（`session_start: [SessionStart]`） |
| 一致性保障 | `build-hooks.js` 生成 + 逐字节比对，不一致则构建失败 | 数据结构即契约，新增智能体 = 加一行 |
| 能力差异表达 | 分散在代码注释里（如 Cursor 的 `afterFileEdit`、Antigravity 的 7 事件映射到 4 handler） | `verified: true/false` 显式标注 + 注释说明降级原因 |

**CodeWiki 的家族归并设计更优雅**：claude-mem 为每个新平台要复制一整份 hooks.json 并新增一个 Installer 类（Cursor / Antigravity / Windsurf / OpenCode / OpenClaw 各自一份），CodeWiki 只需在 `hooks.yaml` 的 `agents` 里加一行、指定 `family` 即可。**这一项 CodeWiki 领先，不应反向借鉴。**

---

## 四、File Read Gate 的反转（本次调研最重要的发现）

### 4.1 代码证据

`src/cli/handlers/file-context.ts` 全文 273 行，是 PreToolUse(Read) 的处理器。**关键在第 186-192 行的返回值**：

```typescript
// src/cli/handlers/file-context.ts:186-192
return {
  hookSpecificOutput: {
    hookEventName: 'PreToolUse',
    additionalContext: timelines.join('\n\n---\n\n'),
    permissionDecision: 'allow',        // ← 显式允许，不是 deny
  },
};
```

以及第 118-123 行的提示文案：

```typescript
// src/cli/handlers/file-context.ts:118-123
const lines: string[] = [
  `Current: ${currentDate} ${currentTime} ${currentTimezone}`,
  `This file has prior observations — supplementary context follows. The Read result below is the full requested section.`,
  `- **Need details on a past observation?** get_observations([IDs]) — ~300 tokens each.`,
  `- **Need a structural map first?** smart_outline("${safePath}") — line numbers only, cheaper than re-reading.`,
];
```

对照文档站描述的 v5 版本：

```
Read blocked: This file has prior observations. Choose the cheapest path:
- Already know enough? The timeline below may be all you need (semantic priming).
- Need details? get_observations([IDs]) -- ~300 tokens each.
- Need current code? smart_outline("path") for structure (~1-2k tokens),
  smart_unfold("path", "<symbol>") for a specific function (~400-2k tokens).
- Need to edit? Use smart tools for line numbers, then sed via Bash.
```

**语义完全反转**：

| | v5（文档） | v13（代码） |
|---|---|---|
| 决策 | `DENY` 读取 | `allow` + 附加上下文 |
| 措辞 | "Read blocked" | "This file has prior observations — supplementary context follows" |
| Read 是否执行 | 否 | **是**，且文案明说 "The Read result below is the full requested section" |
| 省 token 的方式 | 不读文件 | 给上下文，让 Agent 后续少读 |

### 4.2 为什么这个反转对 CodeWiki 很关键

我上一版报告（基于文档）把 File Read Gate 列为"最有侵略性也最有效的创新"，并建议 P2-1 争取 PreToolUse 钩子做拦截。**代码实测推翻了这个建议的方向。**

推断其放弃拦截的合理性：

1. **历史知识可能过时** —— 观察是上次会话的产物，文件可能已大改。拒绝 Agent 看当前代码，风险高于收益。
2. **Agent 确实需要当前代码** —— 尤其要编辑时，语义启动（semantic priming）替代不了真实内容。
3. **权限模型冲突** —— 一个记忆插件拒绝宿主 IDE 的文件读取，用户困惑且难以覆盖。

**给 CodeWiki 的修订建议**：
- ~~P2-1（争取 PreToolUse 做读取拦截）~~ → 改为 **P2-1'（附加上下文而非拦截）**：若 CodeBuddy 支持 PreToolUse，其价值是"在 Read 结果旁边附上该文件的历史笔记索引"，**永远 allow**。
- 好消息：**P2-2（SessionStart 软闸门）本来就是"附加"语义，与 v13 的实际做法一致，可放心推进，无需 PreToolUse 支持**。
- 更重要的：claude-mem 从 DENY 走到 ALLOW 花了数个版本，**我们不必重走这段弯路**。

### 4.3 Gate 里真正值得抄的三个细节

拦截语义被否定了，但这三个实现细节依然高价值：

**(1) mtime 新鲜度判定**（`:255-265`）—— 用被描述对象的真实修改时间判断知识是否过期：

```typescript
if (fileMtimeMs > 0) {
  const newestObservationMs = Math.max(...data.observations.map(o => o.created_at_epoch));
  if (fileMtimeMs >= newestObservationMs) {
    logger.debug('HOOK', 'File modified since last observation, skipping context injection', {...});
    return null;    // 文件在观察之后被改过 → 历史知识已过期，不注入
  }
}
```

**对照 CodeWiki**：`index_freshness.py` 的 `stale_after` 是基于**笔记创建时间**的时间窗（笔记自己"过期"了）。claude-mem 是**对端新鲜度**——判断的是被描述的文件变没变。后者更精确：一条 3 个月前的笔记，若目标文件这 3 个月没动过，它依然有效；反之昨天写的笔记，文件今早重构了，它也已失效。

**可移植性高**：CodeWiki 的笔记 frontmatter 有 `related_modules` / `related_components`，可解析出关联文件，用 `os.path.getmtime()` 比对笔记 `created` 时间即可。

**(2) 子代理跳过**（`:141-148`）：

```typescript
if (input.agentId) {
  logger.debug('HOOK', 'Skipping file context: subagent context detected', {...});
  return { continue: true, suppressOutput: true };
}
```

子代理上下文里注入主会话的文件历史是噪音。CodeWiki 的 AGENTS.md 里"委托蒸馏 subagent"等场景同样存在这个问题，**注入前应识别调用方身份**。

**(3) 路径格式双查询**（`:219-232`，issue #2691）：

```typescript
// #2691 — PostToolUse stores whatever path form the observer recorded
// (absolute tool-input path, or project-root-relative per the prompt). The
// PreToolUse:Read query previously sent ONLY the cwd-relative form, so it
// never matched absolute-path storage. Send both candidate forms ...
const candidateQueryPaths = Array.from(new Set([
  absolutePath.split(path.sep).join("/"),
  relativePath,
].filter(Boolean)));
```

**写入端与查询端的路径规范化必须对齐**——这是个高频踩坑点。CodeWiki 的 `wiki_search.py:396-399` 也在做同样的事（`fk.replace("\\", "/")` 保证 doc_key 形状一致），说明两边都踩过。可记录为通用工程经验。

**(4) 特异性排序**（`:69-86`，实现与文档描述一致）：

```typescript
let specificityScore = 0;
if (inModified) specificityScore += 2;      // 文件被修改（不只是读取）
if (totalFiles <= 3) specificityScore += 2; // 观察聚焦
else if (totalFiles <= 8) specificityScore += 1;
```

**(5) 类型图例只有 6 类**（`:21-28`），与文档的 9 类图例不符：

```typescript
const TYPE_ICONS: Record<string, string> = {
  decision: '⚖️', bugfix: '🔴', feature: '🟣',
  refactor: '🔄', discovery: '🔵', change: '✅',
};
```

---

## 五、其他值得关注的实现

### 5.1 token 估算：一行除法

`src/shared/timeline-formatting.ts:74-77`：

```typescript
export function estimateTokens(text: string | null): number {
  if (!text) return 0;
  return Math.ceil(text.length / 4);
}
```

调用处（`SearchManager.ts:229`）：`const tokens = estimateTokens(obs.narrative);` —— **只估正文一个字段**，正是"获取这条要花多少"的语义。

`smart-file-read/parser.ts` 的 `FoldedFile` 接口也带 `foldedTokenEstimate: number`（`:31`），`search.ts` 的 `SearchResult` 带 `tokenEstimate`（`:46`）——**成本可见贯穿了记忆检索与代码检索两条链路**。

**对 CodeWiki 的意义**：P0-1 建议的门槛比预想更低。CodeWiki 的 `injection_budget.py` 已经在用 `len()` 做字符预算，加一个 `/4` 的换算并暴露到检索结果即可，无需引入任何 tokenizer。

### 5.2 Knowledge Corpus：知识场景化

`src/services/worker/knowledge/` 三个类构成一条完整链路：

```
build_corpus(name, filter)          # CorpusBuilder:37-99
  → searchOrchestrator.search()     # 按 filter(query/types/concepts/files/日期) 检索
  → getObservationsByIds()          # 取回完整观察行（date_asc 排序）
  → renderer.generateSystemPrompt() # 生成 system prompt
  → renderer.renderCorpus()         # 渲染语料
  → stats.token_estimate = estimateTokens(renderedText)   # :92
  → corpusStore.write(corpus)       # 落盘为 CorpusFile
prime_corpus(name)   → 创建一个预载该语料的 AI session（带 session_id）
query_corpus(name,q) → 向该 session 提问
rebuild_corpus(name) → 用存储的 filter 重跑检索刷新（不重新预热）
reprime_corpus(name) → 清掉历史 Q&A，开新 session
```

**这是什么**：把"一批筛选出来的观察"固化成一个**可复用的、带 AI session 的知识场景**，之后对它的提问都在这个预载上下文里进行。语料本身落盘为 `CorpusFile`（含 `version`、`filter`、`stats`、`system_prompt`、`session_id`、`observations`），可重建、可列举。

**与 CodeWiki 的对照**：CodeWiki 有 Doctrine（`doctrine.py`，团队共识聚合）与场景块（AGENTS.md 提到"按对象分组写场景块（UPDATE 优先）"）的概念。**Corpus 的独特之处是它保留了 `filter` 并支持 `rebuild`——语料是"查询的固化"而非"内容的拷贝"**，因此可随知识库增长自动刷新。这是一个很实用的设计：CodeWiki 的 Doctrine 若也能记住"它是从哪些查询聚合出来的"，就能支持增量刷新而不必每次全量重算。

### 5.3 smart file read：tree-sitter 做折叠视图

`src/services/smart-file-read/parser.ts`：

- **27 种语言映射**（`LANG_MAP:34-74`）+ 对应 grammar 包（`GRAMMAR_PACKAGES:81-106`），含 python/go/rust/java/kotlin/swift/php/scala/haskell/zig，以及 markdown/yaml/toml/sql。
- **符号类型 20 种**（`CodeSymbol.kind:15`）：function/class/method/interface/type/const/variable/export/struct/enum/trait/impl/property/getter/setter/mixin/section/code/metadata/reference。
- 每个符号带 `signature` / `jsdoc` / `lineStart` / `lineEnd` / `parent` / `exported` / `children`。
- `FoldedFile` 带 `foldedTokenEstimate` —— 折叠后 token 估算。
- `search.ts` 有 `IGNORE_DIRS`（node_modules/.git/dist/build/.next/\__pycache__/.venv/target/vendor…）与 `MAX_FILE_SIZE = 512 * 1024`。

**对照 CodeWiki**：CodeWiki 本身就用 tree-sitter 做依赖图/调用图（10 语言），但**没有"折叠视图"这个消费形态**——即"只给符号签名不给函数体"的中间层。这正是 claude-mem 五层上下文策略的第 3 层（L3 源码），填补了"索引"与"全文"之间的空白。

**这是一个对 CodeWiki 高价值、低门槛的补强**：分析器已有 AST 与符号表，只需加一个"渲染为折叠视图 + 估算 token"的输出层。

### 5.4 商业化与遥测（不借鉴，但需知情）

CHANGELOG 近期条目显示项目方向：CMEM Pro 付费计划（Stripe Checkout、`/api/pro/trial/claim`）、PostHog 遥测（`observer_turn_rollup`、`usage_limit_hit`）、订阅配额守卫（`RateLimitStore`）、schema 已演进到 v50。

遥测脱敏做得较认真（`services/telemetry/scrub.ts` + `error-scrub.ts`，CHANGELOG 反复强调"closed enums、provider 的 limit 文本从不离开机器、字段在 scrub 白名单"）。**这份"遥测字段设计 + 脱敏"的实践值得单独参考**，若 CodeWiki 后续增强 `telemetry.py` 的上报能力。

---

## 六、修订后的借鉴建议

### 6.1 建议清单（基于代码实测修订）

| 编号 | 借鉴项 | 代码依据 | 改动面 | 风险 | 相对上版变化 |
|------|--------|---------|--------|------|------------|
| **P0-1** | 检索结果加 `est_tokens` | `timeline-formatting.ts:74-77`（一行除法） | `wiki_search.py` + `knowledge_loop.py` | 低 | **强化**（实现成本远低于预估） |
| **P0-2** | `query_wiki(by_file=...)` | `/api/observations/by-file` + 特异性排序 `file-context.ts:69-86` | `knowledge_loop.py` + `registry.py` | 低 | 不变 |
| **P0-3** | 工作流写进工具描述 | `important_workflow`（`mcp-server.ts:439-445`）+ 按重要性分层 schema | `registry.py` | 低 | **修正**（不是全部极简，是分层） |
| **P1-1** | `mode="timeline"` | `timeline(anchor, depth_before, depth_after)` | `knowledge_loop.py` | 低-中 | 不变 |
| **P1-2** | 笔记 frontmatter 结构化字段 | `memory_items.facts/concepts/files_modified` + `memory_sources` 溯源表 | `ingest_note` / `frontmatter.py` | 中（须守往返不变量） | **强化**（有独立溯源表可参照） |
| **P1-3** | 折叠视图（smart_outline 等价物） | `smart-file-read/parser.ts`（tree-sitter 27 语言 + `foldedTokenEstimate`） | 新增输出层，复用现有分析器 | 中 | **新增**（高价值） |
| **P1-4** | 对端新鲜度（mtime 判定） | `file-context.ts:255-265` | `index_freshness.py` | 中 | **新增**（比时间窗更精确） |
| **P1-5** | 语料/场景块保留 filter 支持 rebuild | `CorpusBuilder:37-99`（`filter` 随 `CorpusFile` 落盘） | `doctrine.py` | 中 | **新增** |
| **P2-1'** | PreToolUse 做**附加上下文**（非拦截） | `permissionDecision: 'allow'`（v13 实测） | `hooks.yaml` + 新钩子 | 高（需先验证 IDE 支持） | **方向反转** |
| **P2-2** | SessionStart 软闸门 | 与 v13 实际做法同构，无需 PreToolUse | 注入逻辑 | 低 | **优先级上调**（无需新钩子） |
| **P2-3** | 遥测脱敏白名单 | `services/telemetry/scrub.ts` + CHANGELOG 的字段设计纪律 | `telemetry.py` | 低 | 新增 |

### 6.2 明确不借鉴（含修订）

| 项 | 原因（基于代码实测） |
|----|-------------------|
| **读取拦截（DENY）** | claude-mem 自己已从 DENY 改为 ALLOW（`file-context.ts:190`）。**这是最强的反证，不必重走弯路。** |
| **常驻 worker 进程** | 违背 CodeWiki "工具不持模型"的 Doctrine。且实测其复杂度的真实来源：`supervisor/process-registry.ts`(705行) + `worker-service.ts`(1412行) + `plugin/scripts/*.cjs`(万行级构建产物) —— 这个成本是商业化后端带来的，与记忆能力无关。 |
| **多租户 schema（teams/api_keys/audit_log）** | 服务于 SaaS 商业化。CodeWiki 的团队治理走 git 仓库 + 文件所有权（`memories/<user_id>.md` 即 git 级互斥原语），路线不同且更适合开源协作。 |
| **Postgres 后端** | 同上。 |
| **Chroma 向量库** | `ChromaSync.ts`(1067行) + `ChromaMcpManager.ts`(1360行) = **2427 行代码**换一个可选能力，性价比低。CodeWiki 已有 BM25 + 本体论扩展 + 图多跳 + authority/usage 加权。 |
| **每平台一份 hooks.json** | CodeWiki 的 `hooks.yaml` 家族归并更优雅（见 §3.5 对照表）。 |
| **无闸门自动入库** | 实测确认其无内容评审（confirm/draft 匹配均为安装态/会话态/同步态）。与 CodeWiki `confirm_note` + ADR-0002 路线冲突。 |
| **porter 分词** | 对中文无效，CodeWiki 的 jieba 更合适。 |

### 6.3 给 CodeWiki 的三条"不必妄自菲薄"

1. **hook 多智能体抽象 CodeWiki 领先** —— 家族归并 + 事件名候选数组 + `verified` 诚实标注，优于 claude-mem 的"每平台复制一份配置 + 一个 Installer 类"。
2. **中文检索能力 CodeWiki 领先** —— jieba vs porter；且 CodeWiki 的 `query_coverage.missing`（区分"主题相邻"与"真正答案"）在 claude-mem 中没有对等物。
3. **知识治理 CodeWiki 领先** —— `confirm_note` 闸门、笔记状态机（`draft/stable`）、`batch_set_status`、Doctrine 聚合确认，这些 claude-mem 完全没有。

---

## 七、结论

**方法论层面**：本次调研最有价值的产出不是某个功能点，而是**证明了"读文档"与"读代码"会得出方向性相反的结论**。上一版基于文档的报告建议"争取 PreToolUse 做读取拦截"，代码实测后发现 claude-mem 自己已经放弃了这个做法。**建议把"克隆 + 实读 + 标注 commit"固化为本项目竞品调研的标准动作。**

**技术层面**，按性价比排序的三件事：

1. **`est_tokens` 字段**（P0-1）—— 一行 `Math.ceil(len/4)` 就能让"成本可见"落地，与 `injection_budget.py` 现有字符预算口径天然衔接。投入最小，收益最直接。
2. **`query_wiki(by_file=...)` + mtime 对端新鲜度**（P0-2 + P1-4）—— 前者是"改文件 X 时给 X 的历史知识"，后者用文件系统时间戳精准判定知识是否过期。两者组合起来，才是 File Read Gate 剥离掉"拦截"外壳后剩下的真正内核。
3. **折叠视图（P1-3）** —— CodeWiki 已有 tree-sitter 分析器，补一个"签名 + 行号、函数体折叠、带 token 估算"的输出层，就填上了"索引"与"全文"之间的关键空档。

**战略层面**：claude-mem v13 已是一款商业化团队知识 SaaS，其架构复杂度（云端后端、多租户、进程监管、计费）是业务形态驱动的。CodeWiki 应该借鉴的是它**数据建模的演进思路**（`memory_items` 统一 + `memory_sources` 溯源 + filter 可重建的语料），而不是它的部署形态。至于"拦截 Agent 读文件"这条激进路线——**前人已经替我们验证了它行不通**。

---

## 附录 A：源码证据索引

| 结论 | 文件:行 | 关键代码 |
|------|---------|---------|
| 版本 v13.23.1 | `package.json:3` / git `f92996e` | — |
| File Read Gate 已改为 allow | `src/cli/handlers/file-context.ts:186-192` | `permissionDecision: 'allow'` |
| Gate 文案已改 | `src/cli/handlers/file-context.ts:118-123` | "supplementary context follows" |
| mtime 新鲜度判定 | `src/cli/handlers/file-context.ts:255-265` | `fileMtimeMs >= newestObservationMs → return null` |
| 子代理跳过 | `src/cli/handlers/file-context.ts:141-148` | `if (input.agentId)` |
| 路径双格式查询 | `src/cli/handlers/file-context.ts:219-232` | issue #2691 |
| 特异性排序 | `src/cli/handlers/file-context.ts:69-86` | `+2/+2/+1` |
| 类型图例 6 类 | `src/cli/handlers/file-context.ts:21-28` | `TYPE_ICONS` |
| token 估算 | `src/shared/timeline-formatting.ts:74-77` | `Math.ceil(text.length / 4)` |
| 搜索结果带 token | `src/services/worker/SearchManager.ts:229` | `estimateTokens(obs.narrative)` |
| MCP 工具 19+ | `src/servers/mcp-server.ts:439-874` | `important_workflow` / `smart_*` / `observation_*` / `*_corpus` |
| 存储 schema v33 | `src/storage/sqlite/schema.ts:5-151` | 9 张表 |
| `memory_items` 统一模型 | `src/storage/sqlite/schema.ts:85-105` | `kind` CHECK 枚举 |
| 独立溯源表 | `src/storage/sqlite/schema.ts:107-117` | `memory_sources` |
| FTS5 porter 分词 | `src/storage/sqlite/schema.ts:170-181` | `tokenize='porter unicode61'` |
| FTS5 能力探测 | `src/services/sqlite/SessionSearch.ts:65-74` | `_fts5_probe` 建后即 DROP |
| hooks 注册清单 | `plugin/hooks/hooks.json`（生成于 `scripts/build-hooks.js:83-115`） | 6 类事件，无 SessionEnd |
| SessionEnd 被刻意排除 | `src/services/integrations/AntigravityCliHooksInstaller.ts:63-65` | 代码注释 |
| tree-sitter 27 语言 | `src/services/smart-file-read/parser.ts:34-106` | `LANG_MAP` / `GRAMMAR_PACKAGES` |
| 折叠视图 token 估算 | `src/services/smart-file-read/parser.ts:31` | `foldedTokenEstimate` |
| Corpus 构建流程 | `src/services/worker/knowledge/CorpusBuilder.ts:37-99` | search → hydrate → render → estimate → write |
| 商业化方向 | `CHANGELOG.md:7-90` | CMEM Pro / Stripe / PostHog / 配额 |

## 附录 B：调研覆盖的官方文档（均已与代码交叉验证）

| 文档 | 与代码一致性 |
|------|------------|
| README.zh | 部分失真（工具数、组件清单） |
| Architecture Overview | 部分失真（无 smart-file-read、无 server 后端） |
| Architecture Evolution (v3→v5) | 历史叙述，与 v13 现状差距大 |
| Hook Lifecycle | **有误**（多列 SessionEnd、漏 PreToolUse） |
| Database Architecture | **已过时**（4 表 → 9 表 + Postgres） |
| Search Architecture | **已过时**（4 工具 → 19+ 工具） |
| Progressive Disclosure | 理念层仍成立，实现细节有出入（图例 9 类 → 6 类） |
| Context Engineering | 理念层，不受版本影响，参考价值最高 |
| File Read Gate | **核心行为已反转**（DENY → ALLOW） |

---

> 调研过程中产生的源码副本位于 `d:\repos\CodeWiki-CN\.tmp\claude-mem`（浅克隆）。**该目录为调研临时产物，确认报告后请删除或加入 `.gitignore`**，勿提交至仓库。
