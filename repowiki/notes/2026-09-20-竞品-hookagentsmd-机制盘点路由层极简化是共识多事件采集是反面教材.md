---
type: lesson
title: "竞品 hook/AGENTS.md 机制盘点：路由层极简化是共识，多事件采集是反面教材"
tags: ["codewiki", "lesson"]
metadata:
  date: 2026-09-20
  confidence_level: weak
  task_id: 他山之石
  source_session: "1b5f06c022ab4dcd9dfabc02661535f2"
  related_modules: ["mcp/prompts", "cli/utils/ide_config", "hooks"]
  severity: medium
  source_ref: "conversations/conv-working_memory_content-The-following-is-the-existing-working-848ca6.md"
  scene: "hook/AGENTS.md 提示词优化调研"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.10.1, at: 2026-09-20T15:49:53Z }
stale_after: 2027-03-19
origin: conversation

---

## Background

2026-09-20 对 8 个曾调用过的项目（project-cairn、openwiki、better-harness、caveman、teamai-cli、claude-mem、hindsight、letta-code）做了 hook 与 AGENTS.md 用法调研，为 CodeWiki 的 AGENTS.md 托管块瘦身提供依据。决策已落 ADR-0015（`docs/adr/0015-agents-md-slim-and-channel-convergence.md`），本笔记保留盘点的原始事实供后续同类优化复用。

## 各项目机制要点

1. **project-cairn**：AGENTS.md 极简路由层（58 行）——阅读顺序 + 文档职责表（每文件一行角色 + 维护规则）+ 仲裁规则（topic notes > LOG 历史；未确认判断不得写成定论）。`CLAUDE.md` 只写一行 `@AGENTS.md`，多 IDE 读同一份规则，单事实源。
2. **openwiki**：根 AGENTS.md 仅 24 行，托管块声明「optional just-in-time context, not required startup reading」「Treat source code and tests as authoritative」「Do not hand-edit generated pages」——姿态低，只给路由不要求启动即读。
3. **better-harness**：AGENTS.md 定位为「routing and enforcement layer」；文档链接完整性由测试执法（`doc-link-graph.test.mjs` 强制所有 .md 相对链接可解析且从 SKILL.md 路由可达）；测试哲学条款：断言行为而非文本。
4. **caveman**：12 行路由 + `@./skills/.../SKILL.md` import 语法聚合，细节延迟加载。
5. **teamai-cli**：hook 定义降为 `HookDef[]` 数据（`src/builtin-hooks.ts:15-17`），同一 reconcile 引擎驱动内置与团队 hook；渲染输出用 `hooks-golden.test.ts` 逐字节钉死。针对捆绑 [Node](../../codewiki/src/be/dependency_analyzer/models/core.py) 缺 PATH 写包装脚本。
6. **claude-mem**（反面教材为主）：六事件全挂（Setup/SessionStart/UserPromptSubmit/PreToolUse/PostToolUse/Stop），每条命令内联 2000+ 字符 bash 做路径解析，不可测试不可移植。唯一可取：原生 `async: true` 声明式异步（`hooks.json:57`）。
7. **hindsight**：三事件极简接线，命令用宿主注入的 `PLUGIN_ROOT` 环境变量避免路径硬编码。
8. **letta-code**：git hook 层（非 IDE hook 层）pre-commit 校验记忆文件 frontmatter 保护字段，post-commit 镜像远端；commit-on-write 模型与 CodeWiki「知识随仓库版本化 + 确认闸门」方向相反。

## 明确不借

- claude-mem 六事件采集（SessionEnd + 主动沉淀已覆盖，多事件放大噪音）
- claude-mem 内联 bash 路径解析
- letta commit-on-write
- `async: true`（deferred：需真机验证 CodeBuddy 支持，现有 detached subprocess 已工作）

## Rationale

竞品对照实证了「AGENTS.md 应是路由层而非协议全文载体」：12-60 行是健康区间，CodeWiki 原数百行属超重；双通道（AGENTS.md 块 + SessionStart hook）重复注入违反单点收敛。下次做提示词/注入通道优化时直接从这份盘点出发，不必重新调研。
