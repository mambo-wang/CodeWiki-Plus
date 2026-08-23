---
name: multi-ide-hook-wiring
overview: 把 CodeWiki 的 hook/subagent 接线从「仅支持 CodeBuddy」扩展为支持 Qoder 与 Claude Code：用户在既有「创建/启用 hook」流程触发时，自动检测项目根目录存在的智能体配置目录（.codebuddy/.qoder/.claude），为检测到的每个智能体生成对应 hook 注册 + 拷贝脚本 + AGENTS.md 引导段。
todos:
  - id: ide-config-module
    content: 新建 codewiki/cli/utils/ide_config.py：IDE_SPECS 注册表、detect_ide_dirs 自动检测、merge_settings_json 幂等合并、upsert_agents_section、源副本路径解析与脚本拷贝
    status: completed
  - id: install-hooks-command
    content: 新建 install_hooks.py Click 命令（默认自动检测 / --ide / --repo-path），在 cli/main.py 与 commands/__init__.py 注册，输出接线摘要
    status: completed
    dependencies:
      - ide-config-module
  - id: prompt-update
    content: 改造 prompts.py 的 _prompt_init_wiki 与 _prompt_team_memory_hook：首选 codewiki install-hooks 自动检测接线，兜底手动步骤覆盖 Qoder/Claude Code 路径差异
    status: completed
  - id: tests
    content: 新增 tests/test_install_hooks.py：检测逻辑、settings.json 合并去重幂等、端到端接线（tmp_path 假仓库）、默认自动检测与 --ide 模式、重复运行幂等，跑通全部测试
    status: completed
    dependencies:
      - ide-config-module
      - install-hooks-command
  - id: docs-sync
    content: 同步 README 中英措辞、codewiki/hooks/__init__.py docstring、repowiki CLI/MCP 文档章节
    status: completed
    dependencies:
      - install-hooks-command
      - prompt-update
  - id: knowledge-archive
    content: 用 [mcp:codewiki] ingest_note 归档多 IDE 自动检测接线决策，并向用户展示蒸馏 pending 记忆经 confirm_task_memories 确认落盘
    status: completed
    dependencies:
      - docs-sync
---

## 产品概述

将 CodeWiki 的任务记忆 hook/subagent 接线从「仅支持 CodeBuddy」扩展为支持市面上常见智能体（Qoder、Claude Code）。用户触发创建/启用 hook 时，自动检测项目根目录存在哪些智能体配置目录（.codebuddy/.qoder/.claude），检测到哪些就为哪些自动生成 hook 注册与 subagent 定义，无需用户指定。

## 核心功能

- 新增 `codewiki install-hooks` CLI 命令，**默认即自动检测**：
- 无参数运行：扫描项目根目录，自动检测 `.codebuddy/.qoder/.claude` 中存在哪些 IDE 配置目录，为每个检测到的智能体接线（有哪些就创建对应 hook）
- `--ide <name>`：跳过检测，仅接线指定智能体（codebuddy / qoder / claude-code），用于精确控制
- `--repo-path`：指定目标项目路径（默认当前目录）
- 每个智能体接线内容：
- 从 codewiki 包内源副本强制拷贝 `capture_session_end.py`、`task_session_start.py` 到 `<repo>/.<ide>/hooks/`，拷贝 `distill-worker.md` 到 `<repo>/.<ide>/agents/`
- 合并写入 `<repo>/.<ide>/settings.json` 的 SessionStart/SessionEnd hook 注册（保留已有无关配置，按 command 去重幂等）
- 向 `AGENTS.md` 写入任务记忆引导段（幂等，只动 `TEAM-MEMORY-TASK` 标记块；多 IDE 共享同一仓库只写一份）
- 扩展 MCP prompt `team-memory-hook` 与 `init-wiki`：用户触发创建/启用 hook 时**首选自动检测接线**——引导运行 `codewiki install-hooks`（无需指定 IDE，检测到哪些就接线哪些）；CLI 不可用时回退到手动步骤，并给出各 IDE 的 settings.json 路径差异说明
- 同步 README 中英「仅接线支持 CodeBuddy」措辞为支持 CodeBuddy + Qoder + Claude Code（自动检测接线）
- 新增 pytest 测试覆盖：IDE 检测、settings.json 合并、幂等性、AGENTS.md 标记块写入、重复运行幂等

