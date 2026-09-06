---
type: lesson
title: 'OKF v0.2 §7 actor 格式：agent 应写 <producer>/<version>，agent: 前缀不在规范内，消费端仅凭 human:
  前缀推导信任档位'
tags:
- codewiki
- lesson
metadata:
  date: 2026-08-15
  related_modules:
  - codewiki/src/frontmatter.py
  - codewiki/src/config.py
  - codewiki/mcp/tools/knowledge_loop.py
  source_ref: raw\conv-https-mp.weixin.qq.com-s-vzBQPjrRDhDfq3U51DBfaQ-看下我们项目符不符合ok.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 09:08:32+00:00
stale_after: 2026-11-13
origin: conversation
reject_reason: 用户评审后拒绝全部蒸馏草稿
author: mambo-wang
---

## 背景

CodeWiki-CN 按 OKF v0.2 规范做符合性核查时，此前代码里把 agent 产物写成 `agent:codewiki/5.2.0`（`agent:` 前缀 + producer/version），并误以为 §7 的三种 actor 形式包含 `agent:` 前缀。复核规范后确认这是错误理解。

## 正确做法

OKF v0.2 §7 的 actor 规范只有三种形式：`<producer>/<version>`（agent/tool 用）、`human:<id>`（人类用）、`process:<id>`（流水线用）。agent 产物必须写 `<producer>/<version>`，例如 `codewiki/5.2.2`，不能带 `agent:` 前缀。信任档位（unverified / machine-confirmed / human-reviewed）的推导只看 `verified[].by` 是否有 `human:` 前缀，与 agent 字段无关。

## 根因

对规范文本的想当然理解：把『agent』这个名词直接当成前缀写进了格式，而没有严格对照 §7 给出的三种形式。修复涉及 5 个文件：config.py 的 actor_id()、frontmatter.py 的 _default_actor()、knowledge_loop.py 的 _okf_actor()、registry.py 与 prompt_server.py 中的示例文本。
