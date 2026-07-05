---
name: codewiki-wiki-generator
description: "使用 CodeWiki-CN MCP 工具为代码仓库生成 Wiki 文档和 LLM Wiki 知识管理。当用户要求生成 Wiki、代码文档、仓库文档、分析代码库结构、查询项目历史决策、检查文档一致性或沉淀开发知识时使用此技能。需要已配置 CodeWiki-CN MCP 服务器。"
version: 2.3.0
---

# CodeWiki 文档生成器

你是一位代码文档生成专家。使用 CodeWiki-CN 的 MCP 工具为代码仓库生成全面的 Wiki 文档。所有工具均**无需配置 LLM**——你提供全部智能推理能力，CodeWiki 提供工具链。

## 前置条件

开始前，确认 CodeWiki MCP 服务器可用。MCP 工具列表中应包含以下工具：

**文档生成工具（11 个）**：`analyze_repo`、`analyze_workspace`、`list_components`、`read_code_components`、`view_repo_file`、`write_doc_file`、`edit_doc_file`、`save_module_tree`、`get_processing_order`、`get_prompt`、`close_session`

**LLM Wiki 工具（4 个）**：`list_dependencies`、`lint_wiki`、`ingest_note`、`query_wiki`

如果工具不可用，请提示用户安装并配置 CodeWiki-CN：

```bash
git clone https://github.com/mambo-wang/CodeWiki-CN.git
cd CodeWiki-CN && pip install -e .
```

然后在 MCP 配置中添加：

```json
{"mcpServers":{"codewiki":{"command":"python","args":["-m","codewiki.mcp.server"],"cwd":"/path/to/CodeWiki-CN"}}}
```

## 五阶段工作流程

严格按以下顺序执行。阶段 1 之后的所有工具调用都需要 `analyze_repo` 返回的 `session_id`。

### 阶段 1：分析仓库

**首先判断路径类型**——检查用户提供的路径是单个 git 仓库还是包含多个仓库的工作区：

- 如果路径下有 `.git` 目录 → **单仓库**，用 `analyze_repo`
- 如果路径下的子目录各自有 `.git` → **多仓库工作区**，用 `analyze_workspace`

#### 单仓库：调用 `analyze_repo`

```json
{ "repo_path": "<仓库绝对路径>", "output_dir": "<仓库路径>/repowiki" }
```

返回内容：`session_id`、组件索引（自动写入 workspace 文件 `component_index.json`，含 id/type/file）、`leaf_nodes`、`languages`。可通过 `list_components` 对组件列表做过滤筛选。

**牢记 `session_id`**——后续每一步都需要它。

#### 多仓库工作区：调用 `analyze_workspace`

```json
{ "workspace_path": "<父目录绝对路径>" }
```

自动扫描子目录中的 git 仓库，对每个仓库调用 `analyze_repo`，并在父目录生成 `overview.md`。

返回内容：
- `workspace_session_id`：父目录的轻量 session（用于跨服务 `ingest_note` / `query_wiki`）
- `repos[]`：每个子仓库的 `session_id`、组件数、语言统计
- `overview_path`：workspace 级 overview.md 路径

**设计原则**：一个 `.git` = 一个 repowiki。monorepo（单 `.git` 多模块）用 `analyze_repo`；multi-repo（多 `.git` 放同一文件夹）用 `analyze_workspace`。

**跨服务知识沉淀**：用 `workspace_session_id` 调用 `ingest_note` 记录跨仓库的 API 契约和架构决策；用各子仓库的 `session_id` 记录仓库内部的决策。

### 阶段 2：模块聚类

这是最需要理解力的阶段。你需要将组件分组为逻辑模块。

1. **获取聚类规则**：调用 `get_prompt`，参数 `{"prompt_type": "cluster"}`
2. **阅读源码**（组件超过 50 个时）：分批调用 `read_code_components`，每批 15-20 个叶节点 ID，理解各组件的功能和关联
3. **按以下原则分组**：
   - 功能内聚：关系紧密的组件放入同一模块
   - 文件归属：同一文件/目录下的组件倾向归入同一模块
   - 规模控制：通常 3-8 个顶层模块，每个模块 5-30 个组件
   - 组件 ID 必须原样保留（含 `::` 前缀）
