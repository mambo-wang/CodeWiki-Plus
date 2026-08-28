# AGENTS.md — {{WORKSPACE_NAME}} 工作区约定

本仓库是产品线的 harness 主仓库。业务代码仓以独立 clone 方式挂在本仓库子目录下（git 层面完全隔离，非 submodule）。Agent 在本工作区内工作时必须遵守以下约定。

## 工作区结构与检索路由（两跳）

知识分层存放，检索按两跳路由执行：

**第一跳（产品级）**：先查本仓 repowiki，获取产品概述、业务仓导航、跨仓约定。

```
query_wiki(query=..., output_dir=<harness根>/repowiki)
```

导航入口页：`repowiki/wiki/repo-map.md`（各业务仓职责、目录、repowiki 路径一览）。

**第二跳（仓库级）**：命中某个业务仓后，下钻到该业务仓自己的 repowiki 获取模块/实体/笔记等深度知识。

```
query_wiki(query=..., output_dir=<harness根>/<业务仓目录>/repowiki)
```

**跨服务调用关系**：直接对工作区根做多仓分析检索。

```
query_cross_service(workspace_path=<harness根目录>)
```

## 提交纪律（结构性红线）

- 业务代码只在业务仓内提交；本仓只提交 harness 资产（repowiki 产品级知识、约定、脚本）。
- 本仓 `.gitignore` 已排除全部业务仓目录。若在本仓 `git status` 中看到业务仓目录出现，说明 `.gitignore` 失效或业务仓被错误 clone 进来——**立即停下排查，绝不可 `git add`**。
- 业务仓内部的工作流遵循该业务仓自己的 AGENTS.md，本文件不覆盖。

## 分支策略

本仓分支固定、变动不频繁；各业务仓自由选择主线或个人开发分支，互不感知、无需同步。不要在本仓为业务仓的分支做任何记录（没有指针、没有 manifest 锁定）。

## 知识写入路由

| 知识类型 | 写入位置 |
|---------|---------|
| 产品概述、跨仓架构、业务仓间协作约定 | 本仓 `repowiki/`（`ingest_note` / `write_doc_file`） |
| 单个业务仓的业务概述 | 本仓 `repowiki/wiki/repo-map.md` 对应小节 |
| 模块文档、pitfall、decision、lesson 等深度知识 | **业务仓自己的** `repowiki/` |
| 跨服务调用拓扑 | `analyze_workspace(workspace_path=<harness根>)` 产出，位于本仓 `repowiki/`（overview.md + `.meta/`） |

原则：wiki 与它描述的代码同仓演进。描述某业务仓内部实现的知识绝不写入本仓。

## 新业务仓接入清单

优先使用 CodeWiki MCP 工具 `add_workspace_repo(url=<克隆URL>)` 一步完成登记（目录名自动取仓库名）；手工接入时须同步三处：

1. `bootstrap.ps1` / `bootstrap.sh` 的 repos 登记表增加仓库目录名与 URL
2. `.gitignore` 增加一行 `/<业务仓目录>/`
3. `repowiki/wiki/repo-map.md` 补充该仓小节（职责、repowiki 路径、检索方式）
