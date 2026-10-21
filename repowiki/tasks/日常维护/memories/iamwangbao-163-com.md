### 2026-10-19 16:12 #btz8

排查另一台电脑 MCP 接口超时（get_task_context / add_task_memory）：本机实测读 ~183ms、写 ~547ms，写路径大头是 atomic_write→auto_stage 的 git add 子进程（实测单次 ~400ms）。代码链路已确认：两工具不走 auto_push/CBM/sync_check；读路径成本 = notes 全量扫描（337 文件 ~75ms）+ aggregation 首次解析 schema（~95ms，有缓存）。本地量级远不到超时，结论是环境放大因素：①git add 在大仓/杀软扫描/网络盘上可放大到秒级；②git config user.email 解析 timeout=2s（无 pin 时每次新进程都要付）；③Windows 锁 LK_LOCK 最多阻塞 ~10s。下一步：让用户在另一台电脑跑分段计时脚本定位。

### 2026-10-20 18:28 #wllm

2026-10-20 完成「命令薄壳→技能薄壳」改造（ADR-0019）：新增 codewiki/cli/commands/sync_skills.py（`codewiki sync-skills`，23 条 MCP 工作流编译为 `<宿主>/skills/codewiki-<name>/SKILL.md`，frontmatter 三行 name/description/disable-model-invocation，中英双态走 _BODY_I18N）；sync_commands.py 按用户要求保留源码但不再注册 CLI。prompts.py 双副本常量化（_SYNC_SKILLS_STEP）、i18n 四处、CONTEXT.md 三术语、.gitignore 例外、46 个存量命令 git rm 暂存未提交（用户未要求 commit）。验证：聚焦 88 + 全量 1276 全过，okf 基线一致（120/6），ruff/mypy 干净。知识飞轮：新 decision 笔记已 confirm（strong，test_ref=tests/test_sync_skills.py），旧 codebuddy 豁免笔记已 deprecated。遗留：sync_commands.py 死代码处置待用户定夺。

### 2026-10-20 20:20 #o8k7

2026-10-20 「codewiki setup + codewiki-setup 技能」设计定案（经 grill-me 三轮拷问收敛，待开工）：
1) 新 CLI `codewiki setup`（codewiki/cli/commands/setup.py）三段式一键装机：hook 段（复用 install_for_ide，透传 --ide/--capture，无 IDE 目录则 SKIP 不失败）+ .mcp.json 段（恒写项目根一份，幂等合并保留其他 server、codewiki 键覆盖、非法 JSON 硬报错）+ skill 段（复用 sync-skills _render_all）；--repo-path 默认 .；--dry-run 只拦 .mcp.json 写盘、hook/skill 段打印计划；--lang zh|en 非必传，显式传则在 mcpServers.codewiki.env 写 CODEWIKI_LANG。任一段真失败 exit 1 不回滚。
2) `codewiki-setup` 独立技能：仓内静态真源两份（SKILL.zh.md/SKILL.en.md，随 pip 包分发），纳入 sync-skills 渲染集合（23 编译+1 静态拷贝），prune 自洽保留；frontmatter 三行同款 disable-model-invocation；正文两步 pip install --upgrade codewiki-plus（兜底 python -m pip；codewiki 命令不在 PATH 时兜底 python -m codewiki setup）→ codewiki setup；末尾指路 /codewiki-init-wiki。该技能将发布 skillhub，发布语言（zh/en）待发布时再定。
3) prompts.py 工作流不动；README 中英各补一句 setup 指引。验证：新建 tests/test_setup.py + sync-skills 静态资产断言，聚焦 pytest+ruff+mypy。

### 2026-10-21 09:16 #mdhe

2026-10-21「codewiki setup + codewiki-setup 技能」已落地（接 #o8k7 设计定案）：
- codewiki/cli/commands/setup.py 三段式（hook 段复用 install_for_ide / .mcp.json 幂等合并 / skill 段复用 sync_skills.sync_repo），已注册 main.py；.mcp.json server 配置按用户要求定为 README 口径完整形态（python -m codewiki.mcp.server + maxOutputLength 500000 + timeout 600000 + disabled false，--lang 才注入 env.CODEWIKI_LANG）。
- codewiki-setup 静态技能真源 codewiki/assets/skills/codewiki-setup/SKILL.zh|en.md（pyproject artifacts 已收录随包分发），纳入 sync-skills 渲染集合（23+1），prune 自洽；sync_skills.py 抽出公共 sync_repo。
- README 中英各补一键接线指引。验证：聚焦 41+9 全过，全量 1287 passed，ruff/mypy 干净，冒烟 .mcp.json 形态与 env 注入正确。未 commit（用户未要求）。发布 skillhub 的语言选择仍待用户发布时定。

### 2026-10-21 10:09 #4ky8

### 2026-10-21 10:10 #qdr1

