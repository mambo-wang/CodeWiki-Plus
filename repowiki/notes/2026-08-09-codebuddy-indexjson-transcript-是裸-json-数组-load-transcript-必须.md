---
type: pitfall
title: "CodeBuddy index.json transcript 是裸 JSON 数组，_load_transcript 必须支持 list 顶层展开"
tags: ["codebuddy", "pitfall", "sessionend"]
status: deprecated
generated: { by: codewiki/5.2.1, at: 2026-08-09T08:44:48Z }
stale_after: 2026-11-07

metadata:
  date: "2026-08-09"
  origin: "conversation"
  related_components: []
  related_modules: ["team-memory", "mcp", "\"\""]
  source_ref: "raw\\conv-20260808T152648Z.md"
---

## 背景

对话归档链路中，IDE 的 SessionEnd 事件携带 `transcript_path` 指向 `index.json`。实测发现 CodeBuddy 的 `index.json` 顶层是**裸 JSON 数组**（消息元数据：`id`/`role`/`isComplete`），正文分散在 `messages/<id>.json` 独立文件里（`message` 字段是嵌套 JSON 字符串，content 为块数组）。

## 正确做法

`_load_transcript` 的 `list` 分支**必须**先尝试 `_try_expand_codebuddy_index(p, data)` 再返回原始数组。原代码只在 `isinstance(data, dict)` 分支做 CodeBuddy 展开，导致裸数组直接返回元数据列表、归档不到正文（`capture_conversation._extract_transcript` 对每个 item 取 `content`/`message`/`text` 均为 None → `"no usable turns"` → 不写文件）。

修复后 `_load_transcript` 顺序：dict 分支与 list 分支都先尝试 `_try_expand_codebuddy_index`，失败再走 `_extract_inline_turns` 回退（顺序关键，避免元数据列表被误判为有效 turns）。展开时跳过 `role=tool` 的消息，并用 `_KEEP_ROLES = {"user","assistant"}` 白名单过滤 system/thinking。

## 根因

CodeBuddy 的 transcript 布局：`<session>/index.json`（仅元数据）+ `<session>/messages/<id>.json`。`index.json` 是数组而非对象，旧代码假设顶层为对象故漏掉数组分支的展开。

## 适用范围

所有依赖 IDE `transcript_path` 的采集逻辑；任何读取 CodeBuddy 会话文件的代码都需支持该布局。