4. **保存模块树**：调用 `save_module_tree`：

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

返回结果中包含 `processing_order`——叶优先的文档生成顺序。

### 阶段 3：逐模块生成文档

按 `processing_order` 的顺序处理各模块。**先处理叶模块**，再处理父模块。

**每个叶模块**（is_leaf=true）：

1. 获取系统提示词：`get_prompt` → `{"prompt_type": "system_leaf", "variables": {"module_name": "<模块名>"}}`
2. 读取源码：`read_code_components` → 该模块所有组件 ID
3. 如需更多上下文，用 `view_repo_file` 补充读取
4. 撰写文档，包含：模块简介与核心功能、架构图（至少 1 个 Mermaid 图表）、各组件职责说明、交叉引用 `[模块名](模块名.md)`
5. 保存：`write_doc_file` → `{"session_id": "...", "filename": "<模块名>.md", "content": "..."}`

如果 Mermaid 校验失败，修正语法后用 `edit_doc_file`（`command: "str_replace"`）修改。

**每个父模块**（is_leaf=false）：

1. 用 `view_repo_file` 读取所有子模块已生成的 .md 文件
2. 获取总览提示词：`get_prompt` → `{"prompt_type": "overview_module", "variables": {"module_name": "<模块名>"}}`
3. 综合子模块文档，生成父模块总览
4. 用 `write_doc_file` 保存

### 阶段 4：生成仓库总览

1. 获取提示词：`get_prompt` → `{"prompt_type": "overview_repo", "variables": {"repo_name": "<仓库名>"}}`
2. 用 `view_repo_file` 读取所有已生成的模块文档
3. 撰写仓库级总览，包含：项目简介、端到端架构图（Mermaid）、各模块文档的引用链接
4. 保存：`write_doc_file` → `filename: "overview.md"`

### 阶段 5：清理

调用 `close_session` → `{"session_id": "<session_id>"}` 释放内存。

---

## LLM Wiki 使用指南

LLM Wiki 工具将 CodeWiki 从"一次性文档生成"升级为"持续积累的知识系统"。以下是三个核心使用场景。

### 场景 A：基于老项目开发新需求（最有价值的场景）

**目标**：在动手写代码之前，快速理解目标模块的上下文和历史决策。

```
Step 1: query_wiki — 搜索相关上下文
  ↓
Step 2: list_dependencies — 理解依赖关系和影响范围
  ↓
Step 3: 开始编码
  ↓
Step 4: ingest_note — 沉淀本次决策
```

**详细步骤**：

**1. 查询历史上下文**（无需 session，只要有 repowiki 目录）：

```json
{
  "output_dir": "<仓库路径>/repowiki",
  "query": "用户认证模块是怎么实现的，有哪些历史决策",
  "include_notes": true,
  "max_results": 10
}
```

返回结果包含：
- `results[]`：文档和笔记的排名列表，每条有 `source`（doc/note）、`snippet`、`relevance_score`
- `context_package`：一段可直接用于开发规划的上下文摘要
- `related_components[]`：相关组件 ID，告诉你代码在哪

**2. 理解依赖影响范围**（需要 session）：

```json
{
  "session_id": "<session_id>",
  "module_level": true,
  "direction": "both"
}
```

完整依赖图写入 workspace 文件 `dependencies.json`，MCP 返回文件路径和统计摘要。读取文件可获取 `module_dependency_graph`，例如：
```json
{
  "Authentication": {
    "depends_on": ["Database", "Config"],
    "depended_by": ["API", "Admin"]
  }
}
```

这告诉你：改 Authentication 会影响 API 和 Admin，同时它依赖 Database 和 Config。

**3. 开发完成后沉淀决策**：

