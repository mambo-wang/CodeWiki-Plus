调研并修复了 capture_conversation 的 task_id 断链：根因是绑定文件（.meta/task_bindings/）不被自动消费，文档声称「绑定被 capture 消费」但实现无自动衔接。已落地 _resolve_task_from_binding 回退逻辑（放在 _content_hash 之前）+ task_source 字段 + 2 个测试（test_task_manager.py 17 passed，test_ide_hook_capture.py 21 passed）。采用宽松语义（绑定存在即盖章，不校验任务 status）。后续可选：若需「只认 active 任务」，在 _resolve_task_from_binding 里加 tasks/.index.json 的 status 查询。

本次会话修复了 task_session_start.py hook 的两个缺口：①新增「硬性执行顺序」段（会话第一个动作必须是弹任务关联框，严禁先探索代码/先回答）；②直接把 active 任务标题+task_id 注入 additionalContext，避免 agent 再自己 list_tasks。改动同时落在源副本 codewiki/hooks/ 与项目副本 .codebuddy/hooks/ 两个文件（内容一致），确保随包分发到所有用户。

用户通过 @command://codewiki/文档质量审计 命令发起全量 Wiki 质量审计请求，流程被任务引导打断，尚未开始执行 lint_wiki。

已把 hook 支持范围写入 README 中英两处「团队记忆融合→关键约束」：措辞「仅接线支持 CodeBuddy」（`.codebuddy/settings.json`），底层 `_ide_hook.py` 已做 CodeBuddy/Claude-Code 兼容的事件载荷解析，其他 IDE（如 Claude Code）接线尚未提供。

用户通过 @command://codewiki/文档质量审计 命令发起一次全量 Wiki 质量审计（lint_wiki checks=all，5 步：lint → 按严重度处理 → 修复 → flag_issue → 验证），会话被任务引导流程打断，审计尚未开始执行，待后续继续。

用户提出「开始新对话触发选择任务后，query_wiki 和蒸馏操作可放 subagent 执行、别影响正常使用」，该决策已落地：创建 .codebuddy/agents/distill-worker.md，hook/AGENTS.md/prompts.py 同步「补蒸馏委托 subagent、不阻塞回答」措辞。

撰写《CodeWiki-Plus系列7：Subagent机制详解-上下文隔离与专业化分工》文档（docs/articles/），以 distill-worker 的创建与使用为例介绍 subagent 机制与上下文隔离/不阻塞好处。

会话启动补蒸馏委托 subagent 的决策已完整落地：task_session_start.py 双副本（codewiki/hooks + .codebuddy/hooks）、prompts.py（_TASK_MEMORY_AGENTS_SECTION + _prompt_task_workflow）、AGENTS.md、README.md 同步，新建 .codebuddy/agents/distill-worker.md，test_task_session_start.py 新增 4 条断言、friction hint 断言兼容新文案，全部 47 个测试通过。

已撰写 subagent 机制介绍文档：docs/articles/CodeWiki-Plus系列7：Subagent机制详解-上下文隔离与专业化分工.md（含 distill-worker 完整实战案例与 Mermaid 时序图）。

本任务 5 条待确认记忆已获用户确认落盘到 repowiki/tasks/产品维护/memories.md，pending 区已清空。

