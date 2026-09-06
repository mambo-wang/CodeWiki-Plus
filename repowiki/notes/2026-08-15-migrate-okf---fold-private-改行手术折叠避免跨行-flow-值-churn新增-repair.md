---
type: decision
title: migrate_okf --fold-private 改行手术折叠避免跨行 flow 值 churn；新增 repair_double_quoted_escapes
  先修复坏转义再折叠
tags:
- decision
metadata:
  date: 2026-08-15
  related_modules:
  - scripts/migrate_okf.py
  source_ref: raw\conv-https-mp.weixin.qq.com-s-vzBQPjrRDhDfq3U51DBfaQ-看下我们项目符不符合ok.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 09:08:36+00:00
stale_after: 2026-11-13
origin: conversation
reject_reason: 用户评审后拒绝全部蒸馏草稿
author: mambo-wang
---

## 背景

scripts/migrate_okf.py --fold-private 用于把旧格式 notes 迁移为 OKF v0.2（私有键折叠进 metadata）。原实现是整块 YAML 反序列化后整体重写，会产生大范围 diff（churn），且遇到跨行的 flow 值（如 sources 列表）会破坏结构。

## 决策

- 改为『行手术折叠』：逐行扫描 frontmatter，仅对命中的私有键行做行级改写（移到 metadata 块下），未命中行原样保留，最小化 diff。
- 新增 `repair_double_quoted_escapes(fm_lines)`：把单行 `key: "value"` 中非法的反斜杠转义修复为 `\\`（保留 \n \t 等合法转义），使坏 frontmatter 恢复可解析。
- 修复逻辑提前到 fold_private 分支之前：原实现解析失败直接 SKIP，现在先修复再走折叠路径，坏文件也能被 --fold-private 处理。
- 同步修掉脚本内残留的 `agent:codewiki` fallback → `codewiki`（§7 一致性）。

## 结果

对 repowiki 实跑：16 个坏文件全部修复，无 SKIP，每个标记 `repaired invalid YAML escapes; folded metadata: ...`，知识文档（notes/ + wiki/）OKF 合规 0 issue。
