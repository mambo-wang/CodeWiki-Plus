---
type: architecture
title: ontology.yaml 的 types/relations 是未实现的 schema 骨架，只有 terms 被消费
tags:
- architecture
metadata:
  date: 2026-08-15
  related_modules:
  - cache
  - wiki_search
  source_ref: raw\conv-@d-repos-CodeWiki-CN-repowiki-ontology.yaml-看下这个文件的修改记录，是不是t.md
status: deprecated
generated:
  by: codewiki/5.2.2
  at: 2026-08-15 08:57:52+00:00
stale_after: 2026-11-13
origin: conversation
reject_reason: 用户评审未采纳
author: mambo-wang
---

## 背景

用户询问 repowiki/ontology.yaml 的 types/relations 字段是否真的被使用。

## 结论

types/relations 是提交 3600201 里基于本体论文章"理念先行"添加的 schema 骨架——注释、格式、示例写得很完整，但代码消费方、数据填充、反向链接推导、todo 占位机制均未实现，纯属设计预留。只有 terms 是真实生效的。

- 唯一读取该文件的是 cache.py::_load_ontology，它只处理 terms 键，构建同义词扩展映射（cache.py:172：若 data 无 terms 键直接返回 {}，types/relations 被忽略）
- wiki_search.py 消费 _load_ontology + _expand_with_ontology，仅做查询同义词扩展
- init_wiki.py 只是把模板复制到输出目录，不解析内容

## 坑点

注释里写"query_wiki 的 hop 多跳机制可直接消费此图"，但实际 hop 走的是 SQLite wiki_links 表（从文档间 [[]] 链接自动构建），与 relations 毫无关系（cache.py:1392 graph_expand）。未来 Agent 看到注释勿误以为 relations 已被消费。
