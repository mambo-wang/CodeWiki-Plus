---
type: lesson
title: "同一消息前缀的判定散落多处会静默漂移：收敛为单一 helper（Mermaid 错误匹配三处不一致案例）"
tags: ["lesson"]
metadata:
  date: 2026-11-28
  confidence_level: weak
  scene: "代码评审修复/判定口径收敛"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.8, at: 2026-11-28T00:09:43Z }
stale_after: 2027-05-27
---

## Background
提交 a5467805 把 doc_writer.py 第 1500 行的 Mermaid strict 拦截收紧为完整前缀 "mermaid syntax errors found in file:"，但 1594/1910 两处 mermaid_warnings 高亮仍用宽匹配 "syntax errors"——同一消息前缀的判定散落三处，口径分裂，消息前缀再变时会静默漂移。

## 正确做法
收敛为单一判定函数：
```python
def _has_mermaid_syntax_errors(result: str) -> bool:
    return "mermaid syntax errors found in file:" in result.lower()
```
三处（strict 拦截 + 两处高亮）统一调用该 helper，并补防回归单测（断言 unavailable 消息即使含 "syntax errors" 字样也不命中）。

## Rationale
字符串前缀判定散落多处是典型的漂移温床：一处收紧、他处遗忘，行为差异不报错只表现为「高亮与拦截不一致」。任何「同一消息格式的多处判定」都应收敛为单一函数/常量，这与 Doctrine「单点收敛：同构逻辑只留一份」一致。
