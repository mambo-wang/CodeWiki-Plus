---
type: architecture
title: Agent hook 注入的工程化防御与防漂移可复用模式（caveman 提炼）
tags:
- architecture
- juliusbrussee
metadata:
  date: 2026-09-04
  task_id: 他山之石
  severity: medium
  source_ref: conversations/conv-https-github.com-JuliusBrussee-caveman.git-研究下这个技能是如何生效的.md
  scene: 他山之石-caveman研究
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.5.1
  at: 2026-09-04 04:13:46+00:00
stale_after: '2027-09-04'
origin: conversation
verified:
- by: codewiki/5.5.1
  at: '2026-09-04T04:25:35Z'
---

## Background

从外部仓库 JuliusBrussee/caveman 的 hook 注入实现中提炼的可复用工程模式（研究结论已核实，非推测）。适用于任何「把提示词规则注入 Agent 上下文」的加载链路设计。

## 可复用模式

1. **单事实源 + 运行时读取注入**：hook 每次启动都重新读 `SKILL.md`，而不是把规则硬编码拷贝到注入点——规则改动即时生效、不产生两处漂移。

2. **hook 的工程化防御**（最值得抄的一组做法）：
   - `requireSibling()` 校验兄弟模块的导出形状，缺文件时降级而非崩溃；
   - stdin 读取加 2s watchdog，用 `unref()` 防句柄阻塞进程退出；
   - stdin payload 按「首个完整 JSON 对象」触发处理而非等 EOF（规避 Windows 管道 close 延迟）；
   - hook 永不非零退出（避免误杀宿主会话）。

3. **per-session 状态而非全局标志**：模式/档位状态按 `session_id` 隔离存盘（如 `~/.claude/.caveman-sessions/<session_id>.mode`），多窗口会话互不干扰。

4. **重新注入兜底防漂移**：SessionStart 对 `compact`/`resume` 事件同样触发，规则全量重注入——解决「上下文被自动压缩剪掉后模型行为漂回默认风格」的经典问题；配合 UserPromptSubmit 每轮轻量提醒做双保险。

5. **编译期硬闸门**：registry 与目录一致性、frontmatter 名称必须匹配目录名、prompt 字节预算超限即构建失败；冲突技能必须成对声明且 precedence 不同。

6. **token 裁剪**：同一 SKILL.md 按激活档位只注入对应示例行，规则本身按字节预算设限；分类激活（task_types/entry_condition/precedence）只注入当前任务需要的 skill。

## Rationale

这些模式共同解决注入系统三类常见失效：规则漂移（两处拷贝、被压缩剪掉）、进程级脆弱（缺文件/管道延迟导致宿主崩溃）、资源浪费（全量注入超过上下文预算）。
