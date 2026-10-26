## 早期记忆（摘要）

**竞品与外部调研结论：** GitHub 类似项目分三层——直接竞品 TencentDB Agent Memory（团队级四资产记忆中枢，与 CodeWiki 知识飞轮几乎一一对应，重点盯防/借鉴对象）；理念源头 Karpathy LLM Wiki 家族（对外表述类比）；通用记忆中间件 mem0/Letta/Zep/Cognee（设计参考）。腾讯云 Harness 文章（《AI写得快≠真正提效》）调研经 grill 评审定案：三项借鉴全部不立项——①PreToolUse 硬拦截→absorbed（claude-mem v13 反证 DENY 已被行业放弃，既有规划 P2-2 SessionStart 软闸门 + P2-1' 附加上下文已覆盖，文章仅作「软约束遵守度差」佐证）；②等待 skill→deferred（归「发版本」任务线，等 PyPI 生效验证）；③close-loop 闭环→excluded（依赖作者公司 CI/CD/工单系统，超产品边界，CodeWiki 只覆盖第八步知识复盘）。微借鉴一条：「不在中间任何一步静默停下」作为多步骤 prompt 写作原则。文章与知识飞轮高度同构处（成熟度分级、按类型衰减、弱/强信号双通道等）验证了方向；明确不借 Obsidian vault+REST API（CodeWiki 是 MCP 原生）与全量衰减高频扫描（lint 按需跑）。

**Prompt 正文原则（已定案）：** prompt 渲染正文只描述当前实现，不引用 ADR 编号、设计方案文档地址、历史决策变动（如「ADR-0002」「P1 C 线」「handler: source_ingest.py:741」）；Python 源码注释/docstring 里的 ADR 指针按惯例保留供维护者溯源。已按此清理 prompts.py 13 处渲染正文，测试 144 passed 无断言依赖。

**Windows 闪窗修复：** 根因是 MCP server 由 IDE 无控制台拉起，git 子进程新分配控制台窗口闪现。已在 git_sync.py 新增共享 helper windows_creationflags()（CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP，非 Windows 返回 0）并覆盖 run_git_bounded 及另外 4 处直接 subprocess 调用（config.py、doc_writer.py、note_query.py、workspace_bootstrap.py），加守门测试；MCP server 需重启生效。

**蒸馏与压缩闭环：** 产品维护任务蒸馏积压曾清零，3 条笔记确认 stable（MCP 参数长度受限时 submit 走文件侧通道 workaround、无知识密度对话提交空结果 architecture、doctrine SessionStart hook 硬注入 additionalContext 更新）。注意：本会话早前 2 条蒸馏草稿曾被用户拒绝（deprecated）。

**未决事项（P2 待办优先）：**
①MCP 工具面裁剪开关（P2，来自 agentmemory 调研 Round 2 grill 定案 2026-09-25，用户指示先存档不实施）：CODEWIKI_TOOLS=core 环境变量、registry 加 filter，60+ 工具 schema 全量注入占上下文是真缺口；参考 agentmemory 的 AGENTMEMORY_TOOLS=core（裁到 8 个）思路，须按本仓场景重定义核心集。依据：repowiki/wiki/queries/agentmemory-调研.md 第六节。
②distill-worker 是否加 model 字段换弱模型待用户决定——CodeBuddy subagent frontmatter 支持 model（默认跟随主 Agent），若改须同步随包源变体 codewiki/agents/distill-worker.md 与 claude 家族变体 distill-worker.claude.md（取值不同需分别写），且因 toolsMCP 教训需真机验证生效。
③可选深扒 TencentDB Agent Memory 架构与 CodeWiki 逐点对比；可执行 lint_wiki 验证压缩后 Wiki 健康度。

> 原文归档于 memories-archive/iamwangbao-163-com.md，截至 2026-10-10，共 1 条。

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

### 2026-10-05 21:55 #b0tu

