---
title: ClawHubSkill
type: Entity
description: WeKnora 发布在 ClawHub 平台上的技能：文档导入、混合检索与知识管理
generated:
  by: codewiki/5.2.0
  at: 2026-08-03 04:55:05+00:00
stale_after: '2027-02-22'
aliases:
- ClawHub Skill
- WeKnora ClawHub Skill
sources:
- id: README_CN
  resource: raw/sources/README_CN.md
  title: WeKnora（腾讯开源企业级知识库平台）中文 README，用于测试两阶段知识提取流程
  last_modified: 2026-08-03
metadata:
  source_refs:
  - README_CN
  chunk_refs:
  - README_CN:175-177
  - README_CN:177-181
status: stable
verified:
- by: human:wangbao
  at: '2026-08-25T16:48:14Z'
---
# ClawHub Skill

ClawHub Skill 是 [WeKnora](WeKnora.md) 发布在 ClawHub 平台上的技能（clawhub.ai/lyingbug/weknora） [^src:README_CN:175-177]。

## 能力

安装后可通过 WeKnora REST API 完成以下操作 [^src:README_CN:177-181]：

- **文档导入**：通过 Agent 上传文件、导入网页或写入 Markdown 知识
- **[[混合检索策略|混合检索]]**：在单个或多个知识库中进行向量 + 关键词混合搜索
- **知识管理**：以编程方式浏览、编辑和删除知识条目

## 相关页面

[WeKnora](WeKnora.md) · [[混合检索策略]]
