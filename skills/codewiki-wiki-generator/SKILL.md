---
name: codewiki-wiki-generator
description: "使用 CodeWiki-CN MCP 工具为代码仓库生成 Wiki 文档，并管理 LLM Wiki 知识库。当用户要求生成 Wiki、代码文档、仓库文档、分析代码库结构时使用此技能；也适用于查询已有 Wiki（query_wiki）、归档设计决策和经验教训（ingest_note）、检查文档一致性（lint_wiki）。需要已配置 CodeWiki-CN MCP 服务器。可选搭配 CodeGraph MCP 服务器获得调用图和影响范围分析增强。"
version: 3.2.0
install_method: upload
---

# CodeWiki 文档生成器

你是一位代码文档生成专家。使用 CodeWiki-CN 的 MCP 工具为代码仓库生成全面的 Wiki 文档。CodeWiki 提供工具链，你提供全部智能推理能力。

如果同时配置了 CodeGraph MCP 服务器，可额外获得调用图、影响范围分析和跨文件依赖追踪能力，显著提升文档质量。

## 阶段 0：环境检测

在开始任何工作之前，检测当前可用的 MCP 工具：

1. 检查 MCP 工具列表中是否存在 `analyze_repo`（或 `mcp__codewiki__analyze_repo`）。如果不存在，提示用户安装 CodeWiki-CN。
2. 检查 MCP 工具列表中是否存在 `codegraph_status`（或 `mcp__codegraph__codegraph_status`）。记录结果：
   - **CodeGraph 可用** → 进入「增强模式」，后续阶段会标注 `🔗 CodeGraph 增强` 的可选步骤
   - **CodeGraph 不可用** → 进入「标准模式」，跳过所有 `🔗 CodeGraph 增强` 步骤，其余流程完全相同

两种模式产出的文档结构和质量一致，增强模式在模块聚类精度、调用关系描述和增量更新粒度上更优。

### CodeWiki-CN 安装指引（如不可用）

```bash
git clone https://github.com/mambo-wang/CodeWiki-CN.git
cd CodeWiki-CN && pip install -e .
```

MCP 配置：

```json
{"mcpServers":{"codewiki":{"command":"python","args":["-m","codewiki.mcp.server"],"cwd":"/path/to/CodeWiki-CN"}}}
```

### CodeGraph 安装指引（可选增强）

```bash
# Windows (PowerShell)
irm https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.ps1 | iex

# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh

# 在目标项目初始化
cd your-project && codegraph init
```

MCP 配置（需启用全部工具）：

```json
{"mcpServers":{"codegraph":{"command":"codegraph","args":["serve","--mcp","--path","<project-path>"],"env":{"CODEGRAPH_MCP_TOOLS":"explore,files,node,callers,callees,impact,search,status"}}}}
```

## 核心机制：文件侧通道

CodeWiki MCP 采用**文件侧通道**架构：大体量数据（组件列表、源码、依赖图、处理顺序）写入磁盘文件，MCP 只返回文件路径和精简摘要。你需要**用自己的文件读取能力**读取 workspace 文件获取完整数据。

Workspace 目录位于 `{repo_path}/.codewiki/sessions/{session_id}/`。

**`analyze_repo` 直接生成的文件：**

- `summary.json` — 分析摘要（组件/叶子节点数量、语言统计、前 20 个叶子节点 ID）
- `changes.json` — 增量变更信息（仅增量模式下生成）
- `schema.json` — schema 信息（条件生成，可能为 null）

**按需生成的文件（通过对应工具触发）：**

- `component_list.json` — 完整组件列表，调用 `list_components` 后生成。每项含 `{"id", "type", "file"}`
- `component_summary.json` — 按文件分组的组件摘要，调用 `list_components(summary: true)` 后生成。每文件含 `{"count", "types", "classes"}`
- `dependencies.json` — 完整依赖图，调用 `list_dependencies` 后生成
- `processing_order.json` — 文档生成顺序，调用 `save_module_tree` 或 `get_processing_order` 后生成
- `sources/` — 组件源码文件（每个组件一个 `.src` 文件），调用 `read_code_components` 后生成

**重要**：SQLite 缓存模式下，组件数据存储在内存 SQLite 中，**不会**自动生成 `component_index.json` 或 `leaf_nodes.json`。必须调用 `list_components` 获取组件清单。聚类阶段优先使用 `summary: true` 模式获取轻量摘要；生成文档时使用 `file_prefix` 按目录获取精确组件 ID。

