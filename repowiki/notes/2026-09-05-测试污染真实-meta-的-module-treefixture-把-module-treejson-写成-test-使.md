---
type: pitfall
title: 测试污染真实 .meta 的 module_tree：fixture 把 module_tree.json 写成 {"test":...} 使影响分析与
  coverage 失真；从模块页组件清单反推可逆重建
tags:
- pitfall
metadata:
  date: 2026-09-05
  related_modules:
  - module_tree
  - lint_wiki
  severity: medium
  source_ref: conversations/conv-我们是如何保证生成的代码WIKI的准确性可信度.md
  scene: 知识生命周期
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:37:45+00:00
stale_after: '2027-03-04'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:51Z'
---

## Background

repowiki/.meta/module_tree.json 与 first_module_tree.json 被某个测试在同一时刻写成 65 字节的 `{"test":{"components":[],"children":{}}}`——fixture 写进了真实 .meta。

## 后果

- `get_module_tree` 返回 `total_modules=1`；`analyze_repo` changes 不返回 `affected_modules`；coverage/undocumented 检查失真（真实有 22+ 模块页）。
- lint 的 `undocumented` 判定以 module_tree 的 components 集合为准（module_tree = `save_module_tree` 持久化的 IDE 聚类结果）。

## 恢复与预防

- 可逆恢复：从各模块页的「组件清单/文件归属」表格反推重建（两阶段：组件名解析 + 文件列归属兜底），得到 22 模块/1226 组件、`unmatched_ids: []`。
- 根治：测试必须把 fixture 写进**隔离的临时 output_dir**，绝不落到真实仓库 repowiki/.meta；对会持久化到工作区的工具（save_module_tree、capture_conversation 等）尤其要设防。
