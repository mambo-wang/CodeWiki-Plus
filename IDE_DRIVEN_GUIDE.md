# CodeWiki IDE 驱动模式：改造过程与使用指南

## 背景与动机

CodeWiki 原始设计需要用户自行配置 LLM API（API Key + base_url），然后通过 CLI 一键生成文档。这带来两个问题：

1. **配置门槛**：用户需要申请 API Key、了解 provider 差异、处理模型兼容性
2. **灵活性不足**：生成过程是黑盒的，用户无法在过程中干预聚类策略或文档风格

**改造目标**：将 CodeWiki 退化为**纯工具链 MCP Server**，由 AI IDE（CodeBuddy、Cursor 等）的 Agent 全权驱动 Wiki 生成流水线，实现**零 LLM 配置**。

---

## 改造过程

### 架构分析

通过源码分析，CodeWiki 的 Wiki 生成流水线在 4 个环节依赖 LLM：

| 环节 | 代码位置 | 调用方式 | LLM 作用 |
|------|---------|---------|---------|
| 模块聚类 | `cluster_modules.py` | `backend.complete()` | 将组件分组为逻辑模块 |
| 每模块文档 | `pydantic_ai_backend.py` | `agent.run()` 多轮对话 | 读代码、写文档、画 Mermaid 图 |
| 子模块递归 | `generate_sub_module_documentations.py` | 子 Agent 循环 | 递归处理嵌套模块 |
| 父模块总览 | `documentation_generator.py` | `backend.complete()` | 从子文档合成概述 |

关键发现：**依赖分析（Tree-sitter AST 解析）、依赖图构建、拓扑排序、Mermaid 校验** 这套核心工具链完全不需要 LLM。

### 改造策略

将 MCP Server 从"黑盒式一键生成"拆分为"细粒度工具集"：

```
改造前：
  IDE → generate_docs(repo) → [CodeWiki 内部自己调 LLM] → 结果

改造后：
  IDE Agent → analyze_repo → read_code → (Agent 自己推理聚类) → write_doc → overview
              ↑ 纯工具调用    ↑ 纯工具调用   ↑ IDE 自己的 LLM      ↑ 纯工具调用
```

### 新增文件清单

```
codewiki/mcp/
├── server.py                  # 重构：10 个工具注册（8 新 + 2 遗留）
├── session.py                 # 新增：会话状态管理（SessionStore）
├── workspace.py               # 新增：文件侧通道（大结果写入 .codewiki/sessions/）
└── tools/
    ├── __init__.py            # 新增：工具包入口
    ├── analysis.py            # 新增：analyze_repo 增强版 + 增量更新检测
    ├── code_reader.py         # 新增：read_code_components（源码写入 workspace 文件）
    ├── doc_writer.py          # 新增：write_doc_file + edit_doc_file
    ├── module_tree.py         # 新增：save_module_tree + get_processing_order
    └── prompt_server.py       # 新增：get_prompt 提示词模板服务
```

### MCP 工具集

| 工具 | 用途 | 是否需要 LLM |
|------|------|:---:|
| `analyze_repo` | 分析仓库，构建依赖图，返回组件索引 | 否 |
| `read_code_components` | 根据组件 ID 读取源码（写入 workspace 文件） | 否 |
| `write_doc_file` | 创建 .md 文档（含 Mermaid 校验） | 否 |
| `edit_doc_file` | 编辑文档（替换/插入/撤销） | 否 |
| `save_module_tree` | 保存 IDE Agent 的模块聚类结果 | 否 |
| `get_processing_order` | 获取叶优先的文档生成顺序 | 否 |
| `get_prompt` | 获取各阶段的提示词模板 | 否 |
| `close_session` | 关闭会话释放资源 | 否 |
| `generate_docs` | [遗留] 一键生成（需配置 LLM） | **是** |
| `get_module_tree` | [遗留] 获取已有模块树 | 否 |

### 文件侧通道（File-Side-Channel）

为避免大段数据通过 MCP stdio 传输导致性能瓶颈，我们引入了文件侧通道架构：`analyze_repo` 和 `read_code_components` 等大结果不直接返回给 Agent，而是写入 `{repo_path}/.codewiki/sessions/{session_id}/` 目录下的文件，MCP 响应仅包含文件路径和摘要信息。Agent 直接读取磁盘文件获取完整数据。

```
.codewiki/sessions/{session_id}/
├── component_index.json    # 组件索引
├── leaf_nodes.json         # 叶节点列表
├── languages.json          # 检测到的语言
├── summary.json            # 分析摘要统计
├── changes.json            # 增量变更检测结果（仅增量模式）
├── processing_order.json   # 文档生成顺序
└── sources/
    └── {component_id}.src  # 各组件源码
```

