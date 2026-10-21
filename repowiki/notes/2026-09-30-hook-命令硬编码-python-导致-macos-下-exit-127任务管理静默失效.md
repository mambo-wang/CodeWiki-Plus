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
source_conversations: ['conversations/conv-拉取最新代码.md']

---

## Background

历史问题（原笔记记录）：hook 命令硬编码 `python` 导致 macOS 下 exit 127、任务管理静默失效——按安装机平台快照解释器（`_resolve_python_cmd`，Windows 写死 `python`）的设计随机器漂移，跨平台不可复现。

## Decision（2026-10-08 定案，任务「产品维护」）

install-hooks 生成的三个 hook 命令（START/END/PROMPT）改为**写死的跨平台回退**：

```
python3 "{ide_dir}/hooks/task_session_start.py" || python "{ide_dir}/hooks/task_session_start.py"
```

`_resolve_python_cmd`/`_PYTHON_CMD` 已删除。

## 安全前提（为什么 `||` 不会二次执行）

hook 脚本（task_session_start.py / capture_session_end.py / _ide_hook.py）全部 fail-open：`main()` 恒 `return 0`、永不非零退出。因此 python3 缺失（exit 127 走 stderr）后 python 兜底恰好执行一次；mac 上 python3 成功则短路。**若未来某 hook 改为可非零退出，此设计前提即被破坏，需重新评估。**

## 实施要点

- 改动落在生成层常量（`codewiki/cli/utils/ide_hook.py`），三处已提交配置（`.qoder`/`.codebuddy`/`.trae` 的 settings/hooks.json）同步为同一形态，保证 on-disk == 生成产物 → install-hooks 幂等不覆盖。
- 迁移/去重契约不依赖解释器名：`_relative_hook_suffix` 正则只看结尾带引号的 `.py` 相对路径后缀，复合命令仍以 `...py"` 结尾故兼容。
- 判「已启用」只看脚本相对路径后缀、不看解释器名（prompts.py 口径文案已同步）。
- 测试：平台快照测试改为回退形式断言（partition `||` 后左 python3 右 python、头部无路径分隔符）。

## 后续修正（2026-10-13）

TRAE Windows 走 PowerShell 5.1，`||` 是解析期错误导致 hook 静默全灭——TRAE 的命令形态后来改为单解释器（见 `notes/2026-10-13-trae-windows-hook-命令勿用-兜底powershell-51-解析期报错导致-hook-静默不执行.md`）。即本决策的回退形式适用于 bash 语义宿主（Qoder/CodeBuddy），PowerShell 宿主是例外。
