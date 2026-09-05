---
type: pitfall
title: wiki/index.md 条目 summary 复用页面 description 时相对链接失效：_render_index 须按 relpath
  的 dirname 为重定位裸相对链接
tags:
- pitfall
metadata:
  date: 2026-09-05
  related_modules:
  - wiki_index
  severity: medium
  source_ref: conversations/conv-我们是如何保证生成的代码WIKI的准确性可信度.md
  scene: 知识生命周期
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:37:48+00:00
stale_after: '2027-03-04'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:46Z'
---

## Background

lint 报 `wiki/index.md` L40 断链到 `MCP_Tools_Analysis.md`，但该文件确实存在于 `wiki/modules/`。

## 根因

`wiki_index.py::_render_index`（L466 附近）把页面 `description` 原样嵌入条目：

    parts.append(f"* [{entry['title']}]({entry['relpath']}) - {entry['summary']}")

模块页 description 里的 `[MCP_Tools_Analysis](MCP_Tools_Analysis.md)` 按**页面所在目录 modules/ 解析**，嵌进根目录 index.md 后相对路径失效；`fix=true` 自愈无效（文件存在，是路径错，不是缺文件）。

## 修复

新增 `_relocate_summary_links`：把 summary 中的裸相对链接按页面目录补前缀（URL/锚点/绝对路径/已带路径的不动）；输出 `modules/MCP_Tools_Analysis.md`，lint 归零，配 4 个单测。

## 启示

聚合索引页复用「为别处编写的、含相对链接」的文本时，必须按目标位置重定位链接根；lint 的 broken_links 查不到相对路径基准错，需要按「链接所在页实际目录」判据。
