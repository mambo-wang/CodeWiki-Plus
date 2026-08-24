---
title: MCP-Server薄壳架构与参数约定
type: Scenario
description: MCP 薄壳分层、新增工具两处落点、output_dir 解析单点收敛、工具参数先读描述纪律
generated:
  by: codewiki/5.3.0
  at: 2026-08-18 01:51:25+00:00
stale_after: 2026-11-16
aliases:
- MCP-Server薄壳架构与参数约定
status: stable
metadata:
  source_notes:
  - notes/2026-08-15-mcp-server-层架构摩擦点扫描结论7-项按严重度排序.md
  - notes/2026-08-15-mcp-server-薄壳化架构serverpy-职责拆分到-registrypromptsresourcestools.md
  - notes/2026-08-15-output-dir-解析收敛方案resolve-workspace-单点-优先级统一.md
  - notes/2026-08-15-get-prompt-工具参数是-prompt-type-而非-name.md
  - notes/2026-08-24-mcp-prompt-与-agentsmd-是同一约定的两个载体静态常驻注入-vs-按需可查询.md
  - notes/2026-08-24-smoke-test-用临时-output-dir-污染真实仓库缓存导致落盘错位.md
  - notes/2026-08-24-retrieval-statsdb-放-repowikimeta-而非-codewiki-的四个理由.md
  - notes/2026-08-24-telemetry-采用-per-user-jsonl-文件零冲突设计的承重墙.md
  - notes/2026-08-24-测试多-helper-各写一次-jsonl-会互相全量覆盖须-append-merge-且不依赖固定-user-文件名.md
  - 2026-08-24-mcp-prompt-与-agentsmd-是同一约定的两个载体静态常驻注入-vs-按需可查询.md
  - 2026-08-24-smoke-test-用临时-output-dir-污染真实仓库缓存导致落盘错位.md
  - 2026-08-24-retrieval-statsdb-放-repowikimeta-而非-codewiki-的四个理由.md
  - 2026-08-24-telemetry-采用-per-user-jsonl-文件零冲突设计的承重墙.md
  - 2026-08-24-测试多-helper-各写一次-jsonl-会互相全量覆盖须-append-merge-且不依赖固定-user-文件名.md
  summary: MCP prompt 与 AGENTS.md 双载体；smoke test 隔离仓库路径；行为数据存储选址与 per-user jsonl
  heat: 2
---
## 工作场景
codewiki/mcp/ 包的架构分层与工具调用约定。适用于新增/修改 MCP 工具、重构 server 层、排查工具参数与路径解析问题。

## 适用条件
开发新工具、修改 output_dir/session 解析、agent 侧调用本项目 MCP 工具。

## 核心 SOP
1. 新增工具只动两处：tools/<x>.py 实现 handler + registry.py 注册 schema 与 handler_path——薄壳架构：server.py 只留 list_tools/call_tool/main，prompts/resources 各自独立 register，server.py 不再是逻辑承载地。
2. output_dir 解析统一走 resolve_workspace 单点，优先级：显式 output_dir > 显式 repo_path 派生（rp/repowiki）> session.output_dir——「显式 > 可推导 > 缓存」最可预测，修复 stale path；纯解析不 mkdir；抛 ValueError 依赖 dispatch 统一兜底。
3. agent 侧调用工具先读工具描述确认参数名：如 get_prompt 的参数是 prompt_type 不是 name——此坑多次会话重复踩到，描述先于猜测。
4. 同一约定可在两个载体：MCP prompt（静态常驻注入，入口处即得）与 AGENTS.md（按需可查询、随文档更新）——改约定要同步两处，避免漂移。
5. 写测试/smoke 不碰真实仓库：analyze_repo 等工具用真实 REPO_PATH + 临时 output_dir 会污染 .codewiki/analysis_cache.db 缓存，导致后续落盘错位——测试一律用隔离仓库路径。

## 判断逻辑
- output_dir 优先级历史存在三派（session>od>rp / od>rp>session / od>session>rp），是行为分裂源；新代码不再引入局部解析实现。
- dispatch() 已有统一异常兜底（except Exception → {"error": ...}），handler 内抛异常是安全契约，零 try/except。
- 行为数据存储选址看生命周期/消费点/可移植性/git 语义：retrieval_stats.db 放 repowiki/.meta（随仓库走）而非 .codewiki（机器本地）；telemetry 用 per-user jsonl 零冲突设计，单文件方案有并发全量覆盖等三个致命问题。

## 禁忌与反模式
- 不要复制粘贴 _resolve_output_dir 到各工具（历史曾有 7 处同构实现）。
- 不要绕过 dispatch 直接 import handler 手工组装参数（跳过 schema 校验，行为易与 MCP 路径漂移）。
- 不要依赖 find_or_restore 的隐式 session 重建副作用（可能返回 stale path）；显式传 output_dir 可避开。

## 关键事实依据
- registry.py 约 85% 是 schema（已知成本，改一工具跳两处）。
- 模块文档若仍描述「server.py 里的 _prompt_*/_write_*metadata」即为过时（已迁出）。
- 测试种子数据写入要 append-merge 共享 helper、不依赖固定 user 文件名——多 helper 各写一次会互相全量覆盖。