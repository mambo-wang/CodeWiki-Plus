---
type: architecture
title: "Home Repo 模式与多仓工作区同构：知识工程 vs 共享治理"
tags: ["architecture"]
aliases: ["Home Repo", "home repo pattern", "Matt Pocock", "多仓工作区", "harness 仓", "中心仓", "共享 skills 去重", "渐进披露", "竞品对比", "aihero"]
metadata:
  date: 2026-11-13
  confidence_level: weak
  task_id: 他山之石
  related_modules: ["MCP_Tools_Workspace"]
  source_ref: "The Home Repo Pattern, https://www.aihero.dev/the-home-repo-pattern (2026-11-12)；译文 opensource-research/articles/mattpocock-home-repo/translation.md"
  reason: "用户本会话批准归档为 draft，待 confirm_note 确认；结论已对 workspace_bootstrap.py 代码核对"
status: draft
author: wanderingbug
generated: { by: codewiki/5.16.7, at: 2026-11-13T06:59:42Z }
stale_after: 2027-11-13
---

## 背景
Matt Pocock《The Home Repo Pattern》（aihero.dev，2026-11-12）：中心仓集中放共享 skills/AGENTS.md/文档，用导航指针指向其他仓，所有 agent 会话从中心仓启动。对比本仓多仓工作区，定位异同与借鉴点。

## 核心内容
骨架同构：中心 harness 仓作会话入口；业务仓保持独立 git 仓（克隆进子目录+.gitignore，非 submodule，workspace_bootstrap.py:3）；导航指针 repo-map.md（:287）≈ AGENTS.md「Other Repos」；显式决策闸门（init_workspace 首选 layout，:728）≈ setup-prompt 批准前只读。

重心不同——Home Repo 解决「配置/导航去重」，本仓解决「跨仓知识工程」：
- 本仓更深：analyze_workspace 跨服务拓扑 + query_cross_service/query_wiki 结构化检索；登记表唯一事实源 + workspace.json 布局落盘 + 工具自动路由（:27，确定性簿记）；colocated 两跳/centralized 一跳。Home Repo 无需工具、纯 markdown 指针。
- Home Repo 更深：共享 skills「只放一处」去重（本仓按仓从包编译分发，不做用户自定义 skills 跨仓去重）；复用已有外部 checkout（本仓强制克隆进工作区）；规模策略（~20 仓 OK/~400 按领域渐进披露/上千走 marketplace，本仓 repo-map 平铺）。

## 原因
本仓 skills 随包版本化，与 Home Repo「用户自管 skills」不同问题域，共享去重不能照搬；确定性簿记是本仓 doctrine，Home Repo 信任 agent 解释自然语言指针。

## 影响范围
MCP_Tools_Workspace。可借鉴「共享 steering 去重」「规模渐进披露」，立项前须过本仓架构前提；本笔记仅定位存档，未做借鉴决策。
