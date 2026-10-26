---
type: pitfall
title: "CodeBuddy SessionEnd 采集竞态：fire-and-forget hook 与 IDE Finalize 清理竞态导致静默丢弃"
tags: ["codebuddy", "filenotfounderror", "pitfall", "sessionend"]
metadata:
  date: 2026-10-24
  confidence_level: weak
  task_id: 日常维护
  source_session: "841627794bde4abf9a37b975f7c9b3b5"
  related_modules: ["codewiki/mcp/_ide_hook.py", "codewiki/hooks/capture_session_end.py"]
  severity: medium
  source_ref: "conversations\\conv-我发现内网电脑那个codebuddy我发采集对话记录，分析结果是：根因：transcript-展开失败，采集静默丢弃-采.md"
  scene: "对话采集链路（SessionEnd hook）"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.2, at: 2026-10-24T08:01:33Z }
stale_after: 2027-04-22
origin: conversation

---

## Background

内网 CodeBuddy 机器上 SessionEnd 对话采集静默丢弃。采集链路：SessionEnd → `capture_session_end.py` → 后台 `_ide_hook` → 读 transcript_path（指向被结束会话的 index.json）→ 展开 `messages/<id>.json` 提正文 → 写 raw/。

实测：`_load_transcript(index.json)` 返回 106 个无正文元数据 `{id,type,role,isComplete}`；`_try_expand_codebuddy_index(...)` 返回 None；读 `messages/c50fe25b....json` 报 FileNotFoundError。稳定后比对 index ids 184 = message files 184，交集 184——文件本身没丢，只是 SessionEnd 那一刻读不到。

## Root cause

- `capture_session_end.py:230-234` 用 `DETACHED_PROCESS` + `DEVNULL` fire-and-forget 启动采集子进程；
- IDE 触发 SessionEnd → hook 立即返回 → IDE 继续 Finalize 会话（清理/移动 `messages/*.json`）；
- 后台子进程延迟启动去读时文件已被 Finalize 清理 → 展开失败 → 无正文 → 静默丢弃，错误被 DEVNULL 完全吞掉。

本质：CodeBuddy IDE 升级后 transcript 落盘/清理时序变化，与 codewiki-plus 5.16.0 的后台异步采集模式产生竞态。与 `notes/2026-10-21-qoder-sessionend-采集静默失败transcript-的-role-嵌在-message-下导致-0-tu.md` 同症状（SessionEnd 采集 0 turns）但根因不同：Qoder 是 transcript 结构变化（role 嵌在 message 下），本次是文件清理时序竞态。

## Decision/正确做法

采纳「子进程内重试」方案（三个候选中的建议 2）：新增 `_wait_for_message_files`——当 index 是 CodeBuddy 形状但**所有** `messages/<id>.json` 缺失（Finalize 竞态特征）时，指数退避等待落盘（0.1s 起，8 次约 10s 预算），文件出现即继续；部分文件存在则不等待（正常路径零开销）。detached 子进程内等待完全不阻塞 IDE。

未采纳的替代方案：把 SessionEnd 采集改同步（去掉 DETACHED_PROCESS）——会让 IDE 阻塞到采集完成，且 10s 重试预算会直接卡住会话结束，得不偿失。建议 1（升级/降级找已修复版本）走不通：当时最新版 5.16.1（本仓 HEAD）无此修复，需随下个版本发布。

## Rationale

fire-and-forget 后台进程与 IDE 生命周期操作（Finalize 清理）共享同一批文件时必然存在竞态窗口；在后台进程侧做有界等待是唯一既不阻塞 IDE 又能容忍时序抖动的位置。值得沉淀：任何 DETACHED_PROCESS + DEVNULL 的采集设计都要预设「目标文件可能在读取时刻消失」，并留可观测性出口。

## Recovery

内网机器升级到含此修复的版本后，竞态窗口内会等待文件落盘；即使超时失败，也会在 `repowiki/.meta/hook_capture.log` 留下可诊断记录（见配套笔记）。
