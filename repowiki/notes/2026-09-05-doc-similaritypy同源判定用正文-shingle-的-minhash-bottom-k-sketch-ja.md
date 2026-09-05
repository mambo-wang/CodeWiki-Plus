---
type: architecture
title: doc_similarity.py：同源判定用正文 shingle 的 MinHash bottom-k sketch Jaccard（SimHash
  余弦基线非 0，骨架对小文档/模板文档过敏感）
tags:
- architecture
- minhash
metadata:
  date: 2026-09-05
  related_modules:
  - doc_similarity
  - source_ingest
  severity: medium
  source_ref: conversations/conv-user_command-commands-codewiki-外部文档知识抽取-请导入外部文档并从中抽取结构化知识。采用-2.md
  scene: 文档去重
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:34:59+00:00
stale_after: '2027-09-05'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:34Z'
---

## 事实

2026-09-05 新建 `codewiki/src/doc_similarity.py` 做「同一文档不同版本」的内容相似度判定，接入 ingest_source 的 L1 闸门。设计要点：

- 正文按 shingle（中文按字 3-gram / 英文按词）做 MinHash bottom-k sketch（`_SKETCH_K=128`），sketch 存字符串，比较用列表直接算 Jaccard；分类阈值只决定告警强度（`SIMILAR_HIGH=0.50` / `SIMILAR_LOW=0.25`）。
- **标题从正文 shingle 中剔除**（骨架已单独用），否则共用标题的短文档正文 Jaccard 虚高（同标题不同内容实测被误判 0.836 high）。
- 评分 **body 主导、骨架（H1–H6 标题集合 Jaccard）温和加成最多 +0.1**；length_compatibility 后因无调用者被删。
- 实测判别：改版 0.66–1.0 high；无关/模板文档 <0.1 none；性能约 0.03s/文档。
- 二进制/非 md 文档无文本提取器，降级放行不做指纹。

## 试错沉淀

- SimHash 余弦**基线不是 0**：同领域不相关文档也有 0.55 左右（`1 - d/64` 把随机无关文档放在 0.5），测的是「词方向接近」而非「内容重合」，对判同源太粗。
- 骨架信号对小文档过敏感（只有 1 个 H1 的两篇不同纪要 skeleton Jaccard=1.0 直接定分）、对模板文档误伤（年度报告 2024/2025 同骨架被判 0.97 high）——所以骨架只能温和加成。