任务管理适配 Qoder CN + get_prompt 工具通道接工作流名这两轮改动已于 2026-10-05 提交到 develop（1 个 commit，31 文件，含 .codebuddy/.qoder/.trae 接线刷新与 repowiki 知识层同步），working tree 干净，**未 push**（用户只说提交）。上一轮 #scvp 的「仍未提交」作废；其评审结论保留：第三轮 OCR 委托评审 13/13 覆盖、4 条发现全修（关键 Medium=平铺工作流参数被静默丢弃，现由 `_workflow_params()` 全量转发）。验证口径：全量 pytest 1237 passed / 1 skipped、ruff check 干净、真机 stdio 三种调用形状（薄壳嵌套/宿主平铺/平铺 name）全绿。剩余待办：历史草稿笔记仍积压未裁决（consolidate_notes 阈值 10，当前 notes_since=3 未到线）。

### 2026-10-05 21:59 #tse6

澄清宿主配置查找位置（2026-10-05 实测，否掉了「.qoder-cn 还要再适配一轮」这个潜在工作项）：Qoder CN 读**项目级 .qoder/**（不是 .qoder-cn/），本会话 [active-settle] UserPromptSubmit 注入即来自 .qoder/settings.json 的 `python3 -m codewiki.mcp._ide_hook`；~/.qoder-cn/settings.json **无 hooks 键**、~/.qoder-cn/hooks/ 不存在。~/.qoder-cn/ 只管**用户级**：mcp.json 与 settings.json.mcpServers 里的 codewiki（python3）就是当前连上的 53 工具那条（pid 94312 父进程 Qoder CN，cmd 为 python3 -m codewiki.mcp.server，证明项目 settings.json 里那条 Windows `.venv\Scripts\python.exe` 未生效）。同一项目 .qoder/ 被 5 个同源目录（.qoder/.qoder-cli/.qoder-cn/.qoderwork/.qoderworkcn，进程名相同）共用 → install-hooks --ide qoder 装一次全版本受益，不按版本分叉。

### 2026-10-08 17:23 #czyp

develop 已推至 81c5004（两条：734e3b4 任务管理适配 + get_prompt 工具通道；81c5004 工程技能接线文档）。遗留风险待定：`GLOSSARY.md` 以 **mode 120000 软链接**入库，Windows 无开发者模式时 core.symlinks=false，检出会退化为内容仅为字符串 `CONTEXT.md` 的普通文件，按 GLOSSARY.md 取词的工程技能读到空术语表。未拍板：改真文件+双写 / 保留现状接受退化 / 在 clone 前开 symlinks。

### 2026-10-09 09:22 #rlke

## hook 解释器口径改为跨平台回退（2026-10-08）

- **决策**：install-hooks 生成的三个 hook 命令从「按安装机平台快照单一解释器」（`_resolve_python_cmd`，Windows→python / mac→python3）改为固定 `python3 X || python X` 双解释器回退。删除 `_resolve_python_cmd`/`_PYTHON_CMD`。动机：settings.json 随仓库共享，快照口径导致换机反复 exit 127（本机 Windows 拉取 mac 生成的 python3 配置后三个 hook 全挂实锤）。安全前提已核实：三个 hook 脚本 fail-open 恒返回 0，`||` 不会二次执行。
- **同步改动**：.qoder/.codebuddy/.trae 三份已提交配置同步为回退形式（on-disk==生成产物→幂等）；测试改为回退形式断言、删解析器矩阵测试；prompts.py 与 docs/team-memory-hook.md 旧「按本机平台解析」口径更新。全量 1231 passed。
- **踩坑记录**：常量从 f-string 改普通字符串时误留 `{{ide_dir}}`，`.format()` 把 `{{` 还原为字面 `{`，占位符不展开 → `_relative_hook_suffix` 正则失配 → 13 条迁移测试失败。改单花括号修复。
- **同日另一修复**：codewiki MCP 在 Qoder user 作用域启动失败——全局 python 的 codewiki 是指向已删目录 D:\repos\CodeWiki-CN 的死 editable 安装；`~/.qoder-cn/settings.json` command 已改为 `D:\repos\CodeWiki-Plus\.venv\Scripts\python.exe` 绝对路径，`/mcp reload` 后恢复。
- **未落库**：变更在工作区未提交（develop），提交/推送待用户确认。

### 2026-10-09 09:27 #1of2

补蒸馏闭环（2026-10-09）：产品维护任务积压已清空（1 条 2026-09-29 raw 归档至 repowiki/conversations/）。蒸馏产出的 2 条草稿经用户确认落为 stable 笔记：①init 命令「否」失效根因与 opt-out 双通道修复定案（decision）；②宿主命令映射口径——仅 CodeBuddy 自动映射 MCP prompt，其余宿主需 sync-commands 薄壳（architecture，纠正 Trae 自动转化旧口径）。

### 2026-10-09 17:00 #7kn0

记忆压缩改为「无确认 + 异步子代理」派发式（用户定案 2026-10-09）：get_task_context 的 red 档不再内联待压缩条目正文（旧 compaction_work 把 25 条正文灌进主上下文，正是诱发确认框的原因），改携带轻指令 compaction_action（task_id/阈值/keep/summary_max_chars + 三步配方 + gate 明示无需确认），由异步 general-purpose 子代理自己调 compact_task_memories(mode=prepare) 取正文→写摘要→submit。orange/yellow 只报数不派发（防压缩频率失控）；写侧软上限 hint 去掉「consider compacting」劝喻式措辞。改动面：task_manager.py(_compaction_action/两处 hint)、registry.py 两处描述、prompts.py task-workflow 新增第 6 步 + 存储约束段、README 中英、CONTEXT.md、docs 三份（检索与自动压缩设计 D6 加修订记录、capability-matrix、退役与写入检查）、tests/test_task_memory_search.py 两个驱动测试重写。验证：全量 1231 passed/2 skipped、ruff 干净、进程内冒烟确认 red 触发且正文零泄漏。**子代理那一腿的实测第一轮暴露 4 个配方卡点（无 needed=false 停止分支、summary_max_chars 来源未说明、未交代按当前用户分片压缩、submit 未以 needed=true 为前提），已全部补进 dispatch；重载 MCP 后的复跑仍未完成**。

### 2026-10-10 17:10 #cfp6

user_id 漂移修复（B+C）已实施并真机验证（2026-10-10）：新增 `config.resolve_user_id(output_dir) -> (uid, source)`，新链 `CODEWIKI_USER` > 仓库本地身份钉 `repowiki/.meta/user_id`（gitignored、已登记 TEAM_LAYOUT_REBUILDABLE_FILES）> `git -C <output_dir> config user.email` > `user.name` > 机器缓存 > `os.getlogin()` > `local`；**只有 git 当场验证过的身份允许写钉/写缓存**（用户定案「git 优先于缓存」：本机 `~/.codewiki_user_id` 已被退化通道写成 Administrator，缓存再排在 git 前会把错误身份重新钉回克隆）。读钉时净化，防外部钉塞路径分隔符。6 处调用点全传 output_dir（task_manager/telemetry/note_ingest/capture_conversation/outcome_report×2）；C 可见性：get_task_context 与 add_task_memory 回显 `user`+`user_source`。文档口径同步：README 中英、分片方案 §4.2、团队知识库方案 §4.1、prompts.py 存储约束节、registry 两处工具描述。测试：新增 10 条（钉优于缓存与 git、首次派生写钉、退化通道继承、无 output_dir 仍可解析、恶意钉净化、git 盖过中毒缓存、纯缓存不写钉、登录名不写钉、回显字段、写进钉住分片）；`test_team_telemetry.TestUserId` 旧的标量缓存 mock 重写为 dict+lookup_dir 形参。验证：ruff check/format 干净；全量 1242 passed / 1 failed / 2 skipped（唯一失败 `test_locked_rmw_no_lost_update_under_threads` 单跑 17 passed，是 12 分钟负载下的 Windows 并发计时 flake，与本批无关）；/mcp reload 后真机 MCP 回显 `user=iamwangbao-163-com, user_source=pin`，退化模拟（剥缓存/git/登录名）也得同一 uid， Administrator 分片降为他人层。**重载服务进程后才会生效：旧服务进程缓存着旧版 config 模块，新代码导入 resolve_user_id 会失败（本轮实际撞过一次，add_task_memory 直接报错）**。待批准：D 存量合并（产品维护任务下 `memories/Administrator.md` 4.5KB 并入正主分片）与 `%USERPROFILE%\.codewiki_user_id` 残留清理，均未动。

### 2026-10-10 17:19 #e4ge

压缩子代理真机复跑完成并修掉它暴露的落盘缺陷（2026-10-10）：异步 general-purpose 子代理按 compaction_action 执行成功，产品维护热层 3 条归档进 memories-archive/iamwangbao-163-com.md、保留 20 条，全程无用户确认，未碰他人分片（Administrator.md 保持 4528B/7 条）。磁盘核验发现两个问题：①submit 总是前置 `## 早期记忆（摘要）`，而 prepare 返回的 existing_summary 本身带该标题，子代理整段粘回导致标题重复；②摘要正文含 `###` 子标题时被解析器当条目切走（热层实际解析出 21 条而非 20 条，memories_total 虚高）。已修：task_manager.py submit 分支加净化——caller 摘要以 _SUMMARY_HEADING 开头则剥掉（与既有读侧 :299/:783 同口径），并剥空后走「summary required」报错；compaction_action 第②步配方补充「existing_summary 是素材不是正文，摘要正文不得含 ##/### 标题行」。新增测试 test_compact_submit_does_not_double_the_summary_heading，tests/test_task_manager.py + test_task_memory_search.py 共 71 passed，ruff 干净（全量后台复跑中）。**遗留（不修，自愈）**：磁盘热层仍有本次留下的重复标题 + 被误当条目的 `### 本轮追加压缩` 块，因当前 21 条 < 40 条阈值且 21685B < 24576B，compaction_needed=false 无法再 submit 重写；下次真正触发压缩时 submit 会用净化后的摘要整体重写文件，重复块自然归位。另注意：`### 2026-08-26 会话蒸馏完成` 双份是 HEAD 里就存在的旧重复（近重复写入检查上线前的沉积），非本次压缩造成。**MCP 服务进程仍缓存旧模块，本次净化逻辑需 /mcp reload 才对 MCP 通道生效。**

### 2026-10-10 17:50 #zb6u

> [superseded 2026-10-10 by #1sfq]

D 存量修复 + 草稿处置完成（2026-10-10，用户批准「两个都做」）：①`memories/Administrator.md` 7 条经 `locked_rmw` 原样并入正主分片并删除该文件（幂等脚本、原文备份 .scratch/shard-backup-Administrator-*.md；`_stage_removal` 因 auto_push 与 auto_stage 互斥而 no-op，删除仅体现在工作区）；②污染的第二份机器缓存 `%USERPROFILE%/.codewiki_user_id`（内容 Administrator，旧退化通道 import 期写错路径）已备份到 .scratch 后删除——关键机理：`_USER_ID_CACHE_PATH` 在 **import 期**由 `APPDATA or expanduser(~)` 定死，所以两条通道读写的是两个不同文件，这就是「同一机器两个身份」的物理形态；③再压一轮（子代理遵新增格式纪律：正文不得含 ##/### 标题）：compressed 9 / kept 20 / memories_total 20，磁盘实测单一摘要标题、摘要无标题行——上轮重复标题与泄入摘要的 `###` 块已自然归位；④四条草稿全部改写/核验后 confirm_note(strong, evidence=test_ref)：user_id 漂移 pitfall（重写为 B+C+D 已实施口径、行号刷新 config.py:220/149/296、author 从 Administrator 改回正主 uid）+ 三条 2026-09-29（逐条对码核实：_CONVERTIBLE_SUFFIXES={pdf,docx,xlsx}、convert_error 三分类、sidecar 纯内存不在门落盘）；confirm 时误写了一个不存在的测试名作 test_ref，已改为真实的 `tests/test_source_convert.py::test_convertible_suffixes`。**待用户：全仓另有 15 条更旧草稿（多为 2026-09-20/21）未处置；`repowiki/.meta/telemetry/` 的 6 个历史身份分片未合并（D 菜单里未批准那部分）。顺带发现缺陷（未修，零运行时候影响）：`codewiki/mcp/tools/source_ingest.py:321` 有一个只有 docstring 的 `_convert_to_markdown` 空壳，被 :333 的真实现同名遮蔽（先别动，需确认来源是不是合并事故）。工作区全部未提交。

### 本轮追加压缩（截至 2026-10-05，原文归档于 memories-archive/iamwangbao-163-com.md）

**auto_push 链路（核心事实，codewiki/src/git_sync.py）：**
- 核心逻辑 auto_push()：_resolve_auto_push 读 schema.yaml conventions.git_sync.auto_push（默认 False，本仓库已开 true）；auto_push 开启时 auto_stage 自动失效（互斥）。
- 执行顺序：暂存区守卫 → git add -A 只暂存 repowiki/ 子树 → unstage .lck → 用仓库现有 git 身份 commit（message 前缀 codewiki:）→ 无 upstream 则跳过推送保留本地提交 → push 失败走 fetch+rebase 重试≤5 次（冲突 abort），永不 force-push/reset，失败保留本地提交下次搭载（D12 失败契约）。
- 触发锚点两类：handler 自带（close_session/capture_conversation/distill_conversation/batch_ingest/ingest_note/write_doc_file）+ registry.py _PUSH_ON_WRITE 的 12 个工具由 dispatch() 经 auto_push_into_result 统一收口；batch_ingest 用 defer_push() 抑制子项推送、批边界只推一次。

**auto_push 预暂存守卫重构（已定案）：**
- 根因：原守卫在暂存区存在用户手动 add 的任何内容时整体中止 auto_push，导致频繁静默跳过（用户反馈「经常没提交推送」）；force-push 诉求被否决（D10「永不 force」，改写远端历史危及他人提交）。
- 修复：改为路径限定提交 `git commit -m msg -- <repowiki/>`，只提交知识子树；用户暂存的业务文件留在暂存区、不被卷入也不阻塞同步；子树内用户暂存的知识内容随行（已接受）。相关测试改写通过（12+11）；MCP server 需重启生效。

**get_prompt 工具通道 OCR 评审（条目 #scvp，已被 #b0tu supersede，结论以热层为准）：**
- 第三轮委托评审 13/13 文件全覆盖，4 条发现均确认并已修。最关键（Medium）：workflow 分支最初只把平铺的 repo_path/workspace_path 转给构建器，其余平铺参数（action/url/name 等）被静默丢弃（静默错路）；修复为 `_workflow_params()`（prompt_server.py:364）平铺全量转发（工具 plumbing 键除外）+ 嵌套优先，且 `prompt_type` 已作标识符时把 `name` 归还构建器（remove-workspace-repo 必填参数正是 name）。
- 三条 Low 教训：arguments/variables 非 dict 时在 try 外抛栈（改 isinstance 逐项合并）；新增错误字符串须与同文件既有英文报错（`Unknown prompt_type`）同构，不留中文运行时字符串；断言涉及路径的测试硬编码 `/tmp/...` 在 Windows（_resolve_path 走 normpath）必红，须用 os.path.join(os.getcwd(), …)。真机 stdio 三路径复验全绿，全量 pytest 1237 passed/1 skipped，ruff 干净；当时未提交。

> 原文归档于 memories-archive/iamwangbao-163-com.md，截至 2026-10-10，共 3 条。

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

### 2026-10-10 17:56 #1sfq

D + 草稿处置完成，但压缩那一段的结论需修正（2026-10-10，supersedes #zb6u）：①D1/D2 均已完成并实测——`memories/Administrator.md` 7 条经 `locked_rmw` 原样并入正主分片后删文件（备份 .scratch/shard-backup-Administrator-*.md，git 索引已记 D）；`%USERPROFILE%/.codewiki_user_id`（内容 Administrator）备份后删——机理：`_USER_ID_CACHE_PATH` 在 **import 期**由 `APPDATA or expanduser(~)` 定死（config.py:220），两条通道以不同进程环境初始化就会读写两个不同文件，这就是同机双身份的物理形态；healthy/无钉/degraded/MCP 四格均 `iamwangbao-163-com`（pin / git-email / pin / pin）。②四条草稿全部 confirm_note(strong, evidence=test_ref)，逐条对码核实过；我自己写错的假测试名已改回真实的 `tests/test_source_convert.py::test_convertible_suffixes`。③压缩腿：第二轮 compressed 1 / kept 20 / memories_total 20，磁盘实测单一摘要标题、摘要正文无标题行——**但「泄入摘要的 ### 块已自然归位」那句错了**：那个 `### 本轮追加压缩（截至 2026-10-05…）` 块仍在热层（现 :92），与两份重复的 `### 2026-08-26 会话蒸馏完成` 一起成为**永不可压的死重**：`entry_sort_key`（store.py:327）把无时间戳条目排到最后（(1,"")），而 `_split_compaction` 只从最旧端取 compress，所以无日期条目永远落在 keep 窗口内——后果是分片卡在 27391B > 24576B 字节线上，每追加一条就立刻重新触发一次只能吞 1 条真日期的压缩（抖动）。待批准的两个动作：（一）`_split_compaction` 把无日期条目提到 superseded 之后、有日期条目之前优先 compress（语义变化：keep 窗口成员判定不再纯按时间）；（二）一次性用 locked_rmw 将现存三块无日期死重先归档再从热层 dropping。另：archive 里同一时间戳标题最多重复 10 次（历史 legacy 收敛反复重归档，append-only 设计容忍），本轮未动。全仓仍有 15 条更旧草稿（09-20×9、09-21×2、09-22/10-05/10-09 各若干）与 telemetry 6 个历史身份分片未处置；`source_ingest.py:321` 只有 docstring 的 `_convert_to_markdown` 空壳被 :333 同名遮蔽（未修，零运行时影响）。工作区全部未提交；本轮代码改动需 /mcp reload 才对 MCP 通道生效。

### 2026-10-10 18:16 #mrvt

OCR 委托评审完成（2026-10-10，工作区 13 个可审文件，覆盖率 13/13=100%，未做任何修改——用户只要求「审查代码」）。发现 1 中 2 低：①**Medium/bug**：压缩派发指令缺 repo_path——`task_manager.py:1164 _compaction_action(task_id)` 的三步配方和 `prompts.py:1381` 步骤 6 的示例调用都只带 task_id，而 `handle_compact_task_memories:1260-1265` 在无 session 且无 repo_path 时直接返回 `repo_path is required` 错误；异步子代理是全新上下文、唯一信息来源就是这条指令，按字面执行必失败（本轮我自己派发时是手工补的 repo_path，即旁证）。修法：`_compaction_action(output_dir, task_id)` 带上仓库根（output_dir.parent），配方写 `repo_path=<仓库根>`，prompts.py 用现成的 `{repo_path}` 插值同步。②Low：`config.py:226-233` `_read_user_id_cache` docstring 仍称「避免每次冷启动跑 git 子进程」，新链路里缓存已降到 git 之后（只在 git 不可用时兜底），注释与行为矛盾。③Low（未复现，需确认）：`ide_config.py:142-147` 的 `python3 X || python X`——Windows 上 python3 若命中 Microsoft Store 执行别名，横幅走 stdout 且非零退出，UserPromptSubmit 分支（stdout 被宿主机器解析）会拼接噪声；本机根本无 python3 故无法复现。核验通过的点：三个 JSON 的 9 处 command 与常量逐字一致（不产生重复注册）；.gitignore 的 repowiki/.meta/user_id 与 gitignore_entries() 生成式一致且 check-ignore 命中；删掉的 _resolve_python_cmd/_PYTHON_CMD 全仓无残留、os/shutil 非死导入；_relative_hook_suffix 与 _is_codewiki_prompt_cmd 对新命令仍能识别并迁移历史条目；task_manager 引用的 SUMMARY_HEADING/_COMPACTION_* 常量全部存在（不会 NameError），_prepare_compaction_payload 仍被 :1297 使用（非死代码）；全仓已无 user_id() 无参调用点。越界提示（md 不在 OCR 范围）：docs/任务记忆退役与写入检查设计方案.md:23 仍写内联 compaction_work 与旧行号。

### 2026-10-12 11:09 #fho7

提交完成（2026-10-10，用户批准「先修 Medium 再提交」+「按主题拆 3 个提交」）：develop 上三个本地提交，**未推送**。f285ec2 feat: 压缩免确认异步派发 + 身份解析接仓库本地钉（17 files，+542/-178：9 个 codewiki py + 4 tests + 3 宿主 settings + .gitignore）；2a06db6 docs: 设计文档同步口径（8 files：CONTEXT/README + 6 个设计文档）；65a7a66 chore(repowiki): 知识沉淀（15 files，含6 条新 note 入库、memories/Administrator.md 删除）。提交前提交后实证：ruff check/format 全干净；两个相关测试文件 71 passed；全量 pytest 1244 passed / 2 skipped（12m28s，exit 0）——skip 数比早前记录多 1，但在我未改动的文件里（这两个文件本次 0 skip）。Medium 修法落地：_compaction_action(task_id, repo_path) 把调用方自己的 repo_path 回显进配方①③两处 + 一句「子代理无会话上下文」说明，prompts 步骤 6 用 {repo_path} 插值同步，测试加 4 条断言钉住。遗留未入库（等用户点头）：uv.lock +879/-3（markitdown 可选依赖 43 个包的补锁，pyproject 未变，建议单独 chore 提交便于单独 revert）；.scratch/ 47 个未忽略的一次性发布脚本与结果文件（含两份身份备份）——选项是删或加 .gitignore 规则；docs/articles/终结篇.md + images/ 约 20 张图（更早遗留）；repowiki/conversations/ 3 个未蒸馏 raw。代码改动需用户 /mcp reload 才在 MCP 通道生效。

### 2026-10-12 11:25 #is5r

遗留两项已按用户口径处置（2026-10-12）：dfb88b3 chore: .gitignore 忽略 .scratch **顶层散文件**——不能整目录忽略！本仓约定 .scratch/<feature>/issues/*.md 是内部工单区呓 18 个文件已跟踪，故规则为 `.scratch/*` + 反选 `!.scratch/*/`（磁盘已验：18 个工单文件不受影响、子目录新建文件仍显示未跟踪、顶层 47 个 ?? 归 0）。e3ec267 chore: uv.lock 补齐 markitdown 可选 extra 的 43 个传递依赖（pyproject 未变）。develop 现共 5 个本地提交未推送。工作区仍剩 3 个 repowiki 待提交项：子代理派发自包含草稿（**待用户 confirm/reject，确认前不入库**）、#fho7 后的分片增量、wiki log。

### 2026-10-12 11:26 #26g3

收尾（2026-10-12）：上一条 #is5r 里“待提交 3 项”已按用户「提交」入库——子代理派发自包含 lesson 草稿仍为 status: draft（文件入库不等于晋升，待用户 confirm/reject）、任务分片含 #fho7/#is5r 本轮新增、wiki log 同步。commit 后 develop 共 6 个本地提交未推送；工作区只剩 3 个未跟踪 raw 对话与 docs/articles 终结篇旧遗留（都按用户口径不动）。

### 2026-10-12 11:34 #nqvc

本轮 OCR 委托评审闭环已推送：6 个提交（f285ec2..99e4ec0）push 到 origin/develop（81c5004..99e4ec0，fast-forward），Medium 缺陷「压缩派发指令缺 repo_path」的修复随之上线；工作区已跟踪改动归 0，未跟踪仅剩 3 个 repowiki/conversations raw 暂存件。另记一笔待决事项：未跟踪的 docs/articles/CodeWiki-Plus终结篇….md、docs/articles/images/、根目录 vibe_images/ 于 2026-10-12 11:24 被移入 Windows 回收站（非 git 动作，git 从未跟踪过这三者，IDE 本地历史零命中），回收站里仍在、可整件还原，是否恢复待用户决定。

### 2026-10-26 10:25 #nyek

2026-10-26：ADR-0020 P1-3 算子计划链路已实现并通过聚焦测试；随后按 incremental-update 工作流完成 Wiki 增量更新，KnowledgeStore / MCP_Tools_DocWriter / MCP_Tools_Knowledge / MCP_Tools_Quality / MCP_Tools_Workspace 五页重写并重打整文件证据，lint_wiki(stale_refs+stale_evidence) 0 issue，close_session 后 job=done。下一步：提交并推送这批代码+Wiki 变更；另有 13 条 draft 笔记待用户确认后再 batch_set_status 提升。
