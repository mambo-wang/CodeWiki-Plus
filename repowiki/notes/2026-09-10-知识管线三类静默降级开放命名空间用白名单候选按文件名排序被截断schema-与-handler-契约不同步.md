---
type: pitfall
title: 知识管线三类静默降级：开放命名空间用白名单、候选按文件名排序被截断、schema 与 handler 契约不同步
tags:
- pitfall
aliases:
- 静默降级
- 白名单黑名单
- 候选截断
- schema 契约不同步
metadata:
  date: 2026-09-10
  task_id: 技能提取
  related_modules:
  - tool_digest
  - skill_creator
  - registry
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-10 07:46:50+00:00
stale_after: '2027-03-09'
verified:
- by: human:wangbao
  at: '2026-09-10T07:47:27Z'
- by: human:wangbao
  at: '2026-09-10T07:49:22Z'
---

## 坑一：开放命名空间用白名单，必然静默漏判

`tool_digest` 为保留工具成功结果设计了一张工具名白名单（30 个名字）。工具名是**开放命名空间**：各宿主一套（Bash / execute_command / run_terminal_cmd），MCP 工具还带 `mcp__<server>__` 前缀。实测本仓库归档对话里 38 处 MCP 调用（capture / distill / confirm / skill_creator，正是最想捕获的工作流）全部落在名单外，成功结果被静默丢弃——没有日志、没有计数。

**正确做法**：改用**黑名单**（`_READ_ONLY_TOOL_NAMES`）——只排除只读、无副作用、输出体积大的工具（read / search / list / fetch）。判据是失败方向：黑名单漏判只是多留一行 120 字符摘要，白名单漏判是永久丢失这一步证据。

## 坑二：候选按文件名排序 + limit 截断，最新素材永远进不来

`skill_creator._candidate_notes` / `_candidate_scenarios` 原用 `sorted(ndir.glob("*.md"))` 遍历并在 limit 处 break。笔记文件名以日期开头，字典序 = 日期升序 = **最旧优先**。实测候选里最晚只到 2026-09-05，当天新写的笔记被截掉；返回的 `total` 字段不反映截断，调用方以为看到了全部。

**正确做法**：按 `mtime` 倒序（最新优先）+ 提高默认 limit（30→60）+ 返回 `available` 与 `truncated` 字段，让截断可见。

## 坑三：schema enum 与 handler 不同步，直到真调用才暴露

`skill_creator` 的 handler 支持 `install` / `retire`，但 `registry.py` 的 `mode` enum 只有 `prepare|submit`，且缺少 `name` / `reason` 参数声明。日常只用 prepare/submit 时毫无异常，直到真正调用 install 才报 `Input validation error: 'install' is not one of ['prepare', 'submit']`。

**正确做法**：handler 新增模式必须同步改 registry schema（团队既有约定「新增 MCP 能力：handler + registry schema 两处」）；改完还需**重启 MCP server** 才生效——registry 是进程内加载的。

## 根因

三者的共同点是**静默降级**：无日志、无标记、返回值看起来正常，只有实测计数或真正调用到那条分支才会发现。直觉根因（「白名单挺全」「候选够用」「schema 应该跟着改了」）全部被实测数据证伪。
