---
type: lesson
title: "fast-jev-compaction 调研：无损上下文压缩工具，npm 未发布需源码安装"
tags: ["lesson", "typesafe"]
metadata:
  date: 2026-09-21
  confidence_level: weak
  source_session: "58f3db625f10427ca1b8d507c25a7aed"
  severity: medium
  source_ref: "conversations/conv-working_memory_content-The-following-is-the-existing-working-2-d592a1.md"
  scene: "外部工具调研"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.11.0, at: 2026-09-21T04:27:22Z }
stale_after: 2027-03-20
origin: conversation

---

## Background

调研 github.com/tamaratran/fast-jev-compaction（Claude Code 插件 + npm 库），2026-09-20 完成源码级核对与安装。

## 结论

该项目用 TypeSafe 的 Jev 模型做**无损上下文压缩**，替代 Claude Code 内置的「摘要式」compaction。核心思路：传统压缩让 LLM 把旧对话总结成摘要，但摘要有损——文件路径、精确报错、约束条件可能丢失；该项目**从不改写任何内容**，只做「删除决策」。

工作原理（README + 源码核对）：

1. 每个 `tool_use` 通过 `tool_use_id` 与其 `tool_result` 配对；首条消息和最近 N 条（默认 6）固定不动。
2. 发给 Jev 的是完整对话（旧→新），tool result 替换为短标记（如 `ok, 4213 chars (omitted)`），不做摘要。
3. 分阶段压缩状态到 25k token 上限内：tool 输入截断 1000→200→60 字符 → 长文本头尾截取 → 旧消息折叠为一行，逐级应用直到装得下。
4. 对每个非固定调用问 Jev 两个问题——「调用本身是否还需保留」「结果是否需逐字保留」，返回保留概率。
5. 决策（阈值 0.5）：`keepResult ≥ 阈值` → 全保留；否则 `keepCall ≥ 阈值` → 保留调用、结果截断为前 300 字符；否则连调用带结果一起删。
6. 重建消息列表：失去全部内容的消息被移除，不会出现有结果没调用的悬空。

失败（Jev 报错、key 缺失、装不下）会抛异常，由调用方回退到内置摘要。

## 安装事实

- npm registry **未发布该包**（`npm install fast-jev-compaction` 返回 404），需克隆源码后 `npm install && npm run build` 安装（2026-09-20 实测构建成功、29/29 测试通过）。
- 插件方式需 Claude Code CLI 2.1.274+，并设置 `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` 与 `TYPESAFE_API_KEY`；本机未装 Claude Code CLI 时插件方式不可用。
- 库方式：`import { compactMessages } from 'fast-jev-compaction'`，运行需 `TYPESAFE_API_KEY` 环境变量。

## Rationale

「删除决策 vs 有损摘要」的机制对比对上下文压缩/对话蒸馏类设计有直接参考价值；npm 未发布、需源码安装是复用时的前置事实。