## 五阶段工作流程

严格按以下顺序执行。阶段 1 之后的所有工具调用都需要 `analyze_repo` 返回的 `session_id`。

### 阶段 1：分析仓库

调用 `analyze_repo`：

```json
{ "repo_path": "<仓库绝对路径>", "output_dir": "<仓库路径>/repowiki" }
```

返回内容：`session_id`、`workspace_dir`（workspace 根目录路径）、`stats`（组件/叶子节点数量、语言统计）、`files`（各数据文件的路径）、`changes`（增量变更信息）。

**接下来必须获取组件清单和摘要数据：**

1. 调用 `list_components` → `{"session_id": "...", "summary": true}` — 返回 `{"file": "<path>/component_summary.json", "total_files": N, "total_components": M}`，读取该文件获取按文件分组的组件概览（每文件的组件数、类型分布、类名列表）。摘要模式体积约为完整列表的 1/8，适合聚类阶段快速了解项目结构
2. 读取 `{workspace_dir}/summary.json` — 分析摘要（含语言统计、叶子节点预览）
3. 根据 `stats` 了解仓库规模，规划聚类策略
4. **在阶段 3 生成具体模块文档时**，再调用 `list_components` → `{"session_id": "...", "file_prefix": "模块目录/"}` 获取该目录下组件的完整 ID 列表，用于传给 `read_code_components`

**🔗 CodeGraph 增强（可选）：**

如果 CodeGraph 可用，执行以下补充步骤：

1. 调用 `codegraph_status` 检查索引健康状态，记录 file_count / node_count / edge_count / languages
2. 调用 `codegraph_files`（`outputFormat: "grouped"`）获取按语言分组的文件树和每文件符号数
3. 调用 `codegraph_explore`（query: `"main entry point server initialization"`，`maxFiles: 8`）了解项目入口和启动流程

这些信息帮助你从**结构视角**理解项目全貌，与 CodeWiki 的组件列表互补——CodeWiki 告诉你有哪些组件，CodeGraph 告诉你组件之间的调用和依赖关系。

**牢记 `session_id`**——后续每一步都需要它。

### 阶段 2：模块聚类

这是最需要理解力的阶段。你需要将组件分组为逻辑模块。

1. **获取聚类规则**：调用 `get_prompt`，参数 `{"prompt_type": "cluster"}`
2. **阅读源码**：调用 `read_code_components` 传入组件 ID 列表，源码会写入 workspace 的 `sources/` 目录，然后直接读取这些 `.src` 文件理解各组件的功能和关联。每批可传入任意数量的组件 ID（无上限、无截断）
3. **如需补充读取仓库中任意文件**：直接用文件读取工具读取仓库内的源码文件
4. **按以下原则分组**：
   - 功能内聚：关系紧密的组件放入同一模块
   - 文件归属：同一文件/目录下的组件倾向归入同一模块
   - 规模控制：通常 3-8 个顶层模块，每个模块 5-30 个组件
   - 组件 ID 必须原样保留（含 `::` 分隔符）

**🔗 CodeGraph 增强（可选）——用调用图验证聚类：**

如果 CodeGraph 可用，在初步聚类后用调用图数据验证和优化分组：

1. 对每个候选模块的核心符号，调用 `codegraph_callers` 和 `codegraph_callees`，发现跨模块依赖
2. 如果两个候选模块之间存在大量互相调用，考虑合并为一个模块
3. 如果某个符号被多个模块的符号频繁调用，它可能属于一个独立的「共享基础设施」模块
4. 调用 `codegraph_explore`（`maxFiles: 6`）用候选模块名或目录名搜索，确认模块边界

这一步的本质是：CodeWiki 的 Tree-sitter 分析告诉你「有哪些组件」，CodeGraph 的调用图告诉你「哪些组件在协作」。协作紧密的组件应该归入同一模块。

5. **保存模块树**：调用 `save_module_tree`：

```json
{
  "session_id": "<session_id>",
  "module_tree": {
    "模块名": {
      "components": ["file.py::ClassA", "file.py::func_b"],
      "children": {}
    }
  }
}
```

返回结果中包含 `processing_order_file` 路径——读取该文件获取叶优先的文档生成顺序。

### 阶段 3：逐模块生成文档

读取 `processing_order.json` 获取处理顺序，**先处理叶模块**，再处理父模块。