## 边界说明

- 不含 Cursor/Windsurf/Trae（无 hooks 机制，用户已确认排除）
- Qoder 的 agents 子目录格式为尽力兼容：hooks 接线完全支持；distill-worker.md 拷贝为 best-effort，若 IDE 不解析则忽略不影响主流程
- 自动检测是默认行为而非可选开关；`--ide` 仅用于显式指定

## 技术栈

- Python 3.12 + Click（复用现有 CLI 框架，入口 `codewiki.cli.main:cli`）
- 复用现有源副本：`codewiki/hooks/capture_session_end.py`、`codewiki/hooks/task_session_start.py`、`codewiki/agents/distill-worker.md`（已随包发布，pyproject.toml 已含 `codewiki.hooks` 包与 `agents/*.md` package-data，无需改打包配置）
- 测试：pytest（现有 tests/ 目录约定）

## 实现方案

### 核心策略

新增「IDE 接线注册表 + 通用接线执行器」：将 IDE 差异（配置目录、settings.json 事件注册、agents 目录、事件 matcher）收敛为数据表，CLI 命令与 prompt 共用同一套接线逻辑，避免 CodeBuddy 专属逻辑散落。核心复用点：

- hook 脚本本身已做 CodeBuddy/Claude-Code 通用载荷解析（`transcript_path` 内联 turns 兜底、`CLAUDE_PROJECT_DIR` 回退、`CODEBUDDY_PROJECT_DIR`），接线层只需生成对应 IDE 的 settings.json 注册文件，无需改脚本本体
- 三个 IDE 的 hooks 事件格式一致（`SessionStart` matcher=`startup`、`SessionEnd` matcher=`other`），仅配置目录不同：`.codebuddy/` / `.qoder/` / `.claude/`
- **自动检测为默认路径**：`install-hooks` 无参运行时即调用 `detect_ide_dirs()`，按 IDE_SPECS 顺序扫描根目录，检测到哪些目录就为哪些 IDE 接线——正是「用户触发创建 hook 时自动检测智能体类型，有哪些智能体就创建对应 hook」

### 关键设计决策

1. **IDE 注册表驱动**：`IDE_SPECS` 字典定义每个 IDE 的目录名、settings.json 文件名、agents 子目录、是否拷贝 distill-worker。新增一个 IDE 只需加一行数据，天然可扩展
2. **settings.json 幂等合并**：读现有文件 → 深合并 `hooks` 段（按 command 去重，避免重复注册）→ 原子写回（临时文件 + `os.replace`，与任务记忆写入同模式）；保留文件内所有与 CodeWiki 无关的既有配置
3. **AGENTS.md 标记块写入**：复用 prompts.py 的 `_TASK_MEMORY_AGENTS_SECTION` 常量逻辑——已存在 START/END 标记块则整体替换，不存在则追加到末尾；多 IDE 接线时只 upsert 一次，绝不触碰标记块以外的内容
4. **hook 命令路径写绝对路径**：与现有 `.codebuddy/settings.json` 一致（`python "<abs>/hooks/task_session_start.py"`），Windows 下用双引号包裹
5. **源文件路径解析**：优先 `import codewiki` 定位包目录，回退 `CODEWIKI_HOME` 环境变量指向的 checkout，与 prompts.py 现有指引一致；均失败时报错并给出 `pip install codewiki` 指引
6. **prompt 改造策略**：`team-memory-hook` 启用步骤与 `init-wiki` 的 enable_task_management 接线步骤改为「首选运行 `codewiki install-hooks` 自动检测接线（无需指定 IDE）；CLI 不可用时回退到现有手动步骤，并补充 Qoder/Claude Code 的 settings.json 路径说明」，避免破坏现有 CodeBuddy 手动工作流
7. **未检测到 IDE 的反馈**：自动检测结果为空时，输出可操作提示（列出支持的 IDE 与 `--ide` 用法），不静默失败

