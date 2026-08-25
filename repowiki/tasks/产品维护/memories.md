## 早期记忆（摘要）

## 产品维护任务早期记忆摘要

【已落地决策与实现】
- 任务记忆绑定机制：capture_conversation 的 task_id 依赖绑定文件消费，已加 _resolve_task_from_binding 回退逻辑（绑定存在即盖章，不校验任务 status）+ task_source 字段；task_bindings 为一次性消费凭证，supersede 继承旧 task_id。后续可选：若需「只认 active 任务」，在回退逻辑里查 tasks/.index.json 的 status。
- SessionStart hook 强化：task_session_start.py 新增「硬性执行顺序」（会话第一动作必须是任务关联弹框）并直接把 active 任务标题+task_id 注入 additionalContext；codewiki/hooks 源副本与 .codebuddy/hooks 项目副本同步维护。
- 补蒸馏委托 subagent：创建 .codebuddy/agents/distill-worker.md，hook 启用时自动从 codewiki/agents/distill-worker.md 权威版本拷贝到项目；AGENTS.md/prompts.py/README 同步措辞；不阻塞主 Agent 回答。
- 多 IDE hook 自动检测接线（v5.4.0）：CodeBuddy/Qoder/Claude Code 三类 IDE，codewiki install-hooks + IDE 注册表驱动；已发 PyPI 与 GitHub Release。
- README 措辞：hook 采集仅接线支持 CodeBuddy（.codebuddy/settings.json）；_ide_hook.py 已做 CodeBuddy/Claude-Code 事件载荷兼容。
- 蒸馏工具链修复：capture_conversation _unq 提升模块级、_rebuild_index 与 pending_raws_by_task 去引号（修 .index.json task_id 带字面引号 bug）；lint_wiki 新增 fix=true 自愈过期索引；_okf_patch_defaults 补 aliases 默认键并 backfill。
- 测试：test_core_modules_import 因 caw 在 Windows import fcntl 失败加平台跳过；全量 pytest 341 passed 2 skipped。
- 文档：已撰写 docs/articles/CodeWiki-Plus系列7（Subagent 机制详解）；repowiki lint 110 问题清理完毕。

【未决/待办】
- 文档质量审计（lint_wiki checks=all）曾被任务引导打断，用户明确搁置（「不用」），后续如需可重新发起。
- 待验证：distill-worker.md frontmatter（toolsMCP、agentic 模式）依赖 IDE 对 subagent 定义的解析，需在新会话观察 hook 是否成功把蒸馏委托出去。
- 安全：推送时发现对话归档含 PyPI token 已脱敏 amend；建议吊销 token、删除 raw 中的 token、清理 scripts/ 临时文件。

【历史坑/约定】
- Windows GBK 控制台编码会导致 CLI 输出与 twine 发布崩溃。
- GitHub API 直连被阻时用 PowerShell Invoke-RestMethod 走系统网络栈，token 从 git 凭据管理器提取。
- 对话归档原样保留用户密钥会被 GitHub 密钥扫描拦 push。
- 配置合并的 Python 坑：dict 浅拷贝污染原配置 + hooks.get(event, []) 未写回。
- 会话启动的 query_wiki/蒸馏等重操作委托 subagent 执行，避免阻塞用户正常使用。

> 原文归档于 memories-archive.md，截至 2026-08-25，共 24 条。

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
### 2026-08-24 22:33

用户发起代码图谱工具对标调研（CodeGraph/Grapify/CBM），结论：技术底座同源（tree-sitter 10 语言 + SQLite + transitive_impact），影响半径能力已有（analyze_impact 比 codegraph impact 更细）。确认 3 项真实差距并整理为 backlog：①P1 文件监听实时增量同步（watch 模式）②P1 git diff 驱动变更影响闭环（analyze_changes + 测试映射）③P2 代码符号全文/语义检索（FTS5 BM25，可选 embedding）。另含 2 项 P3 可选（死代码扫描、cytoscape 交互可视化）。已落盘 docs/代码图谱能力增强-Backlog.md（沿用 OKF Backlog 文档格式：背景/问题/方案/验收/影响面/优先级）。待用户决定实施顺序。

### 2026-08-24 22:49

需求细化：用户明确两个目标——①修改前按函数查上下游影响（analyze_impact 已覆盖，依赖图谱新鲜度=watch 模式）；②修改后按 commit 范围或工作区未提交变更分析影响。②的精度要求从文件级升级为函数级：git diff 行级解析（--unified=0 取变更行号）→ 组件 start_line/end_line 区间匹配定位变更函数（删除行回退旧版本解析）。backlog 第 2 项已拆分子项②（行级 diff 解析）+子项③（analyze_changes 工具，输入 since 或 worktree=true，含 untracked），验收标准同步更新。复用点：GitPython 已依赖、transitive_impact/resolve_files_to_components 已有。

### 2026-08-24 23:24

## analyze_changes 工具实现完成（Backlog 第 2 项子项②+③）

- 新增 codewiki/mcp/tools/change_analysis.py：`parse_unified_diff`（git diff --unified=0 行级解析，删除行 anchor 映射）、`collect_git_changes`（since=commit 范围 / worktree=暂存+未暂存+untracked）、`locate_changed_components`（变更行号→组件区间匹配）、`suggest_tests`（命名约定+文件系统检查）、`handle_analyze_changes`（transitive_impact 计算影响半径）
- registry.py 已注册 analyze_changes 工具（direction/max_depth/since/worktree 参数）
- tests/test_change_analysis.py 14 个测试全部通过（单元+集成）

