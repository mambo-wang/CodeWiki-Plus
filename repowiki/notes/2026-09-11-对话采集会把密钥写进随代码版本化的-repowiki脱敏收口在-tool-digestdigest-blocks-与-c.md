---
type: decision
title: "对话采集会把密钥写进随代码版本化的 repowiki，脱敏收口在 tool_digest.digest_blocks 与 capture_conversation._extract_transcript"
tags: ["decision", "github"]
metadata:
  date: 2026-09-11
  related_modules: ["MCP_Tools_Knowledge"]
  severity: medium
  source_ref: "raw\\conv-继续调研.md"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.9.0, at: 2026-09-11T13:01:52Z }
stale_after: 2027-09-11
---

## Background

发布版本会话里 `uv publish` 命令带 `$env:UV_PUBLISH_TOKEN='pypi-…'` 原文被 hook 采进 `repowiki/conversations/conv-发布版本.md`，随 L2 知识聚合自动提交（bbc10f9）推到 GitHub 公开仓库。GitHub push protection（GH013）拦下后续推送时，token 已在远端历史里。

## Decision

新增 stdlib-only 脱敏模块 `codewiki/src/secret_redact.py`，在两条采集路径的收口点统一调用：`tool_digest.digest_blocks`（工具行）与 `capture_conversation._extract_transcript`（正文），命中密钥形态即替换为 `<redacted:kind>`。配套 8 条新测试，全量回归 932 passed（提交 37ecf04，重写后 hash）。

## Rationale

repowiki 是随代码版本化、要推送的资产——任何在对话里出现过的密钥都会被写进公开仓库。收口在采集侧比推送前预检更早，且同时覆盖归档与蒸馏两条路径。

## 关键提醒

历史重写只能阻止扩散，救不了已泄露的值：先去服务商后台（此处是 PyPI）revoke，再清历史、force push。GitHub 拦截本身就说明 token 已经离开本机。