### 性能与可靠性

- CLI 为一次性操作（秒级），无热路径；settings.json/AGENTS.md 均为小文件，直接读写即可，无需缓存
- 拷贝脚本用 `shutil.copy2` 保持可执行属性；写入前对拷贝结果做 `ast.parse` 校验（沿用 prompts.py 现有校验思路），失败即报错不静默
- 幂等性保证：重复运行 `install-hooks` 不会产生重复 hook 注册或重复 AGENTS.md 段落

## 架构设计

```
用户触发创建 hook（team-memory-hook 启用 / init-wiki enable_task_management）
        │  prompt 引导首选路径
        ▼
codewiki install-hooks                      （默认自动检测，无 --ide）
        │
        ▼
codewiki/cli/main.py (注册命令)
        │
        ▼
codewiki/cli/commands/install_hooks.py (Click 命令：默认检测 / --ide / --repo-path)
        │
        ▼
codewiki/cli/utils/ide_config.py (核心接线逻辑)
   ├─ IDE_SPECS 注册表（目录/settings/agents/事件映射）
   ├─ detect_ide_dirs(repo) → 检测到的 IDE 名列表（默认路径）
   ├─ install_for_ide(repo, ide) → 拷贝脚本 + 合并 settings.json + 写 AGENTS.md（多 IDE 共享一份）
   ├─ merge_settings_json(现有配置, ide) → 幂等合并（按 command 去重、保留无关配置、原子写）
   └─ upsert_agents_section(agents_md) → 标记块写入
        │
        └─ 源副本读取：import codewiki 定位 codewiki/hooks/ + codewiki/agents/（CODEWIKI_HOME 兜底）
```

无需 Mermaid 图：该改动为单命令线性流程，组件关系简单。

## 目录结构

```
codewiki/
├── cli/
│   ├── main.py                          # [MODIFY] 注册 install-hooks 命令（import + add_command）
│   └── commands/
│       ├── __init__.py                  # [MODIFY] 导出 install_hooks 命令
│       ├── install_hooks.py             # [NEW] Click 命令实现。无参默认自动检测（detect_ide_dirs 扫描 .codebuddy/.qoder/.claude，检测到哪些就为哪些接线）；--ide 指定单个；--repo-path 指定目标；输出每个 IDE 接线结果摘要（拷贝文件、settings.json 合并状态、AGENTS.md 更新状态），检测结果为空时给出可操作提示
│       └── utils/
│           └── ide_config.py            # [NEW] 接线核心模块。IDE_SPECS 注册表；detect_ide_dirs() 扫描根目录返回存在的 IDE 列表；install_for_ide() 执行拷贝+合并+写入全流程；merge_settings_json() 幂等深合并（按 command 去重、保留无关配置、原子写）；upsert_agents_section() 标记块写入；_resolve_pkg_sources() 解析包内源副本路径（import codewiki → CODEWIKI_HOME 兜底）
├── hooks/
│   └── __init__.py                      # [MODIFY] docstring 更新：源副本支持 CodeBuddy/Qoder/Claude Code 三个 IDE 接线
└── mcp/
    └── prompts.py                       # [MODIFY] _prompt_init_wiki 与 _prompt_team_memory_hook（812-907 行）：接线步骤改为「首选运行 codewiki install-hooks 自动检测接线（无需指定 IDE）」，CLI 不可用时回退手动步骤并补充 .qoder/.claude settings.json 路径差异；步骤 2B 关闭流程同步覆盖三个 IDE 目录

README.md                               # [MODIFY] 中英两处「团队记忆融合→关键约束」：删「仅接线支持 CodeBuddy」，改为支持 CodeBuddy + Qoder + Claude Code（启用时自动检测接线）
tests/
├── test_install_hooks.py                # [NEW] 测试：detect_ide_dirs 检测逻辑（构造 .qoder 目录 → 只检测到 qoder）；多 IDE 同时接线；merge_settings_json 合并与去重幂等；install_for_ide 端到端（tmp_path 构造假仓库，验证脚本拷贝+settings 合并+AGENTS.md 标记块）；默认自动检测模式与 --ide 指定模式；重复运行幂等（不重复注册）
repowiki/
├── wiki/modules/CLI_Commands.md         # [MODIFY] 补充 install-hooks 命令说明（若存在命令清单章节）
└── wiki/modules/MCP_Prompts.md          # [MODIFY] 更新 team-memory-hook prompt 描述（若存在对应章节）
```

