### 2026-10-13 09:50 #6op7

已确认 Trae 项目级 Hook 配置方式（官方文档+本机实证）：个人版与企业版项目级均为 `$PROJECT_FOLDER/.trae/hooks.json`（可在 设置>Hooks>项目 由 IDE 创建，或手写）；差异仅在全局 Hook 用户目录：个人版 `~/.trae-cn/hooks.json`（Win: `%userprofile%/.trae-cn/hooks.json`），企业版 `%userprofile%/.trae-cn-enterprise/hooks.json`（本机实测存在）。格式 version=1 + hooks.<EventName> 数组，6 事件：SessionStart/UserPromptSubmit/PreToolUse/PostToolUse/Stop/Notification；stdin 收 JSON、stdout/退出码控流程；多项目根与 Claude Code 配置均合并执行。本仓库 .trae/hooks.json 即企业版项目级活例（SessionStart/Stop/UserPromptSubmit 三事件）。

### 2026-10-13 09:58 #9faa

【调试根因】.trae/hooks.json 三条 hook 在 Windows 上从未触发：Trae Windows 用 PowerShell 跑 hook（本机 5.1），命令里的 `python3 ... || python ...` 中 `||` 是 PS5.1 解析期错误 → 整条命令不执行；且本机无 python3 只有 python 3.14.5。佐证：本会话开场无 SessionStart 注入。修复：三条命令改为直接 `python ...`，模拟 Trae 事件逐一验证通过（SessionStart 注入任务关联文本、UserPromptSubmit 注入 [active-settle]、Stop 正常拉起后台采集）。遗留：①Trae Stop 事件不含 transcript_path → 采集必然空跑（_ide_hook.py 已知平台差异，envelope 不再落盘）；②SessionStart 注入文本是 CodeBuddy 风味（ask_followup_question + 一框列全 12 选项），与 Trae AskUserQuestion 硬上限 4 选项不匹配——Trae适配任务待办。另创建 .claude/settings.json（纯 Claude 格式同样三条 hook）测 Trae 导入兼容，需用户在 设置>Hooks>项目 打开「导入 CLAUDE 中的 Hooks 配置」开关；两配置并存会合并执行导致 SessionStart 双份注入。

### 2026-10-13 10:21 #0f4w

【capped 修复完成】SessionStart 注入文案宿主分档：_chooser_channel() 改为 IDE_DIR_NAME in ('.qoder', '.trae')，改了包内源副本 codewiki/hooks/task_session_start.py 与本仓库 .trae/hooks/ 安装副本（.codebuddy 无限档本就正确、.qoder 靠目录名已命中 capped，均无需动）；空 stdin 模拟验证输出已切到「选项 4 个以内」分支：3 任务+跳过进选项、7 任务进正文清单。遗留：另两个安装副本与源副本是否整体同源未核对。

【|| 根因定位】python3 ... || python ... 模板来自包源码 codewiki/cli/utils/ide_config.py:141-151（START/END/PROMPT_HOOK_CMD 三处），是 2026-09-30 Qoder CN 定案的跨机器可移植方案（settings.json 随仓共享：mac 只有 python3、Windows 只有 python，|| 靠 exit 127 兜底）。该方案假设 POSIX shell 语义，而 Trae Windows 用 PowerShell 5.1 跑 hook，|| 是解析期错误整条不执行——本地手改 .trae/hooks.json 只是创可贴，install-hooks/迁移会重新生成 || 命令复活问题。待决：Trae 家族命令模板形态（平台快照单解释器 vs PowerShell 原生兜底 vs cmd /c 包裹）；改动须同步更新 tests/test_install_hooks.py:725-742 的 || 钉板断言。

### 2026-10-13 10:36 #xnie

【Trae 命令模板修复完成】方案选定「平台快照单解释器」并落地：ide_config.py 新增 _trae_hook_commands()（os.name=='nt'→python，否则 python3；_TRAE_START/END/PROMPT_HOOK_CMD 三模板），merge_settings_json 加 prompt_cmd 参数（默认 PROMPT_HOOK_CMD，claude 家族行为不变），wire_ide 按 spec.format=='trae' 分档。迁移/识别逻辑零改动即可兼容：_relative_hook_suffix 锚定命令尾部相对脚本路径、_is_codewiki_prompt_cmd 按 -m 尾部特征，历史 || 毒命令重跑 install-hooks 自动原地迁移（保留 timeout）。测试：test_install_trae_writes_hooks_json 改钉 trae 三命令、新增 test_trae_hook_commands_single_interpreter_no_shell_fallback（monkeypatch os.name 双平台）与 test_merge_trae_migrates_shell_fallback_commands_in_place、test_wiring_matrix 的 prompt 断言改尾部特征；82 全过。真实仓库 install-hooks --ide trae 幂等 no-change。prompts.py 无需改（TRAE 变体示例本就是单解释器按平台替换）。遗留：①.trae/hooks.json 跨平台共享时 mac 机需重跑 install-hooks 迁回 python3（已知代价，迁移自动）；②Trae Stop 无 transcript_path 采集空跑问题未动；③.qoder/.codebuddy 安装副本与包内源副本是否整体同源未核对。

### 2026-10-13 11:43 #t7cj

完成今日 3 提交（dc962ed/9dc4035/1620d10，HEAD~3..HEAD）的变更评估与代码评审。核心变更：Trae Windows hook 命令修复（ide_config.py 平台适配生成纯 python 命令）+ hook 四副本同步（SHA256 一致已验证）+ schema.yaml 笔记类型晋升/合并扩展。回归测试 142 个全绿。评审结论：无 blocker；2 个遗留问题——R1(minor) schema.yaml 头部注释块被 round-trip 序列化静默丢失（语义对比确认无值删除，纯增量），R2(nit) 全文件重排造成 575 行噪声 diff，同根因。建议后续排查是哪个工具用 yaml load→dump 重写了 schema.yaml。报告已存 .codewiki/workspace/review_reports/20261013-114340-*.json。
