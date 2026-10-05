## 早期记忆（摘要）

## 产品维护任务早期记忆摘要（截至 2026-10-03）

【已落地决策与实现】
- 任务记忆绑定：task_bindings 是一次性消费凭证，capture 落盘后自动删除；supersede 继承旧 task_id；绑定回退不校验任务 status。`add_task_memory` 的 task_id 必填（天然任务级）；`ingest_note` 可选 task_id 写进 frontmatter，由 `get_task_context` 的 related_notes 与 `query_wiki(task_id=...)` 消费；`delete_task` 删任务目录但不删盖章笔记。
- SessionStart hook：第一动作必须是任务关联弹框；定式「单框列全」= 1 次提问工具调用 + 1 个 question + 全部 active 任务 + 新建 + 跳过，未给名字才在正文请名字。`codewiki/hooks` 源副本与 `.codebuddy/.qoder/.trae` 安装副本同步维护。Team Doctrine 硬注入（_load_doctrine）。
- install-hooks 参数收敛（ADR-0014）：`--capture on|off` 独立控制 SessionEnd（trae 为 Stop）注册，off 时保留 SessionStart/脚本/distill-worker；`--active-settle`、`--mode`、`--clean` 全删（传入硬报错），档位由 hooks.yaml 注册表自动判定（支持 SessionStart 走 hook 档，qwenwork 走 prompt 档）；主动沉淀固定启用、蒸馏只产经验笔记；`--status` 含 capture 列与 wired-on-disk 专用值 `hooks(仅SS)+settings(capture off)`。最终形态：`[--ide][--capture][--status][--inject-file][--create-dir][--repo-path]`。
- 主动沉淀协议（ACTIVE-SETTLE 块，prompts.py `_active_settle_section()`）：判据含「澄清/纠偏产品机制与代码事实」，每轮回复收尾前自查，声明宿主 IDE 工作记忆与任务记忆是独立通道（写前者不豁免后者）——修复「纯 Q&A 轮合规漏记」。AGENTS.md 三块由 prompts.py + locales 生成，约 200 行精简到 165 行。
- 压缩机制：`_COMPACTION_SUMMARY_MAX_CHARS` 2048→4096，超限报错改为给出超出字数（over by N）便于按差额裁剪。
- MCP 层 i18n：`locales/{zh,en}.yaml` 全量、无运行时回退（缺 key 返回哨兵，靠 key 集一致性测试暴露）；语言取 `~/.codewiki/config.json lang > CODEWIKI_LANG > OS locale > zh`，不能放项目级 schema.yaml。
- 技能反馈 flag_issue 链路：page_path 指向草稿区 `skills/<name>/SKILL.md`、FNV-1a 幂等哈希（issue_type::page_path）、prepare 聚合 open_issues_by_skill。坑：生效区路径静默失效 / 未知 type 降级 custom / 无关闭工具。UserPromptSubmit 技能提示 hook 已接线，命中面只匹配 status:draft。
- 其他已落地：distill-worker 授权 `mcpServers:[codewiki]` 且省略 tools 行；D19 锁文件集中化（Windows 释放即删仅改 store.locked() sidecar）；write_doc_file auto_evidence 盖章链路；capture `.index.json` 引号 bug 修复；lint fix=true 自愈 stale_refs；代码图谱 analyze_changes + watch（幂等 _fp_detect 防无限循环）。知识飞轮 2026-09-18 全量收口一轮：34 条记忆压缩、60 条笔记聚合成 9+1 场景块（57 退役）、doctrine 刷新并 stable。

【未决/待办】
- i18n 后续未开始：prompts.py 正文英文版、resources catalog 派生、工具层散点、落盘产物语言跟随、tool_count 运行时计数。
- get_task_context 性能瓶颈定位；lint_wiki checks=all 全量审计（用户明确搁置）。
- 安全遗留：吊销泄露过的 PyPI token、删 raw 中 token、清理 scripts/ 临时文件。
- 「仅 Windows 释放即删」约 10 行 + 测试未实现；主动沉淀遵守度仍在观察，效果好则 `--capture off` 停采集链路。
- 《系列11》缺 6 条 sources 实现边界，用户未答复；README「第 11 篇」链接遗留。

