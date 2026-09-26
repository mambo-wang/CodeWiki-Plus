## 早期记忆（摘要）

## 产品维护任务早期记忆摘要（截至 2026-09-07）

【已落地决策与实现】
- 任务记忆绑定：task_bindings 一次性消费凭证，capture 落盘后自动删除，supersede 继承旧 task_id；绑定回退不校验任务 status。
- SessionStart hook：硬性执行顺序（第一动作必须是任务关联弹框）+ active 任务注入；codewiki/hooks 源副本与 .codebuddy/.qoder/hooks 同步维护。Team Doctrine 已硬注入（_load_doctrine）。
- 补蒸馏 subagent（distill-worker）：正确授权 `mcpServers: [codewiki]` 且省略 tools 行（toolsMCP 无效、tools 白名单会挡 MCP）。修复须落回随包源变体（codewiki/agents/*.md）+ 守门测试。
- 多 IDE hook 自动接线（v5.4.0 已发 PyPI）：CodeBuddy/Qoder/Claude Code，install-hooks + hooks.yaml 注册表驱动。
- 代码图谱 Backlog（commit d5293df 已推送）：analyze_changes（git diff --unified=0 行级解析→组件区间匹配→transitive_impact，since/worktree 双模式）+ watch 模式（RepoWatcher 轮询去抖 2s；必须用 cache._fp_detect() 幂等检测否则无限循环；remove_by_file 需 relative_path 列匹配）。P2 符号检索（FTS5）用户决定不做。
- 蒸馏闭环（2026-08-25）：23 对话→19 笔记→6 场景块聚合，29 源笔记退役；doctrine/聚合阈值由 schema.yaml conventions.aggregation 覆盖（doctrine_threshold: 25）。
- D19 锁文件集中化：.lck 迁至 <wiki-root>/.meta/locks/<sha256(abs)[:20]>.lck；Windows 释放即删（仅改 store.locked() sidecar 语义，勿下沉 file_lock 通用层），Unix 因 inode race 保留。升级窗口内新旧锁路径不互斥，升级须重启 server。挂起待办：「仅 Windows 释放即删」约 10 行 + 测试尚未实现。
- 工具链修复：capture _unq/_rebuild_index 去引号（修 .index.json task_id 引号 bug）；lint_wiki fix=true 自愈 stale_refs；_okf_patch_defaults 补 aliases 默认键。
- telemetry 孤儿 .tmp 文件：_atomic_write_lines 崩溃残留，手动删即可。
- write_doc_file sources 自动盖章链路：schema.yaml auto_evidence → _inject_evidence → append_evidence_block，唯一消费者 lint 的 stale_evidence；sources 是采样锚点存在覆盖率缺口。
- MCP 层 i18n（2026-09-07 定案）：YAML 双文件全量（zh.yaml 源、en.yaml 覆盖）、无运行时回退（缺 key 返回哨兵，靠 key 集一致性测试暴露）；语言来源 ~/.codewiki/config.json lang > CODEWIKI_LANG > locale > 兜底 zh，不能放项目级 schema.yaml。M1 基建已落地（i18n.py + locales + server 接线 + wheel 资源 + test_i18n.py）。

【未决/待办】
- i18n 后续（未开始）：prompts.py 22 个正文英文版（约 1250 行创作，最大工作量）、resources catalog 派生、工具层散点、落盘产物语言跟随、tool_count 运行时计数；英文初稿合入前建议人工审校。
- get_task_context 调用慢的性能瓶颈定位（2026-08-28 提出）。
- 文档质量审计（lint_wiki checks=all）用户明确搁置。
- 安全遗留：建议吊销泄露过的 PyPI token、删 raw 中 token、清理 scripts/ 临时文件。
- 系列文章《系列11》缺 6 条 sources 实现边界，是否补写用户未答复。

【历史坑/约定】
- Windows GBK 控制台编码致 CLI/twine 崩溃；GitHub API 被阻时用 Invoke-RestMethod 走系统网络栈。
- 对话归档原样保留密钥会被 GitHub 密钥扫描拦 push。
- GitPython Windows 坑：repo.index.add(".") 会加 .git 内部文件；ls-files --others --exclude-standard 比 Repo.untracked_files 可靠；Path.relative_to 同路径返回 Path('.') 需归一化。
- SearchReplace 无法处理含冲突标记文件，CRLF 需 \r\n 匹配；PowerShell git rebase 卡 vim 用 $env:GIT_EDITOR='true'。
- caw 库 Windows import fcntl 失败，测试加平台跳过。
- 配置合并 Python 坑：dict 浅拷贝污染原配置 + hooks.get(event, []) 未写回。
- 会话启动的 query_wiki/蒸馏等重操作委托 subagent 执行，避免阻塞用户。

> 原文归档于 memories-archive/iamwangbao-163-com.md, memories-archive/legacy.md，截至 2026-09-18。

> 原文归档于 memories-archive/iamwangbao-163-com.md, memories-archive/legacy.md，截至 2026-09-23，共 45 条。

### 2026-09-10 09:37

产品维护会话澄清：《系列13》文章「没加提交 prompt 的 hook」是误判——UserPromptSubmit 技能提示 hook 已实现并接线（ide_config.py:107 PROMPT_HOOK_CMD、hooks.yaml:29 claude 家族、.codebuddy/settings.json:27-38 已入库、commit 0db5ae1）。命中面窄（只匹配 status:draft，当前仅 1 份 draft 技能）+ 真机通道未验证是两大原因；结论是补真机探针验证而非加触发点。

### 2026-09-10 09:37

技能反馈 flag_issue 链路通：page_path 写草稿区 skills/<name>/SKILL.md、幂等哈希 FNV-1a(issue_type::page_path)、prepare 聚合 open_issues_by_skill。仓库已有 1 条真反馈 2ceafde2（maintain-fork-pr-merge，类型被降级 custom 且仍 open）。三个坑：生效区路径静默失效 / 未知 type 降级 custom / 无关闭工具。

### 2026-09-10 20:14

SessionStart 任务关联弹框已改为「单框列全」：只允许 1 次 ask_followup_question、1 个 question，options 一次性列出全部 active 任务 + 新建任务… + 跳过；「新建任务两步弹框」降级为仅在未给名字时的兜底。同步了 hook 源副本、.codebuddy/.qoder 两份生成副本、prompts.py 两处、AGENTS.md 标记块，并新增测试 test_active_tasks_listed_in_one_chooser_box。

### 2026-09-10 20:14

回归结果：tests/test_task_session_start.py + test_install_hooks.py 50 passed；pytest -k "prompt or i18n or task" 113 passed 1 skipped。已 commit 0c9fc2e 并推送 develop（8 文件 +183/−62）。

### 2026-09-10 20:14

产品维护遗留未提交项：README.md 的「第 11 篇」文章链接（上一会话遗留，与本次改动无关），以及 5 个未跟踪的 repowiki/conversations/conv-*.md 与 .codebuddy/skills/repowiki-conclusion-update/，等用户决定是否单独补 commit。

### 2026-09-18 11:05 #g3j1

确认主动沉淀可关联任务：`add_task_memory` 的 task_id 必填（天然任务级）；`ingest_note` 有可选 `task_id` 参数写入 note frontmatter，由 `get_task_context` 的 related_notes 和 `query_wiki(task_id=...)` 消费（registry.py:1039/1230）；`delete_task` 删任务目录但不删盖了 task_id 的笔记（registry.py:2794）。注意：`.codebuddy/memory/` 是 CodeBuddy IDE 宿主自带的工作记忆通道，与 CodeWiki 任务记忆独立并存，任务进展须显式走 `add_task_memory` 落到 repowiki/tasks/ 下。

### 2026-09-18 11:10 #gnu6

用户反馈主动沉淀协议未触发（会话中只写了 IDE 工作记忆 .codebuddy/memory，未写任务记忆）。诊断出三缺口：①四判据不含「产品机制澄清/事实纠偏」类 Q&A 价值轮次，纯问答合规漏记；②宿主 CodeBuddy 系统提示的强指令（MUST 写 .codebuddy/memory）与协议块软措辞竞争，产生已沉淀错觉，协议块未声明两通道独立；③会话中无 per-turn 自查/提醒载体，hook 仅 SessionStart 注入。优化方向（改 prompts.py `_active_settle_section()` 源头+重新生成+守门测试）：判据扩面、加每轮收尾自查硬动作、加双通道独立声明；可选 UserPromptSubmit 周期提醒后置。

### 2026-09-18 12:27 #jdvt

实施 AGENTS.md 主动沉淀协议优化与文本块精简：① ACTIVE-SETTLE 块（prompts.py `_active_settle_section()`）判据扩面（第2条加「澄清/纠偏产品机制、代码事实等关键认知」）、加每轮回复收尾前自查、加双通道独立声明（宿主 IDE 工作记忆不豁免任务记忆）——修复用户反馈的「Q&A 轮合规漏记」问题；② TEAM-MEMORY-TASK 块精简冗余解释；③ locales/zh.yaml+en.yaml `artifacts.agents_md.main` 大幅精简（纠正识别/主动沉淀段压缩，保留测试断言短语）；④ 重新生成 AGENTS.md 三块（write_agents_md + upsert_agents_section + upsert_active_settle_protocol），约 200 行→165 行。测试 122+109 passed。手写的 Agent skills/Team memory fusion 段未动。

### 2026-09-18 13:03 #zffa

压缩摘要上限优化：`_COMPACTION_SUMMARY_MAX_CHARS` 2048→4096（task_manager.py:198），超限报错改为给出超出字数（over by N），便于按差额删减；zh/en `compact_instruction` 补充超限重试指引；设计文档 §5.2 同步；测试断言更新（2049→4097 + over by 1）。68 passed。背景：用户质疑 70 字限制，实为 2048 字符上限被误读，实测 34 条早期记忆压缩到 2048 偏紧被迫丢细节。

### 2026-09-18 15:18 #jx2n

知识飞轮全链路完成：① 任务记忆压缩（34条→摘要，上限已提至4096）；② 笔记聚合（60条→9场景块更新+1新建「竞品调研与借鉴方法」，57条退役，3条deferred）；③ Doctrine 刷新（新增竞品调研SOP与「文档站宣传口径/代码事实口径」判断逻辑，1200/1200压线，已confirm stable，计数器归零）。lint：3个error均为既有skills/windows-dev-env frontmatter问题，与本次无关。

### 2026-09-18 15:46 #clgi

修复 frontmatter 解析 bug：`_read_frontmatter`（note_consolidation.py:124）用 `text.find("---", 3)` 找结束标记，frontmatter 值内含 `---`（如笔记文件名 `commit---amend`）即截断 YAML、解析失败 → lint 误报 SKILL.md 缺 name/status/source_refs。修复为按行匹配 `^---\s*$`。验证：7 keys/6 refs 解析正常，54 passed，skill_lint 3 error→0。遗留：全仓约 30 处同款模式待收敛成共享 helper；MCP server 需重启生效。

### 2026-09-20 17:43 #izmk

完成 install-hooks 参数重构（ADR-0014）：① `--capture on|off` 独立开关（默认 on）控制 SessionEnd（trae 为 Stop）采集注册，off 时移除注册但 SessionStart/脚本/distill-worker 保留；② `--active-settle` 参数删除（传入硬报错），主动沉淀固定启用、ACTIVE-SETTLE 协议块恒渲染，块②保险采集段删除、判据4改沉淀自查；③ 蒸馏无条件只产经验笔记（memories_skipped_reason=channel_exclusive），capture_conversation 的 active_settle 参数与 frontmatter 键删除，ADR-0008 标 superseded、新增 ADR-0014；④ hooks.yaml 删 active_settle 字段、active_settle_of() 退役；⑤ --status 表 active_settle 列改 capture 列，wired-on-disk 新增 hooks(仅SS)+settings(capture off) 专用值；⑥ MCP prompt team-memory-hook/init-wiki 参数 active_settle→capture，locales zh/en 同步；⑦ 设计方案升 v3、README/team-memory-hook.md 同步。全量测试 1176 通过（test_phase2_concurrency 为 Windows 文件锁环境性 flaky，单独跑 17/17 过）。下一步：观察主动沉淀遵守度，效果好则 `--capture off` 停采集链路。

### 2026-09-20 18:45 #ggk5

追加：--mode 参数彻底删除（档位由 hooks.yaml 注册表自动判定——支持 SessionStart 的宿主走 hook 档，不支持的 qwenwork 走 prompt 档），传入即硬报错；连带删除 --clean 与 clean_hook_artifacts()（唯一用途随 --mode 消失）；MCP prompt team-memory-hook 删 mode 参数；README/设计方案/team-memory-hook.md 同步。全量测试 1126 通过。CLI 最终形态：install-hooks [--ide] [--capture on|off] [--status] [--inject-file] [--create-dir] [--repo-path]。

### 2026-09-20 19:15 #wbkl

auto_push 链路梳理完成：核心逻辑在 codewiki/src/git_sync.py 的 auto_push()——_resolve_auto_push 读 schema.yaml conventions.git_sync.auto_push（默认 False）；执行顺序：暂存区守卫（用户已手动 add 则中止）→ git add -A 只暂存 repowiki/ 子树 → unstage .lck → 用仓库现有 git 身份 commit（message 前缀 codewiki:）→ 无 upstream 则跳过推送保留本地提交 → push 失败走 fetch+rebase 重试≤5 次（冲突 abort），永不 force-push/reset，失败保留本地提交下次搭载（D12 失败契约）。锚点两类：handler 自带（close_session/capture_conversation/distill_conversation/batch_ingest/ingest_note/write_doc_file）+ registry.py _PUSH_ON_WRITE 12 个工具由 dispatch() 经 auto_push_into_result 统一收口；batch_ingest 用 defer_push() 抑制子项推送、批边界只推一次。auto_push 开启时 auto_stage 自动失效（互斥）。本仓库 schema.yaml 已开 auto_push: true。

### 2026-09-20 20:04 #fdxk

auto_push 预暂存守卫重构完成：用户反馈「经常没提交推送」要求 force-push。诊断根因：预暂存守卫（git_sync.py）在暂存区有用户手动 add 的任何内容时整体中止 auto_push，用户常暂存文件导致频繁静默跳过。force-push 被否决（D10 决策「永不 force」，改写远端历史危及他人提交）。修复：守卫改为路径限定提交 git commit -m msg -- <repowiki/>，只提交知识子树，用户暂存的业务文件留在暂存区不被卷入不阻塞同步；子树内用户暂存的知识内容随行（接受）。测试 test_auto_push_coexists_with_preexisting_staged_content 改写，test_phase4_second_slice 12 passed + test_git_sync_auto_stage 11 passed。MCP server 需重启生效。

### 2026-09-21 18:12 #86ba

prompts.py 渲染正文清理决策引用完成：用户提出 prompt 正文不应引用 ADR 编号/设计方案文档地址/历史决策变动（如「ADR-0002」「docs/xxx设计方案.md §4」「P1 C 线」「T2+T3」「handler: source_ingest.py:741」），运行时 Agent 只需知道当前行为。已清理 13 处渲染正文（active-settle 块、qwenwork 小节、distill/task-workflow/skill-creator/promote-note/consolidate-knowledge/retract-source 等 prompt）；Python 源码注释/docstring 里的 ADR 指针按惯例保留（维护者溯源用）。测试无断言依赖这些字样，144 passed。原则定案：prompt 渲染正文=只描述当前实现；源码注释=可带决策溯源。

### 2026-09-23 09:10 #kyhw

竞品调研：阅读腾讯云开发者文章《AI写得快≠真正提效：Harness 记忆与验证闭环》（作者焦成杰），完成与 CodeWiki 现状逐点代码核对。核心结论：①文章的「知识库+两级索引+成熟度/引用追踪+自动复盘」与 CodeWiki 知识飞轮高度同构，验证了方向；②真实差距 3 项——(a) PreToolUse 硬拦截「先读知识库再动手」：CodeWiki hooks.yaml 只有 SessionStart/UserPromptSubmit/SessionEnd 三类事件，无 PreToolUse，AGENTS.md 软约束遵守度差（用户 2026-09-18 反馈过漏记）；(b) 等待 skill（轮询到终态、按正确维度等、超时如实上报）：CodeWiki 完全没有，闭环止于「改完代码」；(c) 验证闭环 command（/close-loop 八步固化、运动员/裁判员分离、审查成员工具层面禁写、循环上限 3 轮）：CodeWiki 无此形态。③文章可借鉴细节：写入规范「脱离本次任务上下文仍成立才写」与四问过滤同源；成熟度四级 draft<verified<proven<archived 与 CodeWiki draft/stable/superseded 类似但多了跨场景 proven；衰减按类型定周期与 freshness by_type 同构；弱信号（hook 记读日志）/强信号（复盘声明采纳）双通道与 CodeWiki 检索命中/采纳声明双通道同构。④明确不借：Obsidian vault+REST API（CodeWiki 是 MCP 原生）、全量衰减扫描高频跑（CodeWiki lint 按需跑）。待用户决定是否把 3 项差距落 backlog。

### 2026-09-23 11:41 #43pf

腾讯云 Harness 文章调研定案（grill 评审完成）：用户裁决三项借鉴全部不立项。①PreToolUse 硬拦截→absorbed：claude-mem v13 源码反证 DENY 已被行业放弃，既有规划 P2-2（SessionStart 软闸门）+ P2-1'（附加上下文，spike 触发）已覆盖，文章仅作「软约束遵守度差」佐证；②等待 skill→deferred：归「发版本」任务线（等 PyPI 生效验证）；③close-loop 闭环→excluded：依赖作者公司 CI/CD/工单系统，超产品边界，CodeWiki 只覆盖第八步知识复盘。微借鉴一条：「不在中间任何一步静默停下」作为多步骤 prompt 写作原则。调研笔记已落 draft（notes/2026-09-23-腾讯云-harness-文章调研定案…），待确认。另：本会话早前 2 条蒸馏草稿已被用户拒绝（deprecated）。

### 2026-08-26 会话蒸馏完成（4 条 raw 对话 → 6 条 stable 笔记）

- 输入：repowiki/raw/ 下 4 条 raw（主体为「变更评估与代码评审」144 轮长对话）
- 结果：6 条 store + 2 条 skip（与 2026-08-25 已有 stable 笔记重复）+ 2 条无知识（SessionEnd 信封、命令重复），均已清理/归档
- 6 条确认 stable 笔记：query_wiki 全量重建索引、type-filter 单值精确匹配、analyze-repo 并行时序竞态、load-project-checklist 静默回退、changed-components 行区间近似、read-versioned-lines untracked 空列表
- 待办：aggregation_hint 提示 consolidate_notes（58 条确认、阈值 10）与 refresh_doctrine（阈值 25）到期，已询问用户，待用户决定是否执行

### 2026-08-26 会话蒸馏完成（4 条 raw 对话 → 6 条 stable 笔记）

- 输入：repowiki/raw/ 下 4 条 raw（主体为「变更评估与代码评审」144 轮长对话）
- 结果：6 条 store + 2 条 skip（与 2026-08-25 已有 stable 笔记重复）+ 2 条无知识（SessionEnd 信封、命令重复），均已清理/归档
- 6 条确认 stable 笔记：query_wiki 全量重建索引、type-filter 单值精确匹配、analyze-repo 并行时序竞态、load-project-checklist 静默回退、changed-components 行区间近似、read-versioned-lines untracked 空列表
- 待办：aggregation_hint 提示 consolidate_notes（58 条确认、阈值 10）与 refresh_doctrine（阈值 25）到期，已询问用户，待用户决定是否执行

### 2026-09-23 15:12 #on0j

修复 Windows 闪窗问题：用户反馈 auto_push 自动提交 repowiki 时每次弹几个 cmd 窗口很快关闭。根因：MCP server 由 IDE 无控制台拉起，git 子进程会新分配控制台窗口闪现；git_sync.py run_git_bounded 只设了 CREATE_NEW_PROCESS_GROUP 没设 CREATE_NO_WINDOW。修复：① git_sync.py 新增共享 helper windows_creationflags()（CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP，非 Windows 返回 0），run_git_bounded 改用它；② 同款修复 MCP server 内另外 4 处直接 subprocess 调用：config.py _git_config_value、doc_writer.py git rev-parse、note_query.py _last_commit_time git log、workspace_bootstrap.py _clone_repo git clone。新增守门测试 test_windows_creationflags_suppresses_console；test_git_sync_auto_stage 12 passed + test_phase4_second_slice 11 passed。MCP server 需重启生效。

### 2026-09-23 15:31 #33j9

澄清产品机制：CodeBuddy subagent frontmatter 支持 model 字段（可选，默认跟随主 Agent），distill-worker 当前未写 model 所以跑主 Agent 同款模型；若要给蒸馏 worker 换弱模型，须改随包源变体 codewiki/agents/distill-worker.md（claude 家族变体 distill-worker.claude.md 取值不同需分别写），且因 toolsMCP 教训需真机验证 model 字段确实生效。用户尚未决定是否加。

### 2026-09-26 20:20 #lol0

待办（P2，来自 agentmemory 调研 Round 2 grill 定案 2026-09-25，用户指示先存档不实施）：MCP 工具面裁剪开关——CODEWIKI_TOOLS=core 环境变量，registry 加 filter，60+ 工具 schema 全量注入占上下文是真缺口。参考 agentmemory 的 AGENTMEMORY_TOOLS=core（裁到 8 个）思路，按本仓场景重定义核心集。依据：repowiki/wiki/queries/agentmemory-调研.md 第六节。