## 踩坑记录（测试环境）

1. GitPython 3.1.50 Windows 上 `repo.index.add(".")` 会把 .git 内部文件加进 index 且路径带 ./ 前缀 → 测试 fixture 必须用显式文件列表 add
2. `Path.relative_to` 相同路径返回 Path('.')，`_repo_subdir` 需归一化为 ''，否则子目录过滤逻辑误杀所有路径（untracked 收集为空）
3. `ls-files --others --exclude-standard` 比 `Repo.untracked_files` 可靠（后者 Windows 上会返回已跟踪文件）

## 下一步

- Backlog 第 1 项：watch 模式（文件变更监听→增量影响分析）
- Backlog 第 2 项验收：真实仓库手动验证 analyze_changes（用本仓库的 worktree 变更试跑）

### 2026-08-25 00:26

## 2026-08-25：Backlog 第 1 项 watch 模式完成（24 测试全过）

- 新增 `codewiki/mcp/tools/watch.py`：RepoWatcher 后台轮询线程（纯 stdlib threading.Event.wait，间隔即去抖窗口，默认 2s、最小 1s）；`_incremental_refresh` 复用 handle_analyze_repo 增量管线（remove_by_file → skip_file_paths → builder 只解析变更文件 → 合并缓存 → 重算 leaf → batch_insert incremental）；`handle_watch_repo` MCP 工具（action=start/stop/status）；`attach_graph_stale` 供 impact/crosslink/component_list 附新鲜度提示（degraded/stopped/synced 三态）
- cache.py：_SRC_EXTS 补全 .pyx/.go/.php；新增 remove_file_fingerprints；**remove_by_file 增加 relative_path 列匹配**（相对路径删不掉旧行 → 已删文件组件被 get_components_by_files 读回残留，本次修复）
- analysis.py：指纹 all_files 改用 m.relative_path（原 m.file_path 绝对路径与 _fp_detect 的 os.walk 相对路径键不一致 → 所有文件每次轮询都报变更）；session 持久化 analyze_options（include/exclude patterns）供 watch 复用
- 测试：tests/conftest.py 共享 analyzed_repo fixture；tests/test_watch.py 10 个用例（修改/新增/删除、幂等、降级、生命周期、graph_stale）

**关键踩坑（后续实现注意）**：watch 必须用 cache._fp_detect()（幂等），不能 detect_changes()——git 检测器对未提交修改每次轮询都报变更 → 无限刷新循环。

下一步：Backlog 第 3 项 P2 符号检索（FTS5）需用户确认后继续。

### 2026-08-25 00:37

蒸馏闭环完成：23 条对话→19 条笔记确认落盘（stable）→consolidate_notes 聚合为 6 个场景块，29 条源笔记退役（deprecated），notes_since_last_consolidation 已重置。

### 2026-08-25 00:37

doctrine/聚合阈值改由 repowiki/schema.yaml 的 conventions.aggregation 覆盖（doctrine_threshold: 25），aggregation_state.py 默认值已回滚为 50。

### 2026-08-25 00:37

doctrine 刷新备份机制已移除：doctrine.py 删除 _backup_existing，.backup 目录已删，检索索引已重建（total_pages 46→45）。

### 2026-08-25 00:37

SessionStart hook 已把 Team Doctrine 硬注入 additionalContext（_load_doctrine，codewiki/hooks + .codebuddy/hooks + .qoder/hooks 三份同步，测试 6 passed）；AGENTS.md 软约束不足以保证主动 query_wiki。

### 2026-08-25 00:37

repowiki/wiki/doctrine.md 已 confirm 为 stable（human:wangbao，2026-08-24T16:13:34Z）。

### 2026-08-25 00:37

后续注意 aggregation.notes_since_last_doctrine，达到阈值 25 时需运行 refresh_doctrine。
### 2026-08-25 00:40

## 2026-08-25：代码图谱 Backlog 收尾——已提交推送 develop

- 用户决定不再继续 Backlog 第 3 项（P2 符号检索 FTS5）。
- 本地提交 `d5293df` 已推送 develop：analyze_changes + watch_repo 全部落地（12 文件 +1407 行）。
- 拉取远程 4 提交（含 ADR-0002 任务记忆直写退役 pending 闸门）：registry.py 自动合并无冲突；memories.md 两侧均追加导致冲突，已手动解决（两侧内容全部保留，append-only 语义）。
- 经验：SearchReplace 工具无法处理含 git 冲突标记（<<<<<<<）的文件，且 CRLF 行尾文件需用 \r\n 匹配；git 冲突文件直接用 python 脚本清标记更可靠。PowerShell 下 git rebase --continue 卡 vim → 用 $env:GIT_EDITOR='true' 跳过。

### 2026-08-26 01:04

### 2026-08-26 会话蒸馏完成（4 条 raw 对话 → 6 条 stable 笔记）

- 输入：repowiki/raw/ 下 4 条 raw（主体为「变更评估与代码评审」144 轮长对话）
- 结果：6 条 store + 2 条 skip（与 2026-08-25 已有 stable 笔记重复）+ 2 条无知识（SessionEnd 信封、命令重复），均已清理/归档
- 6 条确认 stable 笔记：query_wiki 全量重建索引、type-filter 单值精确匹配、analyze-repo 并行时序竞态、load-project-checklist 静默回退、changed-components 行区间近似、read-versioned-lines untracked 空列表
- 待办：aggregation_hint 提示 consolidate_notes（58 条确认、阈值 10）与 refresh_doctrine（阈值 25）到期，已询问用户，待用户决定是否执行
