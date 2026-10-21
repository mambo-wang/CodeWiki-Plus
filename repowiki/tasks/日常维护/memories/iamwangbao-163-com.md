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
