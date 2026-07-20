---
name: codewiki-wiki-generator
description: "使用 CodeWiki-CN MCP 工具为代码仓库生成结构化 Wiki 文档并管理 LLM Wiki 知识库。当用户要求生成 Wiki、代码文档、仓库文档、分析代码库结构时使用；也适用于查询已有 Wiki（query_wiki）、归档设计决策和经验教训（ingest_note）、导入第三方文档（ingest_source）、批量导入（batch_ingest）、标记质量问题（flag_issue）、检查文档一致性（lint_wiki，含 health score）。支持 6 种页面类型（module/entity/concept/source/comparison/query）。需要已配置 CodeWiki-CN MCP 服务器。可选搭配 CodeGraph MCP 获得调用图和影响范围分析增强。"
version: 5.0.0
---

# CodeWiki 文档生成器

使用 CodeWiki-CN MCP 工具链为代码仓库生成全面的 Wiki 文档。CodeWiki 提供工具链，你提供全部智能推理能力。

## 使用边界

**做什么：** 代码仓库文档生成、Wiki 知识库管理（查询/归档/一致性检查/外部文档导入/批量操作/质量追踪）。支持 6 种页面类型：module、entity、concept、source、comparison、query。

**不做什么：**
- 不处理非代码类文档生成（报告、PPT、邮件等）
- 不用代码搜索替代 Wiki 查询——「为什么」和「踩过什么坑」类问题只用 `query_wiki`
- 子代理不得自行调用 `analyze_repo` 创建新 session，必须共享主代理的 session_id
- Mermaid 节点 ID 禁止使用中文、空格、冒号

## 阶段 0：环境检测

1. 检查 MCP 工具列表中是否存在 `analyze_repo`。不存在 → 提示用户安装（详见 [安装指南](references/installation.md)）
2. 检查是否存在 `codegraph_status`：
   - 存在 → **增强模式**（标注 `🔗 CodeGraph 增强` 的步骤）
   - 不存在 → **标准模式**（跳过增强步骤）

两种模式产出的文档结构和质量一致，增强模式在模块聚类精度和调用关系描述上更优。

## schema.yaml 配置

`schema.yaml` 是项目的文档"宪法"，控制命名规范、必需章节、文档维度、Mermaid 要求、行数限制、交叉链接开关、lint 阈值，以及 **page_types 路由表**（定义每种页面类型的目录和 frontmatter 字段）和 **extraction_granularity**（提取粒度）。

- **全局默认值**：CodeWiki-CN 安装目录下的 `config.yaml` 定义与语言无关的默认配置，首次 `analyze_repo` 时自动读取并生成 `output_dir/schema.yaml`
- **自定义**：修改 `config.yaml` 改变全局默认值；修改 `output_dir/schema.yaml` 只影响该项目（增量更新时自动合并保留自定义字段，`project` 字段始终自动更新）

## 核心机制：文件侧通道

CodeWiki MCP 采用**文件侧通道**架构：大体量数据写入磁盘文件，MCP 只返回路径和精简摘要。你需要用自己的文件读取能力读取 workspace 文件获取完整数据。

Workspace 目录：`{repo_path}/.codewiki/sessions/{session_id}/`

完整文件清单和读取时机见 [文件侧通道详解](references/sidechannel.md)。

## 五阶段工作流

严格按顺序执行。阶段 1 之后的所有工具调用都需要 `analyze_repo` 返回的 `session_id`。

### 阶段 1：分析仓库

```
analyze_repo → {"repo_path": "<仓库绝对路径>", "output_dir": "<仓库路径>/repowiki"}
```

返回 `session_id`、`workspace_dir`、`stats`、`files`、`changes`。**牢记 session_id。**

接下来：

1. `list_components` → `{"session_id": "...", "summary": true}` → 读取返回的 `component_summary.json`
2. 读取 `{workspace_dir}/summary.json`
3. 根据 stats 规划聚类策略
4. **阶段 3 生成文档时**，再调用 `list_components(file_prefix: "模块目录/")` 获取完整组件 ID