```json
{
  "session_id": "<session_id>",
  "note_type": "decision",
  "title": "从 Session 切换到 JWT 认证",
  "content": "## 背景\n需要支持微服务间无状态认证\n\n## 决策\n采用 JWT + Refresh Token 双 token 方案\n\n## 备选方案\n- Session + Redis：放弃，因为跨服务共享成本高\n- OAuth2：过重，内部服务不需要\n\n## 影响\nAuthentication 和 API 模块需要重构",
  "related_modules": ["Authentication", "API"]
}
```

`related_modules` 可以省略——系统会从 content 中自动匹配模块名。笔记保存在 `repowiki/notes/YYYY-MM-DD-xxx.md`，下次 `query_wiki` 会搜到。

### 场景 B：文档生成后的质量增强

**目标**：确保生成的文档没有断链、引用正确、核心组件都有覆盖。

在阶段 5（close_session）之前执行：

**1. 运行一致性检查**：

```json
{ "session_id": "<session_id>", "checks": ["all"] }
```

返回结构化的问题列表：
- **error**（必须修）：断链、引用已删除的模块
- **warning**（建议修）：高影响力组件未被文档覆盖
- **info**：循环依赖、覆盖率统计

**2. 按优先级修复**：获取修复指南 `get_prompt({"prompt_type": "wiki_lint_report"})`，然后用 `edit_doc_file` 逐个修复 error。

**3. 查看依赖图谱**（可选，帮助理解模块关系）：

```json
{ "session_id": "<session_id>", "module_level": true, "direction": "both" }
```

`high_impact_components` 字段列出被最多组件依赖的核心类，这些组件的文档应该最详细。

### 场景 C：日常文档维护（无 session 模式）

**目标**：不开 session，直接对已有的 repowiki 目录做检查和查询。

`lint_wiki` 和 `query_wiki` 都支持不传 `session_id`，改用 `output_dir` 参数：

```json
// 检查文档健康度
{ "output_dir": "<仓库路径>/repowiki", "checks": ["broken_links", "stale_refs"] }

// 搜索开发上下文
{ "output_dir": "<仓库路径>/repowiki", "query": "数据库迁移方案" }
```

这在以下场景很有用：
- CI/CD 中定期检查文档健康度
- 新成员 onboarding 时搜索已有文档
- code review 时查阅历史决策

### 知识闭环：query → develop → ingest

LLM Wiki 的核心价值是让知识**复利增长**：

```
                    ┌──────────────────────┐
                    │   repowiki/           │
                    │   ├── *.md (文档)     │
                    │   ├── notes/ (笔记)   │
                    │   └── decisions_index │
                    └──────────┬───────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
   query_wiki            开发者编码              ingest_note
   (搜索上下文)         (使用上下文)           (沉淀新决策)
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               │
                    每次循环，知识库更丰富
```

**关键原则**：
- **编码前先 query**：避免重复踩坑，了解历史决策的理由
- **完成后再 ingest**：把"为什么"记下来，不只是"做了什么"
- **笔记聚焦决策**：标题是决策，内容是理由，200-500 字即可

### Schema 自定义

`analyze_repo` 自动生成的 `repowiki/schema.yaml` 可以手动编辑。系统会在下次运行时保留你的修改，只更新自动推断的字段（`languages`、`total_components`）。

**常用自定义**：

1. **关闭自动 crosslink**：`conventions.auto_crosslink` 默认为 `true`，每次 `write_doc_file` 会自动在文档末尾注入模块间交叉引用（Depends on / Used by）。如不需要可设为 `false`。

2. **调整 lint 阈值**：`lint.high_impact_threshold` 控制"高影响力组件"的判定标准（被多少个组件依赖才算高影响力），`list_dependencies` 和 `lint_wiki` 共用此值：
   ```yaml
   lint:
     high_impact_threshold: 5   # 默认 5。小项目(<100组件)可设 3，大仓库(500+)建议 8-10
   ```

3. **自定义文档维度**：编辑 `documentation_dimensions` 和 `required_sections` 来要求文档包含特定内容（如性能考量、安全审计等）。

4. **增量更新策略**：`update_policy.on_code_change` 设为 `manual` 可防止自动更新，适合需要人工审核的场景。

