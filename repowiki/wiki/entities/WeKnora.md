---
title: WeKnora
type: Entity
description: 腾讯开源的企业级 LLM 知识管理框架：RAG 问答 + ReAct 推理 + 自动 Wiki 一体化
generated:
  by: codewiki/5.2.0
  at: 2026-08-03 04:55:04+00:00
stale_after: '2027-02-22'
aliases:
- 维娜拉
- WeKnora 框架
- Tencent WeKnora
sources:
- id: README_CN
  resource: raw/sources/README_CN.md
  title: WeKnora（腾讯开源企业级知识库平台）中文 README，用于测试两阶段知识提取流程
  last_modified: 2026-08-03
- id: README_CN_2.0
  resource: raw/sources/README_CN_2.0.md
  title: WeKnora 中文 README v0.8.0（README_CN_2.0）
  last_modified: 2026-09-05
metadata:
  source_refs: ["README_CN", "README_CN_2.0"]
  chunk_refs: ["README_CN:59", "README_CN:304-307", "README_CN:61", "README_CN:63", "README_CN:227-231", "README_CN:186-199", "README_CN:157", "README_CN:158", "README_CN:165-167", "README_CN:170-172", "README_CN:175-181", "README_CN:233-235", "README_CN:237-243", "README_CN:147", "README_CN:135", "README_CN_2.0:62", "README_CN_2.0:58", "README_CN_2.0:197", "README_CN_2.0:63", "README_CN_2.0:65", "README_CN_2.0:157"]
status: stable
verified:
- by: human:wangbao
  at: '2026-08-25T16:48:14Z'
---
# WeKnora

WeKnora（维娜拉）是腾讯开源的、基于大语言模型（LLM）的知识管理框架，专为企业级文档理解、语义检索与智能推理场景打造 [^src:README_CN:59]。项目基于 MIT 协议发布，可自由使用、修改与分发，但需保留原始版权声明 [^src:README_CN:304-307]。

## 核心能力

框架围绕三大核心能力构建 [^src:README_CN:61]：

- **[RAG](../concepts/RAG.md) 快速问答**：基于知识库的日常知识查询
- **[ReAct Agent 智能推理](../concepts/ReActAgent.md)**：自主编排知识检索、MCP 工具与网络搜索，完成复杂多步任务
- **[Wiki模式](../concepts/Wiki模式.md)**：Agent 从原始文档中自治生成相互链接的 Markdown 知识库与可视化知识图谱

## 关键特性

- 多源数据接入：飞书 / Notion / 语雀 / RSS 自动同步，覆盖 PDF、Word、图片、Excel 等十余种文档格式 [^src:README_CN:63]
- 企业级多空间 [空间RBAC](../concepts/空间RBAC.md)：四级角色矩阵 + 资源归属 + 空间审计日志 [^src:README_CN:61]
- 网站嵌入 Widget、权限范围 API Key 与 Principal 模型、每空间多实例存储后端 [^src:README_CN:61]
- 全流程模块化：大模型、向量数据库、存储等组件均可灵活替换，支持本地与私有云部署，数据完全自主可控 [^src:README_CN:63]
- 可观测性：集成 [Langfuse](Langfuse.md) 追踪 Agent 运行、Token 消耗与任务流水线 [^src:README_CN:63]
- [文档知识图谱](../concepts/文档知识图谱.md)：将文档转化为知识图谱，为索引和检索提供结构化支撑 [^src:README_CN:227-231]

## v0.8.0 新增能力

v0.8.0 引入以下核心能力 [^src:README_CN_2.0:62]：

- **[[技能目录与沙箱运行时]]**：会话级常驻 Docker / E2B / Cube 后端，按空间配置网络策略；移除 Local 宿主机进程后端；Docker 需显式开启；空间技能目录从 ClawHub / SkillHub / git / zip 安装，按沙箱快照、实时进度、文件浏览/编辑、个人与空间环境变量
- **[[跨会话长期记忆]]**：profile / preference / fact / task / interest，自动抽取需确认，`search_memory`
- 进程内 **anydoc** Office 解析（Go 进程内解析 Office 文档） [^src:README_CN_2.0:58]
- 官方 [[DeepSeekHarness插件|DeepSeek Harness 插件]] `@wxg-prc-cpg/dsh-weknora` [^src:README_CN_2.0:197]
- GitLab 与腾讯 IMA 数据源、LiteLLM、Exa 与 Metaso 网络搜索、XMind 解析 [^src:README_CN_2.0:62]

另在 v0.7.x 演进中提供 [[分块编辑与版本历史]]（可视化编辑检索分块、逐版本 diff 与回滚、自动重建索引） [^src:README_CN_2.0:63]、权限范围 API Key 与 Principal 模型（能力级授权 + 按 KB 限制） [^src:README_CN_2.0:65] 与每空间多实例存储后端 [^src:README_CN_2.0:157]。

## 部署方式

依赖 Docker 与 Docker Compose；`git clone` 后配置 `.env`，`docker compose up -d` 启动核心服务，访问 http://localhost 使用 [^src:README_CN:186-199]。支持本地 / Docker / Kubernetes (Helm) 部署与私有化离线部署 [^src:README_CN:157]。界面形态包括 Web UI、RESTful API、`weknora` 命令行、Chrome Extension、网站嵌入 Widget 与微信小程序 [^src:README_CN:158]。

## 生态与集成

配套 Chrome 插件（网页内容一键采集） [^src:README_CN:165-167]、微信小程序 [^src:README_CN:170-172]、[ClawHub Skill](ClawHubSkill.md) [^src:README_CN:175-181] 与配套 MCP 服务器 [^src:README_CN:233-235]。WeKnora 同时是 [微信对话开放平台](微信对话开放平台.md) 的核心技术框架，可在公众号、小程序等微信场景中提供问答服务 [^src:README_CN:237-243]。IM 集成覆盖企业微信 / 飞书 / Lark / QQBot / Slack / Telegram / 钉钉 / Mattermost / 微信 [^src:README_CN:147]，检索层支持 BM25、Dense、GraphRAG 等 [混合检索策略](../concepts/混合检索策略.md) [^src:README_CN:135]。

## 相关页面

[RAG](../concepts/RAG.md) · [ReActAgent](../concepts/ReActAgent.md) · [Wiki模式](../concepts/Wiki模式.md) · [Langfuse](Langfuse.md) · [空间RBAC](../concepts/空间RBAC.md) · [文档知识图谱](../concepts/文档知识图谱.md) · [混合检索策略](../concepts/混合检索策略.md) · [微信对话开放平台](微信对话开放平台.md) · [ClawHubSkill](ClawHubSkill.md)