【历史坑/约定】
- Windows GBK 控制台致 CLI/twine 崩溃；GitHub 被阻时 fetch 走 ssh.github.com:443。
- 对话归档原样保留密钥会被 GitHub 密钥扫描拦 push。
- GitPython：`repo.index.add(".")` 会加 .git 内部文件；`ls-files --others --exclude-standard` 比 untracked_files 可靠；`Path.relative_to` 同路径返回 `Path('.')` 需归一化。
- SearchReplace 无法处理含冲突标记文件，CRLF 需 `\r\n`；PowerShell git rebase 卡 vim 用 `$env:GIT_EDITOR='true'`。
- caw 库 Windows import fcntl 失败，测试加平台跳过；配置合并坑：dict 浅拷贝污染原配置 + `hooks.get(event, [])` 未写回。
- `_read_frontmatter` 曾用 `text.find("---", 3)`，值内含 `---` 即截断 YAML；按行匹配 `^---\s*$` 才是正解（全仓约 30 处同款待收敛）。
- 断言涉及路径必须用平台拼接 + `os.path.normpath`（prompt 的 `_resolve_path` 会 normpath，硬编码 `/tmp/...` 在 Windows 必红）。
- 会话启动的 query_wiki/蒸馏等重操作委托 subagent，避免阻塞用户。

> 原文归档于 memories-archive/iamwangbao-163-com.md、memories-archive/legacy.md，截至 2026-10-03。

> 原文归档于 memories-archive/iamwangbao-163-com.md，截至 2026-10-04，共 14 条。

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

### 2026-09-23 15:12 #on0j

修复 Windows 闪窗问题：用户反馈 auto_push 自动提交 repowiki 时每次弹几个 cmd 窗口很快关闭。根因：MCP server 由 IDE 无控制台拉起，git 子进程会新分配控制台窗口闪现；git_sync.py run_git_bounded 只设了 CREATE_NEW_PROCESS_GROUP 没设 CREATE_NO_WINDOW。修复：① git_sync.py 新增共享 helper windows_creationflags()（CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP，非 Windows 返回 0），run_git_bounded 改用它；② 同款修复 MCP server 内另外 4 处直接 subprocess 调用：config.py _git_config_value、doc_writer.py git rev-parse、note_query.py _last_commit_time git log、workspace_bootstrap.py _clone_repo git clone。新增守门测试 test_windows_creationflags_suppresses_console；test_git_sync_auto_stage 12 passed + test_phase4_second_slice 11 passed。MCP server 需重启生效。

### 2026-09-23 15:31 #33j9

澄清产品机制：CodeBuddy subagent frontmatter 支持 model 字段（可选，默认跟随主 Agent），distill-worker 当前未写 model 所以跑主 Agent 同款模型；若要给蒸馏 worker 换弱模型，须改随包源变体 codewiki/agents/distill-worker.md（claude 家族变体 distill-worker.claude.md 取值不同需分别写），且因 toolsMCP 教训需真机验证 model 字段确实生效。用户尚未决定是否加。

### 2026-09-26 20:20 #lol0

待办（P2，来自 agentmemory 调研 Round 2 grill 定案 2026-09-25，用户指示先存档不实施）：MCP 工具面裁剪开关——CODEWIKI_TOOLS=core 环境变量，registry 加 filter，60+ 工具 schema 全量注入占上下文是真缺口。参考 agentmemory 的 AGENTMEMORY_TOOLS=core（裁到 8 个）思路，按本仓场景重定义核心集。依据：repowiki/wiki/queries/agentmemory-调研.md 第六节。

### 2026-09-27 15:53 #x7ef

澄清产品机制：ingest_source 官方口径支持 PDF/MD/DOCX/HTML 四种格式，但代码无扩展名白名单（source_type 默认取后缀，任意文件可存储注册）。文本格式 .md/.markdown/.html/.htm/.txt/.rst 走完整链路（存储+注册+版本感知去重门）；pdf/docx 为二进制格式，_plain_text() 返回 None——无文本提取器，跳过版本去重门，且外部文档知识抽取流程读不回正文，实际只对文本格式可完整走通。PDF/DOCX 建议先转 Markdown 再导入。

### 2026-09-27 19:51 #xerc

ADR-0018 已拍板并实现：ingest_source 引入 markitdown 转换 sidecar。8 项决策全按推荐：①原始文件无条件保留（哈希锚点+可重转）；②ingest 时一次性转换存 raw/sources/<name>.converted.md；③markitdown 为 optional extra [convert]，未装 fail-open 降级（行为同现状）；④转换失败结构化记录 convert_error（dependency_missing/empty_output/converter_exception）；⑤[^src:...] 引用锚定 sidecar 行号；⑥sidecar 随 auto_push 入库；⑦跨格式 version_sibling 门生效（指纹基于转换文本）；⑧工具描述保守口径。实现要点：转换在去重门之前内存完成（指纹覆盖 pdf/docx），门通过后才落盘 sidecar；_plain_text() 扩展读 sidecar 回退；retract remove_refs 把 sidecar 一并移 .trash。新增 tests/test_source_convert.py 9 个测试，全量 1208 通过。

