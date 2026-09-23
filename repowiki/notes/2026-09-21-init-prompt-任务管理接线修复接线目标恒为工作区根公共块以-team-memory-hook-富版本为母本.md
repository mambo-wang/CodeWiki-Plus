---
type: decision
title: "init prompt 任务管理接线修复：接线目标恒为工作区根，公共块以 team-memory-hook 富版本为母本"
tags: ["codewiki", "decision"]
metadata:
  date: 2026-09-21
  confidence_level: weak
  source_session: "184920b147de4d1f9e2ce9a39d25a453"
  related_modules: ["MCP_Prompts", "MCP_Tools_Workspace"]
  severity: high
  source_ref: "conversations/conv-user_command-commands-codewiki-初始化单仓Wiki工作区-请为项目初始化-Wiki-工作区-560d5c.md"
  scene: "init prompt 任务管理接线修复"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.11.0, at: 2026-09-21T04:31:43Z }
stale_after: 2027-09-21
origin: conversation

---

## Background

2026-09-21 会话中用户发现：初始化单仓/多仓工作区后 AGENTS.md 未更新任务管理相关配置。经源码核对，两个 prompt 情况不同：单仓 `init-wiki` 其实有任务管理接线步骤，由 `enable_task_management` 参数门控（`codewiki/mcp/prompts.py:142`），false 时整块省略（`prompts.py:227-229`）；执行输出里的 `[no-change] AGENTS.md task-memory section present` 是幂等跳过（标记块已存在），不是没更新。多仓 `init-workspace` 则确实没有：prompt 正文（`prompts.py:263-292`）无任务管理/hook 接线步骤，`init_workspace` 工具写 AGENTS.md 时只写 Workspace Conventions + CodeWiki LLM Wiki 两个块（`codewiki/mcp/tools/workspace_workspace.py:587-594`），不写 `TEAM-MEMORY-TASK` / `ACTIVE-SETTLE` 块，也不拷 hook 脚本、不合并 settings.json。

## Decision

经用户确认落定的修复方案：

1. **提取公共块**：以 `_prompt_team_memory_hook` 步骤 2A 的**富版本为唯一母本**，抽成 `_task_management_wiring_steps(repo_path, capture_off)`（含 CLI 优先路径、手动兜底、TRAE 完整变体、AGENTS.md 标记块写入、三个模拟事件验证与反斜杠陷阱警告），三个调用点（init-wiki、init-workspace、team-memory-hook 2A）嵌入同一函数——单点收敛，根治两份手工维护副本的文本漂移。
2. **单仓 `init-wiki`**：`enable_task_management` 改为**默认启用**（opt-out）——无参/任意值渲染接线步骤，仅显式 `false/0/no/off` 跳过；拼错值（如 `ture`）宁可多接一次（幂等无害），不可静默跳过。
3. **多仓 `init-workspace`**：新增 `enable_task_management` + `capture` 门控参数（同构默认启用、同 opt-out 口径）；接线步骤插在「校验产物」之后作为新步骤 4（原「登记业务仓」顺延为 5）；full / clone-only / 直接补克隆三个分支都执行接线（幂等，属「重新同步」语义）。
4. **接线目标恒为工作区根（harness 仓）**：AGENTS.md（任务引导段、主动沉淀协议块的宿主）在工作区根，会话按 harness 模型本来就开在工作区根；centralized 下业务仓连 repowiki 都没有，colocated 下业务仓 repowiki 只装代码文档，任务记忆归工作区级——两种布局行为一致，无例外。**业务仓不接线，且不留「可在业务仓自行运行 install-hooks」的自救引导句**（引导句会诱导 Agent 在业务仓里跑 install-hooks，与原则自相矛盾）。
5. **`team-memory-hook` prompt 不动**（不加多仓守卫）。
6. **locales**：`zh.yaml` / `en.yaml` 同步更新两个 prompt 的参数描述（默认启用、opt-out 口径、工作区根原则）。
7. **测试**：`test_init_wiki_off_has_no_tier_note` 反转为三用例（无参默认开、显式 off 跳过、拼错值按默认开处理）；`test_hook_registry.py` 补 init-workspace 三用例（默认开含工作区根原则断言、显式 off 步骤编号回落、registry args 登记）。

实施完成，全量测试通过（1135 passed, 2 skipped）。

## Rationale

任务管理是工作区级能力，接线目标必须唯一（harness 仓），否则两条入口（init-workspace / team-memory-hook）行为不一致，缺口会从侧门漏回去；同构接线逻辑只留一份，避免副本间文本漂移（本次已实锤：init-wiki 版缺反斜杠陷阱警告，当天验证就踩了坑）。
