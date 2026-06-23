---
name: codewiki-wiki-generator
description: "使用 CodeWiki-CN MCP 工具为代码仓库生成 Wiki 文档。当用户要求生成 Wiki、代码文档、仓库文档或分析代码库结构时使用此技能。需要已配置 CodeWiki-CN MCP 服务器。"
version: 2.0.0
---

# CodeWiki 文档生成器

你是一位代码文档生成专家。使用 CodeWiki-CN 的 MCP 工具为代码仓库生成全面的 Wiki 文档。所有 8 个工具均**无需配置 LLM**——你提供全部智能推理能力，CodeWiki 提供工具链。

## 核心机制：文件侧通道

CodeWiki MCP 采用**文件侧通道**架构：大体量数据（组件索引、源码、处理顺序）写入磁盘文件，MCP 只返回文件路径和精简摘要。你需要**用自己的文件读取能力**读取 workspace 文件获取完整数据。

Workspace 目录位于 `{repo_path}/.codewiki/sessions/{session_id}/`，包含：

- `component_index.json` — 完整组件索引（每项含 id/type/file）
- `leaf_nodes.json` — 完整叶子节点 ID 列表
- `languages.json` — 语言统计
- `summary.json` — 分析摘要
- `changes.json` — 增量变更信息（可选）
- `processing_order.json` — 文档生成顺序
- `sources/` — 组件源码文件（每个组件一个 `.src` 文件）

## 前置条件

开始前，确认 CodeWiki MCP 服务器可用。MCP 工具列表中应包含以下 8 个工具：`analyze_repo`、`read_code_components`、`write_doc_file`、`edit_doc_file`、`save_module_tree`、`get_processing_order`、`get_prompt`、`close_session`。

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

调用 `analyze_repo`：

```json
{ "repo_path": "<仓库绝对路径>", "output_dir": "<仓库路径>/repowiki" }
```

返回内容：`session_id`、`workspace_dir`（workspace 根目录路径）、`stats`（组件/叶子节点数量、语言统计）、`files`（各数据文件的路径）、`changes`（增量变更信息）。

**接下来必须读取 workspace 文件获取完整数据：**

1. 读取 `{workspace_dir}/component_index.json` — 完整组件列表
2. 读取 `{workspace_dir}/leaf_nodes.json` — 叶子节点 ID 列表
3. 根据 `stats` 了解仓库规模，规划聚类策略

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

**每个叶模块**（is_leaf=true）：

1. 获取系统提示词：`get_prompt` → `{"prompt_type": "system_leaf", "variables": {"module_name": "<模块名>"}}`
2. 读取源码：`read_code_components` → 该模块所有组件 ID，然后读取 `sources/` 下的文件
3. 如需更多上下文，直接用文件读取工具读取仓库内相关源文件
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
4. 保存：`write_doc_file` → `filename: "overview.md"`

### 阶段 5：清理

调用 `close_session` → `{"session_id": "<session_id>"}` 释放内存并清理 workspace 文件。

## 增量更新模式

当仓库已生成过文档（`output_dir` 下存在 `metadata.json` 和 `module_tree.json`），`analyze_repo` 的返回结果会包含 `changes` 字段，完整数据写入 `changes.json` 文件（不再截断 changed_files 列表）。

**变更检测策略**：优先使用 `git diff`（对比 commit SHA + 检查工作区未提交变更），非 git 仓库回退到对比文件修改时间。

**增量更新流程**：

1. 调用 `analyze_repo`，检查返回的 `changes` 字段或读取 `changes.json` 文件
2. 如果 `no_changes: true`，告知用户文档已是最新，无需操作
3. 如果 `no_changes: false`，**只更新 `affected_modules` 中列出的模块**：
   - 用 `read_code_components` 读取变更组件的新源码（写入 workspace 文件后读取）
   - 用 `edit_doc_file`（`str_replace`）局部修改对应文档，而非整篇重写
4. 对 `cascade_modules` 中的父模块，读取已更新的子文档后同步刷新总览
5. 最后更新 `overview.md`

增量更新的粒度是**模块级**——一个模块内任一组件变更，该模块文档需要更新。

## 工具速查表

| 工具 | 用途 | 数据流 |
|------|------|--------|
| `analyze_repo` | 分析仓库，构建依赖图 | 写文件到 workspace，返回路径 + 统计 |
| `read_code_components` | 获取组件源码 | 每个组件写入 `sources/*.src`，返回路径 |
| `write_doc_file` | 创建 .md 文档（自动 Mermaid 校验） | 直接写文件 |
| `edit_doc_file` | 编辑文档：`str_replace` / `insert` / `undo` | 直接改文件 |
| `save_module_tree` | 保存模块聚类结果 | 写 module_tree.json + processing_order.json |
| `get_processing_order` | 获取叶优先的处理顺序 | 写 processing_order.json，返回路径 |
| `get_prompt` | 获取提示词模板 | 内联返回（数据量小） |
| `close_session` | 关闭会话释放资源 | 清理 workspace 文件 |

## 文档质量标准

- **语言**：默认中文撰写（除非用户指定其他语言）
- **Mermaid 图表**：每个模块至少 1 个架构图，优先使用 `graph TD` 或 `graph LR`
- **交叉引用**：引用其他模块时使用 `[模块名](模块名.md)` 格式
- **代码示例**：关键函数/类展示签名和简要用法
- **篇幅**：叶模块文档 200-500 行，父模块总览 100-300 行，仓库总览 80-200 行

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
- **大型仓库**：`analyze_repo` 可能需要约 30 秒，可通过 `include_patterns`/`exclude_patterns` 缩小分析范围。不再有组件数量或源码长度的截断限制
- **组件 ID 格式**：始终使用 `component_index.json` 中的原始 ID（如 `src/main.py::MyClass`），保留 `::` 分隔符
