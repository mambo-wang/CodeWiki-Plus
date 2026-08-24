---
type: pitfall
title: install-hooks 幂等去重在 Windows 路径分隔符下失效
tags:
- pitfall
- sessionend
- sessionstart
aliases:
- 幂等去重
- 路径分隔符
- install-hooks
- settings.json 重复注册
metadata:
  date: 2026-08-24
  related_modules:
  - cli
  severity: low
  root_cause: merge_settings_json 按 command 原始字符串精确匹配去重，而 Path 拼接在 Windows 生成反斜杠路径，与手动配置的正斜杠路径字符串不同，等价命令被判为不同条目。
  consolidated_into:
  - wiki/scenarios/IDE-Hook采集链路方法.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 13:46:28+00:00
stale_after: '2027-02-20'
verified:
- by: codewiki/5.4.2
  at: '2026-08-24T13:55:42Z'
reject_reason: 聚合进场景：IDE-Hook采集链路方法
---

## 背景

`codewiki install-hooks` 的 `merge_settings_json` 按 command 字符串**精确匹配**去重，宣称"重复运行不产生重复条目"。在 Windows 上实际运行时，若项目内已有手动写入的正斜杠路径条目（`d:/repos/...`），CLI 新生成的反斜杠路径条目（`d:\repos\...`）会被视为不同命令，同事件同 matcher 下出现**重复注册**。

## 现象

`.codebuddy/settings.json` 的 SessionStart/SessionEnd 各出现两条 command（一条 `/` 路径、一条 `\` 路径），指向同一脚本。功能上无害（第二次触发走内容哈希去重），但配置冗余且每次 install-hooks 都可能再追加。

## 正确做法

1. **生成端统一**：`install_for_ide` 用 `Path.as_posix()` 生成正斜杠命令，与项目内手动配置格式一致。
2. **比较端归一化**：去重比较前把 `\` 归一化为 `/`（`norm = lambda cmd: (cmd or "").replace("\\", "/")`），对历史反斜杠条目也免疫。

## 根因

Windows 下 `Path` 拼接产生反斜杠，字符串与手写正斜杠不同；按原始字符串去重无法识别等价路径。

## 适用范围

任何在 Windows 上对含路径的配置做字符串去重/幂等合并的场景。修复已落地于 `codewiki/cli/utils/ide_config.py`（2026-08-24）。