### LLM Wiki 功能开关

各 LLM Wiki 能力独立控制，没有全局开关。按需启用即可：

| 能力 | 控制方式 | 默认状态 | 说明 |
|------|----------|----------|------|
| Schema 生成 | 无开关 | 始终生效 | `analyze_repo` 自动生成 `schema.yaml`，无法跳过 |
| Crosslink 注入 | `conventions.auto_crosslink` | `true` | 设为 `false` 关闭 `write_doc_file` 自动注入交叉引用 |
| Lint 检查 | `checks` 参数 | 按需选择 | 传 `["all"]` 跑全部，或指定 `["broken_links", "stale_refs"]` |
| Lint 灵敏度 | `lint.high_impact_threshold` | `5` | `list_dependencies` 和 `lint_wiki` 共用，值越大告警越少 |
| 知识沉淀 | 按需调用 | 不产生文件 | `ingest_note` 不调用就不会创建任何笔记 |
| 知识查询 | 按需调用 | 不产生文件 | `query_wiki` 纯读取，无副作用 |

**典型配置示例**——只想要文档生成，不想要任何 LLM Wiki 附加功能：

```yaml
# repowiki/schema.yaml
conventions:
  auto_crosslink: false    # 关闭交叉引用注入
lint:
  high_impact_threshold: 999  # 实质上关闭 undocumented 告警
```

不调用 `ingest_note` 和 `query_wiki` 即可，无需额外配置。

### LLM Wiki 工具速查

| 工具 | 典型调用 | 何时用 |
|------|----------|--------|
| `query_wiki` | `{"output_dir": "...", "query": "..."}` | 编码前搜索上下文 |
| `list_dependencies` | `{"session_id": "...", "module_level": true}` | 评估变更影响范围 |
| `lint_wiki` | `{"output_dir": "...", "checks": ["all"]}` | 文档生成后/定期健康检查 |
| `ingest_note` | `{"session_id": "...", "note_type": "decision", ...}` | 需求/bug 完成后沉淀决策 |
| `get_prompt` | `{"prompt_type": "wiki_query"}` | 获取 wiki 工具使用指南 |

---

## 增量更新模式

当仓库已生成过文档（`output_dir` 下存在 `metadata.json` 和 `module_tree.json`），`analyze_repo` 的返回结果会包含 `changes` 字段：

```json
{
  "changes": {
    "has_previous": true,
    "no_changes": false,
    "method": "git",
    "changed_files": ["auth.py", "utils.py::hash_password"],
    "affected_modules": ["认证模块"],
    "cascade_modules": ["核心系统", "overview"]
  }
}
```

**变更检测策略**：优先使用 `git diff`（对比 commit SHA + 检查工作区未提交变更），非 git 仓库回退到对比文件修改时间。

**增量更新流程**：

1. 调用 `analyze_repo`，检查 `changes` 字段
2. 如果 `no_changes: true`，告知用户文档已是最新，无需操作
3. 如果 `no_changes: false`，**只更新 `affected_modules` 中列出的模块**：
   - 用 `read_code_components` 读取变更组件的新源码
   - 用 `edit_doc_file`（`str_replace`）局部修改对应文档，而非整篇重写
4. 对 `cascade_modules` 中的父模块，读取已更新的子文档后同步刷新总览
5. 最后更新 `overview.md`

增量更新的粒度是**模块级**——一个模块内任一组件变更，该模块文档需要更新。相比全量生成，增量更新通常只需处理 1-3 个模块。

## 工具速查表