Qoder 对话未落 repowiki/raw 的根因（已定位并修复，未提交）：Qoder SessionEnd 钩子本身正常触发且携带 transcript_path（已在 qoder-cn-agent-sdk 的 createCoreBaseInput 中确认载荷含 session_id/transcript_path/cwd/hook_event_name），但 Qoder transcript 是 JSONL，条目形如 {"type":"user","message":{"role":"user","content":[...]}}——role 嵌在 message 下。_ide_hook._load_transcript 按行原样返回后，capture_conversation._extract_transcript 只认顶层 role → 0 turns → 返回 "conversation contained no usable turns."；而 wrapper 的 detached 子进程 stdout/stderr 均为 DEVNULL，故完全静默。修复：codewiki/mcp/_ide_hook.py 新增 _normalize_transcript_entry（顶层 role 条目原样保留，兼容 Claude Code/Qoder 嵌套格式），在 JSONL 与 JSON 数组分支归一化；tests/test_ide_hook_capture.py 补单测 + Qoder E2E。验证：聚焦 41 passed，ruff/format 干净；真实 transcript 端到端在临时仓库采集到 160 turns/83KB。遗留：历史 Qoder 会话仍在 ~/.qoder-cn/projects/<repo>/<session>.jsonl，可按需回填；子进程 stderr 不可见属于可观测性缺口。

### 2026-10-21 10:19 #bkx5

2026-10-21 排查「raw 目录没抓到最近对话」：结论 SessionEnd hook 本身生效（10-21 10:00:37 成功落盘「发版本」会话，.index.json 可证）；10-15/10-19/10-20 会话缺失推测是会话非正常结束（IDE 直接关窗/进程被杀/关机）未触发 SessionEnd，或 detached 子进程未及落盘被终止——hook 是 fire-and-forget，无日志可查。%TEMP% 残留 tm-hook-*.json 均为 pytest sess-bom 夹具，非真实会话。顺带修复真实 bug：working_memory_content / manually_attached_skills 标签未在 _SYSTEM_INJECTION_TAGS 剥离清单中，导致抓取文件名 slug 与正文被工作记忆内容污染（capture_conversation.py 已加两标签 + 回归测试，9+80 测试全过，未 commit）。遗留：hook 链路无落盘日志，失败不可观测，可考虑给 wrapper/子进程加轻量日志。

### 2026-10-21 10:32 #nfl1

### 2026-10-21 10:35 #bf01

历史回填完成（接 #4ky8，其遗留项已处理）：Qoder 历史会话共 11 个 transcript，排除当前会话 ed14a297；c7be4d61（10-21 评审会话）已在 10:16 被修复后的实时 SessionEnd 自动采集（196 turns），回填返回 duplicate。其余 9 个已用修复后的解析链路批量补进 repowiki/raw/：866c3f80(265K,产品维护)、1ef499c7(750K,产品维护)、164a77b4(808K)、65a29a9b(180K)、60447e73(143K)、5161496d(24K)、fc9dd122(18K)、00d2597c(9K)、68bc772a(2K,测试会话)。raw 现有 11 条 pending，哈希全唯一，约 2.2MB。两个超大件（164a77b4 1824 轮 / 1ef499c7 1583 轮）蒸馏成本高，建议单独按需处理。注意：工作区存在一处并非本会话产生的改动（capture_conversation.py 新增 working_memory_content/manually_attached_skills 系统注入标签，10:17 出现），未动，提交前需确认归属。

### 2026-10-21 12:06 #e4rh

全量补蒸馏完成：11 条积压对话全部消化，产出 8 条草稿笔记（batch_ingest fail-open、MCP 显式 repo_path、Qoder 弹框硬约束、setup .mcp.json 口径、历史会话回填方法论、.format 字面占位符、架构审查基线、install-hooks 覆盖修复）。用户指令「确认所有笔记」已执行：28 条 draft 全部 confirm 为 stable（含历史积压 20 条）。过程中实证产品 bug：note_writer.py:156 用 text.find("---",3) 探测 frontmatter 闭合栅栏，title 值内含字面 --- 时误截断→YAML 解析失败→regex 回退把伪 status 行当真写回，confirm 返回 stable 但文件仍是 draft（静默失败）。已手工修复该笔记 title 并确认成功。待办：note_writer 栅栏探测需改为逐行扫描（跳过引号内 ---），或 YAML 解析失败时拒绝写入而非回退。

### 2026-10-21 13:58 #qooj

已修复 confirm_note 静默失败 bug：note_writer.py 两处 text.find("---",3) 朴素栅栏探测改为调用新增收敛函数 codewiki/src/frontmatter.py:find_frontmatter_end()（整行扫描，title 值内字面 --- 不再误截断）。回归测试 tests/test_frontmatter_roundtrip.py 新增 2 项（find_frontmatter_end 单元 + _apply_status_to_file 端到端），10/10 通过；test_backfill_note_authors 5/5 无回归；ruff 全过。注意：全仓 find("---",3) 同构写法共 31 处（evidence/doctrine/wiki_lint/close_session/source_ingest/page_manifest/note_query/note_lifecycle/note_consolidation），本次只修了实证 bug 所在的 note_writer 两处，其余待后续按收敛点逐步迁移。

### 2026-10-21 18:31 #cibq

2026-10-21 补蒸馏收尾：任务「日常维护」2 条积压（SessionEnd 采集排查会话、批量确认草稿会话）已由异步 distill-worker 清空，产出 2 条草稿笔记并经用户确认转 stable：①共享工作区多会话并行时提交必须用显式 pathspec，禁止 git add -A（lesson）；②confirm_note 静默失败根因 text.find("---",3) 栅栏误截断 + find_frontmatter_end() 收敛修复（pitfall）。另：蒸馏排序确认按 captured_at 升序（distill_conversation.py:363-385 _iter_raw_files，缺失 captured_at 视为最旧，同刻并列按 friction DESC）。skill_hint：笔记①命令密度 11 超阈值，是否编译成技能待用户定夺。
