---
type: pitfall
title: 普通字符串里的 {{placeholder}} 经 .format() 只会变成字面 {placeholder}：双花括号转义仅 f-string 需要
tags:
- pitfall
metadata:
  date: 2026-10-21
  confidence_level: weak
  task_id: 产品维护
  source_session: 866c3f80-00e6-4cf2-a227-ed85ecea806a
  related_modules:
  - cli
  severity: medium
  source_ref: conversations/conv-拉取最新代码.md
  scene: 改写含 .format 占位符的字符串常量
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.15.0
  at: 2026-10-21 03:14:10+00:00
stale_after: '2027-04-19'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-10-21T03:59:15Z'
---

## Pitfall

把 f-string 常量改写成普通字符串时，若保留 `{{ide_dir}}` 写法，`.format(ide_dir=...)` 会把 `{{` 解转义成字面 `{`——占位符失效，得到字面 `{ide_dir}` 文本。双花括号是 **f-string** 里输出 `{` 的转义；普通字符串要被 `.format()` 消费就该写单花括号 `{ide_dir}`。

## 实际后果（2026-10-08 案例）

`ide_config.py` 的 START/END 常量从 f-string 改为普通串时误留 `{{ide_dir}}` → 生成命令含字面 `{ide_dir}/...`，不以 `.` 开头 → `_relative_hook_suffix` 正则匹配不到 → 迁移逻辑全线失效，13 条 install_hooks 迁移/去重测试失败（症状：settings 里出现新旧两条命令）。修正为单花括号后 91 条接线测试全过。

## 排查技巧

占位符失效类 bug 的快速验证：直接在 REPL 里对常量跑 `.format(...)` 并 `repr()` 输出，看占位符是否展开；再对下游正则/endswith 单独验证返回值，不要靠脑内推演正则回溯。

与既有笔记 `notes/2026-09-27-sync-commands-的-stub-templateformat-对-i18n-description-中的花括号.md` 互补：那条讲模板对**用户内容**中的花括号零防御（KeyError/索引错乱），本条讲**自己写常量**时误用 f-string 转义习惯导致占位符失效。
