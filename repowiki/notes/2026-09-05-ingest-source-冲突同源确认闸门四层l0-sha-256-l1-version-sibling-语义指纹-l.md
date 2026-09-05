---
type: decision
title: "ingest_source 冲突/同源确认闸门四层：L0 SHA-256 / L1 version_sibling 语义指纹 / L2 conflict 同名异文 / L3 supersede 声明"
tags: ["decision"]
metadata:
  date: 2026-09-05
related_modules: ["source_ingest", "doc_similarity", "registry", "README_CN", "README_CN_f03499.md"]
  severity: high
  source_ref: "conversations/conv-user_command-commands-codewiki-外部文档知识抽取-请导入外部文档并从中抽取结构化知识。采用-2.md"
  scene: "知识生命周期"
status: stable
author: iamwangbao-163-com
generated: { by: codewiki/5.6.0, at: 2026-09-05T11:35:03Z }
stale_after: 2027-09-05
origin: conversation
source_conversations: ['conversations/conv-user_command-commands-codewiki-外部文档知识抽取-请导入外部文档并从中抽取结构化知识。采用.md']

---

## Decision

用户反馈「完善设计文档并改版本号」再导入时无任何提醒（内容与 name 两道旧防线只认精确匹配，双双穿透）。2026-09-05 落地为四层确认闸门，全部**只警告不落盘**：

- **L0** SHA-256 字节去重 → 内容完全相同拦下。
- **L1** `doc_similarity` 语义指纹 → 疑似同文档改版（内容改了 name 也改了）→ `version_sibling`，附分数与证据。
- **L2** 同名不同内容 → `conflict`。
- **L3** 文档 frontmatter `supersedes: <旧source_id>` 显式声明 → `supersede_declared`（声明式语义，比推断准，兜底骨架全变的文档）。

## 用户同意令牌

- `overwrite=true`（同名替换）/ `allow_sibling=true`（确认并存）作为显式令牌，替代 `user_confirmed=yes`；令牌非隐式，切到别的 source/目录即失效。
- 异名 + overwrite 被**拒绝**（同一份内容换名再存 = 孪生副本污染检索）。
- 工具无状态不调 LLM，只报告分数与证据由调用方/用户裁决；误判代价不对称 → 宁可多问（拦错 = 多问一次低成本，漏了 = 孪生污染检索）。

## 判定/范围

`ingest_source` 工具描述补 CONFIRMATION GATE 段写明两种冲突、确认令牌语义、异名拒绝规则；`duplicate`/`conflict` 分支统一返回 `requires_user_confirmation` + `existing` + `user_options`（reuse/overwrite/rename）。

## ingest_source 曾静默覆盖 registry 同名键：磁盘哈希改名只保护文件不保护登记，name 级冲突须走 conflict + overwrite=true + 旧文件入 .trash

> 合并自蒸馏候选：ingest_source 曾静默覆盖 registry 同名键：磁盘哈希改名只保护文件不保护登记，name 级冲突须走 conflict + overwrite=true + 旧文件入 .trash

## 事故背景与根因（2026-09-04 实测，冲突闸门的缘起）

导入 TAM README（与既有 WeKnora README 同名 `README_CN`）时，旧 WeKnora 登记被**无条件覆盖**、无提示。三种重名风险只拦前两种：

1. 内容 hash 完全相同 → duplicate 提示（有效）。
2. 磁盘文件名重名 → **静默加哈希后缀改名**（`README_CN_f03499.md`）——只保护磁盘文件，不保护登记。
3. registry `sources[name]` 键已占用（内容不同）→ dict 键重复**无条件覆盖**。

后果：磁盘旧文件仍在但 registry 的 `README_CN` 已指向新文件；`retract_source(name="README_CN")` 会操作错文件，旧文件成为无法按登记清理的孤儿；摘要页 resource 指向与实际登记不一致。

## 落地细节

- name-level conflict guard 加在去重检查之后、落盘复制之前；`overwrite=true` 同意后先把旧 raw 移入 `.trash/`（retract_source 安全删除模式，可恢复）再落新文件。
- 首发 commit 30c53c4（source_ingest + registry.py + 回归测试 6 项断言）。
- 后续演进为 L0/L1/L2/L3 四层闸门与本笔记上部一致。