`close_session` 会自动清理整个 session 目录。

### 向后兼容

- 现有 CLI（`codewiki generate`、`codewiki config`）完全不变
- 现有 Web App 完全不变
- 遗留 MCP 工具 `generate_docs` 保留，已配置 LLM 的用户仍可使用

---

## 使用方法

### 前置条件

```bash
# 1. 克隆项目
git clone https://github.com/mambo-wang/CodeWiki-CN.git
cd CodeWiki-CN

# 2. 安装依赖
pip install -e .

# 3. 验证
python -c "from codewiki.mcp.server import server; print('MCP Server OK')"
```

### CodeBuddy 配置

**步骤 1**：在 CodeBuddy 中配置 MCP Server。

在 CodeBuddy 的 MCP 配置中添加：

```json
{
  "mcpServers": {
    "codewiki": {
      "command": "python",
      "args": ["-m", "codewiki.mcp.server"],
      "cwd": "/path/to/CodeWiki-CN"
    }
  }
}
```

**步骤 2**：将技能文件拷贝到 CodeBuddy 的技能目录：

```bash
cp -r skills/codewiki-wiki-generator .codebuddy/skills/
```

当你在 Agent 模式中提及"生成文档"或"Wiki"时，CodeBuddy 会自动加载该技能。

**步骤 3**：打开 CodeBuddy Agent 模式，输入：

```
帮我分析这个仓库并生成 Wiki 文档
```

### Cursor 配置

**步骤 1**：在 Cursor Settings → MCP 中添加 Server：

```json
{
  "mcpServers": {
    "codewiki": {
      "command": "python",
      "args": ["-m", "codewiki.mcp.server"],
      "cwd": "/path/to/CodeWiki-CN"
    }
  }
}
```

**步骤 2**：在 Cursor Agent 模式中输入：

```
请为当前仓库生成 Wiki 文档，输出到 docs 目录。
```

### Claude Desktop 配置

在 `~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）中添加：

```json
{
  "mcpServers": {
    "codewiki": {
      "command": "python",
      "args": ["-m", "codewiki.mcp.server"],
      "cwd": "/path/to/CodeWiki-CN"
    }
  }
}
```

### 其他支持 MCP 的 IDE

任何支持 MCP stdio 协议的 AI IDE 均可使用，配置方式类似——指定 `command: python`、`args: ["-m", "codewiki.mcp.server"]`。

---

## IDE Agent 工作流程

当你在 AI IDE 中触发 Wiki 生成时，Agent 会按以下 5 个阶段工作：

```
阶段 1: analyze_repo
  │  → 得到 session_id、组件索引、叶节点列表
  │
阶段 2: get_prompt("cluster") + read_code_components + save_module_tree
  │  → Agent 自己推理，将组件分组为 3-8 个逻辑模块
  │  → 得到叶优先的处理顺序
  │
阶段 3: 逐模块生成
  │  对每个叶模块：
  │  ├── get_prompt("system_leaf") → 获取文档撰写指令
  │  ├── read_code_components → 读源码（从 workspace .src 文件）
  │  └── write_doc_file → 写出 .md（自动 Mermaid 校验）
  │
  │  对每个父模块：
  │  ├── 读取子模块 .md 文件
  │  ├── get_prompt("overview_module") → 获取总览指令
  │  └── write_doc_file → 写出总览
  │
阶段 4: get_prompt("overview_repo") → 生成仓库总览 overview.md
  │
阶段 5: close_session → 释放资源
```

---

## 增量更新

### 原版 `--update` 的问题

原始 CodeWiki CLI 提供了 `codewiki generate --update` 增量更新命令，但存在一个 bug：CLI 适配器创建 `DocumentationGenerator` 时未传入 `commit_id`，导致 `metadata.json` 中 `commit_id` 始终为 `null`。`_detect_changed_files()` 读到 `null` 后直接退化为全量生成。只有 Web 模式（`background_worker.py`）才正确写入了 `commit_id`，所以 CLI 下的 `--update` 实际上**永远等同于全量生成**。

### MCP 增量更新方案

我们在 `analyze_repo` 工具中重新实现了增量检测，并将其升级为双策略模式：

```
第一次调用 analyze_repo：
  → 生成全量文档（changes 字段为 null）

代码变更后再次调用 analyze_repo：
  → 自动检测变更，返回 changes 字段
  → AI Agent 只更新受影响的模块文档