| 工具 | 用途 |
|------|------|
| `analyze_repo` | 分析仓库，构建依赖图，组件索引写入 workspace 文件 + 自动生成 schema.yaml |
| `list_components` | 将完整组件列表写入 workspace 文件（支持按前缀/类型过滤） |
| `read_code_components` | 根据组件 ID 读取源码（格式：`文件::名称`） |
| `view_repo_file` | 只读浏览仓库文件/目录 |
| `write_doc_file` | 创建 .md 文档（自动 Mermaid 校验 + 可选 crosslink 注入） |
| `edit_doc_file` | 编辑文档：`str_replace` / `insert` / `undo` |
| `save_module_tree` | 保存模块聚类结果 |
| `get_processing_order` | 获取叶优先的处理顺序 |
| `get_prompt` | 获取提示词模板（填充后 >4KB 时写 workspace 文件，需传 `session_id`） |
| `close_session` | 关闭会话释放资源（2 小时自动过期） |
| `list_dependencies` | 将完整依赖图写入 workspace 文件（支持组件/模块级聚合） |
| `lint_wiki` | 文档-代码一致性检查（有 session 时写 workspace 文件，无 session 时 inline 返回） |
| `ingest_note` | 沉淀知识笔记（决策、经验教训、架构理由） |
| `query_wiki` | 搜索文档 + 笔记，获取开发上下文 |

## 大数据文件传递模式

为避免 MCP stdio 通道拥塞，所有可能超过 4KB 的数据通过 workspace 文件传递。

### 输入侧：`_file` 参数

以下工具支持 `*_file` 参数，当数据量大时（如超过 200 行），可将内容写入临时文件后传文件路径：

- `write_doc_file`：`content_file` 替代 `content`
- `edit_doc_file`：`old_str_file` 替代 `old_str`，`new_str_file` 替代 `new_str`
- `save_module_tree`：`module_tree_file` 替代 `module_tree`

### 输出侧：workspace 文件结果

返回数据超过 4KB 的工具自动写入 workspace 文件，MCP 只返回文件路径和摘要。IDE 代理用 `view_repo_file` 或原生文件读取能力获取完整数据。

| 工具 | 写入文件 | 返回内容 |
|------|----------|----------|
| `analyze_repo` | `component_index.json`、`leaf_nodes.json`、`languages.json`、`summary.json` | `session_id` + 文件路径 + 紧凑摘要 |
| `list_components` | `component_list.json` | `total` + 文件路径 |
| `list_dependencies` | `dependencies.json` | `total_deps` + `total_modules` + 文件路径 |
| `lint_wiki` | `lint_report.json`（有 session 时） | `total_issues` + `summary` + 文件路径 |
| `get_prompt` | `prompt_{type}.txt`（填充后 >4KB 时） | `prompt_type` + 文件路径 |
| `read_code_components` | `sources/*.src` | 文件路径列表 |
| `save_module_tree` | `processing_order.json` | 文件路径 |
| `get_processing_order` | `processing_order.json` | 文件路径 |

**注意**：`lint_wiki` 无 session 时仍通过 stdio inline 返回（向后兼容）。`get_prompt` 需传 `session_id` 参数才能写入 workspace 文件。

## 文档质量标准

- **语言**：默认中文撰写（除非用户指定其他语言）
- **Mermaid 图表**：每个模块至少 1 个架构图，优先使用 `graph TD` 或 `graph LR`
- **交叉引用**：引用其他模块时使用 `[模块名](模块名.md)` 格式
- **代码示例**：关键函数/类展示签名和简要用法
- **篇幅**：叶模块文档 200-500 行，父模块总览 100-300 行，仓库总览 80-200 行

## Mermaid 语法规范

```mermaid
graph TD
    A[组件A] --> B[组件B]
    A --> C[组件C]
```

- 节点 ID 仅使用字母和数字（避免中文、空格、冒号）
- 节点标签用方括号包裹：`A[显示文本]`
- 子图语法：`subgraph 标题 ... end`
- 禁止使用 `click`、`linkStyle` 等交互语法

## 错误处理

- **Mermaid 校验失败**：工具会返回校验错误信息，修正语法后用 `edit_doc_file` + `str_replace` 重试
- **会话过期**（2 小时超时）：重新调用 `analyze_repo` 创建新会话
- **大型仓库（>10 万行）**：`analyze_repo` 可能需要约 30 秒，可通过 `include_patterns`/`exclude_patterns` 缩小分析范围
- **组件 ID 格式**：始终使用 `component_index` 中的原始 ID（如 `src/main.py::MyClass`），保留 `::` 分隔符
