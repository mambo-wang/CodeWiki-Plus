# AGENTS.md — {{WORKSPACE_NAME}} 工作区约定（集中式布局）

本仓库是产品线的 harness 主仓库。业务代码仓以独立 clone 方式挂在本仓库子目录下（git 层面完全隔离，非 submodule）。本工作区采用**集中式知识布局**：全部知识（产品级 + 各业务仓）统一存放在本仓 `repowiki/`，业务仓目录内没有 `repowiki/`。

## 工作区结构与检索路由（一跳）

`repowiki/` 是唯一知识库：`wiki/modules/<业务仓目录>/` 按仓分区存放代码结构文档；`wiki/entities/`、`wiki/concepts/`、`wiki/comparisons/`、`wiki/queries/`、`wiki/sources/`、`notes/` 等为共享池，页面以 frontmatter `repo:`/`repos:` 标注适用仓（无标注＝产品线全局，对所有仓生效）。

**检索（一跳）**：

```
query_wiki(query=...)                            # 覆盖产品级 + 全部业务仓
query_wiki(query=..., repo=<业务仓目录>)          # 适用于该仓的知识＝该仓分区 + 带该仓标 + 全局
query_cross_service(workspace_path=<harness根目录>)
```

导航入口页：`repowiki/wiki/repo-map.md`（仓清单与分区索引）。

## 提交纪律（结构性红线）

- 业务代码只在业务仓内提交；**全部知识产物在本仓提交**——集中式布局下业务仓是纯代码仓。
- 本仓 `.gitignore` 已排除全部业务仓目录。若在本仓 `git status` 中看到业务仓目录出现，说明 `.gitignore` 失效或业务仓被错误 clone 进来——**立即停下排查，绝不可 `git add`**。
- 业务仓自身的编码约定仍遵循该业务仓自己的 AGENTS.md（其知识库引用块已被移除），本文件不覆盖。

## 分支策略

本仓分支固定、变动不频繁；各业务仓自由选择主线或个人开发分支，互不感知、无需同步。不要在本仓为业务仓的分支做任何记录（没有指针、没有 manifest 锁定）。

## 知识写入路由

| 知识类型 | 写入位置 |
|---------|---------|
| 产品概述、跨仓架构、全局编码规范 | `repowiki/` 相应页型目录，**不打** `repo:` 标（全局） |
| 单个业务仓的业务概述 | `repowiki/wiki/repo-map.md` 对应小节 |
| 模块文档（代码结构） | `repowiki/wiki/modules/<业务仓目录>/` |
| entities/notes/pitfall/decision 等 | 共享池（`wiki/entities/`、`notes/`…），frontmatter `repo:`/`repos:` 标适用仓 |
| 跨服务调用拓扑 | `analyze_workspace(workspace_path=<harness根>)` 产出（`wiki/overview.md` + `.meta/`） |

原则：说一个仓的内部实现 → 该仓分区或带该仓标；说多个仓或产品线 → 全局共享层。

## 新业务仓接入清单

优先使用 CodeWiki MCP 工具 `add_workspace_repo(url=<克隆URL>)` 一步完成登记（目录名自动取仓库名）；集中模式下会自动建 `repowiki/wiki/modules/<仓名>/` 分区骨架，且**不在业务仓内建 `repowiki/`**。手工接入时须同步三处：

1. `bootstrap.ps1` / `bootstrap.sh` 的 repos 登记表增加仓库目录名与 URL
2. `.gitignore` 增加一行 `/<业务仓目录>/`
3. `repowiki/wiki/repo-map.md` 补充该仓小节（职责、分区路径、检索方式）
