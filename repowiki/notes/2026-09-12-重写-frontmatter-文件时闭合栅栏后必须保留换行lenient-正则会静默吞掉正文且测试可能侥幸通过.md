---
type: pitfall
title: "重写 frontmatter 文件时闭合栅栏后必须保留换行：lenient 正则会静默吞掉正文且测试可能侥幸通过"
tags: ["pitfall"]
aliases: ["frontmatter 闭合栅栏换行", "栅栏粘连", "正文被吞"]
metadata:
  date: 2026-09-12
  task_id: 冲突一等对象
  related_modules: ["conflict_case", "frontmatter", "note_writer"]
  severity: medium
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.9.0, at: 2026-09-12T02:18:32Z }
stale_after: 2027-03-11
---

## 背景

ADR-0007 冲突案卷实施中，adjudicate_conflict 重写案卷文件时拼接为 `f"---\n{yaml.safe_dump(fm)}---{body}"` ——闭合栅栏与正文之间缺 `\n`。

## 现象为何危险

`parse_frontmatter` 的正则 `_FRONTMATTER_RE = r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)"`（codewiki/src/frontmatter.py:231）要求闭合栅栏后有换行（或文档结束）。缺换行时 lenient 解析并不报错——它退而求其次寻找下一个 `---`：本案中正文里追加的水平分隔线 `---` 被当作第二闭合栅栏，**整个正文被吸进 frontmatter 块**，但顶层键仍被逐行读出，status/resolution 照样解析成功。

结果是：单元测试全部通过（断言只查了 frontmatter 字段），而人读文件时正文缺失/错位——静默数据损坏。复现：`parse_frontmatter(f"---\n{yaml.safe_dump(fm)}---{body}")` 返回空 dict 或吞正文的 dict，取决于 body 是否含 `---`。

## 正确做法

1. 任何 `yaml.safe_dump` + `f"---\n{...}---"` 拼接，闭合栅栏后必须显式 `\n`：`f"---\n{yaml.safe_dump(fm)}---\n{body}"`（conflict_case.py 两处均已照此）。
2. 测试断言必须验证 `body.startswith("# ")` 这类正文首字符回归锁——只断言 frontmatter 字段会侥幸通过。

## 根因

lenient 解析器的设计目标是从各种历史格式里抢救数据，代价是结构性错误被降级为语义偏移；叠加 YAML 正文常含 `---` 水平线时，第二栅栏的存在让“错误格式”恰好可解析。
