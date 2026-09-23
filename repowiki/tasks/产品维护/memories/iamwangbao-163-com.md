## 早期记忆（摘要）

## 产品维护任务早期记忆摘要（截至 2026-09-05）

【已落地决策与实现】
- 任务记忆绑定：task_bindings 一次性消费凭证，capture 落盘后自动删除，supersede 继承旧 task_id；绑定回退不校验任务 status。
- SessionStart hook：硬性执行顺序（第一动作必须是任务关联弹框）+ active 任务注入；codewiki/hooks 源副本与 .codebuddy/.qoder/hooks 同步维护。Team Doctrine 已硬注入。
- 补蒸馏 subagent（distill-worker，2026-09-16 定案）：`toolsMCP` 非官方字段无效，`tools:` 白名单会挡 MCP 工具致 worker 空转；正确授权 `mcpServers: [codewiki]` 且省略 tools 行。修复须落回随包源变体（codewiki/agents/*.md）+ 守门测试，只修项目副本会被 install-hooks 覆盖。
- 多 IDE hook 自动接线（v5.4.0，已发 PyPI + Release）：CodeBuddy/Qoder/Claude Code，install-hooks + IDE 注册表驱动。
- 代码图谱 Backlog（commit d5293df 已推送）：analyze_changes（git diff --unified=0 行级解析→组件区间匹配→transitive_impact，since/worktree 双模式）+ watch 模式（RepoWatcher 轮询去抖默认 2s；必须用 cache._fp_detect() 幂等检测，git 检测器会无限循环；remove_by_file 需 relative_path 列匹配）。P2 符号检索（FTS5）用户决定不做。
- 蒸馏闭环（2026-08-25）：23 对话→19 笔记→6 场景块聚合，29 源笔记退役；doctrine/聚合阈值由 schema.yaml conventions.aggregation 覆盖（doctrine_threshold: 25），达阈值需 refresh_doctrine。
- D19 锁文件集中化：.lck 迁至 <wiki-root>/.meta/locks/<sha256(abs)[:20]>.lck；Windows 释放即删（仅改 store.locked() sidecar 语义，勿下沉 file_lock 通用层），Unix 因 inode race 保留。升级窗口内新旧锁路径不互斥，升级须重启 server。
- 工具链修复：capture _unq/_rebuild_index 去引号（修 .index.json task_id 引号 bug）；lint_wiki fix=true 自愈 stale_refs；_okf_patch_defaults 补 aliases 默认键。
- telemetry 孤儿 .tmp 文件：_atomic_write_lines 崩溃残留，手动删即可。
- write_doc_file sources 自动盖章链路：schema.yaml auto_evidence → _inject_evidence → append_evidence_block，唯一消费者 lint 的 stale_evidence。

【未决/待办】
- get_task_context 调用慢的性能瓶颈定位（2026-08-28 提出）。
- 文档质量审计（lint_wiki checks=all）用户明确搁置。
- 安全遗留：建议吊销泄露过的 PyPI token、删 raw 中 token、清理 scripts/ 临时文件。

【历史坑/约定】
- Windows GBK 控制台编码致 CLI/twine 崩溃；GitHub API 被阻时用 Invoke-RestMethod 走系统网络栈。
- 对话归档原样保留密钥会被 GitHub 密钥扫描拦 push。
- GitPython Windows 坑：repo.index.add(".") 会加 .git 内部文件；ls-files --others --exclude-standard 比 Repo.untracked_files 可靠。
- SearchReplace 无法处理含冲突标记文件，CRLF 需 \r\n 匹配；PowerShell git rebase 卡 vim 用 $env:GIT_EDITOR='true'。
- caw 库 Windows import fcntl 失败，测试加平台跳过。

> 原文归档于 memories-archive/，截至 2026-09-05。

> 原文归档于 memories-archive/iamwangbao-163-com.md, memories-archive/legacy.md，截至 2026-09-18，共 34 条。
### 2026-08-28 12:16

用户询问 .meta/telemetry/Administrator.jsonl.tmp.19748 孤儿临时文件来源与清理时机：根因是 telemetry.py 的 _atomic_write_lines 崩溃安全写入（临时文件+os.replace）在进程被强杀/崩溃/断电或抛非 OSError 异常时残留；无自动清理机制，不影响 aggregate_usage（glob *.jsonl 不匹配），手动删除即可。

### 2026-08-28 12:16

用户在该会话中报告 codewiki get_task_context 调用很慢，需定位性能瓶颈原因（raw 捕获不完整，仅 user 消息无 assistant 回复，问题转主 Agent 跟进）。

### 2026-09-04 16:17

2026-09-04：D19 锁文件集中化变更完成 review（7 文件 +109/−13，`store.py` 新增 `_lock_path_for()` 将 `.lck` 从目标旁边车迁到 `<wiki-root>/.meta/locks/<sha256(abs)[:20]>.lck`，无 `.meta` 祖先时回退就地 sidecar）。结论：代码质量良好，可直接提交，无必须修改项。

### 2026-09-04 16:17

2026-09-04：D19 相关测试全绿——`tests/test_phase2_concurrency.py` 16 passed（含新增 3 个），加 test_locks/knowledge_store/layout_routing/phase3_4/phase4_second_slice 共 63 passed，合计 79 passed（Windows / Python 3.14.5）；新增跨进程测试真实起 2 个 subprocess 各 +15 断言 =30 且仅 1 个锁文件，证明集中锁与旧实现互斥等价。

### 2026-09-04 16:17

2026-09-04：针对 `.meta/locks/` 锁文件累积问题，用户已拍板选「仅 Windows 释放即删」方案——下一步是在 `store.locked()` 出口做 best-effort unlink（吞错），Unix 因 inode race 保留不删，并在 `locks.py`/docstring 注明原因，约 10 行 + 测试。实现时务必只改 sidecar 语义的 `store.locked()`，不要下沉到 `file_lock` 通用层（`wiki_index`/`workspace_bootstrap` 锁的是数据文件本身）。

### 2026-09-04 16:17

2026-09-04：评估后否决了 `lint_wiki` 补刀清扫锁文件——锁文件存在是常态非问题（只能 fix-only 不能当 check 上报），Unix 下同样踩 inode race，且释放即删生效后残留量被钉死在上界，补刀收益极低。

### 2026-09-04 16:17

2026-09-04：D19 review 记录的非阻塞观察（未处理）：`_lock_path_for()` 每次调用做 resolve+祖先遍历+mkdir（低频可接受，热点可加「root→locks_dir」缓存）；Windows 下路径大小写不同会导致哈希不同、锁不互斥（内部路径已归一化，风险极低）；升级窗口内新旧进程锁路径不同、互不互斥，升级须重启 server。

### 2026-09-05 19:12

回答了用户关于 `MCP_Tools_DocWriter.md` frontmatter `sources` 生成与使用的提问：梳理出「`schema.yaml` 的 `auto_evidence` 开关 → `write_doc_file` 落盘后 `_inject_evidence` → `append_evidence_block` 外科插入」的自动盖章链路，及其唯一消费者 lint 的 `stale_evidence`；实测本页两条证据（gen/tpl）重算哈希与记录一致，当前状态 `ok`，lint 不会报警。同时厘清了 `sources` 的三个生产者与四类同名歧义。

### 2026-09-05 19:12

上一轮补蒸馏产出的 3 条草稿笔记处置结果：笔记 1（锁文件清理采用「仅 Windows 释放即删」，Unix 一律保留不删）与笔记 3（D19 锁文件集中到 `<wiki-root>/.meta/locks/<sha256(目标绝对路径)[:20]>.lck`）已由用户确认为 `stable`；笔记 2（`file_lock` 的锁文件可能是数据文件本身，释放即删只能加在 `store.locked()`，不能下沉到通用 `file_lock`）仍为 `draft`，待用户 `confirm_note` 或 `reject_note`。

### 2026-09-05 19:12

挂起待办（未实现）：「仅 Windows 释放即删」约 10 行 + 测试，只改 `store.locked()` 出口做 best-effort unlink 并吞掉异常；原因是 Unix 存在 inode race（等锁方持有旧 inode fd，unlink 后新进程开新 inode，互斥失效导致丢更新）。已否决的替代方案：用 lint_wiki 补刀清理锁文件（理由：锁文件存在是常态非问题、只能 fix-only 不能当 check、Unix 同样踩 race、收益极低）。

### 2026-09-05 19:12

核对 `docs/articles/CodeWiki-Plus系列11：机器写的Wiki凭什么可信——证据、保鲜与冲突消解.md` 对 `sources` 生成与 `stale_evidence` 的覆盖：文章第二节「落盘时」与第五节「证据漂移」已覆盖设计意图（内容哈希 vs git SHA、单页上限 8、不覆盖人工证据、只提醒不改写），但缺 6 条实现边界（sources 是采样锚点存在覆盖率缺口、三生产者区分、多仓 `evidence_roots` 解析、warning 级别只扣 3 分、无行号退化为整文件哈希、注入须在 `_record_page_manifest` 之前）。已向用户提议把这些补写成文档或一条 architecture 笔记，**用户尚未答复**；文章 78 行「被频繁检索命中复核提醒顺延」未核实（属 `stale_notes` 检查）。

### 2026-09-05 19:12

候选 lesson 笔记「蒸馏 subagent 自报的笔记状态不可信，需用 `get_task_context` 的 `related_notes[].status` 复核」已向用户提议写入 Wiki，**用户尚未答复**；本次蒸馏已将其作为 `draft` 笔记产出，等待确认闸门。本轮「产品维护」补蒸馏（1 条 raw，11 轮）完成，产出 5 条 draft 笔记 + 5 条任务记忆，pending raw 归零。

### 2026-09-07 14:49

2026-09-07 会话（source_session 993f1c39697248b4a2c07b3edec98972）提出并定案 MCP 层中文返回文本的 i18n：YAML 双文件全量（`codewiki/mcp/locales/zh.yaml` 为源、`en.yaml` 全量覆盖）、一次性全做、无运行时回退（缺 key 返回哨兵，靠发版前 key 集一致性测试暴露）、范围含 prompt 元数据 + 22 个正文 + instructions + resources + 工具层散点 + 落盘产物。

### 2026-09-07 14:49

审计结论（已核对）：工具 schema description 与错误消息全部为英文，中文 i18n 工作量不含这部分；中文集中在 prompts.py（正文约 1250 行 + 元数据约 100 行）、resources.py catalog（约 92 行）、server.py instructions（57 行）、工具层散点几十行，合计约 1500 行需英文创作。

### 2026-09-07 14:49

语言来源定案：`~/.codewiki/config.json` 的 lang 字段 > `CODEWIKI_LANG` 环境变量 > 系统 locale 推断 > 兜底 zh；不能放项目级 `repowiki/schema.yaml`（MCP server 启动期无 repo 上下文）。用户侧切换语言的方式是在 MCP 配置里加 `"env": {"CODEWIKI_LANG": "en"}`。

### 2026-09-07 14:49

M1 基建已落地：新增 `codewiki/mcp/i18n.py`（`t()` / `current_lang()` / lru_cache 加载 locales）、`codewiki/mcp/locales/zh.yaml` 与 `en.yaml`；`codewiki/mcp/server.py` 已接线（i18n 导入 + Server 构造前初始化语言 + instructions 改为从语料取）；`pyproject.toml` 的 wheel artifacts 已加入 locales 资源。

### 2026-09-07 14:49

`tests/test_i18n.py` 已建立（key 集一致性、占位符一致性、缺 key 哨兵、语言解析优先级四组断言），尚未运行验证是否全绿。

### 2026-09-07 14:49

待办（未开始，按依赖顺序）：(1) prompts.py 22 个 Prompt 的 title/description 接入语料；(2) 22 个 `_prompt_*` 正文函数重写为「按语言取模板片段 + 保留逻辑」并产出英文版（约 1250 行创作，本次最大工作量）；(3) resources.py 的 `prompts/catalog` 改为从 `list_prompts` 派生（消除 15 vs 22 漂移）；(4) 工具层中文散点；(5) 落盘产物（agents_md / wiki_index / reading_guide / schema_generator）语言跟随；(6) `tool_count` 改运行时计数、instructions 里 11→22 修正。

### 2026-09-07 14:49

风险提示：英文正文初稿由 Agent 创作，定案时建议合入前做一次面向英文可读性的审校，避免机器直译风格拉低产品完成度。

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

### 2026-08-26 会话蒸馏完成（4 条 raw 对话 → 6 条 stable 笔记）

- 输入：repowiki/raw/ 下 4 条 raw（主体为「变更评估与代码评审」144 轮长对话）
- 结果：6 条 store + 2 条 skip（与 2026-08-25 已有 stable 笔记重复）+ 2 条无知识（SessionEnd 信封、命令重复），均已清理/归档
- 6 条确认 stable 笔记：query_wiki 全量重建索引、type-filter 单值精确匹配、analyze-repo 并行时序竞态、load-project-checklist 静默回退、changed-components 行区间近似、read-versioned-lines untracked 空列表
- 待办：aggregation_hint 提示 consolidate_notes（58 条确认、阈值 10）与 refresh_doctrine（阈值 25）到期，已询问用户，待用户决定是否执行

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
