---
type: pitfall
title: Qoder SessionEnd 采集静默失败：transcript 的 role 嵌在 message 下导致 0 turns
tags:
- pitfall
- sessionend
aliases:
- Qoder 会话没有保存到 raw
- SessionEnd 不生效
- Qoder transcript 解析 0 turns
- qoder raw 抓取失败
metadata:
  date: 2026-10-21
  confidence_level: strong
  related_modules:
  - _ide_hook
  - capture_conversation
  severity: high
  root_cause: _ide_hook._load_transcript 对 JSONL 按行返回原对象，但 Qoder/Claude Code transcript
    的 role 位于 message.role，capture_conversation._extract_transcript 只读顶层 role，全部轮次被丢弃；detached
    子进程 stdout/stderr 均 DEVNULL，失败完全静默。
  verification:
    test_ref: tests/test_ide_hook_capture.py::test_qoder_transcript_e2e
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.15.0
  at: 2026-10-21 02:09:45+00:00
stale_after: '2027-04-19'
verified:
- by: human:mambo-wang
  at: '2026-10-21T03:48:46Z'
---

## 现象

Qoder 会话结束后 repowiki/raw/ 没有新增 conv-*.md；Qoder 日志里 SessionEnd 项目钩子却显示 success=true、exit_code=0。

## 排查路径

1. Qoder 日志确认 SessionEnd 项目钩子已执行：`hook.started hook_name="SessionEnd:other" source="project"`，exit 0。
2. 在 Qoder agent SDK（`resources/app.asar.unpacked/.../qoder-worker-runtime.obf.mjs`）确认 `createCoreBaseInput` 构造的载荷含 `session_id`、`transcript_path`、`cwd`、`hook_event_name`——接线本身没问题。
3. 取真实 transcript（`~/.qoder-cn/projects/<repo>/<session>.jsonl`）走内层采集：`_load_transcript` 加载 214 条，`_extract_transcript` 归一化后 0 条，返回 `{"error": "conversation contained no usable turns."}`。

## 根因

Qoder（及 Claude Code）的 transcript 是 JSONL，每条形如：

```json
{"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "..."}]}}
```

role 嵌在 `message` 下，顶层 `type` 只是条目种类。`_extract_transcript` 只接受顶层 `role`，于是用户/助手轮次全被跳过；附件、快照等条目本来也应丢弃。采集失败被 wrapper 的 detached 子进程吞掉（stdout/stderr 均为 DEVNULL），外部看不到任何报错。

## 修复

`codewiki/mcp/_ide_hook.py` 新增 `_normalize_transcript_entry`：

- 顶层 `role` 属于 user/assistant → 原样返回（保留宿主元数据，不影响既有 CodeBuddy/内联格式）；
- 否则若 `message.role` 属于 user/assistant → 归一化为 `{role, content}`；
- 其余条目（attachment、runtime-config、active-leaf 等）丢弃。

在 `_load_transcript` 的 JSONL 回退分支与 JSON 数组分支都应用。

## 验证

`tests/test_ide_hook_capture.py` 新增 `test_load_transcript_qoder_jsonl` 与 `test_qoder_transcript_e2e`；真实 transcript 在临时仓库端到端采集 160 turns / 83KB，frontmatter 含 source_session。

## 后续注意

- 子进程 stderr 仍不可见，采集失败只能靠代码路径排查；如需可观测性可给 wrapper 加日志落盘（未做）。
- 历史会话 transcript 仍在 `~/.qoder-cn/projects/<repo>/<session>.jsonl`，可按需回填 raw。
