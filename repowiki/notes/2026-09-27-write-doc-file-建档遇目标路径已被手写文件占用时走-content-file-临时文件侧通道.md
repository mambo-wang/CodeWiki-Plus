---
type: procedure
title: write_doc_file 建档遇目标路径已被手写文件占用时，走 content_file 临时文件侧通道
tags:
- procedure
metadata:
  date: 2026-09-27
  confidence_level: weak
  task_id: 他山之石
  source_session: d66c8f4336854d4e993cc7be40a0ef77
  related_modules:
  - mcp
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-c22842.md
  scene: Wiki文档建档
  compiled_into:
  - skills/write-doc-file-content-file-sidechannel/SKILL.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-27 04:53:16+00:00
stale_after: '2027-03-26'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-09-27T05:01:24Z'
---

## Background

2026-09-25 用 write_doc_file 正式建档 repowiki/wiki/queries/agentmemory-调研.md 时，因先用 write_to_file 手写了同路径文件，触发文件路由冲突，write_doc_file 拒绝写入。

## 正确做法（content_file 侧通道建档流程）

需要 write_doc_file 正式建档（frontmatter、交叉链接、索引注册）时：

1. 把正文写入一个临时文件（如 `.codebuddy/tmp-<名称>.md`）；
2. 删除目标路径上已手写的占位文件；
3. 调用 write_doc_file(content_file=<临时文件路径>, ...) 让工具正式建档；
4. 成功后删除临时文件。

## Rationale

值得持久：write_doc_file 要求目标路径不存在（由工具负责创建与元数据注入），手写文件占位会冲突；content_file 参数是官方文件侧通道，既避免大载荷内联，也绕开路由冲突。此流程在本次调研建档中实际跑通。
