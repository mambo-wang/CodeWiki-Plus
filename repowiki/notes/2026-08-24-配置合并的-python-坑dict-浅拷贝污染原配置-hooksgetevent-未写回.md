---
type: pitfall
title: 配置合并的 Python 坑：dict 浅拷贝污染原配置 + hooks.get(event, []) 未写回
tags:
- pitfall
metadata:
  date: 2026-08-24
  task_id: 产品维护
  related_modules:
  - cli
  - ide-config
  severity: medium
  source_ref: conversations/conv-当前项目添加的hook和subagent只支持codebuddy，优化为支持市面上常见的智能体，比如自动检测有.qode.md
  consolidated_into:
  - wiki/scenarios/IDE-Hook采集链路方法.md
status: deprecated
generated:
  by: codewiki/5.4.2
  at: 2026-08-24 03:33:22+00:00
stale_after: '2027-02-20'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-08-24T03:40:50Z'
reject_reason: 聚合进场景：IDE-Hook采集链路方法
---

## 背景

多 IDE 接线把新 IDE 的 hooks 合并进已有 settings.json 时出现幂等判断恒真的 bug。

## 两个坑

1. **浅拷贝污染**：`dict(existing)` 只复制顶层，嵌套的 `hooks` 子字典仍是共享引用。往子字典追加条目会同时改掉 existing 原配置，导致「已存在」比较恒成立、幂等判断失效。
2. **get 未写回**：`hooks.get(event, [])` 返回默认空列表后若未 `hooks[event] = ...` 写回，append 的内容直接丢失。

## 修复

嵌套结构用 `copy.deepcopy` 深拷贝；事件键用 `hooks.setdefault(event, [])` 显式初始化后再 append。

## 适用范围

所有读取-修改-写回 JSON 配置的场景（settings.json / package.json 等）。
