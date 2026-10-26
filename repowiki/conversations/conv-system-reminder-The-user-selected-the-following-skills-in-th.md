---
type: Conversation
title: "conversation 20261021T023202Z"
status: distilled
stale_after: 2027-01-19
generated: { by: codewiki/5.16.0, at: 2026-10-21T02:32:02Z }
captured_at: "2026-10-21T02:32:02Z"
content_hash: "sha256:770546ef55cb10bab8b84de9cbc4e710b764ff99390050377e620426954ba5ee"
friction_score: 40
friction_signals: "correction=0,interrupt=0,repeat=2,user_turns=41"
keep_raw: false
link_to: ""
source_session: "fc9dd122-6339-46c5-9cc7-2a13741b059a"
turn_count: 115
---

# Conversation Transcript

user: <system-reminder>
The user selected the following skills in this order. Use them and strictly follow each skill's instructions:
- improve-codebase-architecture
</system-reminder>

[@improve-codebase-architecture](skill://improve-codebase-architecture)
assistant: [{'type': 'thinking', 'thinking': '用户选了 improve-codebase-architecture skill，但这个 skill 不在可用列表里，需要先弹任务关联框（SessionStart hook 要求），然后告知用户该 skill 不可用并询问替代方案。', 'signature': ''}]
assistant: [tool: AskUserQuestion · {"questions": [{"header": "任务关联", "multiSelect": false, "options": [{"description": "产品维护", "label": "产品维护"}, {"description": "发版本", "…
user: [tool-ok: - 多智能体"="产品维护". You can now continue with these answers in mind.]
assistant: [{'type': 'thinking', 'thinking': '用户选择了"产品维护"任务，我需要绑定这个任务并获取上下文，同时注意到用户调用的 `improve-codebase-architecture` 技能不在可用列表中，需要告知用户。', 'signature': ''}]
assistant: [tool: mcp_call · {"arguments": {"source_session_id": "fc9dd122-6339-46c5-9cc7-2a13741b059a", "task_id": "产品维护"}, "toolName": "mcp__codewiki__set_session_task"…
assistant: [tool: mcp_call · {"arguments": {"task_id": "产品维护"}, "toolName": "mcp__codewiki__get_task_context"}]
user: [tool-ok: {"error": "Task '\u4ea7\u54c1\u7ef4\u62a4' does not exist."}]
user: [tool-ok: {"error": "Task '\u4ea7\u54c1\u7ef4\u62a4' does not exist."}]
assistant: [{'type': 'thinking', 'thinking': '任务绑定失败，需要先列出任务确认「产品维护」是否存在；同时用户调用的 skill 不在可用列表中，需要检查是否有相近的替代 skill。', 'signature': ''}]
assistant: [tool: mcp_call · {"arguments": {}, "toolName": "mcp__codewiki__list_tasks"}]
assistant: [tool: Glob · **/*improve-codebase-architecture*]
user: [tool-ok: {"ok": true, "tasks": []}]
user: [tool-ok: repowiki\conversations\conv-对-CodeWiki-CN-跑-improve-codebase-architecture-skill.md]
assistant: [{'type': 'thinking', 'thinking': '任务列表为空说明任务记忆系统可能未启用，需要先查看之前跑过的 skill 对话记录了解 improve-codebase-architecture 是什么，再决定下一步。\n', 'signature': ''}]
assistant: [tool: Read · D:\repos\CodeWiki-Plus\repowiki\conversations\conv-对-CodeWiki-CN-跑-improve-codebase-architecture-skill.md]
user: [tool-ok: 23]
assistant: [{'type': 'thinking', 'thinking': '用户调用的 `improve-codebase-architecture` skill 不在可用列表中，任务关联已完成（产品维护），现在需要告知用户 skill 不可用并询问替代方案。', 'signature': ''}]
assistant: 收到任务关联「产品维护」（注：任务列表当前为空，本次会话未绑定到持久化任务记忆）。

关于 `@improve-codebase-architecture` skill：**当前会话的可用 skill 列表里没有这个 skill**。从历史记录看，2026-08-24 曾对 CodeWiki-CN 跑过同名 skill 并产出 6 个候选改进点（frontmatter/layout deep module、WikiStore 写入 seam、拆 registry.py、SearchIndex seam、WorkspaceResolver、handler 结构化返回）。

请确认本次意图：
assistant: [tool: AskUserQuestion · {"questions": [{"header": "Skill 处理", "multiSelect": false, "options": [{"description": "用 codewiki 的「架构审查与热点分析」skill 对本仓库（CodeWiki-Pl…
user: [tool-ok: Your questions have been answered: "improve-codebase-architecture 不在当前 skill 列表，请选择替代方案："="跑架构审查 skill". You …
assistant: [{'type': 'thinking', 'thinking': '用户选择了跑架构审查 skill，直接调用 codewiki 的架构审查与热点分析技能。', 'signature': ''}]
assistant: [tool: Skill · {"skill": "codewiki:架构审查与热点分析"}]
user: [tool-ok: Launching skill: codewiki:架构审查与热点分析]
user: Base directory for this skill: D:\repos\CodeWiki-Plus\.qoder\commands\codewiki

# 架构审查与热点分析



通过依赖图分析理解代码库的高层架构：识别核心层/服务层/应用层、发现依赖热点和耦合风险、定位入口点和模块边界。



调用 MCP 获取完整工作流并按其执行：



```

get_prompt(name="architecture-review", arguments={"repo_path": "."})

```



返回的工作流包含分阶段指引，逐步照做即可。

不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
assistant: [{'type': 'thinking', 'thinking': '用户要求跑架构审查，skill 指引先调 `get_prompt(name="architecture-review", arguments={"repo_path": "."})` 拿工作流模板，所以我先获取 MCP 工具的 schema 再调用。\n', 'signature': ''}]
assistant: [tool: mcp_get · {"toolName": "mcp__codewiki__get_prompt"}]
user: [tool-ok: {"name":"mcp__codewiki__get_prompt","description":"Retrieve CodeWiki's prompts. Two families share this tool.…
assistant: [{'type': 'thinking', 'thinking': '按 skill 指引调用 get_prompt 获取 architecture-review 工作流模板。', 'signature': ''}]
assistant: [tool: mcp_call · {"arguments": {"arguments": {"repo_path": "."}, "name": "architecture-review", "repo_path": "."}, "toolName": "mcp__codewiki__get_prompt"}]
user: [tool-ok: }]
assistant: [{'type': 'thinking', 'thinking': '工作流第一步要 analyze_repo，先获取该工具的 schema 再调用。\n', 'signature': ''}]
assistant: [tool: mcp_get · {"toolName": "mcp__codewiki__analyze_repo"}]
user: [tool-ok: {"name":"mcp__codewiki__analyze_repo","description":"Analyze a code repository: Tree-sitter AST parsing → fun…
assistant: [{'type': 'thinking', 'thinking': '工作流要求调用 analyze_repo，schema 已拿到，现在对本仓库执行分析。', 'signature': ''}]
assistant: [tool: mcp_call · {"arguments": {"repo_path": "D:\\repos\\CodeWiki-Plus"}, "toolName": "mcp__codewiki__analyze_repo"}]
user: [tool-error: {"session_id": "64f22370c43e", "workspace_dir": "D:\\repos\\CodeWiki-Plus\\.codewiki\\workspace", "repo_name": "CodeWiki-Plus", "output_dir": "D:\\repos\\CodeWiki-Plus\\repowiki", "stats": {"total_components": 2030, "total_leaf_nodes": 92, "languages": {"python": 2030}}, "files": {"summary": "D:\\repos\\CodeWiki-Plus\\.codewiki\\workspace\\summ…
assistant: [{'type': 'thinking', 'thinking': 'analyze_repo 返回了仓库级统计，但工作流步骤 2-5 需要依赖图数据（list_dependencies、list_components、analyze_impact），先并行拉取这些核心数据。', 'signature': ''}]
assistant: [tool: mcp_get · {"toolName": "mcp__codewiki__list_dependencies"}]
assistant: [tool: mcp_get · {"toolName": "mcp__codewiki__list_components"}]
assistant: [tool: mcp_get · {"toolName": "mcp__codewiki__analyze_impact"}]
user: [tool-ok: {"name":"mcp__codewiki__list_dependencies","description":"Write the full dependency graph to a workspace file…
user: [tool-ok: {"name":"mcp__codewiki__list_components","description":"Write the full component index to a workspace file. R…
user: [tool-ok: {"name":"mcp__codewiki__analyze_impact","description":"Transitive dependency impact analysis. Given component…
assistant: [{'type': 'thinking', 'thinking': '按工作流步骤 2/3 并行拉取模块级依赖图与高影响组件清单。\n', 'signature': ''}]
assistant: [tool: mcp_call · {"arguments": {"direction": "both", "module_level": true, "repo_path": "D:\\repos\\CodeWiki-Plus"}, "toolName": "mcp__codewiki__list_dependen…
assistant: [tool: mcp_call · {"arguments": {"direction": "depended_by", "repo_path": "D:\\repos\\CodeWiki-Plus"}, "toolName": "mcp__codewiki__list_dependencies"}]
user: [tool-ok: }]
user: [tool-ok: }]
assistant: [{'type': 'thinking', 'thinking': '依赖图文件已生成，需要读取 high-impact 组件数据以识别核心层。', 'signature': ''}]
assistant: [tool: Bash · python -c "import json; d=json.load(open(r'D:\repos\CodeWiki-Plus\.codewiki\workspace\dependencies.json','r',encoding='utf-8')); print('keys:', l…
user: [tool-ok: ?                                                                                depended_by=22 depends_on=0]
assistant: [{'type': 'thinking', 'thinking': 'high_impact_components 的 id 字段缺失，需要查看原始 JSON 结构确认实际字段名。\n', 'signature': ''}]
assistant: [tool: Bash · python -c "import json; d=json.load(open(r'D:\repos\CodeWiki-Plus\.codewiki\workspace\dependencies.json','r',encoding='utf-8')); hi=d['high_impac…
user: [tool-ok: {'component_id': 'codewiki\\mcp\\prompts.py::_resolve_path', 'depended_by_count': 22}]
assistant: [{'type': 'thinking', 'thinking': 'high-impact 列表已拿到，但里面混入了 vendored 的 backend 分析器代码（src/be/...），需要先核对目录布局确认哪些是本项目一等公民代码，再做模块级聚合。', 'signature': ''}]
assistant: [tool: Bash · ls -la codewiki/src/ 2>&1 | head -30; echo "---"; ls codewiki/ 2>&1]
user: [tool-ok: utils]
assistant: [{'type': 'thinking', 'thinking': '需要确认 codewiki/src/be 是 vendored 第三方代码还是本项目一等公民，以决定架构分析是否应排除它。\n', 'signature': ''}]
assistant: [tool: Bash · ls codewiki/src/be/ 2>&1; echo "---"; ls codewiki/src/fe/ 2>&1; echo "---be README/origin---"; find codewiki/src/be -maxdepth 2 -name "README*" -…
user: [tool-ok: ---be README/origin---]
assistant: [{'type': 'thinking', 'thinking': '需要确认 be/fe 是否为一等公民代码还是 vendored 第三方，查 pyproject 与代码引用情况。', 'signature': ''}]
assistant: [tool: Bash · cat pyproject.toml | head -50; echo "---"; grep -rn "from codewiki.src.be\|from codewiki.src.fe\|import codewiki.src.be\|import codewiki.src.fe" …
user: [tool-ok: codewiki/src/be/agent_tools/read_code_components.py]
assistant: [{'type': 'thinking', 'thinking': 'be/fe 被一等公民代码引用，属于项目一部分，需要按目录维度统计 depended_by 分布以识别真正的架构热点。', 'signature': ''}]
assistant: [tool: Bash · python -c "]
user: [tool-ok: first record: {'source': '.trae\\hooks\\capture_session_end.py::_codewiki_launch_env', 'target': '.trae\\hook…
assistant: [{'type': 'thinking', 'thinking': '需要按目录维度聚合 depended_by 数据，识别一等公民模块的热点分布，排除 vendored 的 be/fe 子目录干扰。\n', 'signature': ''}]
assistant: [tool: Bash · python -c "]
user: [tool-error: Exit code 1 File "<string>", line 12 src = r['source'].replace('\','/') ^ SyntaxError: unterminated string literal (detected at line 12)]
assistant: [{'type': 'thinking', 'thinking': '上一个 Python 脚本因为反斜杠转义问题失败，改用双反斜杠修复并重新运行目录聚合统计。\n', 'signature': ''}]
assistant: [tool: Bash · python -c "]
user: [tool-ok: 20  codewiki]
assistant: [{'type': 'thinking', 'thinking': '需要进一步细分 codewiki/src 与 codewiki/mcp 内部的热点分布，以识别真正的架构核心模块。\n', 'signature': ''}]
assistant: [tool: Bash · python -c "]
user: [tool-ok: 22  codewiki\mcp\prompts.py::_resolve_path]
assistant: [{'type': 'thinking', 'thinking': '热点文件已识别，接下来需要检查这些核心文件的大小和函数数量，以评估是否存在上帝模块问题。', 'signature': ''}]
assistant: [tool: Bash · python -c "]
user: [tool-ok: 240 lines /   4 def+class  codewiki\mcp\server.py]
assistant: [{'type': 'thinking', 'thinking': '接下来需要检查这些热点文件之间是否存在循环依赖，以识别架构耦合风险。\n', 'signature': ''}]
assistant: [tool: Bash · python -c "]
user: [tool-ok: codewiki/src/be/caw_backend.py <-> codewiki/src/be/caw_toolkit.py]
assistant: [{'type': 'thinking', 'thinking': '需要读取几个关键热点文件以理解它们的实际职责，从而判断架构改进方向。\n', 'signature': ''}]
assistant: [tool: Read · D:\repos\CodeWiki-Plus\codewiki\mcp\cache.py]
assistant: [tool: Read · D:\repos\CodeWiki-Plus\codewiki\mcp\registry.py]
user: [tool-ok: 80	    def to_node(self, source_code: str = "", docstring: str = "") -> Node:]
user: [tool-ok: 60]
assistant: [{'type': 'thinking', 'thinking': '已完成数据收集，现在整理架构审查发现并向用户展示热点与改进候选，询问下一步深入方向。', 'signature': ''}]
assistant: 架构审查完成。以下是基于依赖图分析的 CodeWiki-Plus 架构发现。

## 架构审查报告（CodeWiki-Plus @ 99e4ec0）

**规模**：2030 个 Python 组件 / 92 个叶节点 / 7972 条依赖边

### 1. 层次图

```mermaid
graph TD
    subgraph "应用层 / 入口边界"
        CLI[codewiki/cli<br/>CLI 命令]
        HOOKS[codewiki/hooks<br/>Session hooks]
        MCP_S[codewiki/mcp/server.py<br/>MCP 入口]
    end
    subgraph "编排层 / MCP 工具"
        REG[mcp/registry.py ★3404行<br/>53 个工具 schema + dispatch]
        TOOLS[mcp/tools/*<br/>~30 个工具 handler]
        CACHE[mcp/cache.py ★1885行<br/>SQLite 分析缓存]
        WS[mcp/workspace.py<br/>SessionWorkspace]
    end
    subgraph "核心层 / 领域服务"
        STORE[src/store.py ★1505行<br/>KnowledgeStore]
        CFG[src/config.py<br/>配置]
        FM[src/frontmatter.py<br/>frontmatter 解析]
        RET[src/retrieval.py<br/>检索内核]
    end
    subgraph "vendored 后端"
        BE[src/be/dependency_analyzer<br/>多语言分析器]
        BE2[src/be/documentation_generator]
    end
    CLI --> REG --> TOOLS
    MCP_S --> REG
    HOOKS --> TOOLS
    TOOLS --> CACHE --> STORE
    TOOLS --> WS --> STORE
    TOOLS --> FM --> STORE
    TOOLS --> RET
    STORE --> CFG
    TOOLS --> BE
```

### 2. 热点文件 Top 10（按 fan-in 被依赖边数）

| Fan-in | 文件 | 行数 | 职责 | 风险 |
|---|---|---|---|---|
| 316 | `mcp/cache.py` | 1885 | SQLite 分析缓存 + LazyComponentStore + 检索内核 re-export | **上帝模块** |
| 277 | `src/store.py` | 1505 | KnowledgeStore 全部写入/查询 | **上帝模块** |
| 164 | `src/be/.../php.py` | - | vendored 语言分析器 | 低（vendored） |
| 152 | `cli/utils/logging.py` | 83 | CLILogger | 低（小文件） |
| 115 | `src/be/.../typescript.py` | - | vendored | 低 |
| 72 | `src/config.py` | 594 | 配置 | 中 |
| 69 | `mcp/tools/task_manager.py` | 1469 | 任务记忆管理 | **上帝模块** |
| 65 | `mcp/tools/wiki_search.py` | 847 | 检索入口 | 中 |
| 61 | `mcp/tools/workspace_layout.py` | 397 | 输出路径约定 | 中 |
| 58 | `mcp/tools/distill_conversation.py` | 2106 | 蒸馏 worker | **上帝模块** |

### 3. 循环依赖（14 对 mutual，按风险排序）

| 循环对 | 说明 | 风险 |
|---|---|---|
| `mcp/cache.py` ↔ `src/store.py` | 缓存 ↔ 领域存储 | **高**（核心层互染） |
| `mcp/cache.py` ↔ `src/retrieval.py` | 缓存 ↔ 检索内核 | **高** |
| `src/config.py` ↔ `src/store.py` | 配置 ↔ 存储 | 中 |
| `mcp/tools/workspace_bootstrap.py` ↔ `workspace_layout.py` | 初始化 ↔ 布局 | 中 |
| `mcp/tools/wiki_index.py` ↔ `wiki_lint.py` | 索引 ↔ 质量 | 中 |
| `mcp/tools/distill_conversation.py` ↔ `note_ingest.py` | 蒸馏 ↔ 入库 | 中 |

### 4. 候选改进点（按 deep module 思路）

**C1 — `mcp/cache.py` 拆出检索内核适配器**（最强候选）
- 现状：1885 行，既做 SQLite 持久化又 re-export `src/retrieval.py` 的 11 个符号给下游
- 症状：`LazyComponentStore.items` 被 131 处调用（全仓最高）——典型的"缓存门面膨胀"
- 拆法：`mcp/cache.py` 只留 SQLite 层；检索内核 re-export 移到新 `mcp/retrieval_adapter.py`；`LazyComponentStore` 按职责拆 `component_store.py`

**C2 — `mcp/registry.py` 3404 行单文件**
- 现状：53 个工具 schema 全堆在一个 dict 里，4 个顶级函数
- 症状：每次新增工具都要改这个文件（git 冲突热点）
- 拆法：每个工具 handler 文件自带 `TOOL_DEF = ToolDef(...)`，registry 改成自动发现（扫 `mcp/tools/*.py` 的 `TOOL_DEF` 属性）

**C3 — `src/store.py` 1505 行 KnowledgeStore**
- 现状：写入/查询/索引刷新/原子写全在一个类
- 症状：与 `cache.py`、`config.py` 形成双向循环
- 拆法：抽出 `store/writer.py`、`store/query.py`、`store/index.py`；`locked()`/`atomic_write` 移到 `store/locking.py`

**C4 — `mcp/tools/distill_conversation.py` 2106 行**
- 现状：46 个函数，蒸馏全流程（raw 读取、LLM 调用、submit、supersedes 处理）
- 症状：与 `note_ingest.py` 双向依赖
- 拆法：LLM 调用层抽 `distill/llm.py`；submit 协议层抽 `distill/submit.py`

**C5 — `mcp/tools/wiki_lint.py` 2748 行**
- 现状：40 个检查函数 + 报告生成 + 修复建议
- 拆法：按检查类别拆 `lint/frontmatter.py`、`lint/staleness.py`、`lint/adoption.py`

**C6 — `mcp/tools/workspace_bootstrap.py` ↔ `workspace_layout.py` 循环**
- 现状：初始化时依赖布局常量，布局又依赖初始化产物
- 拆法：抽出 `workspace_conventions.py` 作为纯数据模块，两边都依赖它

### 5. 推荐优先级

按"改动风险 × 收益"排序：**C1 > C2 > C3 > C6 > C4 > C5**

- C1 解决最高频热点 + 打破核心层循环
- C2 让 53 个工具的增删改不再冲突
- C3 是核心层去上帝模块的关键一步

需要我深入某个候选（比如 C1 的具体拆法 + 接口设计）吗？
user: 其实就是代码架构上的优化对吧，本身功能是没问题的
assistant: [{'type': 'thinking', 'thinking': '用户在确认理解，需要简洁回应确认并给出下一步选项。', 'signature': ''}]
assistant: 对，纯代码架构优化——功能行为完全不动，只动"怎么组织"。

具体来说：
- **不碰**：MCP 工具的输入输出 schema、CLI 命令的语义、Wiki 生成结果、知识入库逻辑
- **只动**：文件怎么拆、循环依赖怎么解、热点模块怎么瘦身

六个候选全是"搬家"——把函数从 A 文件挪到 B 文件，让调用关系变成单向、让大文件变小、让新增功能不再改同一个文件。测试全过、行为零变化。

要不要我挑一个候选（比如 C1 `mcp/cache.py` 拆分）做具体的接口设计给你过目？还是先放着，等后面排期？
user: 看看功能上可以做哪些优化或者拓展吗
assistant: [{'type': 'thinking', 'thinking': '用户转向功能优化/拓展方向。我需要先按 active-settle 沉淀上一轮架构审查的成果（任务记忆），然后切换到功能层面。先做沉淀，再回应。\n需要判断哪些算停顿点：上一轮完成了架构审查里程碑（分析结果），用户话题已转向功能拓展，因此需要补沉淀。\n沉淀内容：产品维护任务下，记录架构审查结论与候选改进点。', 'signature': ''}]
assistant: [tool: mcp_call · {"toolName": "mcp__codewiki__add_task_memory", "arguments": {"task_id": "产品维护", "content": "架构审查完成（CodeWiki-Plus @ 99e4ec0）：2030 组件 / 92 叶节点 …
user: [tool-ok: {"error": "Task '\u4ea7\u54c1\u7ef4\u62a4' does not exist."}]
assistant: [{'type': 'thinking', 'thinking': '任务不存在，可能任务 ID 编码或任务系统未启用。先列任务确认状态。\n', 'signature': ''}]
assistant: [tool: mcp_call · {"toolName": "mcp__codewiki__list_tasks", "arguments": {}}]
user: [tool-ok: {"ok": true, "tasks": []}]
assistant: [{'type': 'thinking', 'thinking': '任务系统为空，可能未启用或前次会话绑定的任务已清理。直接回复用户即可，无法写入任务记忆系统。\n需要回应用户的功能拓展问题。先简单确认沉淀失败原因，然后给出方向建议。', 'signature': ''}]
assistant: 任务记忆系统当前无活跃任务，未落盘。功能拓展方向我先列几个高价值且符合当前架构的机会，你再挑。
assistant: [tool: AskUserQuestion · {"questions": [{"question": "想先看哪个功能方向？", "header": "功能拓展", "options": [{"label": "检索增强", "description": "搜索召回率、跨语言/跨仓库、实体链接、向量化索引", "…
user: [tool-ok: Your questions have been answered: "想先看哪个功能方向？"="检索增强". You can now continue with these answers in mind.]
assistant: [{'type': 'thinking', 'thinking': '用户选择检索增强方向，需要先了解当前检索实现（codewiki/src/retrieval.py 与 mcp/tools/wiki_search.py），再给出优化/拓展建议。\n', 'signature': ''}]
assistant: [tool: Read · D:\repos\CodeWiki-Plus\codewiki\src\retrieval.py]
assistant: [tool: Read · D:\repos\CodeWiki-Plus\codewiki\mcp\tools\wiki_search.py]
user: [tool-ok: 120	    "very",]
user: [tool-error: 1 """BM25 search engine for CodeWiki docs + notes. 2 3 When an active session with a SQLite cache is available, search uses the 4 SQLite token index for efficient token-level pre-filtering. Falls back to 5 the legacy JSON file index otherwise. 6 """ 7 8 from __future__ import annotations 9 10 import json 11 import logging 12 import re 13 import…
assistant: [{'type': 'thinking', 'thinking': '用户选择检索增强，我已读取 retrieval.py 和 wiki_search.py 开头部分。需要更深入看关键函数（bm25_score、search 实现）以及了解当前索引结构，然后给出功能拓展建议。\n', 'signature': ''}]
assistant: [tool: Grep · D:\repos\CodeWiki-Plus\codewiki\src\retrieval.py]
assistant: [tool: Grep · D:\repos\CodeWiki-Plus\codewiki\mcp\tools\wiki_search.py]
user: [tool-ok: 348:def bm25_score(]
user: [tool-error: 3:When an active session with a SQLite cache is available, search uses the 4:SQLite token index for efficient token-level pre-filtering. Falls back to 43:# seam: AnalysisCache (SQLite) in prod/sessions, the legacy JSON index as 51:class SearchIndex(_Protocol): 159:class _IndexData: 329:def build_full_index(output_dir, session=None): 330: """Bui…
assistant: [{'type': 'thinking', 'thinking': '已了解当前检索核心：BM25 + SQLite token index + JSON fallback + ontology/usage heat，无向量/embedding/dense。需要给出功能拓展建议。\n结合项目上下文和代码事实，给出检索增强方向建议。', 'signature': ''}]
assistant: 先小结当前检索现状，再列功能拓展机会。

## 当前检索实现（依据代码核对）

- **内核**：`codewiki/src/retrieval.py` 提供 BM25、tokenize、snippet、ontology 扩展、usage heat、doc authority（依据：`codewiki/src/retrieval.py:1-17`）
- **适配器**：`mcp/tools/wiki_search.py` 通过 `SearchIndex` 协议提供两条路径
  - 有 session：SQLite cache 索引（`analysis_cache.db`）
  - 无 session：JSON `search_index.json` fallback
- **当前没有**：embedding/向量检索、dense rerank、实体链接、跨仓库联合检索、查询扩展（LLM rewrite）、搜索结果重排序

## 检索增强方向（按投入产出排序）

### 1. Hybrid Search（BM25 + 轻量 dense rerank）★推荐
**功能**：BM25 召回候选 → 小模型 sentence embedding 做 top-k rerank，提升语义近义词召回。

**为什么先做这个**：
- 当前 BM25 对"同义词/近义表达"脆弱（如用户搜"配置损坏"，文档写的是"配置损坏时...打日志"）
- 不必换底座，只在 `_ensure_index`/`search` 里加一列 embedding
- 可用 `sentence-transformers/all-MiniLM-L6-v2`（纯 CPU、约 80MB），离线可跑

**改动面**：
- `retrieval.py`：新增 `encode_passage()`、`rerank(query, candidates)`，保持 `bm25_score` 不变
- `mcp/tools/wiki_search.py`：`SearchIndex` 协议增加 `rerank` 阶段；SQLite 加 `doc_embeddings` 表
- 新增可选依赖 `sentence-transformers`，fail-open：缺失时退化回纯 BM25

**可量化验证**：用现有 golden retrieval baseline 跑 recall@5 / MRR，rerank 后应提升。

---

### 2. 查询理解与重写（Query Rewriting）
**功能**：把用户口语化查询扩展成同义词/代码符号，提高召回。

**实现**：
- 轻量：基于 ontology 扩展（已有 `expand_with_ontology`）+ 常见代码术语同义词表
- 重型：调 LLM 把 "怎么修 session 任务关联" 重写为 "task_session_start set_session_task get_task_context"
- 优势：不需要改索引，只改 `tokenize`/查询入口

---

### 3. 实体/符号链接（Entity Linking）
**功能**：把 wiki 里的代码符号（`codewiki.mcp.cache.LazyComponentStore`）、ADR、决策点自动链到代码定义页。

**实现**：
- 复用 `analyze_repo` 已解析的 component graph
- 在 `build_indexable_text` 时把符号名加入可索引文本
- 搜索结果高亮显示"此文档提到 X 符号"

**价值**：解决"我知道有个函数但搜不到"的问题。

---

### 4. 跨仓库联合检索
**功能**：多仓工作区下，`query_wiki` 一次检索返回所有仓库的相关结果。

**现状约束**：当前 `output_dir` 是单仓库 `repowiki/`（`mcp/tools/workspace_layout.py:default_output_dir`）
**实现**：
- workspace 层面建统一索引（或 federation：每个 repo 各自查后合并）
- 新增 `query_wiki(mode='workspace')` 或 `query_cross_service` 的检索版本

---

### 5. 搜索结果反馈闭环（轻量）
**功能**：记录用户点击了哪条结果，自动提升其 authority/usage heat。

**实现**：
- `mcp/tools/telemetry.py` 已有用户行为采集
- 把 click/save 信号写回 `usage_ranking.json`
- 下次搜索同查询时相关文档排名上升

---

## 建议启动顺序

如果想**快速见效** → 先做 **2（查询重写）+ 5（点击反馈）**，不改索引结构，风险最低。

如果想**长期竞争力** → 先做 **1（Hybrid Search rerank）**，这是检索底座升级。

想让我把某个方向拆成设计稿（接口、依赖、测试方案、工作量估算）吗？
