---
type: architecture
title: "CodeBuddy 全局 MCP 默认延迟加载：工具 schema 按需拉取而非每轮常驻，「49 工具常驻 22–35k token」前提存疑"
tags: ["architecture", "codebuddy", "deferexecutetool", "toolsearch"]
metadata:
  date: 2026-09-11
  task_id: Cli能力
  related_modules: ["MCP_Server"]
  severity: medium
  source_ref: "conversations/conv-manually_attached_skills-Please-use-the-use_skill-tool-to-in-75d169.md"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.9.0, at: 2026-09-11T13:05:47Z }
stale_after: 2027-09-11
origin: conversation

---

## CodeBuddy 全局 MCP 默认延迟加载：工具 schema 按需拉取而非每轮常驻

评估「CLI 对齐 MCP 省 token」时，实测 MCP `get_all_tools()` 载荷 88,727 字符（49 工具），据此推断「工具 schema 每轮常驻 22–35k token」，并设计了 P1 描述瘦身 / P2 分层暴露面 / P3 CLI 投影的方案。

排查子代理 MCP 授权时，从 CodeBuddy 官方 Subagents 文档挖到关键描述：**scoped MCP 与全局 MCP 使用相同的延迟加载策略，默认 MCP 工具走 deferred loading——模型先通过 ToolSearch 发现工具，再通过 DeferExecuteTool 调用**。与会话实际行为互证：调 codewiki 工具走 `mcp_get_tool_description` → `mcp_call_tool` 两步，系统提示里只有 49 个工具的**名字列表**，没有一份 schema——那 88k 字符是按需拉取的，不是每轮常驻。

对前提的影响（截至发现时未经 `/context all` 实测定论）：

| 原假设 | 修正后 |
|---|---|
| MCP 工具定义每轮常驻 22–35k token | 常驻的可能只有工具名，schema 按需 |
| P1 描述瘦身省 7.7k token/轮 | 只省「被拉取那一次」，收益量级下调 |
| CLI/skill 渐进披露是两个数量级优势 | MCP 自身已是渐进式，优势被抹平 |
| AGENTS.md 精简 36% | 不受影响——纯文本注入，无延迟加载机制 |

坐实只需 `/context all` 里 MCP 块的真实 token 数：几百~1k（工具名列表）则 P1 与 CLI 方案收手；22k+ 则本条作废、P1 照做。实测前不要拿估算口径推进依赖「MCP 常驻」前提的设计。
