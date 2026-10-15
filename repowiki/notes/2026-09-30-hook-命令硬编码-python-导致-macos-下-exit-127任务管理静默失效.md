---
type: pitfall
title: hook 命令硬编码 python 导致 macOS 下 exit 127（任务管理静默失效）
tags:
- pitfall
- sessionend
- sessionstart
- userpromptsubmit
metadata:
  date: 2026-09-30
  confidence_level: strong
  verification:
    reviewed_by: ocr:delegate-round-2
    test_ref: tests/test_install_hooks.py
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.14.1
  at: 2026-09-30 14:24:06+00:00
stale_after: '2027-04-03'
verified:
- by: human:mambo-wang
  at: '2026-10-05T12:52:53Z'
---

## 问题现象
Qoder CN（macOS）上 codewiki 的三个 hook（SessionStart / SessionEnd / UserPromptSubmit）全部 exit 127（command not found），表现为「任务关联弹框从来不出、对话从来不采集」，且 IDE 端只看到静默失败，要翻 `~/.qoder-cn/logs` 才能看到 127。

## 根因
`codewiki/cli/utils/ide_config.py` 生成的 hook 命令硬编码为 `python "..."`（`START_HOOK_CMD` / `END_HOOK_CMD` / `PROMPT_HOOK_CMD`）。Windows 和带 python2 兼容链接的环境有 `python`，而 macOS 上 PEP 394 只保证 `python3`，于是 hook 一启动即 127。这不是 hook 机制不支持——实测 Qoder CN 完整支持 claude 家族的 hook 契约（stdin 事件 + `hookSpecificOutput.additionalContext`），只是解释器名字不对。

## 修复口径
1. 生成侧：`_resolve_python_cmd()` —— Windows 恒 `python`；POSIX 按 `python3` > `python` 用 `shutil.which` 探测，均缺失时回退 `python`。
2. 存量侧：`merge_settings_json` 把既有命令按相对脚本后缀 / `-m codewiki.mcp._ide_hook --enable` 尾部特征原地迁移为新命令（保留 timeout、不重复注册）；`unwire_hook_registration` 用同一口径匹配，历史写死解释器的条目也能被摘干净。

## 排查启示
宿主 hook “没反应”时先看日志里的退出码，而不是先怀疑 hook 事件不支持：127 = 命令本身拉不起来（解释器/路径），不是接线档位问题。hook 脚本内部异常也统一走 stderr 落日志，不要指望 IDE 弹窗。