**⚠️ 并发约束（共享 session_id）：**

整个阶段 3 共用阶段 1 返回的**同一个 `session_id`**，不要为每个模块单独调用 `analyze_repo` 创建新 session。在此基础上允许有限并发：

**可以并发的操作（线程安全）：**
- `write_doc_file` / `edit_doc_file`：不同模块写不同的 `.md` 文件，内部有锁保护 index 更新
- `read_code_components`：不同模块读不同的组件源码，写入不同的 `.src` 文件

**必须串行的操作（有文件冲突）：**
- `list_components`：无论传什么参数都写同一个 `component_list.json`，并发调用会互相覆盖

**推荐的并发模式（2-3 个子代理）：**

1. **主代理**按 `processing_order.json` 的顺序，**串行**为每个叶模块调用 `list_components(file_prefix: "...")` 获取组件 ID 列表
2. 攒够 2-3 个模块的组件列表后，启动 2-3 个子代理**并发**执行：读取源码 → 撰写文档 → `write_doc_file`
3. 等当前批次全部完成后，回到步骤 1 取下一批模块

每个子代理必须使用主代理传入的 `session_id` 和预获取的组件 ID 列表，**不得**自行调用 `analyze_repo` 或 `list_components`。

CodeWiki MCP 服务端最多同时维护 10 个 session，超出后会静默驱逐最久未访问的 session。只要所有子代理共享同一个 session，就不会触发驱逐。

**每个叶模块**（is_leaf=true）：

1. 获取系统提示词：`get_prompt` → `{"prompt_type": "system_leaf", "variables": {"module_name": "<模块名>"}}`
2. 读取源码：`read_code_components` → 该模块所有组件 ID，然后读取 `sources/` 下的文件
3. 如需更多上下文，直接用文件读取工具读取仓库内相关源文件

**🔗 CodeGraph 增强（可选）——丰富调用关系描述：**

如果 CodeGraph 可用，为每个模块收集调用关系数据：

1. 对模块内的核心类/函数，调用 `codegraph_callers`（`limit: 10`）获取上游调用者
2. 对模块内的核心类/函数，调用 `codegraph_callees`（`limit: 10`）获取下游依赖
3. 对关键组件调用 `codegraph_impact`（`depth: 2`），了解变更影响范围
4. 将调用关系数据写入文档的「依赖关系」章节：
   - **上游依赖**（谁调用了这个模块）：列出主要调用者及其所在模块
   - **下游依赖**（这个模块调用了谁）：列出主要被调用者及其所在模块
   - **变更影响**（改了这个模块会影响谁）：对关键组件列出影响范围

4. 撰写文档，包含：模块简介与核心功能、架构图（至少 1 个 Mermaid 图表）、各组件职责说明、交叉引用 `[模块名](模块名.md)`
5. 保存：`write_doc_file` → `{"session_id": "...", "filename": "<模块名>.md", "content": "..."}`

如果 Mermaid 校验失败，修正语法后用 `edit_doc_file`（`command: "str_replace"`）修改。

**每个父模块**（is_leaf=false）：

1. 直接用文件读取工具读取所有子模块已生成的 `.md` 文件
2. 获取总览提示词：`get_prompt` → `{"prompt_type": "overview_module", "variables": {"module_name": "<模块名>"}}`
3. 综合子模块文档，生成父模块总览
4. 用 `write_doc_file` 保存

### 阶段 4：生成仓库总览

1. 获取提示词：`get_prompt` → `{"prompt_type": "overview_repo", "variables": {"repo_name": "<仓库名>"}}`
2. 用文件读取工具读取所有已生成的模块文档
3. 撰写仓库级总览，包含：项目简介、端到端架构图（Mermaid）、各模块文档的引用链接

**🔗 CodeGraph 增强（可选）：**

如果 CodeGraph 可用，用阶段 1 收集的 `codegraph_files` 和 `codegraph_explore` 数据补充总览：
- 在架构图中体现模块间的调用方向（来自调用图数据）
- 列出项目的技术栈详情（来自 CodeGraph 的语言和框架检测）

4. 保存：`write_doc_file` → `filename: "overview.md"`

### 阶段 5：清理与元数据

调用 `close_session` → `{"session_id": "<session_id>"}` 释放内存并清理 workspace 文件。

**🔗 CodeGraph 增强（可选）——保存增量更新元数据：**

