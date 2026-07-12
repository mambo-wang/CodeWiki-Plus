# 错误处理

## Mermaid 校验失败

`write_doc_file` 内置 Mermaid 语法校验。校验失败时工具返回错误信息，修正语法后用 `edit_doc_file(command: "str_replace")` 修改。

常见 Mermaid 错误：
- 节点 ID 含中文或空格 → 改用纯字母数字
- 标签未用方括号 → `A[显示文本]`
- 使用了交互语法（click/linkStyle）→ 删除

## 会话过期（2 小时超时）

重新调用 `analyze_repo` 创建新会话，获取新的 `session_id` 后继续。

## session not found

通常是 session 被服务端驱逐。CodeWiki MCP 最多同时维护 10 个 session，超出后静默驱逐最久未访问的。

**常见原因**：子代理自行调了 `analyze_repo` 创建了新 session，导致主代理的 session 被驱逐。

**解决方案**：
1. 所有子代理必须共享主代理的 `session_id`，不得自行创建新 session
2. 如果已被驱逐，重新调用 `analyze_repo` 获取新 session_id 后继续

## 大型仓库

`analyze_repo` 可能需要约 30 秒。优化策略：
- 使用 `include_patterns` / `exclude_patterns` 缩小分析范围
- 不再有组件数量或源码长度的截断限制

## 组件 ID 格式

始终使用 `component_list.json` 中的原始 ID（如 `src/main.py::MyClass`），保留 `::` 分隔符。

**Windows 注意**：组件 ID 使用反斜杠（如 `backend\src\main.py::MyClass`）。`read_code_components` 传入正斜杠会返回 `not_found`。须从 `list_components` 或 `summary.json` 确认 ID 格式后再使用。

## CodeGraph 相关错误

### 索引缺失

`codegraph_status` 报错时，在项目目录执行 `codegraph init`（Windows 路径用正斜杠如 `D:/repos/project`），然后重试。

### 索引过期

CodeGraph 通过文件监听器自动同步。如果报告过期，等待几秒后重试。

### 符号歧义

使用 `codegraph_node` 加 `file` 参数消歧。

### 工具调用失败

静默跳过该步骤，继续标准模式流程。CodeGraph 是增强而非必需。

## QoderWork 环境特有

### bash 输出 "output file could not be read"

偶发问题。解决方案：将输出重定向到文件后再用 Read 工具读取。

### MCP 启动超时 (-32001)

CodeWiki MCP 启动约需 4.2 秒，可能触发超时。需适当增大客户端超时设置。

### 模块找不到 (-32000)

在 IDE 的 MCP 配置中添加 `env.PYTHONPATH` 指向 CodeWiki-CN 目录。