## 关键代码结构

### IDE 注册表（核心契约，多模块依赖）

```python
# codewiki/cli/utils/ide_config.py
IDE_SPECS: dict[str, dict] = {
    "codebuddy":   {"dir": ".codebuddy", "settings": "settings.json", "agents_dir": "agents", "copy_agent": True},
    "qoder":       {"dir": ".qoder",     "settings": "settings.json", "agents_dir": "agents", "copy_agent": True},
    "claude-code": {"dir": ".claude",    "settings": "settings.json", "agents_dir": "agents", "copy_agent": True},
}
HOOK_FILES = ("capture_session_end.py", "task_session_start.py")
AGENT_FILE = "distill-worker.md"
HOOKS_REGISTRATION = {  # 事件注册骨架，command 运行时补全绝对路径
    "SessionStart": [{"matcher": "startup", "hooks": [{"type": "command", "command": "<cmd>", "timeout": 15}]}],
    "SessionEnd":   [{"matcher": "other",  "hooks": [{"type": "command", "command": "<cmd>", "timeout": 30}]}],
}
```

### 幂等合并契约

`merge_settings_json(existing: dict | None, spec, start_cmd, end_cmd) -> dict`：保留 `existing` 中全部既有键；对 `hooks.SessionStart/SessionEnd` 数组按 `command` 去重后合并 CodeWiki 的注册项；返回合并结果由调用方原子写回。

### prompt 兜底指引契约

`_prompt_team_memory_hook` 步骤 2A 新增首选路径：「运行 `codewiki install-hooks --repo-path <repo>` 自动检测根目录 .codebuddy/.qoder/.claude，检测到哪些智能体就为哪些接线（无需指定 IDE）」；CLI 不可用时回退手动步骤，列出三个 IDE 的 settings.json 路径差异，hook 脚本与 distill-worker 源副本的强制拷贝命令仅目标目录随 IDE 变化。步骤 2B 关闭流程同步覆盖三个 IDE 目录。

## Agent Extensions

### MCP

- **codewiki**
- 用途：实现完成后用 `ingest_note` 归档「多 IDE 自动检测接线方案」决策笔记（decision 类型），沉淀 IDE 注册表驱动 + 触发时自动检测的设计取舍；同时用于在计划落地后向用户展示蒸馏 worker 产出的 6 条 pending 任务记忆，经 `confirm_task_memories` 确认落盘
- 预期结果：决策笔记以 draft 状态进入 notes/ 待确认；任务记忆经用户确认后写入 `repowiki/tasks/产品维护/memories.md`

### SubAgent

- **code-explorer**
- 用途：实现阶段核对 `codewiki/cli/commands/` 现有命令风格、prompts.py 中 `_prompt_team_memory_hook`（812-907 行）完整函数体与 repowiki 文档中 CLI/MCP 章节的精确插入点，并行检索避免主 Agent 逐个 read_file
- 预期结果：返回精确的文件路径、行号与可复用的现有代码模式，供 install_hooks.py 与文档同步直接套用