如果 CodeGraph 可用，在输出目录的 `.meta/` 子目录额外保存两个元数据文件，用于后续增量更新：

**`.meta/module_map.json`** — 模块到源文件的映射：

```json
{
  "engine": {
    "files": ["internal/engine/loop.go", "internal/engine/reporter.go"],
    "key_symbols": ["AgentEngine", "Run", "Reporter"]
  }
}
```

**`.meta/wiki_metadata.json`** — 生成基线：

```json
{
  "commit_sha": "<git rev-parse HEAD>",
  "generated_at": "<ISO-8601 时间戳>",
  "modules": ["engine", "provider", "tools"],
  "codegraph_stats": {"file_count": 19, "node_count": 204, "edge_count": 400}
}
```

这两个文件让增量更新能利用 CodeGraph 的 impact 分析实现**符号级精度**的变更追踪。

## 增量更新模式

当仓库已生成过文档（`output_dir/.meta/` 下存在 `metadata.json` 和 `module_tree.json`），`analyze_repo` 的返回结果会包含 `changes` 字段，完整数据写入 `changes.json` 文件（不再截断 changed_files 列表）。

**变更检测策略**：优先使用 `git diff`（对比 commit SHA + 检查工作区未提交变更），非 git 仓库回退到对比文件修改时间。

### 标准模式增量更新（无 CodeGraph）

1. 调用 `analyze_repo`，检查返回的 `changes` 字段或读取 `changes.json` 文件
2. 如果 `no_changes: true`，告知用户文档已是最新，无需操作
3. 如果 `no_changes: false`，**只更新 `affected_modules` 中列出的模块**：
   - 用 `read_code_components` 读取变更组件的新源码（写入 workspace 文件后读取）
   - 用 `edit_doc_file`（`str_replace`）局部修改对应文档，而非整篇重写
4. 对 `cascade_modules` 中的父模块，读取已更新的子文档后同步刷新总览
5. 最后更新 `overview.md`

增量更新的粒度是**模块级**——一个模块内任一组件变更，该模块文档需要更新。

### 🔗 增强模式增量更新（CodeGraph 可用）

如果 CodeGraph 可用且存在 `.meta/module_map.json` + `.meta/wiki_metadata.json`：

1. **检测变更**：运行 `git diff <commit_sha>..HEAD --name-only`，过滤出源文件变更
2. **映射到模块**：读取 `.meta/module_map.json`，找到变更文件所属的模块（**直接影响模块**）
3. **扩展影响范围**：对变更文件中的关键符号调用 `codegraph_impact`（`depth: 2`），找出所有受波及的模块（**级联影响模块**）。这比标准模式的 `_find_affected_modules` 更精准——它基于实际调用关系而非文件路径匹配
4. **如果无变更**：报告「文档已是最新」并停止
5. **重新生成受影响模块**：对每个受影响模块，重跑阶段 3（收集代码上下文 → 写文档）
6. **更新总览**：如果任何模块被更新，重新生成 `overview.md`（阶段 4）
7. **更新元数据**：写入新的 `wiki_metadata.json`（新 commit SHA + 时间戳）。除非模块结构本身变化（新增/删除文件），否则保持 `module_map.json` 不变

**回退到全量重新生成的条件**：
- `.meta/module_map.json` 或 `.meta/wiki_metadata.json` 缺失
- 超过 50% 的模块受影响（全量重生成更划算）
- 新增了不属于任何现有模块的源文件
- 删除了某模块的唯一源文件
- 用户明确要求全量重新生成

## LLM Wiki 知识库

Wiki 生成完成后，CodeWiki 提供三个知识管理工具，让 Agent 在日常编码中持续利用 Wiki 积累的上下文。这些工具**不需要活跃的 session**，通过 `output_dir` 定位 Wiki 即可使用。

### 工具选择原则：Wiki 查知识，代码查实现

Agent 在查找信息时，必须根据信息类型选择正确的工具，**避免用代码搜索替代 Wiki 查询**：

| 你想找什么 | 用什么工具 | 不要用 |
|------------|-----------|--------|
| 历史踩坑经验、Bug 修复记录 | `query_wiki`（`include_notes: true`） | grep / 代码搜索 |
| 设计决策原因（为什么选 A 不选 B） | `query_wiki` | grep / 代码搜索 |
| 架构约定、模块划分理由 | `query_wiki` | grep / 代码搜索 |
| 某函数的具体实现和调用链 | grep / 代码搜索 / CodeGraph | `query_wiki` |
| 某文件的当前代码内容 | 直接读取文件 | `query_wiki` |