### 2026-09-27 21:04 #tx6y

代码评审（两轴 subagent + 主 Agent 复核）发现并修复孤儿 sidecar bug：_convert_to_markdown 原在版本门之前就落盘 sidecar，门拦下时残留孤儿文件。修复为纯内存转换（返回 (registry_fields, converted_text)），门通过后随最终 dest_name（含哈希后缀）落盘。测试补孤儿文件断言。其余发现：①ADR「转换只做一次确定性缓存」与实现（每次 ingest 重转）不一致——待对齐；②_CONVERTIBLE_SUFFIXES 含 pptx/xlsx/epub 超出 ADR 决策⑧保守口径——待对齐（要么收窄后缀集，要么扩 ADR 口径）；③决策⑤引用锚定仅文档约定无实现（属抽取 command 层职责，可接受）；④retract 中移 .trash 逻辑重复（judgement call，暂不动）。全量 1208 通过。

### 2026-09-27 22:24 #k6kk

评审遗留项已拍板并闭环：①官方口径扩为 PDF/MD/DOCX/HTML/XLSX，_CONVERTIBLE_SUFFIXES 收窄为 {.pdf,.docx,.xlsx}（pptx/epub 未验证不承诺，测试断言同步）；②ADR §2 改为如实描述「每次 ingest 重转，sidecar 随导入覆盖」。ADR-0018 决策⑧已修订并标注修订日期。全量 1208 通过。

### 2026-09-29 10:58 #llbw

init-wiki/init-workspace 任务管理接线「否」失效修复完成（grill 定案）：①根因是命令薄壳不注入开关参数且无意图映射指引，用户答「否」死在自由文本里，opt-out 默认照常接线；②定案维持 opt-out（初始化=一步到位），双通道修复：薄壳补开关参数映射指引段（sync_commands.py _SWITCH_HINTS/_switch_block）+ 渲染正文补用户意愿闸门句（步骤 2/4 开头）；③sync-commands 升级为必做步骤，措辞纠正为「只有 codebuddy 自动映射 MCP prompt 为命令，其余宿主都需 sync-commands」，CLI 宿主判定已自动化无需用户选；④locales zh/en 同步 description 与 args；⑤测试补 5 个断言用例，全量 1211 passed。本仓库薄壳已重新生成（.qoder/.trae 各 23 个）。

### 2026-09-30 22:23 #886d

任务管理适配 Qoder CN 完成（三项）：① SessionStart hook 弹框指引按宿主分支——`.qoder` 副本走 AskUserQuestion（单题 options 硬上限 4：最近 3 个 active 任务 + 跳过，其余任务写进 question 正文由「其他」自由输入承接，新建任务无需第二次弹框），其他宿主保持 ask_followup_question「一框列全」原文；② hook 命令解释器平台感知——`ide_config._resolve_python_cmd()`，Windows 恒 python、POSIX 按 python3>python 探测，并在 merge_settings_json/unwire 中把旧解释器命令原地迁移（含 `python -m codewiki.mcp._ide_hook` 尾部特征匹配）；③ 任务索引 `.index.json` 缺失/损坏/为空时回退扫描 `tasks/*/task.md` frontmatter，active 任务按 task.md+memories 最新 mtime 倒序。验证：全量 pytest 1226 passed / 1 skipped，ruff check+format 干净，真机 `install-hooks --ide qoder` 幂等 + `.qoder/hooks` 副本实测产出 4 选项合规弹框（9 个 active 任务）。下一步：变更尚未提交。

### 2026-09-30 22:54 #8s0x

OCR 委托评审自己的适配改动后修了确认项：capped 档（AskUserQuestion）只按硬上限 4 设计、漏了**硬下限 2**——0 个进行中任务时框里只剩「跳过」一项，弹框调用直接失败（新仓库首个会话最该引导建任务的那次）；现已在有空位时补「新建任务」选项，并把「进行中共 N 个任务…正文任务清单」那段挪进 `if rest:`（之它会悬空指着一个不存在的小节）。同时修了 label 截断撞车：同一前 12 字的长中文标题（task_id 由标题生成、换用 id 仍撞）改为撞车时逐步延长至可区分，因为 label 没有硬字符上限（只有 header 限 12）。`prompts.py` 的 task-workflow 与 AGENTS.md 引导段同步口径（硬上限 4 / 硬下限 2 / 补「新建任务」）。新增 3 条边界测试（选项数 0/1/2/3/4/9 任务、无悬空正文清单、label 唯一），全量 pytest 1229 passed，ruff 干净，.qoder 安装副本已重同步。Medium 「解释器快照写进共享 settings.json」未改行为，只在 ide_config.py 注释里钉下「换机/克隆后重跑 install-hooks 是每机一次」的口径；未提交。