```

**变更检测策略**（按优先级）：

1. **Git 策略**：读取 `metadata.json` 中的 `commit_id`，与当前 HEAD 做 `git diff`，同时检查 `git status` 捕获未提交的变更
2. **Mtime 策略**（非 git 仓库回退）：对比源文件修改时间与 `metadata.json` 中的 `timestamp`

**返回结构**：

```json
{
  "changes": {
    "has_previous": true,
    "no_changes": false,
    "method": "git",
    "changed_files": ["auth.py"],
    "affected_modules": ["认证模块"],
    "cascade_modules": ["核心系统", "overview"]
  }
}
```

- `affected_modules`：直接受影响的模块，需要更新文档
- `cascade_modules`：间接受影响的父模块（子文档变了，总览也要刷新）和 `overview`

### Agent 增量更新流程

当 `analyze_repo` 返回 `changes` 且 `no_changes: false` 时，Agent 执行：

```
1. 只处理 affected_modules 中的模块：
   ├── read_code_components → 读取变更组件源码
   └── edit_doc_file(str_replace) → 局部修改文档（而非整篇重写）

2. 处理 cascade_modules 中的父模块：
   ├── 读取已更新的子文档
   └── edit_doc_file → 刷新总览部分

3. 最后更新 overview.md
```

相比全量生成的 5 阶段流程，增量更新通常只需处理 1-3 个模块，耗时大幅缩短。

### 实现细节

核心代码在 `codewiki/mcp/tools/analysis.py`，新增 4 个函数（约 170 行）：

| 函数 | 职责 |
|------|------|
| `_detect_changes()` | 主入口，协调 git/mtime 策略，调用模块映射 |
| `_detect_via_git()` | Git 检测：commit diff + uncommitted changes |
| `_detect_via_mtime()` | Mtime 回退：扫描源文件修改时间 |
| `_find_affected_modules()` | 子串匹配变更文件 → 模块映射（复用原版逻辑） |

`handle_analyze_repo()` 在构建完组件索引后调用 `_detect_changes()`，将结果附加到返回 JSON 的 `changes` 字段中。首次运行（无旧文档）时 `changes` 为 `null`，行为和之前完全一致。

### 同时修复的架构问题

改造过程中发现 `codewiki/__init__.py` 无条件 `import` 了 CLI 模块，导致启动 MCP Server 也必须安装 `keyring`、`click` 等 CLI 专属依赖。已将该 import 移除，MCP Server 现在可以轻量启动。CLI 入口（`__main__.py` 和 `pyproject.toml` 的 `codewiki = "codewiki.cli.main:cli"`）均直接从 `codewiki.cli.main` 导入，不受影响。

---

## 输出结构

生成的文档结构与原始 CodeWiki 一致：

```
docs/
├── overview.md              # 仓库总览（从这里开始读）
├── module1.md               # 各模块文档
├── module2.md               # ...
├── module_tree.json         # 模块层级结构
├── first_module_tree.json   # 初始聚类结果
└── metadata.json            # 生成元数据
```

---

## 原始 CLI 模式（仍然可用）

如果你更喜欢命令行一键生成，原始方式完全不受影响：

```bash
# 配置 LLM
codewiki config set \
  --provider openai-compatible \
  --api-key YOUR_KEY \
  --base-url https://api.example.com \
  --main-model claude-sonnet-4

# 一键生成
codewiki generate
```

详见 [README.md](README.md) 中的 Quick Start 章节。

---

## 常见问题

**Q: MCP Server 启动报错找不到依赖？**
A: 确保已运行 `pip install -e .` 安装 CodeWiki 及其依赖。

**Q: analyze_repo 分析很慢？**
A: 大型仓库（>10 万行）的 Tree-sitter 解析需要一定时间，通常 30 秒内完成。可以通过 `--include` / `--exclude` 缩小分析范围。

**Q: Mermaid 校验报错？**
A: Agent 会自动根据校验结果修正语法。如果反复失败，可以检查 `mermaid-py` 是否正确安装。

**Q: 如何让 Agent 用英文写文档？**
A: 在对话中明确指定："Please generate the Wiki documentation in English."

**Q: 会话超时了怎么办？**
A: 会话默认 2 小时超时。超时后重新调用 `analyze_repo` 即可创建新会话。

**Q: 代码改了之后如何增量更新文档？**
A: 直接对 AI Agent 说"更新 Wiki 文档"。Agent 调用 `analyze_repo` 时会自动检测变更，返回的 `changes` 字段会指出哪些模块受影响。Agent 只更新受影响的模块文档，而非全部重新生成。支持 git 仓库和非 git 仓库两种检测方式。

**Q: 增量更新的粒度是什么？**
A: 模块级。一个模块内任一组件的源文件变更，该模块的整篇文档会被标记为需要更新。同时其父模块的总览也会被标记（级联更新）。`overview.md` 在任何变更时都会刷新。