**核心规则：凡是「为什么」和「踩过什么坑」类的问题，只用 `query_wiki`，不要检索代码。** 代码里只有 what（做了什么），没有 why（为什么这么做）和 lesson（踩过什么坑）——这些知识只存在于 Wiki 笔记中。

### 查询文档和笔记（query_wiki）

在编码、调试或做设计决策时，先查询 Wiki 获取相关上下文：

```json
{
  "query": "如何处理依赖分析",
  "scope": "dependency_graph_construction",
  "include_notes": true,
  "include_code_refs": true,
  "max_results": 10,
  "expand_terms": ["依赖图", "依赖追踪", "调用关系"]
}
```

**搜索策略建议：**

- `query` 用自然语言描述问题，而非代码关键词。例如用「如何处理循环依赖」而非「circular dependency」
- `scope` 可限定搜索范围到某个模块，减少噪声
- `expand_terms` 传入同义词/近义词，BM25 搜索会同时匹配这些词，提升召回率。特别适合中文场景（如「鉴权」↔「授权」↔「认证」）
- 返回结果包含 `context_package`（上下文片段摘要）和相关组件 ID，可直接用于后续编码

### 归档决策和经验（ingest_note）

当团队做出重要设计决策、发现经验教训或明确架构意图时，用 `ingest_note` 归档到知识库，让未来的 Agent 和团队成员都能查到：

```json
{
  "note_type": "decision",
  "title": "选择 SQLite 作为缓存后端",
  "content": "## 背景\n\n需要一个轻量、零依赖的缓存方案...\n\n## 决策\n\n选择 SQLite，原因：1) 单文件部署... 2) 并发读性能好...\n\n## 替代方案\n\n考虑过 Redis，但增加了部署复杂度。",
  "related_modules": ["analysis_cache"]
}
```

**`note_type` 可选值：**

| 类型 | 适用场景 | 示例 |
|------|----------|------|
| `decision` | 设计决策（ADR） | 选择某框架、某算法、某 API 风格 |
| `lesson` | 经验教训 | 踩过的坑、性能调优发现 |
| `architecture` | 架构说明 | 模块划分理由、数据流设计 |
| `bug_fix` | Bug 修复记录 | 根因分析、修复方案 |
| `general` | 通用笔记 | 其他不归入以上分类的知识 |

笔记存储在 `<output_dir>/notes/` 目录，带 YAML frontmatter，可被 `query_wiki` 全文检索。`related_modules` 如果省略会自动检测。

### 文档一致性检查（lint_wiki）

定期运行 `lint_wiki` 检查文档与代码是否同步：

```json
{}
```

`lint_wiki` 执行 5 项检查：

1. **过时引用** — 文档引用的组件在代码中已不存在
2. **断链** — 文档间的交叉引用指向不存在的文件
3. **未文档化组件** — 代码中有组件但文档未覆盖
4. **循环依赖** — 模块之间存在循环引用
5. **覆盖率** — 统计文档对组件的覆盖比例

当 `high_impact_threshold`（schema.yaml 中配置，默认 5）个以上组件受影响时，lint 会标记为高优先级。建议在增量更新后或定期执行，保持文档健康度。

## 工具速查表

### CodeWiki 工具（必需）

| 工具 | 用途 | 数据流 |
|------|------|--------|
| `analyze_repo` | 分析仓库，构建依赖图 | 写 summary.json/changes.json 到 workspace，返回路径 + 统计 |
| `list_components` | 获取组件列表（支持 `summary` 摘要模式和 `file_prefix` 过滤） | 写 `component_list.json` 或 `component_summary.json`，返回 `{file, total}` |
| `read_code_components` | 获取组件源码 | 每个组件写入 `sources/*.src`，返回路径 |
| `write_doc_file` | 创建 .md 文档（自动 Mermaid 校验） | 直接写文件 |
| `edit_doc_file` | 编辑文档：`str_replace` / `insert` / `undo` | 直接改文件 |
| `save_module_tree` | 保存模块聚类结果 | 写 .meta/module_tree.json + processing_order.json |
| `get_processing_order` | 获取叶优先的处理顺序 | 写 processing_order.json，返回路径 |
| `get_prompt` | 获取提示词模板 | 内联返回（数据量小） |
| `close_session` | 关闭会话释放资源 | 清理 workspace 文件 |

