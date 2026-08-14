---
type: pitfall
title: "repowiki/raw/ 目录堆积会使同步捕获线性变慢，逼近 60s 超时"
tags: ["pitfall"]
status: deprecated
generated: { by: codewiki/5.2.2, at: 2026-08-12T11:58:40Z }
stale_after: 2026-11-10

metadata:
  date: "2026-08-12"
  origin: "conversation"
  related_components: []
  related_modules: ["mcp", "hooks", "\"\""]
  source_ref: "raw\\conv-hook是同步执行还是异步执行的.md"
---

## 背景

长对话下 hook 捕获是否会超时的分析。

## 风险点

`capture_conversation.py` 在去重/替换时遍历 `raw_dir.glob("conv-*.md")` 逐个 `read_text`。若 hook 一直开着但从未跑蒸馏，`repowiki/raw/` 堆积上百个文件，每轮捕获都要全量读一遍，随文件数线性变慢，长对话 + 大量 raw 叠加时可能逼近 60s 超时。

## 正确做法

- 用文件索引（`repowiki/raw/.index.json`）替代全量 `read_text`，或把 `subprocess.run` 改为 `subprocess.Popen` fire-and-forget，让 IDE 不等捕获完成（注意会失去同步超时保护）。
- 定期蒸馏清理 raw，避免堆积。
