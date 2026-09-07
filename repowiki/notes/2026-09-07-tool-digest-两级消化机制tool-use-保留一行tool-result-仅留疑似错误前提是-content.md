---
type: architecture
title: tool_digest 两级消化机制：tool_use 保留一行、tool_result 仅留疑似错误；前提是 content-block 列表
tags:
- architecture
metadata:
  date: 2026-09-07
  related_modules:
  - tool-digest
  - capture
  severity: medium
  source_ref: conversations/conv-SKILL-CREATOR需求的PHASE-2是不是还没启动.md
  scene: 对话采集素材保真度
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 03:01:21+00:00
stale_after: '2027-09-07'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:19Z'
---

## 背景

codewiki/src/tool_digest.py（约 199 行，stdlib-only）是 §9 素材保真度的实现，两条采集路径（codewiki/mcp/tools/capture_conversation.py 与 codewiki/mcp/_ide_hook.py）共享同一 import 单点，不会漂移。

## 三档处理

| 档 | 处理 |
|---|---|
| 纯噪音（thinking/reasoning/thought/system/context） | 无条件丢弃 |
| tool_use / tool_call / function_call | 保留一行 `[tool: 名 · 首个参数行]`，≤160 字符，保持原始顺序（顺序即「命令→报错→修复」链） |
| tool_result / function_result | 仅疑似错误时保留 `[tool-error: 摘录]`（is_error 标记或命中错误指纹），≤360 字符；成功结果丢弃 |

## 关键边界

1. **前提是 content 为 content-block 列表**：手搓 `conversation=[{"role":…,"content":"纯文本"}]`（QwenWork 协议）没有 tool 行，不是 bug，是上游没给结构化块。
2. **历史语料找不回来**：§9 于 2026-09-06 落地，此前抓的会话（raw/ 与 conversations/ 归档 43 个，`[tool:` 命中 0）工具细节已永久丢弃；带工具行的语料从落地日开始攒，B 层（工具序列相似度）判据因此冷启动。
3. "not found" 是较宽的错误指纹，成功输出含 "not found" 会被误留一行（宁多勿少）。
4. 绝对路径会原样写进 raw（推送前需扫描脱敏）。