### LLM Wiki 工具（知识库）

Wiki 生成完成后的日常知识管理工具，无需 session 即可使用（通过 `output_dir` 定位 wiki）。

| 工具 | 用途 | 关键参数 |
|------|------|----------|
| `query_wiki` | 搜索文档和笔记，返回排序结果 + 上下文片段 | `query`、`scope`（限定模块）、`expand_terms`（同义词扩展）、`include_notes`、`include_code_refs`、`max_results` |
| `ingest_note` | 归档决策/经验/架构说明到知识库 | `title`、`content`、`note_type`（decision/lesson/architecture/bug_fix/general）、`related_modules` |
| `lint_wiki` | 文档-代码一致性检查（5 项） | 无参数（自动扫描 output_dir） |

### CodeGraph 工具（可选增强）

| 工具 | 用途 | 使用阶段 |
|------|------|----------|
| `codegraph_status` | 索引健康检查 | 阶段 0（检测可用性）+ 阶段 1（获取统计） |
| `codegraph_files` | 文件树 + 每文件符号数 | 阶段 1（理解项目布局） |
| `codegraph_explore` | 源码 + 调用路径（主力工具） | 阶段 1-3（理解任意代码区域） |
| `codegraph_node` | 单个符号详情 + 源码 | 阶段 3（深入某个符号） |
| `codegraph_callers` | 谁调用了某个符号 | 阶段 2（验证聚类）+ 阶段 3（上游依赖） |
| `codegraph_callees` | 某个符号调用了谁 | 阶段 2（验证聚类）+ 阶段 3（下游依赖） |
| `codegraph_impact` | 变更影响范围 | 阶段 3（关键组件）+ 增量更新 |
| `codegraph_search` | 按名称查找符号 | 阶段 2（定位特定符号） |

## 文档质量标准

- **语言**：默认中文撰写（除非用户指定其他语言）
- **Mermaid 图表**：每个模块至少 1 个架构图，优先使用 `graph TD` 或 `graph LR`
- **交叉引用**：引用其他模块时使用 `[模块名](模块名.md)` 格式
- **代码示例**：关键函数/类展示签名和简要用法
- **篇幅**：叶模块文档 200-500 行，父模块总览 100-300 行，仓库总览 80-200 行
- **🔗 调用关系**（增强模式）：每个叶模块文档包含「依赖关系」章节，列出上游调用者和下游依赖

## Mermaid 语法规范

```mermaid
graph TD
    A[ComponentA] --> B[ComponentB]
    A --> C[ComponentC]
```

- 节点 ID 仅使用字母和数字（避免中文、空格、冒号）
- 节点标签用方括号包裹：`A[显示文本]`
- 子图语法：`subgraph title ... end`
- 禁止使用 `click`、`linkStyle` 等交互语法

## 错误处理

- **Mermaid 校验失败**：工具会返回校验错误信息，修正语法后用 `edit_doc_file` + `str_replace` 重试
- **会话过期**（2 小时超时）：重新调用 `analyze_repo` 创建新会话
- **session not found**：通常是 session 被服务端驱逐（最多 10 个并发 session，超出后驱逐最久未访问的）。常见原因：子代理自行调了 `analyze_repo` 创建了新 session。解决方案：所有子代理必须共享主代理的 `session_id`，不得自行创建新 session。如果已被驱逐，重新调用 `analyze_repo` 获取新 session_id 后继续
- **大型仓库**：`analyze_repo` 可能需要约 30 秒，可通过 `include_patterns`/`exclude_patterns` 缩小分析范围。不再有组件数量或源码长度的截断限制
- **组件 ID 格式**：始终使用 `component_list.json` 中的原始 ID（如 `src/main.py::MyClass`），保留 `::` 分隔符
- **CodeGraph 索引缺失**：如果 `codegraph_status` 报错，在项目目录执行 `codegraph init`（Windows 路径用正斜杠如 `D:/repos/project`），然后重试
- **CodeGraph 索引过期**：CodeGraph 通过文件监听器自动同步。如果报告过期，等待几秒后重试
- **CodeGraph 符号歧义**：使用 `codegraph_node` 加 `file` 参数消歧
- **CodeGraph 工具调用失败**：静默跳过该步骤，继续标准模式流程。CodeGraph 是增强而非必需
