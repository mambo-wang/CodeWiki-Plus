---
type: pitfall
title: YAML frontmatter 裸 f-string 插值 Windows 路径产生非法转义 \c 导致整个 frontmatter 无法解析（OKF
  §11 违规），字符串字段一律用 json.dumps 转义
tags:
- pitfall
metadata:
  date: 2026-08-15
  related_modules:
  - codewiki/mcp/tools/knowledge_loop.py
  - scripts/migrate_okf.py
  source_ref: raw\conv-https-mp.weixin.qq.com-s-vzBQPjrRDhDfq3U51DBfaQ-看下我们项目符不符合ok.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 09:08:33+00:00
stale_after: 2026-11-13
origin: conversation
reject_reason: 用户评审后拒绝全部蒸馏草稿
---

## 背景

ingest_note 写 frontmatter 时用裸 f-string 拼行：`source_ref: "{source_ref}"`，而 source_ref 是 Windows 路径 `raw\conv-20260808T145202Z.md`，其中的 `\c` 不是合法 YAML 双引号转义，导致整个 frontmatter 无法解析，16 个 notes 文件全部中招（OKF §11 违规）。

## 正确做法

任何可能含反斜杠/引号/冒号的字符串字段写入 frontmatter 一律用 `json.dumps(value, ensure_ascii=False)` 生成 YAML 双引号标量，禁止裸 f-string 插值。json.dumps 会把 `\` 转成 `\\`、`"` 转成 `\"`，经 YAML safe_load 后能还原为原字符串。

## 根因

f-string 只做字符串拼接，不做 YAML 转义；开发者误以为双引号包住就安全，没意识到反斜杠在 YAML 双引号标量里有转义语义。

## 适用范围

title/root_cause/source_ref 三处写路径已全部修复；历史坏文件用 migrate_okf.py 的 repair_double_quoted_escapes() 批量修复（把非法反斜杠加倍）。
