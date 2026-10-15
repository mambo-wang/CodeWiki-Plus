# ADR-0017: MCP prompt 编译为宿主命令文件（sync-commands）

- **状态**：已接受（2026-09-27，grill-with-docs 两轮拷问后拍板）

## 背景

CodeWiki 的 23 个工作流提示词注册在 `_PROMPT_REGISTRY` / `prompts_map`（`codewiki/mcp/prompts.py`），经 MCP `get_prompt` 暴露给宿主 Agent。Trae/codebuddy 宿主 IDE 会自动把 MCP prompt 映射为可用的命令，仓库无需文件；但**非 codebuddy 宿主**（本仓库实测为 Qoder，`.qoder/` 目录存在）没有这条自动通道，它们若想触发这些工作流，只能靠 Agent 记得调 `get_prompt`——没有可见入口。

现状 `.trae/commands/` 平铺的 23 个命令文件是 codebuddy 环境手工维护的薄壳，与其他宿主脱节，且与 codewiki 子目录（`初始化单仓工作区.md`）双轨。

## 关键事实

- `prompts.py` 的 `prompts_map`（23 条）是工作流提示词的单一真源；name 固定 kebab-case，title/description/args 全走 i18n（`prompts.<name>.*`），语言由 `config.json lang > $CODEWIKI_LANG > OS locale > zh` 决定
- codebuddy 自动把 MCP prompt 转成命令 → 仓库内为 codebuddy 再生成命令文件是重复劳动
- `codewiki/cli/utils/ide_config.py` 已能枚举 `.codebuddy/.qoder/.claude/.gemini/.trae`（存在哪个目录就为哪个宿主接线，install_hooks 同款逻辑）；本仓库实际存在 `.codebuddy/.qoder/.trae`
- 现有 `generate-wiki.md` 薄壳形态：标题 + 描述 + `get_prompt(name=..., arguments={...})` 调用块 + "模板真源在 prompts.py，以 get_prompt 返回内容为准"

## 决策

### 1. 独立幂等入口（Q1=C）

新增 CLI 子命令 `codewiki sync-commands [--lang zh|en] [--dry-run]`：确定性实现、可测试、可预览，不依赖 MCP 会话。`init-wiki` / `init-workspace` 的 prompt 正文末尾各加一步"调用 `codewiki sync-commands` 把全部工作流提示词编译为宿主命令文件"。不做 MCP 工具薄包装（第一版无实际需求，等有再封装同一实现）。

### 2. 内容形态 = 命令薄壳（Q2）

命令文件不渲染提示词全文，只写"如何获取全文"，结构对齐现有 `generate-wiki.md`：

```markdown
# <i18n title>

<i18n description 第一段>

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="<name>", arguments={"<arg0>": "<默认值>", ...})
```

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
```

参数从 `_PROMPT_REGISTRY` 的 args 元数据注入（`init-wiki` → `repo_path: "."`，`init-workspace` → `workspace_path: "."`，无参数则省略 arguments）。

### 3. 目标目录 = 宿主判定（Q3）

- 能判定当前宿主（MCP ClientInfo 的 name 字段，如 trae/qoder/claude-code）→ 只写该宿主的 `commands/codewiki/`；**.codebuddy 忽略**（IDE 自动转化，重复创建无意义）
- 判定不到 → 枚举仓库根 IDE 配置目录（`.codebuddy/.qoder/.claude/.gemini/.trae`），**排除 .codebuddy**，各自写入 `commands/codewiki/`
- 兜底：上述均不可行时，写 `.trae/commands/codewiki/` 作为仓库级命令登记处（agent 读到仓库即知可用命令，不依赖宿主原生识别）

### 4. 命名跟随 i18n locale（Q4）

文件名语言由生成时的 locale 定格：zh → 当前语言标题的 slug（如 `初始化Wiki项目.md`，与既有中文命令风格一致）；en → prompt 的 name（kebab-case，如 `init-wiki.md`）。标题/描述正文同步按该 locale 渲染。

### 5. 范围 = 全部 23 个 prompt（Q4）

按 `prompts_map` 全量生成，少一个即隐性缺口。

### 6. 存量单源化（Q6）

删除 `.trae/commands/` 平铺的 23 个手工薄壳与 `codewiki/初始化单仓工作区.md`，全部由生成器统一产出。命令文件是"生成快照"，权威在 MCP，仓库内不留手工副本。

### 7. 覆盖策略 = 全量覆盖（Q5）

每次执行无条件全量重写目标文件，不做锚点/哈希保护——文件本质是快照，手改无意义（权威在 `get_prompt`），保留手改只会掩盖漂移。

## 后果

- **正面**：非 codebuddy 宿主获得可见的命令入口（斜杠命令原生识别）；命令文件单一真源、可全量重建；codebuddy 宿主零重复（自动转化，跳过生成）。
- **负面**：中文文件名命令在部分工具生态的兼容性需验证（Qoder/Claude 支持任意文件名，冒烟时确认）；`sync-commands` 未跑时命令文件缺席（首次 init 触发即可补齐）。
- **风险**：clientInfo 判定误判（把 codebuddy 判成非 codebuddy）→ 多生成一份无害；判定不到走枚举/兜底，仍可达目标。

## 实现顺序

1. `sync_commands` CLI 实现（读 registry → 渲染薄壳 → 宿主判定 → 写入）+ 单测（23 个全量、i18n 文件名、宿主判定分支、幂等）
2. `init-wiki` / `init-workspace` prompt 末尾加 sync-commands 调用步骤
3. 删除存量平铺命令（单源化迁移）
4. 冒烟：本仓库跑 `sync-commands --dry-run` 核对产物，Qoder 目录实测斜杠命令

## 补充（2026-10-03）：工具通道也要接住工作流名

薄壳正文写的是 `get_prompt(name=..., arguments={...})`——MCP `prompts/get` 的形状。但**只暴露 MCP 工具的宿主没有 `prompts/get` 通道**（Qoder CN 实测），而工具 `get_prompt` 的真参数是 `prompt_type`、枚举只收模板类名字：照薄壳指引调用直接被 schema 拒绝，薄壳沦为指向死路的可见入口。契约没错，是实现少了一条通道，故补齐实现而不改薄壳与 AGENTS.md：

- `_WORKFLOW_PROMPTS`（原 `prompts_map`，从 handler 函数体内提到模块级）是「工作流名 → 渲染函数」的唯一真源，`prompts/get` 协议通道与工具通道共用同一张表；
- 工具通道兼容 `name` 别名与 kebab/camel 两种写法；`prompt_type` 的 enum 由 `workflow_prompt_names()` 生成（不再手维护，防漂移），`required` 清空，两个名字参数至少要传一个——缺失或未知都返回模板类 + 工作流两份可用清单；
- 命名撞车时模板类精确优先：`code_analysis` 是模板，`code-analysis` 是工作流，内容不同不可混；下划线写法只在模板类未命中时才归一化为工作流名。

回归见 `tests/test_get_prompt_tool_channel.py`。