🔗 增强模式额外步骤见 [CodeGraph 增强](references/codegraph.md#阶段-1-增强)。

### 阶段 2：模块聚类

这是最需要理解力的阶段。

1. `get_prompt` → `{"prompt_type": "cluster"}` 获取聚类规则
2. `read_code_components` 读取组件源码（传入 ID 列表 → 写入 `sources/*.src` → 读取 `.src` 文件）
3. 如需补充，直接读取仓库内源文件
4. 分组原则：
   - **功能内聚**：关系紧密的组件放入同一模块
   - **文件归属**：同文件/目录的组件倾向同一模块
   - **规模控制**：3-8 个顶层模块，每模块 5-30 个组件
   - **ID 保留**：组件 ID 原样保留（含 `::` 分隔符）

🔗 增强模式：用 `codegraph_callers`/`codegraph_callees` 验证聚类，详见 [CodeGraph 增强](references/codegraph.md#阶段-2-验证聚类)。

5. 保存模块树：

```json
save_module_tree → {
  "session_id": "<session_id>",
  "module_tree": {
    "模块名": {
      "components": ["file.py::ClassA", "file.py::func_b"],
      "children": {}
    }
  }
}
```

读取返回的 `processing_order_file` 获取叶优先的处理顺序。

### 阶段 3：逐模块生成文档

读取 `processing_order.json`，**先处理叶模块，再处理父模块**。

**并发约束（共享 session_id）：**

| 可并发 | 必须串行 |
|--------|----------|
| `write_doc_file` / `edit_doc_file` | `list_components`（写同一文件） |
| `read_code_components` | |

**推荐模式**：主代理串行调用 `list_components(file_prefix)` 获取组件 ID → 2-3 个子代理并发执行（读源码 → 撰写 → 写文档）→ 批次完成后取下一批。

子代理必须使用主代理传入的 `session_id` 和预获取的组件 ID 列表，**不得**自行调用 `analyze_repo` 或 `list_components`。CodeWiki MCP 最多维护 10 个 session，超出后静默驱逐最久未访问的。

**叶模块**（is_leaf=true）：

1. `get_prompt` → `{"prompt_type": "system_leaf", "variables": {"module_name": "<模块名>"}}`
2. `read_code_components` → 读取源码
3. 🔗 增强模式：收集调用关系数据（详见 [CodeGraph 增强](references/codegraph.md#阶段-3-调用关系)）
4. 撰写文档：模块简介、架构图（≥1 个 Mermaid）、组件职责、交叉引用 `[模块名](模块名.md)`
5. `write_doc_file` → `{"session_id": "...", "filename": "<模块名>.md", "content": "...", "page_type": "module"}`

> `page_type` 参数控制文件路由：`module` → `wiki/modules/`，`entity` → `wiki/entities/`，`concept` → `wiki/concepts/` 等。默认为 `module`。生成实体/概念等页面时指定对应类型即可。

**父模块**（is_leaf=false）：

1. 读取所有子模块已生成的 `.md` 文件
2. `get_prompt` → `{"prompt_type": "overview_module", "variables": {"module_name": "<模块名>"}}`
3. 综合子模块文档生成总览 → `write_doc_file` 保存

### 阶段 4：生成仓库总览

1. `get_prompt` → `{"prompt_type": "overview_repo", "variables": {"repo_name": "<仓库名>"}}`
2. 读取所有模块文档
3. 撰写总览：项目简介 + 端到端架构图（Mermaid）+ 各模块引用链接
4. `write_doc_file` → `filename: "overview.md"`

### 阶段 5：清理

```
close_session → {"session_id": "<session_id>"}
```

🔗 增强模式额外保存增量更新元数据，详见 [CodeGraph 增强](references/codegraph.md#增量元数据)。

## 增量更新

当 `output_dir/.meta/` 下存在元数据时，`analyze_repo` 返回 `changes` 字段（完整数据在 `changes.json`）。

**标准模式**：

1. 检查 `changes` → `no_changes: true` 则告知用户文档已是最新
2. `no_changes: false` → **只更新 `affected_modules`** 中的模块
3. 用 `edit_doc_file(str_replace)` 局部修改，不整篇重写
4. 级联刷新 `cascade_modules` 的父模块总览 → 更新 `overview.md`

**增强模式**：用 `codegraph_impact(depth: 2)` 实现符号级精度的变更追踪，详见 [CodeGraph 增量更新](references/codegraph.md#增量更新)。

**回退全量重生成的条件**：元数据文件缺失、>50% 模块受影响、新增/删除了不属于任何现有模块的源文件、用户明确要求。

## LLM Wiki 知识库

Wiki 生成后，8 个知识管理工具**无需活跃 session**，通过 `output_dir` 定位 Wiki 即可使用。完整用法和示例见 [知识库详解](references/knowledge-base.md)。

### 结构化 Wiki 布局

所有内容按页面类型组织在 `wiki/` 子目录下，由 `page_router.py` 统一路由：

| 页面类型 | 目录 | 说明 |
|----------|------|------|
| `module` | `wiki/modules/` | 模块文档 |
| `entity` | `wiki/entities/` | 实体：类、接口、数据库表 |
| `concept` | `wiki/concepts/` | 概念：设计模式、业务概念 |
| `source` | `wiki/sources/` | 外部文档摘要 |
| `comparison` | `wiki/comparisons/` | 对比分析 |
| `query` | `wiki/queries/` | 研究查询 |

另有 `raw/sources/`（第三方文档原文件）、`.meta/issues.json`（质量问题）、`.meta/source_registry.json`（外部文档注册表）。

### 工具选择原则

| 信息类型 | 工具 | 禁止用 |
|----------|------|--------|
| 历史踩坑、设计决策、架构约定 | `query_wiki` | grep / 代码搜索 |
| 函数实现、调用链、文件内容 | grep / 代码搜索 / 直接读文件 | `query_wiki` |

**核心规则**：代码里只有 what，没有 why 和 lesson——后者只存在于 Wiki 笔记中。

### 快速参考

**query_wiki** — 搜索文档和笔记（支持类型过滤）：
```json
{"query": "自然语言问题", "include_notes": true, "type_filter": "entity", "expand_terms": ["同义词1", "同义词2"]}
```

**ingest_note** — 归档经验到知识库（新增 pitfall/known_issue/workaround 类型）：
```json
{"note_type": "decision|lesson|architecture|bug_fix|pitfall|known_issue|workaround|general", "title": "标题", "content": "Markdown 内容", "related_modules": ["模块名"], "severity": "high", "aliases": ["别名1"]}
```

**ingest_source** — 导入第三方文档到 `raw/sources/`：
```json
{"name": "rfc-7519", "source_type": "rfc", "source_path": "/path/to/file", "description": "JWT 规范", "related_pages": ["auth-module"]}
```

**retract_source** — 撤回外部文档（`flag_stale` 标记过期 / `remove_refs` 删除并清理引用）：
```json
{"source_name": "rfc-7519", "mode": "flag_stale"}
```

**batch_ingest** — 批量导入多个笔记/文档（也支持 `items_file` 路径）：
```json
{"items": [{"item_type": "note", "note_type": "decision", "title": "...", "content": "..."}, {"item_type": "source", "source_type": "api_doc", "source_path": "...", "name": "..."}]}
```

**flag_issue** — 标记 Wiki 质量问题，写入 `issues.json`，驱动 health score：
```json
{"issue_type": "broken_link|missing_doc|inconsistent|outdated|orphan", "page_path": "wiki/modules/auth.md", "severity": "error|warning|info", "description": "链接指向不存在的页面"}
```

**lint_wiki** — 文档一致性检查（9 项：过时引用、断链、未文档化组件、循环依赖、覆盖率、孤立页面、无出链、缺少别名、过期外部源），返回 `health_score`（0-100）：
```json
{"checks": ["stale_refs", "broken_links", "orphan_pages", "missing_aliases", "stale_sources"]}
```

**get_prompt 新模板** — 7 个页面类型模板（entity_page/concept_page/source_summary/comparison_page/query_page/taxonomy_plan/extraction_scan），加上原有 3 个共 10 个 Wiki 模板：
```json
{"prompt_type": "entity_page", "variables": {"entity_name": "PaymentService"}}
```

## Mermaid 规范

- 节点 ID 仅用字母和数字
- 节点标签用方括号：`A[显示文本]`
- 子图：`subgraph title ... end`
- 禁止 `click`、`linkStyle` 等交互语法
- 校验失败 → 用 `edit_doc_file(str_replace)` 修正

## 文档质量标准

- **语言**：默认中文
- **图表**：每个叶模块 ≥1 个 Mermaid 架构图，优先 `graph TD` 或 `graph LR`
- **交叉引用**：`[模块名](modules/模块名.md)`（wiki/ 内部使用相对路径）
- **别名**：文档 frontmatter 中声明 `aliases` 列表，搜索时获得 3× BM25 权重提升
- **篇幅**：叶模块 200-500 行，父模块 100-300 行，仓库总览 80-200 行
- **代码示例**：关键函数/类展示签名和简要用法

## 参考文档

按需加载以下参考文档，不要在开始时全部读取：

- [安装指南](references/installation.md) — CodeWiki-CN 和 CodeGraph 的安装与 MCP 配置
- [文件侧通道详解](references/sidechannel.md) — workspace 文件清单与读取时机
- [CodeGraph 增强](references/codegraph.md) — 增强模式的安装、配置和详细步骤
- [知识库详解](references/knowledge-base.md) — LLM Wiki 工具的完整参数和示例
- [工具速查表](references/tools.md) — 全部 MCP 工具的参数速查
- [错误处理](references/errors.md) — 常见错误场景与解决方案
