# 安装指南

## CodeWiki-CN 安装

```bash
git clone https://github.com/mambo-wang/CodeWiki-CN.git
cd CodeWiki-CN && pip install -e .
```

MCP 配置（添加到客户端的 mcpServers 配置中）：

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

**Windows 注意事项**：

- QoderWork 环境下 CodeWiki MCP 启动约需 4.2 秒，可能触发 `-32001` 超时错误，需适当增大超时
- CodeBuddy 等其他 IDE 需要额外配置 `env.PYTHONPATH=D:\repos\CodeWiki-CN`，否则找不到模块（`-32000` 错误）

## CodeGraph 安装（可选增强）

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
{
  "mcpServers": {
    "codegraph": {
      "command": "codegraph",
      "args": ["serve", "--mcp", "--path", "<project-path>"],
      "env": {
        "CODEGRAPH_MCP_TOOLS": "explore,files,node,callers,callees,impact,search,status"
      }
    }
  }
}
```

**Windows 路径注意**：CodeGraph 路径参数使用正斜杠，如 `D:/repos/project`。
