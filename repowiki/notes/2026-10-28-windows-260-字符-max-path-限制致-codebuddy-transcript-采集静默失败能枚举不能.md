---
type: pitfall
title: Windows 260 字符 MAX_PATH 限制致 CodeBuddy transcript 采集静默失败：能枚举不能读的幽灵文件
tags:
- codebuddy
- codebuddyextension
- findfirstfile
- pitfall
- sessionend
metadata:
  date: 2026-10-28
  confidence_level: strong
  task_id: 产品维护
  severity: high
  reason: 真机验证通过：真实 CodeBuddy 会话（消息文件 269 字符）修复前必返 None，修复后展开 14 轮对话；聚焦测试 40 passed
  verification:
    commit_ref: 5ce63ae
    test_ref: tests/test_ide_hook_capture.py::test_expand_codebuddy_index_long_path
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.16.4
  at: 2026-10-28 11:38:42+00:00
stale_after: '2027-04-27'
verified:
- by: human:iamwangbao-163-com
  at: '2026-10-29T00:56:57Z'
---

## 现象

CodeBuddy IDE 的 SessionEnd hook（team-memory capture）每天触发但 `repowiki/raw/` 始终为空，`repowiki/.meta/hook_capture.log` 里全是 `SessionEnd: no usable turns (transcript missing or unreadable)`。

## 根因

CodeBuddy IDE 的 transcript 存储布局堆叠了 3 段 UUID：

```
%LOCALAPPDATA%\CodeBuddyExtension\Data\{userId}\CodeBuddyIDE\{userId}\history\{workspaceHash}\{conversationId}\messages\{messageId}.json
```

index.json 约 225 字符（可读），messages/<id>.json 约 261-269 字符（超 Windows 260 MAX_PATH）。目录枚举（FindFirstFile）能看到文件名，但直接访问（CreateFile/stat）报「路径不存在」——形成「幽灵文件」假象，极易误诊为文件系统损坏或 IDE 清理了会话。系统 LongPathsEnabled=0 时 Python 的 `Path.is_file()`/`read_text()` 对超限路径直接抛 FileNotFoundError。

## 诊断技巧

- `Get-ChildItem` 能列出文件（Length、Attributes 正常）但 `Test-Path` 返回 False → 先查路径长度，再怀疑文件系统。
- 加 `\\?\` 前缀后 `Test-Path` 变 True 即实锤 MAX_PATH 限制。

## 修复

`codewiki/mcp/_ide_hook.py` 新增 `_win_long_path(path)`：Windows 下给绝对路径加 `\\?\` 前缀（UNC 转 `\\?\UNC\`），在 `_load_transcript` 入口单点应用——下游 `index_path.parent / "messages"` 的所有子路径拼接自动继承前缀，无需逐处修改。非 Windows 纯 no-op。

## 教训

- Windows 上「能枚举但不能读」的文件，第一嫌疑是 MAX_PATH 而非文件系统故障。
- 长路径兼容应在路径树入口单点转换，不要在每个 open/stat 处散弹式加前缀。
