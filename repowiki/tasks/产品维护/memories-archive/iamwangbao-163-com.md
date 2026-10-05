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

### 2026-10-03 05:23 #ur2w

> [superseded 2026-10-03 by #afid]

新缺陷（未修，待定口径）：命令薄壳与 AGENTS.md 都让 Agent 调 `get_prompt(name="task-workflow")`，但 codewiki 的 `get_prompt` 工具真参数是 `prompt_type`，枚举只含模板类（cluster/wiki_query/reflection 等 23 个），**不含 registry 里的工作流名**；本会话在 Qoder CN 实调 `prompt_type="team-memory-hook"` 直接被 schema 拒。registry 只由 MCP prompts 通道（prompts/list）+ `sync_commands` 消费，Qoder 已把它们呈现为 `/codewiki:任务记忆工作流` 命令。候选修法：① 薄壳正文改用宿主原生 prompts 口径（不再写 get_prompt 调用块）；② `handle_get_prompt` 兼容 `name` 并接 registry 名。待拍。

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
