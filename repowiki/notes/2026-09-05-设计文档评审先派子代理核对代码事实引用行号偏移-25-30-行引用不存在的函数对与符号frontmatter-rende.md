---
type: lesson
title: 设计文档评审先派子代理核对代码事实：引用行号偏移 25-30 行、引用不存在的函数对与符号（frontmatter render、route_page_type）
tags:
- lesson
metadata:
  date: 2026-09-05
  severity: medium
  source_ref: conversations/conv-对-docs-claude-mem借鉴详细设计方案.md-做拷问式评审（grill）：先派子代理核对方案引用的全部代码事.md
  scene: 方案评审
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:33:43+00:00
stale_after: '2027-03-04'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:52Z'
---

## Background

docs/claude-mem借鉴详细设计方案.md 评审时，先派子代理核对方案引用的全部代码事实，发现三类漂移。

## 发现（2026-09-02 核实）

1. **行号普遍偏移 25-30 行**：如 max_chars 实际在 knowledge_loop.py:1725（文档写 1696）、_walk 在 2617（文档写 2588）——语义全部属实，**实施以语义定位为准**，行号修正应随修订一次做掉。
2. **引用了不存在的函数对**：frontmatter.py 无 render/序列化函数（只有 parse_frontmatter + format_frontmatter_value），文档 §2.6 与 CONTEXT.md 词汇表引用的 `parse(render(x))==x` 往返不变量对应函数对不存在。
3. **符号漂移更彻底**：route_page_type 全仓库不存在；PAGE_TYPE_DIRS 真身在 codewiki/src/config.py（不在 frontmatter.py）。词条应按代码现状重写。

## 正确做法

对引用具体行号/符号/函数对的设计文档，评审第一轮先用子代理核对代码事实（文件存在性、行号、符号真身位置、测试断言），把「语义属实但定位过时」与「引用了不存在对象」分开标注，再进入决策拷问。
