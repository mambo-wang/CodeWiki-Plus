---
type: lesson
title: 历史会话回填方法论：走 handle_capture_conversation 正典路径，先核 git_sync 模式与 task_bindings，supersede/duplicate
  语义自动去重
tags:
- lesson
- sessionend
metadata:
  date: 2026-10-21
  confidence_level: weak
  task_id: 日常维护
  source_session: ed14a297-e047-4eba-a36e-a07ac3b1ff1c
  related_modules:
  - mcp-tools
  - hooks
  severity: medium
  source_ref: conversations/conv-为什么最近的对话没有抓取保存到-repowiki-raw目录下-，sessionEnd-Hook没生效吗.md
  scene: 产品维护：SessionEnd 修复后的历史 transcript 回填
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.15.0
  at: 2026-10-21 03:17:57+00:00
stale_after: '2027-04-19'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-10-21T03:59:13Z'
---

## Background

2026-10-21 修复 Qoder SessionEnd 采集 bug（role 嵌在 message 下导致 0 turns，见 `notes/2026-10-21-qoder-sessionend-采集静默失败transcript-的-role-嵌在-message-下导致-0-tu.md`）后，对 `~/.qoder-cn/projects/<项目>/` 下的历史 transcript 做了全量回填（11 个会话，~2.2MB）。沉淀可复用的回填操作要点。

## 回填正典路径

用修复后的解析管线走正式 handler，而不是手写 raw 文件：

```python
from codewiki.mcp._ide_hook import _load_transcript
from codewiki.mcp.tools.capture_conversation import _extract_transcript, handle_capture_conversation
turns = _extract_transcript(_load_transcript(path))  # 含脱敏与系统注入标签剥离
handle_capture_conversation({"repo_path": ..., "conversation": turns, "source_session_id": sid, "task_id": binding_or_empty}, SessionStore())
```

好处：raw/index/telemetry 与真实采集完全一致；`_extract_transcript` 自动做 secret redaction 与 `<working_memory_content>` 等系统注入块剥离。

## 前置核查（避免副作用）

1. **git 同步模式**：`handle_capture_conversation` 首次写入会触发 `session_ff_only`（git pull --ff-only）。`_resolve_mode`（`codewiki/src/git_sync.py:105`）读 `schema.yaml` 的 `conventions.git_sync.mode`，**默认 'advisory'**（D14）→ 不触发 pull。回填前确认模式，避免在脏工作区上意外 ff 前进。
2. **task_id 归属**：会话→任务绑定存在 `repowiki/.meta/task_bindings/<session_id>.json`。有绑定就盖章，没有就留空（不要凭猜测盖章）。
3. **排除当前活跃会话**：live 会话由 SessionEnd 自动采集，回填它只会被稍后的 recapture supersede。

## 去重语义（实测）

- 同一 source_session 再次采集 → **supersede**：旧 pending raw 被替换（10:00 采的 10KB 被 10:31 的更长版本顶掉）。
- 内容哈希完全一致 → 返回 **duplicate**，不重复落盘。回填时撞到 duplicate 说明该会话已被实时钩子采过（本次 c7be4d61 即如此，等于生产验证修复生效）。
- 蒸馏完成后 raw 从 `raw/` 移入 `conversations/` 归档，index 同步更新。

## 成本提醒

回填前先盘点各 transcript 的轮数与字符量（`_load_transcript`+`_extract_transcript` 干跑统计即可）：超大件（如 1824 轮/808K 字符）蒸馏成本很高，建议按需单独处理，不要一次性全蒸；琐碎测试会话（7 轮/1.2K）预期 no_knowledge，蒸掉清积压即可。
