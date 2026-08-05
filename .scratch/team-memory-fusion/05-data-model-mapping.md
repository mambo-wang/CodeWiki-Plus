status: resolved
type: research
title: 数据模型与记忆分层（L0-L3/Skill/Asset/ACL）映射成本
body: |
  评估把 Team-Agent-Memory 的记忆数据模型（L0-L3 分层、Skill 资产、资源/Asset、ACL 用户隔离）映射到 CodeWiki-CN 概念的成本。

  ## 调研要点
  - L0-L3（对话/事件/语义/用户画像）分层：CodeWiki-CN 现有哪些可承载，缺哪些。
  - Skill 资产：与 CodeWiki-CN 的 `repowiki/` 笔记、`AGENTS.md` 经验的对应关系。
  - 资源/Asset（文件/代码/图片）与 ACL：是否需新增存储与权限层。
  - 映射成本是否因融合形态（内置 vs 桥接）不同而差异巨大。

## 交付
- 数据模型映射表：Team-Agent-Memory 概念 -> CodeWiki-CN 现有 / 需新增。
- 各概念落地成本分级（低/中/高）及关键阻碍。

Blocked by: #1, #2

# 结论（resolved）

基于 01/02 的事实，TAM 记忆模型到 CodeWiki-CN 的映射如下：

| TAM 概念 | CodeWiki-CN 现状 | 映射成本 | 关键阻碍 |
|---|---|---|---|
| L0 对话(原始 turns) | 无 | 高 | 需新增对话采集与存储层（CodeWiki-CN 当前不接对话流） |
| L1 语义原子(事实/偏好/约束/事件) | `notes/`(lesson/decision) 近似 | 中 | 现有 note 无"原子"粒度与自动抽取管线；需接 L0→L1 蒸馏 |
| L2 场景知识块 | `wiki/modules/` 近似 | 低-中 | 可复用 CodeWiki 文档生成，但需按场景聚类而非按模块 |
| L3 用户/团队画像 | 无 | 高 | 需新增用户/team 实体与持久画像 |
| Skill 资产 | `.codebuddy/skills/`(IDE 资源, 非产出) | 中-高 | 需建 Skill 注册/检索/沉淀体系，与现有 IDE skills 边界需厘清 |
| 资源/Asset(文件/代码/图片) | `repowiki/` 产物(文件) | 低 | 元数据注册可复用现有 symbol_map/source_registry |
| ACL/用户隔离 | 无 | 高 | 需新增多租户/角色模型，当前 scope 仅是目录过滤 |
| 透明代理注入(MemoryProxy) | 无 | 中 | 需加 LLM 调用中间件把记忆拼入 system prompt |

**形态差异**：
- 桥接形态下，映射成本几乎为零——CodeWiki-CN 不承载 TAM 数据模型，只做**写入入口**（`ingest_note`→TAM L3/Skill）与**读取入口**（TAM MemoryProxy→CodeWiki `query_wiki` 上游）。
- 内置形态下，L0/L3/ACL/Skill 四项需从零构建（高成本），L1/L2/Asset 可复用现有文档/笔记体系（中低成本）。

**最大阻碍**：L0 对话采集层与 ACL 多租户层在 CodeWiki-CN 完全缺失，是内置形态的主要工程量来源。