distill-worker 源码化已完成：codewiki/agents/distill-worker.md 为权威版本，hook 启用（init 或 team-memory-hook）时自动拷贝到项目 .codebuddy/agents/，pyproject.toml package-data 已加入 agents/*.md。

待验证点：distill-worker.md 的 frontmatter（toolsMCP 字段名、agentic 模式 Task spawn）依赖 IDE 对 subagent 定义的解析，建议下次新会话观察 hook 是否成功把蒸馏委托出去。

文档质量审计（lint_wiki 全量检查）曾被任务引导打断、用户明确搁置（"不用"），后续如需可重新发起。

多 IDE hook 自动检测接线功能已开发完成并发布 v5.4.0：CodeBuddy/Qoder/Claude Code 三类 IDE 自动检测接线，codewiki install-hooks CLI + IDE 注册表驱动；发布经 PyPI（twine --disable-progress-bar）与 GitHub Release（Invoke-RestMethod）。

### 2026-08-24 23:13

完成 repowiki 增量更新 Wiki：lint 110 问题全部清理（stale_refs 49 error、missing_aliases 30、orphan 7 清零；no_outlinks 56、superseded 46 确认为内容级/提示性 info）。

### 2026-08-24 23:13

修复 capture_conversation.py：_unq 提升模块级，_rebuild_index 与 pending_raws_by_task 统一去引号，修复 .index.json task_id 带字面引号 bug。

### 2026-08-24 23:13

lint_wiki 新增 fix=true 参数：stale_refs 全来自 index.md 索引失效时自动 rebuild_index 自愈，新增 test_lint_fix.py，registry schema 同步更新。

### 2026-08-24 23:13

修复生成路径与 patch 路径不一致：_okf_patch_defaults 补 aliases 默认键（与 _build_okf_frontmatter 对齐），存量页面用 backfill_aliases.py 回填。

### 2026-08-24 23:13

test_core_modules_import 因第三方库 caw 在 Windows 上 import fcntl 失败，测试加平台跳过保护（Linux 保留完整测试）。

### 2026-08-24 23:13

推送 develop（2 commits）期间发现对话归档含 PyPI token 已脱敏 amend；建议吊销 token、删除 raw 中的 token、清理 scripts/ 临时文件。全量 pytest 341 passed 2 skipped。

### 2026-08-24 23:13

完成 repowiki 增量更新 Wiki：lint 110 问题全部清理（stale_refs 49 error、missing_aliases 30、orphan 7 清零；no_outlinks 56、superseded 46 确认为内容级/提示性 info）。

### 2026-08-24 23:13

修复 capture_conversation.py：_unq 提升模块级，_rebuild_index 与 pending_raws_by_task 统一去引号，修复 .index.json task_id 带字面引号 bug。

### 2026-08-24 23:13

lint_wiki 新增 fix=true 参数：stale_refs 全来自 index.md 索引失效时自动 rebuild_index 自愈，新增 test_lint_fix.py，registry schema 同步更新。

### 2026-08-24 23:13

修复生成路径与 patch 路径不一致：_okf_patch_defaults 补 aliases 默认键（与 _build_okf_frontmatter 对齐），存量页面用 backfill_aliases.py 回填。

### 2026-08-24 23:13

test_core_modules_import 因第三方库 caw 在 Windows 上 import fcntl 失败，测试加平台跳过保护（Linux 保留完整测试）。

### 2026-08-24 23:13

推送 develop（2 commits）期间发现对话归档含 PyPI token 已脱敏 amend；建议吊销 token、删除 raw 中的 token、清理 scripts/ 临时文件。全量 pytest 341 passed 2 skipped。

### 2026-08-24 23:14

完成 repowiki 增量更新 Wiki：lint 110 问题全部清理（stale_refs 49 error、missing_aliases 30、orphan 7 清零；no_outlinks 56、superseded 46 确认为内容级/提示性 info）。

### 2026-08-24 23:14

修复 capture_conversation.py：_unq 提升模块级，_rebuild_index 与 pending_raws_by_task 统一去引号，修复 .index.json task_id 带字面引号 bug。

### 2026-08-24 23:14

lint_wiki 新增 fix=true 参数：stale_refs 全来自 index.md 索引失效时自动 rebuild_index 自愈，新增 test_lint_fix.py，registry schema 同步更新。

### 2026-08-24 23:14

修复生成路径与 patch 路径不一致：_okf_patch_defaults 补 aliases 默认键（与 _build_okf_frontmatter 对齐），存量页面用 backfill_aliases.py 回填。

### 2026-08-24 23:14

test_core_modules_import 因第三方库 caw 在 Windows 上 import fcntl 失败，测试加平台跳过保护（Linux 保留完整测试）。

### 2026-08-24 23:14

推送 develop（2 commits）期间发现对话归档含 PyPI token 已脱敏 amend；建议吊销 token、删除 raw 中的 token、清理 scripts/ 临时文件。全量 pytest 341 passed 2 skipped。

### 2026-08-24 23:16

完成 task_bindings 绑定文件生命周期改造：capture_conversation 落盘成功后自动删除绑定文件（一次性消费凭证），supersede 时继承旧 task_id 防丢归属，显式传 task_id 不消费绑定。

### 2026-08-24 23:16

tests/test_task_manager.py 新增 2 个测试（test_capture_deletes_binding_after_successful_write、test_explicit_task_id_does_not_consume_binding），54 个测试全过。

### 2026-08-24 23:16

同步更新 AGENTS.md 任务记忆段落与 codewiki/mcp/prompts.py 的 task-workflow 提示词，说明绑定生命周期语义。

### 2026-08-24 23:17

完成 task_bindings 绑定文件生命周期改造：capture_conversation 落盘成功后自动删除绑定文件（一次性消费凭证），supersede 时继承旧 task_id 防丢归属，显式传 task_id 不消费绑定。

### 2026-08-24 23:17

tests/test_task_manager.py 新增 2 个测试（test_capture_deletes_binding_after_successful_write、test_explicit_task_id_does_not_consume_binding），54 个测试全过。

### 2026-08-24 23:17

同步更新 AGENTS.md 任务记忆段落与 codewiki/mcp/prompts.py 的 task-workflow 提示词，说明绑定生命周期语义。
