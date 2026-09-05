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
source_conversations: ['conversations/conv-https-github.com-DietrichGebert-ponytail-研究下这个技能是如何生效的.md']

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

## ponytail 的 5 个可复用工程手法（单一事实源/永不阻塞/fail-open/副作用最小化/debt 台账）

> 合并自蒸馏候选：ponytail 的 5 个可复用工程手法（单一事实源/永不阻塞/fail-open/副作用最小化/debt 台账）

## ponytail 同主题的增量手法（与 caveman 提炼互补）

DietrichGebert/ponytail 的 hooks 实现与 caveman 属同一类「规则单事实源 + hook 注入」工程，多数模式已在上文覆盖；以下为 ponytail 版本带来的增量点：

1. **fail-open 优先（明文化）**：坏正则、不可解析 payload、无 agent_type 一律降级为「照常注入」（PONYTAIL_SUBAGENT_MATCHER 解析失败不阻断子代理注入），宁可多注入也不静默丢人格。
2. **副作用最小化**：跨会话 config 只有 /ponytail default X 一条写路径；状态栏 nudge 用 flag 只提示一次；卸载脚本只删自己的状态行。
3. **把「以后再说」变成台账**：规则要求用 `# ponytail: <天花板> — <升级路径>` 标注刻意简化，再由 /ponytail-debt 收割成清单，避免技术债腐化。
4. **Windows EOF 陷阱具体化**：读 stdin 一律配 1s setTimeout(...).unref() 兜底——Windows PowerShell 包装会吞掉 EOF 导致钩子挂死（上游 issue #443）。
5. **规则副本同源校验脚本**：scripts/check-rule-copies.js——改了规则文本而分发副本没同步，测试就红（CodeWiki 多宿主分发可借鉴的防漂移闸门）。