### 2026-10-03 05:22 #pwbh

第二轮 OCR 复审后落的修正（定性比第一轮温和）：手工接线示例里的 `python` **不是 bug**——那些块是 ```powershell 语境（Windows 下 `python` 正确），真正缺的是平台提示。故只在 `codewiki/mcp/prompts.py` 三处补口径（手工接线示例段、模拟事件验证段、步骤 1 判「已启用」段：判据只看脚本相对路径后缀、不看解释器名），`docs/team-memory-hook.md` 前置条件改 `<python>` 并在命令路径段补「解释器是安装机快照 + 127 先看退出码再看接线档位」；去掉新任务选项 description 里嵌套的「」。未动：`ide_config.py:387` docstring 示例（纯示意后缀提取、无解释器语义）。待用户定：刷新本仓 `.codebuddy/` 接线（副本缺 ③ 回退、settings 仍为 `python` → 本机 127，但会改共享配置）。验证：全量 pytest 1229 passed / 1 skipped、targeted 128 passed、ruff check+format 干净、`.qoder` 副本与源 diff 为空、`_prompt_team_memory_hook` 渲染 10204 字符含新口径。仍未提交。

### 2026-10-03 10:10 #afid

get_prompt 工作流名缺口已修（选定「补实现不改契约」路线）：`_WORKFLOW_PROMPTS`（原 handler 函数体内的 prompts_map）提到 `codewiki/mcp/prompts.py` 模块级，成为工作流名→渲染函数唯一真源，新增 `workflow_prompt_names()` / `render_workflow_prompt()`；`handle_get_prompt` 接住 `name` 别名 + kebab/camel 两种写法，`prompt_type` 的 enum 由 `workflow_prompt_names()` 生成（模板类 23 + 工作流 23 = 46，不再手维护），`required` 清空，名字缺失/未知都返回模板类+工作流两份清单；同名时模板类精确优先（`code_analysis` 是模板、`code-analysis` 是工作流）；工作流分支把平铺的 repo_path/workspace_path 转发进 params（否则退回 cwd 指向别的仓库）。薄壳正文与 AGENTS.md 的 `get_prompt(name=...)` 写法一字未改——ADR-0017 契约本来就对，是实现少了一条通道，ADR-0017 末尾补「补充（2026-10-03）」段记录。验证：新增 `tests/test_get_prompt_tool_channel.py` 7 个用例，真机 stdio 冒烟（拉起 `python3 -m codewiki.mcp.server` 走 tools/list + tools/call）拿到 task-workflow 全文 5157 字符、repo_path 转发生效。同轮落了本仓 `.codebuddy/`+`.trae/` 接线刷新（install-hooks：settings/hooks.json 三条命令 python→python3，三份 hook 副本与源 diff 为空）。

### 2026-10-04 20:44 #scvp

第三轮 OCR 委托评审（get_prompt 工具通道那一轮改动）：13/13 文件全覆盖，4 条发现均确认并已修。最有价值的一条（Medium）：工作流分支最初只把平铺的 repo_path/workspace_path 转给构建器，其余平铺参数（action/url/name…）会被静默丢弃——要 action=status 却拿到默认接线指引，属静默错路；现提 `_workflow_params()`（prompt_server.py:364）平铺全量转发（工具 plumbing 键除外）+ 嵌套优先，且 `prompt_type` 已作标识符时把 `name` 归还构建器（remove-workspace-repo 的必填参数正好叫 name）。另外三条 Low：`arguments`/`variables` 非 dict 时在 try 外抛栈（改 isinstance 逐项合并）；新增缺名错误用了本文件唯一的中文运行时字符串（改回与 `Unknown prompt_type` 同构的英文）；新测试硬编码 `/tmp/...` 而 `_resolve_path` 走 `os.path.normpath`，Windows 必红（改用 `os.path.join(os.getcwd(), …)`，仓库已有平台安全例：tests/test_hook_registry.py:425）。真机 stdio 三路径复验全绿（嵌套/平铺/平铺 name），全量 pytest 1237 passed / 1 skipped，ruff 干净。仍未提交；热层 34/40 到压缩线。

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
