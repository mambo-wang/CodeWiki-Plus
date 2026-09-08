---
type: Scenario
title: IDE-Hook采集链路方法
description: hook 同步采集异步蒸馏、多宿主家族分发变体、MCP 不透传自定义子代理、hook 防御清单与 stdin BOM、非交互装技能
tags:
- CodeWiki-CN
generated:
  by: codewiki/5.8.0
  at: 2026-09-08 05:55:03+00:00
stale_after: 2026-12-07
aliases:
- IDE-Hook采集链路方法
status: stable
metadata:
  generated_from: f08feab
  resource: repo://CodeWiki-CN
  code_fingerprint: sha256:829467a7f49459ddf16d1711753a335b7338eb7409360e8d30565d9f78d11621
  source_notes:
  - notes/2026-08-29-subagent-定义的-frontmatter-按宿主家族分发同名文件不同-schema.md
  - notes/2026-09-04-agent-hook-注入的工程化防御与防漂移可复用模式caveman-提炼.md
  - notes/2026-09-04-在-codebuddy-使用跨-agent-技能纯-skillmd-直接装-codebuddyskillshooks-需.md
  - notes/2026-09-07-npx-skills-add-非交互环境停-tui用--y-跳过-a-指定-agentuniversal-目录始终落盘.md
  - notes/2026-09-07-powershell-管道给-stdin-注入-utf-8-bom-致-jsonloads-失败stdin-解码须-ut.md
  summary: 补入多宿主家族分发变体、MCP 不透传自定义子代理的绕法、hook 防御清单与 stdin BOM 容错
  heat: 4
---
## 工作场景
IDE hook 采集链路（capture_session_end.py → _ide_hook.py → capture_conversation）、subagent 定义分发与跨 Agent 技能安装。适用于开发/排查 IDE 对话采集、hook 注入引导、多宿主 subagent 与技能分发。

## 适用条件
改 hook 脚本、排查「会话结束未归档」、部署蒸馏 subagent、把同一份配置/技能分发到多个 IDE 家族、非交互环境装技能。

## 核心 SOP
1. 读 IDE transcript 先识别格式：index.json 的 messages 只有元数据且存在 messages/ 兄弟目录时，逐个读 `messages/<id>.json`（索引+分片结构）。
2. hook 执行模型「同步采集 + 异步蒸馏」：hook 只落 raw（subprocess.run timeout=60），LLM 蒸馏永远显式后台触发。
3. 改 hook 先改源副本（`codewiki/hooks/`）再同步项目副本。
4. hook 注入引导写硬性执行顺序 + 直接注入任务标题/task_id，软措辞不可靠。
5. 多 IDE 支持按家族归并：hooks.yaml 三家族 + 事件名映射表 + 安装探测，接线由 IDE_SPECS 驱动。
6. 配置合并用 `copy.deepcopy`；`hooks.get(event, [])` 取值后必须写回。
7. hook 采集机制仅正式接线 CodeBuddy（底层已兼容 Claude Code），README 用「仅接线支持」措辞；扩展只需生成对应 settings.json 注册同一批 wrapper。
8. distill-worker.md 权威版本存 `codewiki/agents/`（随包发布），hook 启用时自动拷贝到 `.codebuddy/agents/`；pyproject package-data 须声明 `"agents/*.md"`。
9. **多宿主分发按家族发变体**：CodeBuddy 认 `tools: ReadFile` + `toolsMCP` 等私有字段，claude 家族（Qoder/Claude Code/Gemini CLI）认 `name/description` + 可选 tools，喂错家族解析出空工具集直接拒绝加载；目标文件名恒定，变体缺失回退默认源（降级不断线）。同名 ≠ 同 schema，同 schema ≠ 同权限模型，两层都要实测。
10. **MCP 不透传自定义子代理**：claude 家族变体省略 tools 行（继承最稳），不要枚举 `mcp__` 限定名；确需 MCP 时改 spawn 宿主**内置** general-purpose 子代理、以 distill-worker.md 正文当剧本。验证用子代理自己的 `mcp_list`；改完定义必须新开会话（subagent 注册表是启动时快照）。
11. **hook 防御清单**：规则单事实源 + 运行时读取注入（不硬编码拷贝）；`requireSibling()` 校验兄弟模块形状、缺失降级；stdin 加 watchdog + unref 防挂起；按首个完整 JSON 触发而非等 EOF（Windows 管道 close 延迟）；hook 永不非零退出；fail-open 优先；per-session 状态而非全局标志；SessionStart 对 compact/resume 也重注入（防压缩后行为漂移）+ UserPromptSubmit 每轮轻提醒。
12. **stdin 解码一律 `utf-8-sig` + `lstrip("\ufeff")`**（PowerShell 管道可能注入多个 BOM）；验证 hook 优先用 `--conversation <file>` 文件方式而非管道。
13. **非交互装技能**：`npx skills add` 加 `-y` 跳过 TUI、`-a codebuddy` 指定 agent；Universal 目录 `~/.agents/skills/` 始终落盘（TUI 未完成也已安装）；纯 SKILL.md 技能可直接复制到 `~/.codebuddy/skills/<id>/`，新会话生效（无 hook 时档位状态不持久化，压缩后可能漂移需重说一次）。

## 判断逻辑
- transcript 噪声只保留 user/assistant；SessionEnd envelope 用 user 角色（system 会被静默丢弃）。
- 注入系统三类失效：规则漂移（两处拷贝/被压缩剪掉）、进程脆弱（缺文件/管道延迟）、资源浪费（全量注入超预算）——防御要逐条对应。
- 多宿主分发不能假设宿主能力一致，按家族裁剪而非共用一份。

## 禁忌与反模式
- 块剥离正则不要用 `^[ \t]*` 行首锚点（捕获层可能给行加角色前缀）。
- 不手工复制 distill-worker.md 到各项目（版本漂移），走随包发布自动拷贝。
- 不把 CodeBuddy 版 frontmatter 喂给 claude 家族宿主。
- 不只看 spawn 成功就认为 MCP 可用。

## 关键事实依据
- transcript_path 指向 index.json（仅元数据），真实内容在 `messages/<id>.json`。
- 31 个智能体可收敛为 3 家族 schema。
- BOM 事故根因是主路径与 wrapper 的 stdin 防御不对齐（已补 `test_stdin_utf8_bom_tolerated`）。