---
type: pitfall
title: server.py 硬编码 version 与 pyproject 漂移：MCP initialize 返回版本误导客户端
tags:
- pitfall
metadata:
  date: 2026-09-07
  related_modules:
  - mcp
  - release
  severity: medium
  source_ref: conversations/conv-本周改动有点大，请把CODEWIKI-MCP整体测试一遍，重点测试最近一周的改动.md
  scene: MCP 整体测试
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 03:04:05+00:00
stale_after: '2027-03-06'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:17Z'
---

## 背景

2026-09-02 测试发现 `codewiki/mcp/server.py` 硬编码 `version="5.2.1"`，与 `pyproject.toml` 的 5.5.1 不一致。

## 影响

MCP `initialize` 握手返回的版本号会误导客户端（下游按版本判断能力时出错）。

## 正确做法

server 版本号应从 `codewiki.__version__`（或 pyproject 读取）注入，勿在 server.py 手写常量；发版时把「三处版本引用」清单扩为四处核查（pyproject / __init__.py / uv.lock / server.py）。
