---
title: MCP-Server薄壳架构与参数约定
type: Scenario
description: MCP 薄壳分层、session_id 隐式约定、output_dir 解析单点、索引重建陷阱、doctrine 注入通道
generated:
  by: codewiki/5.3.0
  at: 2026-08-18 01:51:25+00:00
stale_after: 2026-11-16
aliases:
- MCP-Server薄壳架构与参数约定
status: stable
metadata:
  summary: session_id 隐式参数约定；query_wiki 索引重建性能陷阱；doctrine 唯一注入通道；YAML 静默回退日志修复
  heat: 3
  source_notes:
  - notes/2026-08-03-mcp-工具-schema-不声明-session-idhandler-隐式读取.md
  - notes/2026-08-26-handle-query-wiki-在-session-存在时每次查询都全量重建检索索引.md
  - notes/2026-08-26-load-project-checklist-对-yaml-损坏静默回退-none-无日志难排查.md
  - notes/2026-08-25-doctrine-不会自动注入-agent-上下文唯一通道是-query-wikimodeoverview.md
  - notes/2026-08-25-知识摄入到自动检索链路ingest-note-自动写索引close-session-兜底终态.md
---
## 工作场景
codewiki/mcp/ 包的架构分层与工具调用约定。适用于新增/修改 MCP 工具、重构 server 层、排查工具参数与路径解析问题、理解 doctrine 注入机制。

## 适用条件
开发新工具、修改 output_dir/session 解析、agent 侧调用本项目 MCP 工具、排查检索/doctrine 注入问题。

## 核心 SOP
1. 新增工具只动两处：tools/<x>.py 实现 handler + registry.py 注册 schema 与 handler_path——薄壳架构：server.py 只留 list_tools/call_tool/main，prompts/resources 各自独立 register。
2. session_id 是隐式参数：registry.py 的 inputSchema **不声明** session_id，handler 内直接 `arguments.get("session_id")` 读取。新增/修改工具 schema 时不要声明 session_id；改 schema 前先对照同类既有工具的写法。
3. output_dir 解析统一走 resolve_workspace 单点，优先级：显式 output_dir > 显式 repo_path 派生（rp/repowiki）> session.output_dir——纯解析不 mkdir；抛 ValueError 依赖 dispatch 统一兜底。
4. agent 侧调用工具先读工具描述确认参数名：如 get_prompt 的参数是 prompt_type 不是 name——描述先于猜测。
5. 同一约定可在两个载体：MCP prompt（静态常驻注入）与 AGENTS.md（按需可查询）——改约定要同步两处。
6. 写测试/smoke 不碰真实仓库：用隔离仓库路径避免污染 .codewiki/analysis_cache.db。
7. doctrine 不会自动注入 Agent 上下文：唯一通道是 query_wiki(mode='overview')（读 wiki/doctrine.md 截断 1300 字符）。SessionStart hook 已补 _load_doctrine 注入正文（缺失/超 20KB 优雅降级）；AGENTS.md 指令是软约束，与任务提示竞争时常落败。
8. handle_query_wiki 在 session 存在时每次查询都全量重建检索索引（DELETE 三表重建且无锁）——这是评审工具卡顿深层根因。并行化需三件套：预热一次索引 → 查询走 skip_index_build → 再并行 collector。
9. load_project_checklist 等配置加载函数对 YAML 损坏必须打 logger.warning（带文件路径与异常原因），不可静默回退 None——R-07 已修复此模式。

## 判断逻辑
- output_dir 优先级历史存在三派，是行为分裂源；新代码不再引入局部解析实现。
- dispatch() 已有统一异常兜底，handler 内抛异常是安全契约。
- 行为数据存储选址看生命周期/消费点/可移植性/git 语义。
- 索引重建触发条件过宽（session 存在即重建）应复用 freshness 判断避免重复重建。

## 禁忌与反模式
- 不要在 inputSchema 中声明 session_id（违反项目隐式参数约定）。
- 不要复制粘贴 _resolve_output_dir 到各工具。
- 不要绕过 dispatch 直接 import handler 手工组装参数。
- 不要假设 AGENTS.md 中的指令会被 Agent 可靠执行（软约束）。
- 不要让配置加载函数静默吞掉异常（必须有日志通道）。

## 关键事实依据
- registry.py 约 85% 是 schema（已知成本，改一工具跳两处）。
- doctrine 注入已通过 SessionStart hook 补强（_load_doctrine），但 query_wiki(mode='overview') 仍是主通道。
- 索引全量重建无条件 DELETE 三表，并发调用产生数据竞争。
