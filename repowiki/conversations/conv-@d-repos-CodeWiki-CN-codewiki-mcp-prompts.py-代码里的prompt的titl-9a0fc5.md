---
type: Conversation
title: "conversation 20260907T094013Z"
status: distilled
stale_after: 2026-12-06
generated: { by: codewiki/5.7.0, at: 2026-09-07T09:40:13Z }
captured_at: "2026-09-07T09:40:13Z"
content_hash: "sha256:962a62bd9e711f65153b0c0bf2da5171efdbac3b27d1d95c1801e297ad88bdb3"
friction_score: 10
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=26"
keep_raw: false
link_to: ""
source_session: "993f1c39697248b4a2c07b3edec98972"
turn_count: 205
---

# Conversation Transcript

user: @d:\repos\CodeWiki-CN\codewiki\mcp\prompts.py  代码里的prompt的title和description可以做国际化吗，根据当前系统语言或者配置文件里配置的语言返回对应的语言
assistant: [tool: ask_followup_question · {"questions": [{"question": "是否将本会话关联到一个进行中的任务？", "header": "任务关联", "options": [{"label": "CodeWiki 架构深化分析", "description": "tas…
user: <question>是否将本会话关联到一个进行中的任务？</question>
<answers>
产品维护(task_id=产品维护)
</answers>
</question_item>
</questions>
</question_answer>
assistant: [tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\", \"set_session_task\"], [\"codewiki\", \"get_task_context\"]]"}]
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "set_session_task", "arguments": "{\"source_session_id\": \"993f1c39697248b4a2c07b3edec98972\", \…

[tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "get_task_context", "arguments": "{\"task_id\": \"产品维护\"}", "explanation": "拉取「产品维护」任务的上下文"}]
assistant: 任务「产品维护」已绑定（pending_raw_count=0，无积压蒸馏）。现在开始分析你的问题。

先读取 `prompts.py` 及相关接线代码，了解当前 prompt 的注册与返回机制。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py"}]

[tool: list_dir · {"target_directory": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp"}]
assistant: 文件已读。prompt 的 title/description 目前是硬编码中文（`register()` 内 `list_prompts` 与 `get_prompt`，`codewiki/mcp/prompts.py:1378-1776`）。现在确认两点：MCP 侧是否有语言协商通道、项目现有配置/语言处理机制。

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\server.py"}]
assistant: MCP 协议层没有 per-request 语言协商，先确认本项目已有配置机制能否承载「语言配置」。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\src\\config.py"}]

[tool: search_content · d:\repos\CodeWiki-CN\repowiki\schema.yaml]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\resources.py", "limit": 60}]
assistant: 再看几个关键点：全局配置文件结构、MCP SDK 版本（确认协议是否支持语言协商）、以及现有代码里 `language` 相关用法的含义。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\pyproject.toml"}]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\_ide_hook.py]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\cli\\config_manager.py", "limit": 80}]
assistant: [tool: search_file · *.py]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\cli\\models\\config.py"}]
assistant: 确认 MCP SDK 中 `prompts/list` 请求结构与 handler 签名，判断协议层是否有语言协商可能。

[tool: search_content · d:\repos\CodeWiki-CN\.venv\Lib\site-packages\mcp\types.py]

[tool: search_content · d:\repos\CodeWiki-CN\.venv\Lib\site-packages\mcp\server\lowlevel\server.py]
assistant: [tool: search_content · d:\repos\CodeWiki-CN\.venv\Lib\site-packages\mcp\types.py]
assistant: 代码事实已核对完毕。快速查一下知识库有没有相关的既有决策，避免遗漏。

[tool: mcp_get_tool_description · {"toolRequests": "[[\"codewiki\", \"query_wiki\"]]"}]
assistant: [tool: mcp_call_tool · {"serverName": "codewiki", "toolName": "query_wiki", "arguments": "{\"query\": \"MCP prompt title description 国际化 语言\", \"mode\": \"chec…
assistant: 知识库无相关既有决策（`mode=check` 无命中），可直接基于代码事实作答。为确保行号准确，重定位关键锚点。

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\prompts.py]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\server.py]
assistant: 核对完毕。直接回答你的问题。

## 结论

**可以做，但有一个协议级前提必须先说清**：MCP 的 `prompts/list` 和 `prompts/get` 请求里**没有语言协商参数**——检查 SDK 类型定义，`RequestParams` 只有 progressToken，`ListPromptsRequestParams` 继承 `PaginatedRequestParams` 仅有 cursor，`GetPromptRequestParams` 只有 `name + arguments`（`.venv/Lib/site-packages/mcp/types.py:61-123`）。所以**无法做到"每次请求按客户端语言动态返回"**，语言只能在 **server 进程启动时选定一次**（对每个 IDE 会话是独立的 stdio 进程，实际够用）。

## 现状盘点

| 位置 | 内容 | 现状 |
|---|---|---|
| `list_prompts` handler | 22 个 `Prompt` 的 `title`/`description`/参数 `description` | 硬编码中文（`codewiki/mcp/prompts.py:1376-1825`） |
| `get_prompt` handler | `GetPromptResult.description=f"CodeWiki 工作流指引: {name}"` | 硬编码中文（`codewiki/mcp/prompts.py:1827`） |
| server 会话级 | `_SERVER_INSTRUCTIONS` 中文，随每次会话注入（`codewiki/mcp/server.py:80-144`） | 硬编码中文 |
| prompt 正文 | 22 个 `_prompt_*` 函数返回的全中文工作流（`codewiki/mcp/prompts.py:94-1373`） | 硬编码中文 |

## 落地方案（最小侵入）

**1. 语言解析**，优先级建议：显式配置 > 系统语言 > 兜底 `zh`：

```python
def _resolve_lang() -> str:
    # 1) 环境变量最显式
    env = os.environ.get("CODEWIKI_LANG") or os.environ.get("LANG")
    # 2) 用户级配置 ~/.codewiki/config.json 的 "language" 键
    #    （MCP server 目前不加载 CLI 的 ConfigManager，启动时 raw 读一个键即可，不必耦合 Configuration dataclass）
    # 3) 系统语言：Windows 用 ctypes.windll.kernel32.GetUserDefaultUILanguage()
    #    （注意 locale.getdefaultlocale() 已 deprecated，且 IDE 拉起进程通常不设 LANG）
    # 4) 默认 "zh"
```

**2. 元数据翻译表**，把当前中文常量搬进两层 dict：

```python
_META: dict[str, dict[str, tuple[str, str]]] = {
    "init_wiki": {
        "zh": ("初始化 Wiki", "为代码仓库初始化并生成 LLM Wiki 文档"),
        "en": ("Initialize Wiki", "Initialize and generate the LLM Wiki for a repo"),
    },
    ...
}
```

`register()` 里 `lang = _resolve_lang()` 一次，构造 `Prompt(..., title=_META[name][lang][0], description=_META[name][lang][1])`。`get_prompt` 的 description 同样查表（`codewiki/mcp/prompts.py:1827`）。22 个 prompt 元数据量小，静态 dict 足够，不必上 gettext 资源文件。

**3. 一个关键提醒——范围一致性**：title/description 是「列表 UI 展示」，Agent 真正消费的是 prompt **正文**（`_prompt_*` 返回值，94-1373 行）和 server `_SERVER_INSTRUCTIONS`（`codewiki/mcp/server.py:80`）。若只翻译元数据，英文用户会看到英文标题、但点进去拿到的是中文工作流正文，反而误导。完整国际化需覆盖三层：元数据 → 正文模板 → instructions（tool 的 schema description 在 registry 里，是第四层，工作量大）。建议按需分层实施，至少元数据 + 正文同步。

另注意：语言源不建议放项目级 `repowiki/schema.yaml`——MCP server 是无 repo 上下文的进程（`repo_path` 是工具级参数），且 `list_prompts` 不接收 repo_path，启动期拿不到项目配置；用户级配置或环境变量才是 server 启动期可读的。

需要的话我可以直接按这个方案实现（元数据 + 语言解析 + `_SERVER_INSTRUCTIONS` 双语），正文全量翻译可评估后分两批做。
user: 是不是可以在配置mcp的时候，mcp配置项增加语言参数？    "codewiki": {

      "type": "stdio",

      "command": "D:\\repos\\CodeWiki-CN\\.venv\\Scripts\\python.exe",

      "args": [

        "-m",

        "codewiki.mcp.server"

      ],

      "disabled": false

    }
assistant: 完全可以，这正是最直接的做法。确认一下 server 端启动与注册的接线点，给你精确的改法。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\server.py"}]
assistant: 完全可以，而且这正好落在 Doctrine 的「显式参数 > 可推导 > session 缓存」上——MCP 配置里显式声明的语言是 server 启动期唯一可靠的输入源。你的 MCP 配置有两种写法：

**接法 A：`env` 字段（推荐，最干净）**

```json
"codewiki": {
  "type": "stdio",
  "command": "D:\\repos\\CodeWiki-CN\\.venv\\Scripts\\python.exe",
  "args": ["-m", "codewiki.mcp.server"],
  "env": { "CODEWIKI_LANG": "en" },
  "disabled": false
}
```

server 端只需读环境变量，不用改任何启动/解析逻辑。

**接法 B：`args` 加参数（需要动 server 入口）**

```json
"args": ["-m", "codewiki.mcp.server", "--lang", "en"]
```

但 `main()` 目前没有任何参数解析（`codewiki/mcp/server.py:258-265`），要加 argparse 或在模块顶层手动 parse `sys.argv`，侵入更大。**A 优于 B**。

## server 端要动的两个点

接线点都在**模块级、进程启动早期**，读 env 一次即可生效，无需 per-request 处理：

1. **`prompts.py`**：`register()`（`codewiki/mcp/prompts.py:1374`）开头加一行 `lang = _resolve_lang()`，`_resolve_lang()` 优先级：`CODEWIKI_LANG` env → `~/.codewiki/config.json` 的 `language` 键 → 系统 UI 语言 → 兜底 `zh`。随后 `list_prompts` / `get_prompt`（含 `codewiki/mcp/prompts.py:1827` 的 description）都按 `lang` 从双语文案表取词。

2. **`server.py`**：`_SERVER_INSTRUCTIONS` 目前是模块级常量（`codewiki/mcp/server.py:80`），`Server(...)` 在 138-145 行创建时就把它定死。需改成按 `lang` 选取：`_SERVER_INSTRUCTIONS` 保留 zh 版，加一个 `_SERVER_INSTRUCTIONS_EN`，构造时 `instructions=_SERVER_INSTRUCTIONS_EN if _resolve_lang()=="en" else _SERVER_INSTRUCTIONS`。

> 提示：本仓库「根据配置或 env 选择语言」先例可参考 `CODEWIKI_SERVER_LOG` 的处理（`codewiki/mcp/server.py:196-199`），风格一致：`os.environ.get(...) or 默认值`。

## 唯一需要明确的取舍

MCP 配置是**每 server 一份**，所以语言是「整个 server 进程」的，无法在同一进程内区分不同 IDE 客户端的语言——但实际中一个 IDE 会话对应一个 stdio 进程（你的配置里就是 `python -m codewiki.mcp.server` 单实例），一个用户改自己配置即可，这个粒度刚好合适。

要我按这个方案实现吗？实现范围建议：`_resolve_lang()` + prompts 元数据双语文案表 + `_SERVER_INSTRUCTIONS` 英文版，prompt 正文翻译可分两批做。
user: ~/.codewiki/config.json  这个不用了，生成一个简单的方案
assistant: `config.json` 来源砍掉后方案可以压到很薄。先取几个现有条目的真实 name/title 作示例，避免编造文案。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py", "offset": 1374, "limit": 70}]
assistant: 砍掉 `config.json` 后，方案可以压到「一个 env + 一张覆盖表 + 两处小改」。

## 简单方案

**语言源只剩一个**：环境变量 `CODEWIKI_LANG`（由 MCP 配置的 `env` 字段注入，见下）。不读配置文件、不探测系统语言——`CODEWIKI_LANG` 缺省即 `zh`（当前默认行为，零回归）。

**文案策略：只写英文覆盖表，中文沿用现有内建**。现有 22 个 `Prompt` 的硬编码中文文案全部保留（`codewiki/mcp/prompts.py:1381-1825`），新增一张小表只补 `en` 列——zh 路径完全不动，en 路径在返回前做一次字段覆盖。这样翻译量最小、可独立回退。

```python
# prompts.py 顶部
def _lang() -> str:
    """UI 语言：CODEWIKI_LANG env → 兜底 zh（zh/en 之外的值一律回落 zh）"""
    lang = os.environ.get("CODEWIKI_LANG", "").strip().lower()
    return lang if lang in ("zh", "en") else "zh"

# 仅 en 覆盖表；zh 用内建文案
_EN_META: dict[str, tuple[str, str]] = {
    "init-wiki": (
        "Initialize Single-Repo Wiki Workspace",
        "Zero-config initialization: create the directory skeleton, copy an annotated "
        "schema.yaml template, and write AGENTS.md. Run once before any Wiki generation.",
    ),
    "init-workspace": (...),
    "add-workspace-repo": (...),
    # ... 共 22 条
}
```

**改动点 1 — `list_prompts`**（`codewiki/mcp/prompts.py:1378`）：handler 内构造完列表后按语言覆盖，zh 直接返回原列表：

```python
async def list_prompts() -> list:
    prompts = [ ... 现有 22 个 Prompt ... ]
    en = _EN_META
    if _lang() == "zh":
        return prompts
    return [
        p.model_copy(update={"title": en[p.name][0], "description": en[p.name][1]})
        if p.name in en else p
        for p in prompts
    ]
```

**改动点 2 — `get_prompt`**：`description=f"CodeWiki 工作流指引: {name}"`（`codewiki/mcp/prompts.py:1827`）改为按 `_lang()` 输出 `"CodeWiki workflow guide: {name}"`。

**明确不做**（保持简单，后续需要再扩展）：参数 `PromptArgument.description`、prompt 正文、`_SERVER_INSTRUCTIONS`。三者若要本地化，各自加一列/加一份即可，互不影响。

**使用方式**——你的 MCP 配置加 `env` 即可，无需改启动代码：

```json
"codewiki": {
  "type": "stdio",
  "command": "D:\\repos\\CodeWiki-CN\\.venv\\Scripts\\python.exe",
  "args": ["-m", "codewiki.mcp.server"],
  "env": { "CODEWIKI_LANG": "en" },
  "disabled": false
}
```

改动总量：约 30 行表数据（22 条翻译）+ 2 处逻辑小改，不新增文件、不动启动入口。确认后我就按这个实现。
user: 可以把多语言放到单独的配置文件中吗，比如properties文件，取的时候根据语言和key获取，便于管理
assistant: 可以，这就是标准的资源文件（i18n）模式。先确认项目现有的 YAML 依赖与读取惯例，保持风格一致。

[tool: search_content · d:\repos\CodeWiki-CN\pyproject.toml]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]
assistant: YAML 是现成答案——`PyYAML>=6.0.2` 已是硬依赖（`pyproject.toml:53`），全库惯例是 `import yaml` + `yaml.safe_load`（如 `codewiki/src/frontmatter.py:116-121`）。**properties 在 Python 无内置解析**、无层级、多行 description 要转义续行，会很痛苦；YAML 有层级、块文本、注释，正是 properties 诉求在 Python 里的等价物。推荐 YAML。

## 资源文件模式方案

**目录结构**（与 `prompts.py` 同层）：

```
codewiki/mcp/locales/
  zh.yaml     # 中文（从现有 22 条内嵌文案搬出）
  en.yaml     # 英文（对照 zh 翻译）
```

**文件内容（YAML 层级即 key）**：

```yaml
# zh.yaml
prompt:
  init-wiki:
    title: "初始化单仓Wiki工作区"
    description: >
      零配置初始化：创建目录结构、拷贝带注释的 schema.yaml 模板、
      写入 AGENTS.md（含使用建议和自我反思协议）。
      在开始任何 Wiki 生成或知识管理之前执行一次。
  init-workspace:
    title: "初始化多仓WIKI工作区"
    description: >
      把当前工作目录初始化（或重新同步）为多仓工作区：…
# 其余 20 个 …
prompt_description: "CodeWiki 工作流指引: {name}"   # get_prompt 的 description
```

**加载器**（约 20 行，点分 key + 语言回退）：

```python
# codewiki/mcp/i18n.py
_LOCALES = Path(__file__).parent / "locales"

def current_lang() -> str:
    lang = os.environ.get("CODEWIKI_LANG", "").strip().lower()
    return lang if lang in ("zh", "en") else "zh"

@lru_cache(maxsize=None)
def _load(lang: str) -> dict:
    path = _LOCALES / f"{lang}.yaml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def t(key: str, **fmt) -> str:
    """按当前语言取词：当前语言缺失 → zh → 返回 key 本身（防静默）"""
    for lang in (current_lang(), "zh"):
        node = _load(lang)
        for part in key.split("."):
            node = (node or {}).get(part)
            if node is None:
                break
        else:
            return node.format(**fmt) if fmt else node
    return key
```

**接线改动**：
1. `list_prompts` 里 22 个 `Prompt` 的 `title=`/`description=`（`codewiki/mcp/prompts.py:1381-1825`）改为 `title=t("prompt.init-wiki.title")` 之类，中文文案全部从代码搬进 `zh.yaml`；
2. `get_prompt` 的 description（`codewiki/mcp/prompts.py:1827`）改为 `t("prompt_description", name=name)`；
3. 语言仍由 MCP 配置 `env: { "CODEWIKI_LANG": "en" }` 注入，缺省 `zh`——与上轮一致，不加 config.json。

**两个待你拍板的点**：

1. **zh 是否也全量搬进 YAML？** 推荐搬——文案才真正集中管理（zh/en 对照翻译、改文案不碰代码）。代价是这轮 diff 大（22 条文案迁出 + 22 条英文翻译），一次性。若想最小 diff，可只建 `en.yaml`、zh 沿用代码内建（回退链里"zh"走代码缺省），但管理就分散了。
2. **打包提醒**：`locales/*.yaml` 是包内非 py 资源，需确认构建配置会把它们打进 wheel/dist，否则装包后读取会失败。

确认这两点后我就按方案实现。
user: <manually_attached_skills>
Please use the use_skill tool to invoke this skill.

name: grill-me
description: A relentless interview to sharpen a plan or design.
</manually_attached_skills>

@command://grill-me  看看这个方案可以吗
assistant: [tool: use_skill · grill-me]
assistant: [tool: use_skill · grilling]
assistant: 方案收到。grill 之前先自己把两个「事实」查掉——打包是否含包内资源、现有测试是否锁死了文案内容，这些不该让你回答。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\pyproject.toml", "limit": 60}]

[tool: search_content · d:\repos\CodeWiki-CN\tests]
assistant: [tool: search_content · d:\repos\CodeWiki-CN\pyproject.toml]
assistant: 事实已查清，可以开始。先校准共识，再上第一轮问题。

**已定（你的拍板 + 代码事实）：**
- 语言源 = `CODEWIKI_LANG` env（MCP 配置 `env` 注入），缺省 `zh`；不要 config.json、不做系统语言探测
- 文案外置资源文件，按「语言 + key」取
- 起点范围 = MCP prompt 的 `title`/`description` + `get_prompt` 的 description

**我自己查掉的两个事实（不用你回答）：**
- 打包：hatchling wheel 的 artifacts 只列了 `codewiki/templates/**/*`、`py.typed`、`codewiki/agents/**/*`（`pyproject.toml:98-102`）——**新增 `locales/*.yaml` 不会自动进 wheel**，必须同步改 artifacts，否则装包后文件丢失。这是真实风险点。
- 回归面：`tests/` 里对 MCP prompts 的引用全是 mock 桩（`test_hook_registry.py`、`test_promotion.py`），**没有测试锁定现有中文文案**，改动不会破坏测试。

---

## 设计树 · 第 1 轮（前沿问题）

❓ **Q1 — 资源文件格式**：你上一轮说"比如 properties 文件"。properties 在 Python 无内置解析、无层级、description 多行要转义续行；JSON 无注释、多行差；**YAML** 已是硬依赖（`pyproject.toml:53`）、支持层级/块文本/注释，全库有惯例。但你若考虑未来接翻译平台/双语工具链，`key=value` 扁平 properties 更通用。选哪个？

➡️ 推荐 **YAML**（`zh.yaml`/`en.yaml` 嵌套结构，key 即路径）；若你有翻译平台兼容诉求再改 properties。

❓ **Q2 — 中文文案的去向**：两个选项——(a) zh/en **双文件全量**，22 条中文从 `prompts.py` 搬进 `zh.yaml`，代码里只剩 `t("prompt.init-wiki.title")`；(b) 只建 `en.yaml`，zh 沿用代码内建文案（diff 小，但文案管理仍分散两处，回退链也更绕）。

➡️ 推荐 **(a) 双文件全量**——你选资源文件的动机就是"便于管理"，半内建半文件是两头不讨好；代价是这轮 diff 大、要逐条搬运 22 条文案。

❓ **Q3 — 缺 key 时的行为与防漂移**：若 `en.yaml` 漏译某条 key，运行时该显示什么？(a) 回退 `zh`；(b) 显示 key 本身（"prompt.init-wiki.title"）暴露错误。另外 zh/en 两个文件靠人工同步，key 集漂移是必然风险——要不要加一道防线（轻量测试断言两文件 key 集一致，或加载时对不一致打日志）？

➡️ 推荐 **回退 zh + 补一个 key 集一致性测试**——漏译显示中文比显示裸 key 体面，但必须有测试兜住"永远不知道漏了哪条"。

❓ **Q4 — 本轮范围是否含 `_SERVER_INSTRUCTIONS`**：你的原话是 title/description。但每次会话注入给 Agent 的 `instructions`（`codewiki/mcp/server.py:80-136`）是纯中文大段文本——对英文环境的 Agent，这个比 prompt 列表标题影响大得多。要一起纳入吗？（英文版 instructions 文本量大，可只翻正文骨架）

➡️ 推荐 **本轮只做 title/description**（你划的范围，闭环小、可独立验收）；instructions 单独立一项后续做——避免这轮又变成一个"翻几千字"的大活。

---

回答这 4 题后，我根据答案展开下一轮（会涉及文件结构、key 规范、翻译分工、`CODEWIKI_LANG` 文档落点等下游决策）。
user: <cb_summary>
This session is being continued from a previous conversation that was compacted to stay within the model context window.
Messages after this summary (if any) are the original recent turns. Tool results from before this summary were omitted.
If you need exact code, command output, or file contents from before compaction, re-read those files. Do not treat omitted tool bodies as still in context.

Earlier user requests:
- @d:\repos\CodeWiki-CN\codewiki\mcp\prompts.py  代码里的prompt的title和description可以做国际化吗，根据当前系统语言或者配置文件里配置的语言返回对应的语言
- <question_answer> <questions> <question_item id="q-0"> <question>是否将本会话关联到一个进行中的任务？</question> <answers> 产品维护(task_id=产品维护) </answers> </question_item> </questions> </question_answer>

Earlier assistant notes (truncated):
- 任务「产品维护」已绑定（pending_raw_count=0，无积压蒸馏）。现在开始分析你的问题。  先读取 `prompts.py` 及相关接线代码，了解当前 prompt 的注册与返回机制。
- 文件已读。prompt 的 title/description 目前是硬编码中文（`register()` 内 `list_prompts` 与 `get_prompt`，`codewiki/mcp/prompts.py:1378-1776`）。现在确认两点：MCP 侧是否有语言协商通道、项目现有配置/语言处理机制。
- MCP 协议层没有 per-request 语言协商，先确认本项目已有配置机制能否承载「语言配置」。
- 再看几个关键点：全局配置文件结构、MCP SDK 版本（确认协议是否支持语言协商）、以及现有代码里 `language` 相关用法的含义。
- 确认 MCP SDK 中 `prompts/list` 请求结构与 handler 签名，判断协议层是否有语言协商可能。
- 代码事实已核对完毕。快速查一下知识库有没有相关的既有决策，避免遗漏。
- 知识库无相关既有决策（`mode=check` 无命中），可直接基于代码事实作答。为确保行号准确，重定位关键锚点。
- 核对完毕。直接回答你的问题。  ## 结论  **可以做，但有一个协议级前提必须先说清**：MCP 的 `prompts/list` 和 `prompts/get` 请求里**没有语言协商参数**——检查 SDK 类型定义，`RequestParams` 只有 progressToken，`ListPromptsRequestParams` 继承 `PaginatedRequestParams` 仅有 cursor，`GetPromptRequestParams` 只有 `name + arguments`（`.venv/Lib/site-packages/mcp/types.py:61-123`）。所以**无法做到"每次请求按客户端语言动态返回"**，语言只能在 **server 进程启动时选定一次**（对每个 IDE 会话是独立的 stdio 进程，实际够用）。  ## 现状盘点  | 位置 | 内容 | 现状 | |---|---|---| | `list_prompts` handler | 22 个 `Prompt` 的 `title`/`description`/参数 `description` | 硬编码中文（`codewiki/mcp/prompts.py:1376-1825`） | | `get_prompt` handler | `GetPromptResult.description=f"CodeWiki 工作流指引: {name}"` | 硬编码中文（`codewiki/mcp/prompts.py:1827`） | | server 会话级 | `_SERVER_INSTRUCTIONS` 中文，随每次会话注入（`codewiki/mcp/server.py:80-144`） | 硬编码中文 | | prompt 正文 | 22 个 `_promp…

Tools used before this summary: search_content × 9, read_file × 7, mcp_call_tool × 3, mcp_get_tool_description × 2, ask_followup_question × 1, list_dir × 1, search_file × 1
</cb_summary>

Q3不用回退，我们发版本前跑测试能暴露该问题，暴露问题后补充相关内容即可   Q4 包含，需要再看下是否还有别的中文会返给智能体的，一起改掉
assistant: Q3、Q4 收到。Q3 定案：**不做运行回退**——缺 key 靠发版前的 key 集一致性测试暴露，暴露后补文案。Q4 范围从 title/description 扩大到「所有返回给 Agent 的中文」。Q1（格式）、Q2（zh 是否全量搬入）你还没答，我稍后重新问。

先派一个审计员把「到底还有哪些中文会返回给智能体」盘清楚——这是事实，该我查，不劳你记。

[tool: task · {"subagent_name": "code-explorer", "description": "盘点 MCP 层返回给 Agent 的中文文本", "prompt": "只读审计任务（不要写任何代码、不要修改文件）。仓库根目录 d:\\repos\\CodeWiki-CN。目标是盘点…
assistant: 审计结果很关键——**工具 schema 与错误消息全部是英文**（中文 i18n 工作量归零），中文集中在 prompts.py（正文 1250+ 行）、resources.py、server.py instructions、工具层少量散点。范围比你最初想的深：正文不是纯文案，是夹带 f-string 占位符、JSON 示例、HTML 标记的模板。抽查一个正文函数确认结构再继续问。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py", "offset": 94, "limit": 120}]
assistant: 正文结构抽查完毕，这个事实改变设计难度，先说清楚：

**`_prompt_init_wiki`（`codewiki/mcp/prompts.py:94-204`）不是纯文案，是"逻辑 + 模板"**：条件分支（`enable_task_management` 决定 `hook_block` 拼不拼、`step_shift` 步进移位）、运行时占位符（`{repo_path}`、`{2 + step_shift}`）、JSON 示例 `{{ }}` 转义、PowerShell/JSON 代码围栏、引用常量块（`_TASK_MEMORY_AGENTS_SECTION`，中文）。22 个正文函数同构。**这意味着"把 1250 行正文整块搬进 YAML"不可能**——每个函数必须重写成"按语言取模板片段 + 保留逻辑"，英文版正文是一次约 1250 行的英文创作，不是查表翻译。

现在把待定决策补全。

---

## 设计树 · 第 2 轮

❓ **Q1（重问）— 资源格式**：YAML vs `.properties`——这是上一轮遗留。YAML 有层级、块文本、注释、PyYAML 已是依赖；properties 兼容翻译平台但多行文本痛苦。

➡️ 推荐 **YAML**。

❓ **Q2（重问）— 中文去向**：zh/en **双文件全量**（文案全部搬出代码，代码零中文）还是只建 en 文件、zh 用代码内建？

➡️ 推荐 **双文件全量**——既然范围扩到 1500 行，不搬 zh 就是两处维护同 1500 行，比搬更糟。

❓ **Q6 — 交付节奏（核心）**：审计把中文分成四块——prompt 正文约 1250 行、元数据层（title/description/参数说明 + `get_prompt` 描述）约 100 行、resources 约 92 行、instructions 57 行、工具层散点几十行。合计约 **1500 行需要英文创作**，其中正文还需要重写函数（逻辑与模板分离）。怎么推进？

- (a) **一次全做**：机制 + 全部 1500 行英文一次合入。diff 巨大、正文英文需一次 review，风险集中。
- (b) **机制一次搭好，内容分批**：加载器/资源文件/测试基建/元数据层改造一次合入（批次 1 只翻 ~200 行：元数据 + instructions + resources + 工具散点）；22 个正文函数的重写与英文创作独立成批次 2。key 集一致性测试按"`zh.yaml` 已有 key ⊆ `en.yaml`"设计，天然支持分批——每批抽完 key、补完英文才能绿。

➡️ 推荐 **(b)**——Q3 的"测试暴露漏译"在分批机制下依然成立，但不会逼迫一个 PR 里塞 1500 行英文。

❓ **Q7 — 落盘产物是否算"返回给智能体"**：审计发现还有一类中文**不走 MCP 响应、但 Agent 随后会读文件看到**——写入目标仓库的 AGENTS.md 约定块（`tools/agents_md.py:218-345`）、index.md/阅读指南（`wiki_index.py`、`reading_guide.py`）、schema.yaml 中文模板描述（`schema_generator.py`）。它们是"生成到用户仓库的长期产物"，语言应跟产物语境（用户仓库）而非 server 运行时语言；尤其 schema 模板语言与未来生成文档的语言强相关。纳入本次范围吗？

➡️ 推荐 **排除**，独立决策——先把 MCP 直返通道做完做对，落盘产物的语言策略需要单独定（含"是否要英文版 schema 模板/AGENTS 约定"的产品决策）。

---

回这 4 题后我展开下一轮（会涉及 key 结构规范、片段拆分粒度、instructions/resources 的放置、`CODEWIKI_LANG` 文档落点等）。
user: Q6 A    Q7纳入  其他按推荐
assistant: 范围锁定：**一次全做，含落盘产物，格式 YAML、zh/en 双文件全量**。开工前补三个事实，其中一个是架构关键点：`prompts/catalog`（resources.py 里的 15 条中文描述）与 `list_prompts` 注册表（22 条中文元数据）是不是**同一份描述在两处重复维护**——如果是，翻一处、另一处自动跟随，翻译量直接砍半且免一致性测试；如果是硬编码重复，这是本次最大的暗坑。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\resources.py"}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\server.py", "offset": 75, "limit": 80}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\agents_md.py", "offset": 200, "limit": 150}]
assistant: 三个事实到位，其中两个是**架构级发现**：

1. **`prompts/catalog` 是硬编码重复且已漂移**：resources.py 手写 15 条描述，而 `list_prompts` 注册表是 22 条（`resources.py:245-367` vs `prompts.py:1378-1780`）——同一种描述两处维护，数量都对不上。
2. **`server.py` instructions 声称"11 个 Prompt 模板"，实际注册 22 个**（`server.py:89`）——又是一处漂移。
3. **`agents_md.py` 与 prompt 正文同构**：f-string 大模板 + 中文条件片段（`agents_md.py:217-347`），落盘产物翻译不是查表而是同样的"逻辑+模板"重构。

这些漂移说明：**代码里可派生的数据被硬编码成中文常量，是漂移之源**。i18n 把文案集中化时正好暴露它们。查一下语言配置该挂在哪——现有配置机制长什么样。

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\src\config.py]
assistant: 配置机制确认：CLI 侧已有全局用户设置 `~/.codewiki/config.json`（`cli/config_manager.py:29`），项目惯例是 `CODEWIKI_*` 环境变量（`CODEWIKI_HOME`/`CODEWIKI_USER`…）。语言配置有可靠的落点。

---

## 设计树 · 第 3 轮

❓ **R1 — 语言从哪来、谁优先**：你最初说"当前系统语言或配置文件里配置的语言"。MCP server 是 IDE 拉起的 stdio 进程，三个候选来源：

- `~/.codewiki/config.json` 的 `lang` 字段（用户持久设置，跨会话稳定）
- `CODEWIKI_LANG` 环境变量（IDE/启动脚本注入，覆盖会话级）
- 系统 locale（自动推断，但不可控）

➡️ 推荐优先级：**显式配置（config.json `lang` > env）> 系统 locale 推断（`zh_*`→zh，其他→en）> 兜底 zh**。非法值记日志后回 zh——注意这与 Q3"不回退"不冲突：Q3 管的是"翻译缺失不回退"，这里是"配置非法时的默认值"。

❓ **R2 — 存量中文产物怎么办**：已生成的中文 AGENTS.md 块、index.md、schema.yaml 在语言切到 en 后是否追溯重写？

➡️ 推荐 **不追溯**——只影响新生成/整体重写路径（AGENTS 标记块 upsert、index.md 重建、schema.yaml 首次拷贝时跟随当前语言）；schema.yaml 已存在则绝不动（含用户自定义注释与增量合并值）。追溯重写会无差别改动用户仓库，diff 噪音不可控。

❓ **R3 — 迁移中遇到的"硬编码漂移"是否顺带修**：i18n 把文案集中化时会撞见三处已漂移的数据——catalog 只有 15 条而注册表 22 条、instructions 声称"11 个 Prompt 模板"、`tool_count: 49` 手写且要靠注释提醒同步。处理方式？

- (a) **照搬现状**：逐字搬中文文案，漂移原样保留（行为完全不变，但把错误翻译进 en）
- (b) **顺带去漂移**：catalog 改为从 `list_prompts` 注册表派生、`tool_count` 运行时从 registry 计数、instructions 里的数量改为真实值——每处都是"单一事实源"，翻译量还因 catalog 消除重复而减少

➡️ 推荐 **(b)**——这类漂移本来就是硬编码文案的伴生缺陷，趁集中化一起根除，否则 en 版上线第一天就是错的。行为差异：catalog/计数会变正确（从 15→22 条、49 保持但不再手写）。

---

一个流程提醒不占问题名额：en 全量是一次约 1500 行英文内容创作，初稿由我产出，建议合入前做一次面向英文可读性的审校（机器直译风格的 prompts 会拉低产品完成度）。三题回完，下轮收敛到实现层（文件布局、key 命名、正文片段拆分规范、测试断言细节）。
user: 全部按你推荐来
assistant: 决策树闭合，定案汇总如下，然后开始落地：

**已定案**：YAML 双文件全量（zh 源/en 全量覆盖）｜一次性全做｜无运行时回退，靠发版前 key 集一致性测试兜底｜范围 = prompts 元数据+22 正文、instructions、resources、工具层散点、落盘产物｜语言来源 config.json `lang` > env `CODEWIKI_LANG` > 系统 locale > zh｜存量中文产物不追溯重写｜顺带去硬编码漂移（catalog 派生、tool_count 计数、修数量谎报）。

实现层不再问决策性分叉，直接开工。先探四个落地事实：包内资源打包方式（YAML 能否进 wheel）、PyYAML 依赖、MCP 入口启动时序、测试目录结构。

[tool: search_file · pyproject.toml]

[tool: search_file · setup.py]

[tool: search_file · conftest.py]

[tool: search_content · d:\repos\CodeWiki-CN]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\pyproject.toml"}]

[tool: list_dir · {"target_directory": "d:\\repos\\CodeWiki-CN\\tests"}]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\server.py", "offset": 150, "limit": 130}]
assistant: server 结构明确：`Server(...)` 在模块顶层 import 时构造（`server.py:138`），prompts/resources 注册也在 import 时——语言初始化必须放在 server 构造之前。先看测试惯例与 config.json 结构，然后落地 M1 基建。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\tests\\conftest.py"}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\cli\\config_manager.py", "limit": 80}]
assistant: 测试惯例清楚（标准 pytest、直接调 handler）。config.json 是顶层 JSON。开始 M1（基建 + instructions 接入）。先看 server.py 头部 import 区以确定接线位置。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\server.py", "limit": 75}]
assistant: 接线点确认。创建 i18n 基建模块。

[tool: write_to_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\i18n.py", "content": "\"\"\"Two-locale message catalog for text returned to agents.…
assistant: 创建 locales 目录与首个语料文件（zh 源语料，逐字搬 `_SERVER_INSTRUCTIONS`，按 R3 定案把数量谎报 11→22 修正）。

[tool: write_to_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "content": "# CodeWiki MCP 多语言语料（中文源，唯一事实源）\n#\n# 规则：\n# 1. zh.y…
assistant: 创建 en.yaml（英文创作，结构对等 zh 源）。

[tool: write_to_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "content": "# CodeWiki MCP message catalog (English).\n#\n# en.y…
assistant: 接线 server.py：加入 i18n 导入并初始化语言（在 Server 构造之前），再把 instructions 常量改为从语料取。

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\server.py", "old_str": "from codewiki import __version__\nfrom codewiki.mcp.sessi…
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\server.py", "old_str": "_SERVER_INSTRUCTIONS = \"\"\"\\\nCodeWiki-CN MCP Server —…
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\pyproject.toml", "old_str": "artifacts = [\"codewiki/templates/**/*\", \"codewiki/py.typed\", \"…
assistant: 写 M1 测试套件（key 集一致性、占位符一致性、缺失暴露、语言解析优先级）。

[tool: write_to_file · {"filePath": "d:\\repos\\CodeWiki-CN\\tests\\test_i18n.py", "content": "\"\"\"i18n catalog tests for codewiki/mcp/i18n.py.\n\nPre-releas…

[User Cancelled]
user: 继续
assistant: [tool: ask_followup_question · {"questions": [{"question": "本会话（MCP 层 i18n 落地）关联到哪个进行中的任务？", "options": [{"label": "产品维护", "description": "推荐——本会话正在做 prompt/资源…
user: 继续开发
assistant: 用户选择继续开发（跳过关联）。启动后台补蒸馏（不阻塞），同时继续 M1：重写一致性测试。

[tool: task · {"subagent_name": "distill-worker", "description": "补蒸馏产品维护积压对话", "prompt": "你是蒸馏 worker，走 Mode C（纯 MCP JSON）流程，处理任务「产品维护」（task_id=产品维护）的历史对话积压。步…

[tool: write_to_file · {"filePath": "d:\\repos\\CodeWiki-CN\\tests\\test_i18n.py", "content": "\"\"\"i18n catalog tests for codewiki/mcp/i18n.py.\n\nPre-releas…
assistant: [tool: execute_command · uv run pytest tests/test_i18n.py -q]
assistant: M1 全绿（13 passed, 1 skipped）。进入 M2：prompts 元数据层 + catalog 派生。先读 prompts.py 头部常量与 register 段。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py", "limit": 94}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py", "offset": 1374, "limit": 180}]
assistant: 读完剩余元数据段，然后一次性完成 M2（注册表化 + catalog 派生）。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py", "offset": 1553, "limit": 282}]
assistant: M2 需要替换 `list_prompts` 的 400 行硬编码数组与 resources 的手写 catalog——用一次性脚本按锚点切片替换（避免重写大文件），随后补注册表与语料。

[tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_migrate.py", "content": "\"\"\"One-shot migration helper: swap har…
assistant: [tool: execute_command · python C:\Users\Administrator\AppData\Local\Temp\cw_i18n_migrate.py]
assistant: [tool: delete_file · {"target_file": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_migrate.py", "explanation": "迁移脚本已用完，清理临时文件"}]

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py", "old_str": "import logging\nimport os\nfrom typing import Any\n\nlog…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\resources.py", "old_str": "import json\nimport logging\nfrom pathlib import Path\…
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py", "old_str": "def register(server):\n    \"\"\"Register prompt handler…
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py", "old_str": "        return GetPromptResult(\n            description…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "old_str": "    8. 对话蒸馏: 调用 Prompt \"distill-conversations\" 从…
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py", "old_str": "        return GetPromptResult(\n            description…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "old_str": "    8. Conversation distillation: invoke Prompt \"…
assistant: [tool: execute_command · uv run pytest tests/test_i18n.py -q]

[tool: read_lints · {"paths": ["d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py", "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\resources.py", "d:\\repos\\CodeWiki…
assistant: M2 全绿、lint 干净。做一次端到端验证（中英双语渲染 + 未知 prompt 兜底 + catalog 派生）。

[tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_verify.py", "content": "\"\"\"Ad-hoc end-to-end check of the i18n …
assistant: [tool: execute_command · python C:\Users\Administrator\AppData\Local\Temp\cw_i18n_verify.py]
assistant: 端到端双语切换正常（22 条元数据、catalog 派生、未知兜底均已英文化；正文仍是中文，属 M4）。跑全量测试确认无回归。

[tool: execute_command · uv run pytest -q 2>&1 | tail -25]
assistant: 全量测试 exit 0（无回归）。继续 M3：resources 层剩余（静态/模板元数据、capabilities、page-types），并处理第三处漂移——`capabilities` 里硬编码的版本号 `v5.5.0`（实际 5.7.0）。

[tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_migrate2.py", "content": "\"\"\"One-shot migration: localize the r…
assistant: [tool: execute_command · python C:\Users\Administrator\AppData\Local\Temp\cw_i18n_migrate2.py]
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "old_str": "resources:\n  catalog:\n    usage: \"通过 MCP prompt…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "old_str": "resources:\n  catalog:\n    usage: \"Use the MCP p…
assistant: [tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_verify2.py", "content": "\"\"\"Ad-hoc check of the localized resou…
assistant: [tool: execute_command · uv run pytest tests/test_i18n.py -q 2>&1 | Select-String -Pattern "passed|failed" ; python C:\Users\Administrator\AppData\Local\Temp\c…
assistant: [tool: replace_in_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_verify2.py", "old_str": "    print(\"  static:\", [(r.uri.split(…
assistant: [tool: execute_command · python C:\Users\Administrator\AppData\Local\Temp\cw_i18n_verify2.py]

[tool: execute_command · uv run pytest tests/test_i18n.py -q]
assistant: M3 完成并验证（版本动态为 v5.7.0、tool_count 派生 49、page-types/capabilities 双语、catalog 22 条）。剩余最大块是 M4：22 个 prompt 正文（约 1250 行逻辑+模板混杂）。继续推进——先读第一批正文函数确定重写模式。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py", "offset": 345, "limit": 175}]
assistant: M4 模式确立：正文 =「模板进语料 + 代码保留逻辑与变量计算」。第一批迁移 4 个正文函数（incremental-update / search-wiki / quality-check / extract-knowledge，后者含条件片段需拆子 key）。

[tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_migrate3.py", "content": "\"\"\"One-shot migration: first batch of…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "old_str": "    aliases: \"frontmatter_extra.aliases 中的别名也参与 w…
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "old_str": "    aliases: \"Aliases in frontmatter_extra.aliase…

[tool: execute_command · python C:\Users\Administrator\AppData\Local\Temp\cw_i18n_migrate3.py]
assistant: [tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_verify3.py", "content": "\"\"\"Ad-hoc check: first batch of prompt…
assistant: [tool: execute_command · uv run pytest tests/test_i18n.py -q 2>$null | Select-Object -Last 3 ; python C:\Users\Administrator\AppData\Local\Temp\cw_i18n_verify3…
assistant: 脚本区间误删了 `_prompt_code_analysis`（它位于 quality-check 与 impact-review 之间）。立即从 git HEAD 恢复该函数。

[tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_restore.py", "content": "\"\"\"Restore _prompt_code_analysis, drop…
assistant: [tool: execute_command · python C:\Users\Administrator\AppData\Local\Temp\cw_i18n_restore.py]
assistant: [tool: execute_command · python C:\Users\Administrator\AppData\Local\Temp\cw_i18n_verify3.py]
assistant: 第一批正文双语渲染正常（中英各 4 篇，无哨兵；`unresolved_braces=True` 两例是 `variables={"granularity":"focused"}` 的 JSON 字面量，属预期）。清理临时脚本并查看改动范围。

[tool: execute_command · Remove-Item $env:TEMP\cw_i18n_*.py -Force -ErrorAction SilentlyContinue; git status --short; git diff --stat]
assistant: [tool: execute_command · uv run pytest -q 2>$null | Select-Object -Last 4]
user: 全量测试跑太久了，什么进展了
assistant: 进展汇报（全量测试已停，按你说的节奏来）：

## 已完成

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M1 基建 | `codewiki/mcp/i18n.py`（YAML 目录加载、`t()` 无回退哨兵、语言解析 config.json `lang` > `CODEWIKI_LANG` > locale > zh）、`locales/{zh,en}.yaml`、`pyproject` 打包 locales | 完成 |
| M2 元数据 | prompts 元数据 22 条（title/description/参数说明）外置；`list_prompts`、`get_prompt` 描述与未知兜底走 i18n；**catalog 改为从注册表派生**（15→22 条漂移根除） | 完成 |
| M3 resources | 静态/模板资源元数据、capabilities、page-types 全外置；**版本 `v5.5.0`→动态 5.7.0、`tool_count` 改从 registry 派生** | 完成 |
| M4 正文 | 22 篇中已完成 4 篇（incremental-update / extract-knowledge / search-wiki / quality-check），含条件片段 `granularity_note` 拆子 key 的模式 | 4/22 |
| 去漂移 | instructions「11 个 Prompt」→22；catalog 15→22；capabilities 版本号/工具数 | 完成 |

测试：`tests/test_i18n.py` 13 项全过（en 覆盖 zh 全 key、占位符集合一致、缺 key 出哨兵、语言优先级 7 个用例）。端到端实测中英双语渲染：元数据/资源/兜底文案已全英文切换，4 篇正文英文版已生效。

## 一个事故已修复

迁移脚本的替换区间过宽，误删了 `_prompt_code_analysis`（它夹在 quality-check 与 impact-review 之间）。已从 `git show HEAD` 恢复该函数，并加了「22 个正文函数必须齐全」的自检，全部通过。后续批次会把函数数量断言内置进脚本。

## 剩余

1. **正文 18 篇**（约 1000 行中文 → 英文创作）——最大头，逐批推进
2. **工具层散点**：`review_checklist.py`、`task_manager.py`、`note_query.py`、`wiki_lint.py`、`doc_writer.py`、`distill_conversation.py`、`prompt_server.py`、`workspace_bootstrap.py`
3. **落盘产物**：`agents_md.py`（AGENTS.md 约定块）、`wiki_index.py`、`reading_guide.py`、`schema_generator.py`——按你定的"只影响新生成、不追溯重写存量"

## 两点需要你定

- **改动未提交**（4 个文件改 + 2 个新增 + 语料 ~800 行）：是先提交这一批再继续，还是继续堆到 M4 做完一起提交？
- **正文节奏**：继续按 3-4 篇一批推（每批跑 `test_i18n`），还是你想先试用一下 `CODEWIKI_LANG=en` 看效果再决定投入？

另外后台蒸馏 worker 已产出 8 条 i18n 相关草稿笔记（待 `confirm_note`），其中一条正是"硬编码中文常量承载可派生数据必然漂移、i18n 集中化时应顺带根除"——与本次 R3 定案一致。
user: 我mcp没配环境变量，为什么查到的prompt是英文？    "codewiki": {

      "type": "stdio",

      "command": "D:\\repos\\CodeWiki-CN\\.venv\\Scripts\\python.exe",

      "args": [

        "-m",

        "codewiki.mcp.server"

      ],

      "disabled": false

    }
assistant: 好问题——这暴露了一个真 bug。你的配置里没有任何语言设置，按定案应该落到「系统 locale 推断」，中文系统应判为 zh。先在本机诊断实际值。

[tool: execute_command · D:\repos\CodeWiki-CN\.venv\Scripts\python.exe -c "import locale, pathlib, os; print('getlocale:', locale.getlocale()); print('LANG:', …
assistant: 确认是 bug：Windows 的 `locale.getlocale()` 返回 `('Chinese (Simplified)_China', '936')`——是**英文语言名**而非 `zh_CN`，我的判断只认 `zh*` 前缀，所以中文系统被误判成 en。修复并补测试。

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\i18n.py", "old_str": "    # 3) OS locale inference\n    code = _system_locale_cod…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\tests\\test_i18n.py", "new_str": "def test_resolve_locale_inference(tmp_path):\n    cfg = tmp_pa…
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\tests\\test_i18n.py", "old_str": "def test_resolve_locale_inference(tmp_path):\n    cfg = tmp_pa…
assistant: [tool: execute_command · uv run pytest tests/test_i18n.py -q 2>$null | Select-Object -Last 3; D:\repos\CodeWiki-CN\.venv\Scripts\python.exe -c "import locale, …
assistant: 修好了，`resolved: zh`，测试 14 项全过。

## 根因

语言解析第三顺位是「系统 locale 推断」，但 Python 在 Windows 上报的是**语言名而非 ISO 代码**：

```
locale.getlocale() -> ('Chinese (Simplified)_China', '936')   # 不是 'zh_CN'
```

我的判断只写了 `code.startswith("zh")`，`"chinese (simplified)_china"` 不匹配，于是落到「非 zh → en」——中文 Windows 被判成英文。你在配置里确实没设任何语言，是兜底路径算错了。

## 改动

- `codewiki/mcp/i18n.py`：`"zh"` 前缀 **或** 名称含 `chinese` 都判为中文（繁体 `Chinese (Traditional)_Taiwan` 同样算 zh）
- `tests/test_i18n.py`：新增 `test_resolve_windows_locale_names`，钉住 Windows 语言名这一支（含简体/繁体/英文三种）

## 你需要做的

语言在 **server 进程启动时解析一次**，所以要**重启 MCP**（IDE 里重载/禁用再启用，或重启 IDE）才会切回中文。

想强制英文时再显式配置（任一即可）：
- `~/.codewiki/config.json` 加 `"lang": "en"`
- 或启动环境设 `CODEWIKI_LANG=en`（优先级低于 config.json）

## 一个待你拍板的点

现在的行为是「未配置 → 跟系统语言走」，所以系统切英文界面时 CodeWiki 会自动变英文。如果你更想要「**不显式配置就永远中文**」，把兜底从 locale 推断改成直接 zh 即可（一行改动）。要改吗？
user: 先这样吧。现在还有什么需要做的吗，该翻译的都翻译完了吗
assistant: 没有，**远没翻完**——现在英文模式是「目录英文、点开正文还是中文」的混合状态。准确的清单如下。

## 已翻译（en 覆盖完整）

| 范围 | 内容 |
|---|---|
| 会话指引 | `server.instructions`（57 行） |
| 元数据 | 22 条 prompt 的 title/description/参数说明、`get_prompt` 描述与未知兜底 |
| 资源 | 静态/模板资源元数据 6 条、catalog（22 条派生）、capabilities（7 分类标签 + 5 key_patterns）、page-types（6 类描述 + 章节名 + 4 条 wikilink 规则） |
| 正文 | **4 / 22 篇**（incremental-update、extract-knowledge、search-wiki、quality-check） |

## 未翻译（剩余工作量）

1. **正文 18 篇**，约 1000 行中文——`init-wiki`、`init-workspace`、`add/remove-workspace-repo`、`generate-wiki`、`code-analysis`、`impact-review`、`change-review`、`architecture-review`、`workspace-analysis`、`cross-service-trace`、`ingest-note`、`team-memory-hook`、`distill-conversations`、`task-workflow`、`consolidate-knowledge`、`skill-creator`、`promote-note`。另含两个被引用的中文常量块 `_TASK_MEMORY_AGENTS_SECTION`、`_QWENWORK_CAPTURE_SECTION`。
2. **工具层散点常驻文案**：`review_checklist.py`（~51 行评审题面）、`task_manager.py`、`workspace_bootstrap.py`、`note_query.py`、`wiki_lint.py`、`doc_writer.py`、`distill_conversation.py`、`prompt_server.py`。
3. **落盘产物**（你定的 Q7 纳入）：`agents_md.py` 的 AGENTS.md 约定块、`wiki_index.py`、`reading_guide.py`、`schema_generator.py` 的 schema.yaml 中文描述。

按设计**明确不做**：工具 schema（registry.py 49 个工具全英文）、错误消息（全英文，统一兜底在 `registry.dispatch`）。

## 顺带说明三件悬着的

- **默认值策略**：保持现状（未配置 → 跟系统 locale），已按你说的"先这样吧"。
- **改动未提交**：`prompts.py` / `resources.py` / `server.py` / `pyproject.toml` 已改，新增 `i18n.py` + `locales/` + `tests/test_i18n.py`。建议先提交这一批——元数据层已经完整可用，且刚出过一次误删事故，有个回滚点更稳。
- **后台蒸馏**：产出了 8 条 i18n 相关草稿笔记（含"硬编码中文常量承载可派生数据必然漂移"那条），仍是 draft，需要你 `confirm_note` 才正式入库。

要不要我继续推进正文？我建议先提交当前批次，再按 3–4 篇一批往下推（每批跑 `test_i18n`，脚本内置函数数量断言防误删）。
user: 你说的正文是不是不会返给智能体，或者说用户看不到？这种我觉得直接用英文写就行，国际通用
assistant: 先纠正一个关键事实：**正文 100% 会返回给智能体**。`prompts/get` 的返回结构里，`GetPromptResult.messages[0].content.text` 装的就是正文全文——用户在 IDE 里选中 `/generate-wiki` 时，这 1250 行的指引会**整段进入 LLM 上下文**，而且在多数 IDE 里它以 user 消息形式出现在对话中，用户也看得到。所以"不返给智能体/用户看不到"不成立。

但你的直觉指向了一个更重要的耦合，我做实现时才看清：

**指令语言会传染产出语言。** 正文不是"说明书"，它是 Agent 的执行脚本——`write_doc_file` 写出的 wiki 页面、`ingest_note` 存的笔记、落盘的 AGENTS.md/schema.yaml，语言都跟着指令走。把正文改成英文单版，等于把中文用户的产出也一起换成英文（中文项目里长出英文 wiki）。这不是省不省翻译的问题，是"中文用户还要不要中文产出"的问题。

由此只有两个自洽的方案，混着做会自相矛盾：

| | A 全 i18n（现方案） | B 指令+产物统一英文 |
|---|---|---|
| 正文 | zh/en 双份，还需翻 18 篇 | 英文单版，不进语料 |
| 落盘产物 | 随语言生成 | 英文 |
| 中文用户产出 | 中文 wiki | 英文 wiki |
| 维护成本 | 1000 行双份 + 漂移风险 | 一次改写，零双份 |

折中方案（正文英文单版、产物仍 i18n）我不建议：Agent 读英文指令却在中文仓库里写中文 AGENTS.md，产物与指令长期不一致。

你拍板：

[tool: ask_followup_question · {"questions": [{"question": "指令层与产出语言策略选哪个？（正文 = 22 篇工作流指引；产物 = AGENTS.md 约定块/schema.yaml 描述/index.md/阅读指南）", "options": [{"labe…
user: <title>指令与产出语言策略</title>

<question>指令层与产出语言策略选哪个？（正文 = 22 篇工作流指引；产物 = AGENTS.md 约定块/schema.yaml 描述/index.md/阅读指南）</question>
<answers>
A 全 i18n(保持现方案：继续翻剩余 18 篇正文 + 产物 i18n，中文用户继续拿中文指令与中文产出)
</answers>
</question_item>

<question>若选 B（统一英文），已完成的部分怎么处理？</question>
<answers>
暂不处理(先定策略，已做的 4 篇原样留着，等下一轮一起收拾)
</answers>
</question_item>
</questions>
</question_answer>
assistant: 策略定为 **A 全 i18n**，继续推进正文。第二批取连贯的 4 篇（code-analysis / impact-review / change-review / architecture-review）。先精确定位函数区间（上次事故就是因为区间估错，这次先拿行号）。

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\prompts.py]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py", "offset": 392, "limit": 224}]
assistant: 第二批正文区间定位完毕（392-613），脚本会内置「22 个函数必须齐全」的写前断言。

[tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_migrate4.py", "content": "\"\"\"One-shot migration: prompt bodies …

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "old_str": "      ## 步骤 5: 验证修复\n      再次调用 lint_wiki 确认问题已解决"…

[User Cancelled]
user: 看看竞品是怎么做的，是不是只需要把instructions系统提示词优化一下就行了，比如说加一条语言限制，请用xxx语言输出
assistant: 这个思路值得认真验——它可能把剩下 18 篇正文的翻译工作量直接归零。但它的成败取决于一个我没验证过的前提：**MCP 的 `instructions` 到底会不会被 IDE 注入成系统提示词**（Claude Desktop 长期有「忽略 server instructions」的已知问题）。先查竞品与该前提。

[tool: web_search · MCP server instructions ignored Claude Desktop Cursor support system prompt injection]

[tool: web_search · Context7 MCP server prompt templates description language i18n only English]
assistant: 搜索结果偏泛。直接查规范原文与竞品源码，确认两件事：`instructions` 在协议里是「必须注入」还是「建议注入」，以及竞品 MCP 层文案到底做不做多语言。

[tool: web_fetch · https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle]

[tool: web_fetch · https://raw.githubusercontent.com/upstash/context7-mcp/master/README.md]
assistant: 查到两个决定性事实，都指向你的直觉是对的，但落点要换。

## 1. 竞品：MCP 层文案一律英文，多语言只做给人看的文档

Context7（Upstash，MCP 领域的标杆）的仓库结构很说明问题：

- **MCP 层零 i18n**：暴露给 LLM 的 `resolve-library-id` / `query-docs`，工具名与参数说明全是英文一份。
- **i18n 目录里是 README**：`i18n/README.{zh-CN,zh-TW,ja,ko,es,fr,de,ru,ar…}` 共 20 种语言——翻译的是**人类读的文档**，不是协议里的文案。
- **行为约束不下沉到 server**：它想让用户"总是用 Context7"时，做法是让用户自己加规则文件——Cursor 写 `Settings > Rules`，Claude Code 写 `CLAUDE.md`，示例规则就是一句英文 `Always use Context7 when...`。

结论：主流做法是「给机器的文案英文单份、给人的文档做多语言、行为约定交给宿主规则文件」。我们正在做的 22 篇正文双份翻译，是竞品连英文版都只写一份、直接不翻的那一层。

## 2. 但"加一条语言限制"放在 MCP instructions 里不可靠

规范里 `instructions` 的定义就一句话：

```
"instructions": "Optional instructions for the client"
```

整份 lifecycle 规范对它**没有任何 MUST/SHOULD 的注入要求**——客户端怎么处理由实现自定（Claude Desktop 早期就是直接忽略）。所以把语言约束寄托在它上面，是赌客户端实现。

## 3. 关键：我们有一条比 MCP instructions 可靠得多的注入通道

**写进用户仓库根目录的 AGENTS.md**。各 IDE 都稳定加载项目根的 AGENTS.md / CLAUDE.md，而我们 `tools/agents_md.py` 本来就在往那里写约定块。把「所有产出使用 XXX 语言」写进这个块（zh 版写中文、en 版写英文，随 i18n 走），才是 100% 生效的语言闸门。MCP instructions 里可以再放一句作为双保险。

## 由此我推荐调整策略（方案 E）

| 层 | 处置 | 剩余工作量 |
|---|---|---|
| 元数据/资源层 | 保留已完成的 i18n（IDE 里给人看的"菜单"，竞品不做但无害） | 0 |
| 22 篇工作流正文 | **停止翻译**，保持中文单份（读者是 LLM，语言无所谓） | 0（省掉 1000 行） |
| 产出语言 | 语言约束写进 **AGENTS.md 约定块**（i18n），instructions 加一句双保险 | ~10 行 |
| 产物层 | AGENTS.md 约定块、schema.yaml 模板注释、index.md 骨架做 i18n | ~150 行 |

仍要提醒边界：AGENTS.md 只在 `init_wiki` 过的仓库存在；schema.yaml 这类模板文案不受语言约束影响（它是 Python 写死的，不是 LLM 产出），所以那部分仍需要 i18n，省不掉。

也纠正一下前提：正文**会**整段进入 LLM 上下文（上一轮说过），用户也可能在对话里看到。但你的结论依然成立——理由不是"看不到"，而是"读者是 LLM，产出语言另由约束控制"。

已翻的 4 篇正文（incremental-update 等）已在语料里，保留无害（zh 模式都是中文，en 模式这 4 篇是英文、其余中文，不影响执行），不用回退。

要按方案 E 走吗？这会覆盖你上一轮选的 A。
user: 好的按照方案E走，已经翻译的4篇正文回退撤销
assistant: 方案 E 已定，先干净回退那 4 篇正文（恢复为代码内中文 f-string，并从双语料删除 `bodies` 段）。

[tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_revert.py", "content": "\"\"\"Revert batch-1 prompt bodies back to…
assistant: [tool: execute_command · python C:\Users\Administrator\AppData\Local\Temp\cw_i18n_revert.py]
assistant: [tool: execute_command · uv run pytest tests/test_i18n.py -q 2>$null | Select-Object -Last 2; git diff --stat -- codewiki/mcp/prompts.py; "bodies refs: " + (Se…
assistant: 回退干净：14 项测试仍绿，`bodies` 引用归零，prompts.py 只剩元数据外置与注册表化的改动。

现在执行方案 E 的核心机制——**语言约束**。先落到 MCP instructions（双份各加一节，客户端注入时生效）：

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "old_str": "    8. 对话蒸馏: 调用 Prompt \"distill-conversations\" 从…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "old_str": "    8. Conversation distillation: invoke Prompt \"…
assistant: [tool: execute_command · uv run pytest tests/test_i18n.py -q 2>$null | Select-Object -Last 2; D:\repos\CodeWiki-CN\.venv\Scripts\python.exe -c "import sys; sys…
assistant: 方案 E 第一段落完成。

## 已完成

| 项 | 状态 |
|---|---|
| 4 篇正文回退 | 恢复为 `prompts.py` 内联中文 f-string，22 个函数齐全；`locales/*` 的 `bodies:` 段整体删除，`bodies.` 引用归零 |
| 语言约束 | `server.instructions` 双语各加「语言」小节（zh：所有产出用中文；en：Produce all output in English），并明确写了"指引语言 ≠ 产出语言"，避免 Agent 模仿中文正文 |
| 验证 | 14 项测试全绿；双语 instructions 末节渲染正确 |

## 现在的实际状态

英文模式 = **英文的 prompt 目录/资源元数据 + 中文工作流指令 + instructions 要求英文产出**。最后这条只有在客户端真的把 `instructions` 注入系统提示时才生效（规范无保证），所以它只是双保险——**真正的可靠闸门是 AGENTS.md**，还没做。

## 剩余（按方案 E）

1. **AGENTS.md 约定块 i18n + 语言约束段**（`tools/agents_md.py:226-347`，约 120 行中文）——唯一的大块，也是最可靠的那道闸门，各 IDE 都稳定加载项目根 AGENTS.md
2. `schema_generator.py` 的 schema.yaml 中文注释模板（LLM 不会帮你翻译，Python 写死的）
3. `wiki_index.py` 的 index.md 骨架、`reading_guide.py` 的阅读指南
4. 工具层散点短提示（评审题面、hint 等，量小）——这块要不要做你定，它介于"机器指令"和"给人看的提示"之间

要我继续做第 1 项（AGENTS.md 约定块）吗？它需要读完整函数后把 120 行约定搬进语料并写英文版，是剩下的主要工作量；做完这道闸门，方案 E 才算闭环。
user: 好，继续
assistant: 继续 AGENTS.md 约定块。先读完整函数结构（含变量计算与动态片段），避免迁移时漏掉中文条件片段。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\agents_md.py", "limit": 200}]
assistant: 结构清楚。开始迁移 AGENTS.md 约定块：模板进语料（含新增「产出语言」段），函数保留逻辑与模块列表计算。

[tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_agents.py", "content": "\"\"\"Migrate _build_section (agents_md.py…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "old_str": "    aliases: \"frontmatter_extra.aliases 中的别名也参与 w…
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "old_str": "    aliases: \"Aliases in frontmatter_extra.aliase…

[tool: execute_command · python C:\Users\Administrator\AppData\Local\Temp\cw_i18n_agents.py]
assistant: [tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_verify4.py", "content": "\"\"\"Ad-hoc check: AGENTS.md block rende…
assistant: [tool: execute_command · uv run pytest tests/test_i18n.py -q 2>$null | Select-Object -Last 2; python C:\Users\Administrator\AppData\Local\Temp\cw_i18n_verify4.…
assistant: AGENTS.md 块双语渲染全部正确（无 `{{` 泄漏、JSON 示例与 `\n` 转义正确、语言段生效）。这一步动了 close_session 写入链路，跑受影响的测试子集确认没破坏。

[tool: search_content · d:\repos\CodeWiki-CN\tests]
assistant: [tool: execute_command · uv run pytest tests/test_centralized_layout_fixes.py tests/test_install_hooks.py tests/test_openviking_borrowings.py tests/test_strip_…
assistant: AGENTS.md 块完成且无回归（受影响子集 166 项全过）。方案 E 的主闸门已经落地。快速确认下一块（schema.yaml 模板）的中文是内嵌在代码里还是在模板文件中，这决定它的 i18n 做法。

[tool: list_dir · {"target_directory": "d:\\repos\\CodeWiki-CN\\codewiki\\templates"}]
assistant: AGENTS.md 块已闭环。顺手查到一个**简化剩余工作的关键事实**：产物层与评审题面的中文不在代码里，而在模板文件中——

```
codewiki/templates/
  schema.yaml            ← schema.yaml 中文注释模板
  review_checklist.yaml  ← 评审题面（之前以为内嵌在 review_checklist.py）
  ontology.yaml
  workspace/  github_pages/
```

这意味着这两块的 i18n 不需要翻译代码字符串，只需**按语言放两份模板文件 + 代码按 `lang` 选路径**（`schema.yaml` / `schema.en.yaml`，或 `templates/zh/`、`templates/en/`）。比前面的正文迁移简单一个量级，而且 `pyproject` 的 `artifacts` 已包含 `codewiki/templates/**/*`，新增文件自动进 wheel。

## 当前状态

| 层 | 状态 |
|---|---|
| i18n 基建 + 语料 + 测试 | 完成（14 项） |
| prompt 元数据 / 资源层 | 完成（22 条 + catalog 派生 + capabilities/page-types） |
| instructions 语言约束 | 完成（双语） |
| **AGENTS.md 约定块 + 语言闸门** | **完成**（双语，转义/JSON 示例/模块链接均验证正确） |
| 工作流正文 | 按方案 E 不翻译，已回退为中文单份 |
| 受影响测试 | 166 项全过 |

## 剩余

1. `templates/schema.yaml` → 加英文版 + 按 lang 选文件（首次拷贝按语言；已存在不动，符合 R2 不追溯）
2. `templates/review_checklist.yaml` → 同上
3. `wiki_index.py` 的 index.md 骨架、`reading_guide.py` 的阅读指南（代码内中文，量小）
4. 工具层散点短提示（评审 hint 等）——要不要做仍待你定

要我继续把 1、2 做了吗？这两块做完，方案 E 的产物层就基本闭环了。
user: 都做了
assistant: 开工。先做 `templates/schema.yaml`：读模板内容与它的加载点。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\templates\\schema.yaml"}]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\schema_generator.py]
assistant: 模板 242 行，中文集中在注释与部分取值（`page_types.*.description`、各类 `required_sections`）。先看加载点代码，再产出英文版模板。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\schema_generator.py", "offset": 220, "limit": 60}]
assistant: 模板加载点是模块级常量 `_CONFIG_PATH`。先确认它被哪些地方引用，同时产出英文版模板。

[tool: search_content · d:\repos\CodeWiki-CN]

[tool: write_to_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\templates\\schema.en.yaml", "content": "# CodeWiki default schema template (English vari…
assistant: 模板加载点只在本文件内使用。改为按语言选模板，并保留「已有 schema.yaml 不动」的既定行为。

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\schema_generator.py", "old_str": "_CONFIG_PATH = Path(__file__).resolve().…

[tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_verify5.py", "content": "\"\"\"Ad-hoc check: schema template switc…
assistant: [tool: execute_command · python C:\Users\Administrator\AppData\Local\Temp\cw_i18n_verify5.py; uv run pytest tests/test_i18n.py tests/test_workspace_layout.py t…
assistant: 英文模板有 YAML 解析错误——`skill` 的 description 值里含半角 `": "`（中文版是全角所以没暴露）。修复，并顺手加一条**防漂移测试**：两份模板的键结构必须一致（这正是前面根除的同类问题）。

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\templates\\schema.en.yaml", "old_str": "    description: SKILL.md behavioral-instructi…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\tests\\test_i18n.py", "old_str": "from __future__ import annotations\n\nimport re\n\nimport pyte…
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\tests\\test_i18n.py", "old_str": "def test_set_lang_rejects_unsupported():\n    with pytest.rais…
assistant: [tool: execute_command · python C:\Users\Administrator\AppData\Local\Temp\cw_i18n_verify5.py; uv run pytest tests/test_i18n.py -q 2>$null | Select-Object -Last…
assistant: schema 双语切换成功（15 项测试通过，含新的防漂移测试）。继续 `review_checklist.yaml`：读模板与加载点。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\templates\\review_checklist.yaml"}]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\review_checklist.py]
assistant: 模板只有 47 行，但真正的大头是**代码内置的评审题面** `BUILTIN_CHECKLISTS`（约 51 行中文）。先读它和模板拷贝点。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\review_checklist.py", "offset": 40, "limit": 210}]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]
assistant: 模板拷贝点在 `init_wiki.py`，内置清单是代码常量。读拷贝逻辑并确认 `BUILTIN_CHECKLISTS` 的外部引用。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\init_wiki.py", "offset": 25, "limit": 25}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\init_wiki.py", "offset": 100, "limit": 25}]

[tool: search_content · d:\repos\CodeWiki-CN]
assistant: 拷贝点确认（`init_wiki.py` 同时拷 schema 与 review_checklist，且都存在时跳过）。先产出英文模板与内置清单双语语料。

[tool: write_to_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\templates\\review_checklist.en.yaml", "content": "# CodeWiki review_changes generic revi…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "old_str": "      {end_marker}", "new_str": "      {end_marker…
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "old_str": "      {end_marker}", "new_str": "      {end_marker…

[tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_checklist.py", "content": "\"\"\"Localize the builtin review check…
assistant: [tool: execute_command · python C:\Users\Administrator\AppData\Local\Temp\cw_i18n_checklist.py]
assistant: 模板选择逻辑要落到 `init_wiki.py`（它同时拷 schema 与 review_checklist）。先看 schema 模板的使用处。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\init_wiki.py", "offset": 55, "limit": 45}]
assistant: 模板路径改为按语言在**拷贝时**解析（不固化在模块级，避免语言切换失效）。

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\init_wiki.py", "old_str": "# Schema template: package-bundled copy is the …
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\init_wiki.py", "old_str": "    schema_dest = output_dir_p / \"schema.yaml\…
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\init_wiki.py", "old_str": "    if _REVIEW_CHECKLIST_TEMPLATE and _REVIEW_C…
assistant: [tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_verify6.py", "content": "\"\"\"Ad-hoc check: review checklist + te…
assistant: [tool: execute_command · python C:\Users\Administrator\AppData\Local\Temp\cw_i18n_verify6.py; uv run pytest tests/test_i18n.py tests/test_review_changes.py tes…
assistant: 模板与清单双语切换全部正确。继续工具层散点。先精确定位这几处中文（并顺带 lint 检查已改文件）。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\note_query.py", "offset": 715, "limit": 22}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_lint.py", "offset": 1188, "limit": 14}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\doc_writer.py", "offset": 1430, "limit": 14}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\review_changes.py", "offset": 305, "limit": 12}]
assistant: 定位到 4 处（note_query / wiki_lint / doc_writer / review_changes）。先改其中 3 处（第 4 处需要更多上下文定位函数边界），并配套语料。

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\note_query.py", "old_str": "    total_est = sum(e[\"est_tokens\"] for e in…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\doc_writer.py", "old_str": "            if old_fp and old_fp != new_code_f…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\review_changes.py", "old_str": "    note = \"\"\n    if not sources:\n    …

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "old_str": "      questions: \"模块导入是否触发重副作用（网络、文件写、DB 连接）？\"",…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "old_str": "      questions: \"Does importing the module trigg…
assistant: [tool: execute_command · uv run pytest tests/test_i18n.py tests/test_review_changes.py tests/test_query_transparency.py tests/test_stale_evidence_signal.py tes…
assistant: 本轮收尾。已完成部分验证通过（54 项测试）。

## 本轮完成

| 项 | 内容 |
|---|---|
| `templates/schema.yaml` | 新增英文版 `schema.en.yaml`（242 行，含 `page_types` 描述与各类 `required_sections`），`schema_generator` 与 `init_wiki` 均按语言选模板；**已有 schema.yaml 不覆盖**（符合 R2 不追溯） |
| `templates/review_checklist.yaml` | 新增英文版；`init_wiki` 按语言选 |
| 内置评审清单 | `BUILTIN_CHECKLISTS` 由代码常量改为语料驱动（`review_checklist.<组>.<id>.title/questions`，15 条），**id 结构留在代码里**保证项目覆盖层按 id 合并不受影响 |
| 工具散点 3 处 | `note_query` 的 by_file hint（含空结果提示）、`doc_writer` 的 fingerprint 漂移告警、`review_changes` 的"未找到 SPEC" |
| 防漂移测试 | 新增 `schema.yaml` / `schema.en.yaml` 键结构一致性断言——两份手维护模板正是旧 catalog 漂移的同类隐患 |

实测双语：`schema.yaml`↔`schema.en.yaml`、`review_checklist.yaml`↔`.en.yaml` 切换正常；清单标题与问题随语言切换且条目数一致（10 + 5）。

## 剩余（7 处，量都不大）

- `wiki_lint.py` 的 stale note suggestion（1 处，需先定位函数边界）
- `prompt_server.py:1114-1120` 知识沉淀候选提醒
- `distill_conversation.py` prepare 清单提示 + merge 来源标记
- `task_manager.py:792-797` 压缩指令块
- `workspace_bootstrap.py:698-713` 布局征询文案
- `wiki_index.py` 的 index.md 骨架、`reading_guide.py` 的阅读指南（落盘产物）
- `init_wiki.py:291` 返回给 Agent 的初始化结果说明

## 两点提醒

1. **改动尚未提交**，且自上次全量测试（M3 阶段）后新增了大量改动——提交前建议完整跑一次 `uv run pytest`（约几分钟，你之前嫌久，可以用 `pytest -q -x` 或分目录跑）。
2. `pyproject.toml` 的 `artifacts` 已含 `codewiki/templates/**/*`，新增的两个 `.en.yaml` 自动进 wheel；`locales/**/*` 也已加入。

要我继续把这 7 处做完吗？做完方案 E 就全部闭环了。
user: 好的 继续做
assistant: 继续。先并行读取剩余点位的精确上下文。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_lint.py", "offset": 1175, "limit": 26}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\prompt_server.py", "offset": 1108, "limit": 20}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\task_manager.py", "offset": 786, "limit": 18}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\workspace_bootstrap.py", "offset": 694, "limit": 24}]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\workspace_bootstrap.py", "limit": 30}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\prompt_server.py", "limit": 30}]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\task_manager.py]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\prompt_server.py]
assistant: 信息齐了。开始批量改造（wiki_lint 用局部导入；task_manager 把常量改为惰性函数，避免 import 期固化语言）。

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_lint.py", "old_str": "        issue = {\n            \"check\": \"sta…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\task_manager.py", "old_str": "_COMPACT_INSTRUCTION = (\n    \"阅读 entries_t…

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\workspace_bootstrap.py", "offset": 31, "limit": 25}]
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\workspace_bootstrap.py", "old_str": "from codewiki.mcp.tools.workspace_lay…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\prompt_server.py", "old_str": "from codewiki.mcp.session import SessionSto…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\task_manager.py", "old_str": "                \"instruction\": _COMPACT_IN…
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\workspace_bootstrap.py", "old_str": "                \"question\": (\n    …

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\prompt_server.py", "old_str": "            \"📝 知识沉淀候选 ({n} 项)\\n\\n\"\n   …

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "old_str": "  review_changes:\n    no_spec_note: \"未找到 SPEC——仅…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "old_str": "  review_changes:\n    no_spec_note: \"No SPEC fou…
assistant: [tool: execute_command · uv run pytest tests/test_i18n.py tests/test_task_manager.py tests/test_workspace_bootstrap.py tests/test_low_adoption.py tests/test_fr…
assistant: 162 项通过。继续最后 4 处，先定位。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\distill_conversation.py", "offset": 795, "limit": 14}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\distill_conversation.py", "offset": 1655, "limit": 16}]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\wiki_index.py]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\reading_guide.py]
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\distill_conversation.py", "old_str": "        marker = f\"> 合并自蒸馏候选：{title…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\distill_conversation.py", "old_str": "        if any(c.get(\"friction_scor…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "old_str": "    layout_centralized: \"知识全部集中在本工作区 repowiki，业务仓…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "old_str": "    layout_centralized: \"All knowledge is central…
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\reading_guide.py", "offset": 64, "limit": 80}]
assistant: 继续 reading_guide（落盘产物）。改造中文标题/说明/表头为语料驱动。

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\reading_guide.py", "old_str": "        # Build markdown. 带 OKF 兼容 frontmat…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "old_str": "  distill_conversation:\n    merge_marker: \"> 合并自…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "old_str": "  distill_conversation:\n    merge_marker: \"> Mer…
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\reading_guide.py", "old_str": "                        \"\",\n            …
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\reading_guide.py", "old_str": "                \"---\",\n                f…
user: <cb_summary>
This session is being continued from a previous conversation that was compacted to stay within the model context window.
Messages after this summary (if any) are the original recent turns. Tool results from before this summary were omitted.
If you need exact code, command output, or file contents from before compaction, re-read those files. Do not treat omitted tool bodies as still in context.

Earlier user requests:
- Q3不用回退，我们发版本前跑测试能暴露该问题，暴露问题后补充相关内容即可   Q4 包含，需要再看下是否还有别的中文会返给智能体的，一起改掉
- Q6 A    Q7纳入  其他按推荐
- 全部按你推荐来
- 继续
- 继续开发
- 全量测试跑太久了，什么进展了
- 我mcp没配环境变量，为什么查到的prompt是英文？    "codewiki": {
       "type": "stdio",
       "command": "D:\\repos\\CodeWiki-CN\\.venv\\Scripts\\python.exe",
       "args": [
         "-m",
         "codewiki.mcp.server"
       ],
       "disabled": false
     }
- 先这样吧。现在还有什么需要做的吗，该翻译的都翻译完了吗
- 你说的正文是不是不会返给智能体，或者说用户看不到？这种我觉得直接用英文写就行，国际通用
- <question_answer> <title>指令与产出语言策略</title> <questions> <question_item id="strategy"> <question>指令层与产出语言策略选哪个？（正文 = 22 篇工作流指引；产物 = AGENTS.md 约定块/schema.yaml 描述/index.md/阅读指南）</question> <answers> A 全 i18n(保持现方案：继续翻剩余 18 篇正文 + 产物 i18n，中文用户继续拿中文指令与中文产出) </answers> </question_item> <question_item id="cleanup"> <question>若选 B（统一英文），已完成的部分怎么处理？</question> <answers> 暂不处理(先定策略，已做的 4 篇原样留着，等下一轮一起收拾) </answers> </question_item> </questions> </question_answer>
- 看看竞品是怎么做的，是不是只需要把instructions系统提示词优化一下就行了，比如说加一条语言限制，请用xxx语言输出
- 好的按照方案E走，已经翻译的4篇正文回退撤销
- 好，继续
- 都做了

Earlier assistant notes (truncated):
- 模板加载点是模块级常量 `_CONFIG_PATH`。先确认它被哪些地方引用，同时产出英文版模板。
- 模板加载点只在本文件内使用。改为按语言选模板，并保留「已有 schema.yaml 不动」的既定行为。
- 英文模板有 YAML 解析错误——`skill` 的 description 值里含半角 `": "`（中文版是全角所以没暴露）。修复，并顺手加一条**防漂移测试**：两份模板的键结构必须一致（这正是前面根除的同类问题）。
- schema 双语切换成功（15 项测试通过，含新的防漂移测试）。继续 `review_checklist.yaml`：读模板与加载点。
- 模板只有 47 行，但真正的大头是**代码内置的评审题面** `BUILTIN_CHECKLISTS`（约 51 行中文）。先读它和模板拷贝点。
- 模板拷贝点在 `init_wiki.py`，内置清单是代码常量。读拷贝逻辑并确认 `BUILTIN_CHECKLISTS` 的外部引用。
- 拷贝点确认（`init_wiki.py` 同时拷 schema 与 review_checklist，且都存在时跳过）。先产出英文模板与内置清单双语语料。
- 模板选择逻辑要落到 `init_wiki.py`（它同时拷 schema 与 review_checklist）。先看 schema 模板的使用处。

Tools used before this summary: replace_in_file × 29, execute_command × 26, read_file × 22, write_to_file × 20, search_content × 11, search_file × 3, task × 2, list_dir × 2, ask_followup_question × 2, web_search × 2, web_fetch × 2, delete_file × 1, read_lints × 1
</cb_summary>

继续
assistant: 继续最后一处落盘产物 `wiki_index.py`（index.md 骨架等），先定位相关代码段。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_index.py", "offset": 463, "limit": 55}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_index.py", "offset": 262, "limit": 14}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_index.py", "offset": 368, "limit": 50}]
assistant: wiki_index 需要改 5 处。先确认 `_PAGE_TYPE_LABELS` 无其他引用，并同步双语语料。

[tool: search_content · d:\repos\CodeWiki-CN]

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "old_str": "  distill_conversation:\n    friction_hint: \"提示：f…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "old_str": "  distill_conversation:\n    friction_hint: \"Tip:…
assistant: 语料追加锚点未命中，需确认文件当前结构。

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\locales\zh.yaml]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\locales\en.yaml]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "offset": 525, "limit": 30}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "offset": 521, "limit": 30}]
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "old_str": "    friction_hint: \"提示：friction_score ≥ 20 的会话含明显…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "old_str": "    friction_hint: \"Tip: conversations with frict…
assistant: 语料就绪。现在改 `wiki_index.py` 的 7 处引用。

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_index.py", "old_str": "# Chinese labels for page types\n_PAGE_TYPE_LA…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_index.py", "old_str": "    for page_type, label in _PAGE_TYPE_LABELS.…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_index.py", "old_str": "    try:\n        from codewiki.src.config imp…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_index.py", "old_str": "        parts.append(\"## 入门指引\")", "new_str":…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_index.py", "old_str": "        parts.append(\"## 知识笔记\")", "new_str":…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_index.py", "old_str": "                header = (\n                  …

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_index.py", "old_str": "    if summary is None:\n        summary = \"(…
assistant: 同文件并发写锁冲突，后 4 处未生效，改为逐个重试。

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_index.py", "old_str": "        parts.append(\"## 入门指引\")", "new_str":…
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_index.py", "old_str": "        parts.append(\"## 知识笔记\")", "new_str":…
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_index.py", "old_str": "                header = (\n                  …
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_index.py", "old_str": "    if summary is None:\n        summary = \"(…
assistant: wiki_index 完成。剩最后 `init_wiki.py` 的返回文案。

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\init_wiki.py]
assistant: `init_wiki.py` 已无中文。最后全量扫一遍 `mcp/tools` 的散点中文，确认没有遗漏。

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools]
assistant: [tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\wiki_lint.py]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\wiki_index.py]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\tools\reading_guide.py]
assistant: `wiki_lint.py` 还剩 1 处返回给 Agent 的采纳率提示 + 1 处操作日志文案，读取上下文。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_lint.py", "offset": 1325, "limit": 32}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_lint.py", "offset": 2505, "limit": 16}]
assistant: 最后 2 处（同文件，逐个改）。

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_lint.py", "old_str": "        adopted = int(adoption_counts.get(rel_p…
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_lint.py", "old_str": "                \"suggestion\": (\n            …
assistant: [tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_lint.py", "old_str": "            append_log(str(output_dir), \"lint_…
assistant: 补上对应语料（追加到已有的 `wiki_lint` 组内）。

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "old_str": "    stale_note_suggestion: \"超过 {overdue_days} 天未验…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "old_str": "    stale_note_suggestion: \"Unverified for {overd…
assistant: 全部散点改造完毕。检查 lint 并跑相关测试验证。

[tool: read_lints · {"paths": ["d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_lint.py", "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\tools\\wiki_index.py", "d:…
assistant: lint 结果中除 `distill_conversation.py` 的既有历史类型告警外无新增错误。跑相关测试验证。

[tool: execute_command · uv run pytest tests/test_i18n.py tests/test_low_adoption.py tests/test_freshness.py tests/test_skill_creator.py tests/test_query_trans…
assistant: 发现命名空间不一致风险：`reading_guide`/`index` 语料落在 `tools:` 组下，而代码用的是 `artifacts.*` 前缀。先核查语料顶层结构。

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\locales\zh.yaml]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki]
assistant: 确认命名空间应为 `artifacts.*`——`reading_guide`/`index` 语料被误放进 `tools` 组。需把它们移入 `artifacts` 组。先读两边结构。

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "offset": 300, "limit": 14}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "offset": 440, "limit": 12}]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\locales\en.yaml]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "offset": 515, "limit": 62}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "offset": 508, "limit": 62}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "offset": 434, "limit": 14}]
assistant: 修复命名空间：把 `reading_guide`/`index` 两个子组从 `tools` 组移入 `artifacts` 组。先删（两文件并行）。

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "old_str": "    layout_centralized: \"知识全部集中在本工作区 repowiki，业务仓…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "old_str": "    layout_centralized: \"All knowledge is central…
assistant: 删除成功。现在把两组插入 `artifacts` 组尾部。

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "old_str": "      所有产出使用**中文**——Wiki 文档、笔记、代码注释、commit message…

[tool: replace_in_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "old_str": "      Produce all output in **English** — Wiki doc…
assistant: 命名空间已修复。写验证脚本断言双语取值，并重跑一致性/布局相关测试。

[tool: write_to_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\cw_i18n_verify8.py", "content": "\"\"\"Verify artifacts.* keys resolve in …
assistant: [tool: execute_command · python C:\Users\Administrator\AppData\Local\Temp\cw_i18n_verify8.py; uv run pytest tests/test_i18n.py tests/test_workspace_layout.py t…
assistant: 全部完成，验证通过（61 项测试，双语 missing=0）。

## 收尾总结：方案 E（i18n 集中化 + 双语）剩余部分已全部闭环

本轮完成：

| 类别 | 内容 |
|---|---|
| `wiki_index.py`（index.md 产物） | 7 处语料化：frontmatter aliases、自动生成注释、标题、入门指引/知识笔记分节、类型分组标签（`_PAGE_TYPE_LABELS` 常量改为惰性 `_page_type_labels()`）、操作日志头、`(无摘要)` 兜底 |
| `reading_guide.py`（阅读指南产物） | 全部中文文案语料化（frontmatter title/description、intro、推荐阅读顺序表头、模块排名、页脚统计行） |
| `wiki_lint.py` 剩 2 处 | 零采纳（low_adoption）suggestion、「检查完成 N 个问题」操作日志 |
| 命名空间修复 | `reading_guide`/`index` 语料组原本误插在 `tools:` 下、而代码用 `artifacts.*` 前缀——已把两组移入顶层 `artifacts:` 组（与 `agents_md` 等同类产物对齐） |

**关键坑**：这次命名空间错位暴露了一个盲区——`t()` 对缺失 key 返回带前缀哨兵，普通渲染测试默认中文时照样取得到值（因为我当时把语料放进了 `tools` 组而代码查 `artifacts`，中文命中不了就报 MISSING……不过修复前验证显示取到值），说明**双语都断言、且直接查 missing 计数**比单测更有把握。`test_i18n.py` 的占位符一致性测试并不检查 key 是否存在，今后新增 key 建议在测试里加一条"双语 missing 计数均为 0"。

## 现在的整体状态（方案 E 全量）

- 22 篇正文（instructions/prompts）中已翻译的 4 篇按你的指示回退，正文维持中文主版本
- 产物层与提示散点全部 i18n 化：AGENTS.md 约定块、schema.yaml、review_checklist（内置清单 + 模板）、index.md、阅读指南、操作日志，以及 note_query / wiki_lint / doc_writer / review_changes / task_manager / prompt_server / workspace_bootstrap / distill_conversation 的返回文案
- 语言闸门在系统提示与 AGENTS.md 中已加"请用 X 语言输出"约束

## 提醒

- **改动未提交**。建议发版本前跑一次全量 `uv run pytest`（分片已验证过受影响模块，但全量最保险）。
- 需不需要我现在跑全量，或直接帮你整理提交？
user: <cb_summary>
This session is being continued from a previous conversation that was compacted to stay within the model context window.
Messages after this summary (if any) are the original recent turns. Tool results from before this summary were omitted.
If you need exact code, command output, or file contents from before compaction, re-read those files. Do not treat omitted tool bodies as still in context.

Earlier user requests:
- 继续

Earlier assistant notes (truncated):
- wiki_index 完成。剩最后 `init_wiki.py` 的返回文案。
- `init_wiki.py` 已无中文。最后全量扫一遍 `mcp/tools` 的散点中文，确认没有遗漏。
- `wiki_lint.py` 还剩 1 处返回给 Agent 的采纳率提示 + 1 处操作日志文案，读取上下文。
- 最后 2 处（同文件，逐个改）。
- 补上对应语料（追加到已有的 `wiki_lint` 组内）。
- 全部散点改造完毕。检查 lint 并跑相关测试验证。
- lint 结果中除 `distill_conversation.py` 的既有历史类型告警外无新增错误。跑相关测试验证。
- 发现命名空间不一致风险：`reading_guide`/`index` 语料落在 `tools:` 组下，而代码用的是 `artifacts.*` 前缀。先核查语料顶层结构。

Tools used before this summary: replace_in_file × 20, search_content × 10, read_file × 7, read_lints × 1, execute_command × 1
</cb_summary>

22 篇正文（instructions/prompts）这个用户能看到吗
assistant: [tool: ask_followup_question · {"questions": [{"question": "本会话要关联哪个任务？（用于跨会话任务记忆与补蒸馏归属）", "options": [{"label": "产品维护", "description": "task_id=产品维护"}, {"labe…
user: <question>本会话要关联哪个任务？（用于跨会话任务记忆与补蒸馏归属）</question>
<answers>
跳过(本次会话不做任务关联)
</answers>
</question_item>
</questions>
</question_answer>
assistant: [tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\prompts.py"}]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\resources.py", "offset": 250, "limit": 100}]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\server.py]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\locales\zh.yaml]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\zh.yaml", "offset": 70, "limit": 120}]

[tool: search_content · d:\repos\CodeWiki-CN\codewiki\mcp\locales\en.yaml]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\i18n.py"}]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\codewiki\\mcp\\locales\\en.yaml", "limit": 80}]
assistant: [tool: search_content · d:\repos\CodeWiki-CN\repowiki]

[tool: execute_command · git -C d:/repos/CodeWiki-CN diff --stat codewiki/mcp/prompts.py codewiki/mcp/resources.py codewiki/mcp/server.py]
assistant: [tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\repowiki\\tasks\\产品维护\\memories\\iamwangbao-163-com.md"}]
assistant: 结合代码核对和本任务（产品维护）的 i18n 上下文，回答如下。

## 结论：人类用户在界面上看不到这 22 篇正文

"用户能看到吗"要分两个角色回答——因为 22 篇正文唯一的消费方是 **Agent**，不是人类。

**人类用户（IDE/MCP 客户端 UI）——看不到正文，只能看到元数据。** 正文全文只有一个出口：`prompts/get` 按名调用时返回（`codewiki/mcp/prompts.py:1531-1540`），而它需要调用方主动按 name 请求。其余所有暴露通道都不含正文：

- `prompts/list` 只返回 name/title/description/arguments 描述（`prompts.py:1463-1477`）
- `codewiki://prompts/catalog` 资源由 `prompt_catalog()` 派生，同样只有元数据（`prompts.py:1429-1447`、`resources.py:292-304`）
- 没有任何 HTTP/UI 端点把 `_prompt_*` 函数生成的 instructions 正文渲染给人类

**Agent（prompts 的实际消费者）——看得到。** 通过 `prompts/get` 能取到任意一篇全文，作为工作流指引注入上下文。但 Agent 本身跨语言理解无损，读中文正文不存在障碍。

## 对当前 i18n 决策的含义

现在的工作树状态：工具层散点、resources 派生、server.instructions、22 个 prompt 的元数据都已接入语料；**唯独 22 篇正文仍硬编码中文、未 i18n**（`prompts.py:96-1373`，整个 `_prompt_*` 函数体内无 `_i18n.t()` 调用）——对应记忆里待办 (2)「约 1250 行英文创作，本次最大工作量」（依据：`repowiki/tasks/产品维护/memories/iamwangbao-163-com.md:71`）。

而现有设计本身就有一处自洽声明，在 `server.instructions` 的「## 语言」段：

> 工作流指引本身是中文的，但那是给你的指令，不代表产出语言。

（`codewiki/mcp/locales/zh.yaml:72`；en.yaml:66 对应英文版）——即**正文语言与产出语言刻意解耦**。既然正文人类用户不可见、Agent 又能无障碍读中文，做 1250 行英文创作的主要收益其实只剩"服务端代码全链路英文化"的完整度，不像落盘产物（AGENTS.md、index.md、schema.yaml 模板，用户真的会打开文件）那样有直接的可见性收益。

如果接受"正文是给 Agent 的指令、不随语言走"这条既有定位，待办 (2) 可以裁剪掉，22 篇正文维持单语中文即可，元数据双语已覆盖人类可见部分。是否裁剪由你定——我的判断倾向是**裁剪**，理由就是上面的可见性分析。

要不要我先把这条可见性结论记进任务记忆或补一条 decision 笔记草稿？
user: <cb_summary>
This session is being continued from a previous conversation that was compacted to stay within the model context window.
Messages after this summary (if any) are the original recent turns. Tool results from before this summary were omitted.
If you need exact code, command output, or file contents from before compaction, re-read those files. Do not treat omitted tool bodies as still in context.

Earlier user requests:
- 22 篇正文（instructions/prompts）这个用户能看到吗
- <question_answer> <questions> <question_item id="q-0"> <question>本会话要关联哪个任务？（用于跨会话任务记忆与补蒸馏归属）</question> <answers> 跳过(本次会话不做任务关联) </answers> </question_item> </questions> </question_answer>

Tools used before this summary: read_file × 5, search_content × 4, ask_followup_question × 1
</cb_summary>

<user_special_instructions>
Please refer to the instructions below to complete the user's task.
Provide a concise summary of the current conversation so far, focusing on the user's explicit requests and your previous actions，Refer to the following points and don't repeat the following points：



Relevant technologies/frameworks involved

Related files, code snippets, and reasons for edits

Issues resolved and those under investigation

The most recent tasks, including file names/code

Only actions directly related to the most recent work



The summary must be based solely on the conversation history. Do not call any tools.

Keep it concise, ideally within 200–300 words.


</user_special_instructions>

@command://summarize
assistant: ## 会话总结

**背景**：本会话为产品维护任务的 i18n 改造工作（MCP 层中文返回文本英文化），正在逐项落地 2026-09-07 定案的 YAML 双文件方案（`zh.yaml` 源 + `en.yaml` 全量）。

**用户核心问题**：22 篇 prompt 正文（`_prompt_*` 函数生成的 instructions）人类用户能否看到——用于判断待办 (2)「约 1250 行英文正文创作」是否值得做。

**我的回答**：分角色可见性——
- 人类用户（IDE UI）**看不到正文**：正文唯一出口是 `prompts/get`（`prompts.py:1531-1540`），需 Agent 显式按名调用；`prompts/list`、`codewiki://prompts/catalog` 资源均只含元数据。
- Agent 看得到全文，但跨语言理解无损。
- 与 `zh.yaml:72`「工作流指引本身是中文的，但那是给你的指令，不代表产出语言」的设计自洽。
- **倾向建议：裁剪待办 (2)**，元数据双语已覆盖人类可见部分。

**当前工作树状态**：工具层散点、resources catalog 派生化（15/22 漂移已消除）、server.instructions、prompts 元数据均已接入 i18n；**仅剩 22 篇正文硬编码中文未改造**（`prompts.py:96-1373`）。

**进行中**：蒸馏子代理（distill-i18n-session）正在后台补蒸馏产品维护积压对话；用户选择跳过本次会话任务关联。git 未提交改动含 prompts.py/resources.py/server.py 及十余个 tools 文件。
user: 跑一遍测试，然后提交 推送代码
assistant: 我先看一下项目测试配置与当前 git 状态，然后运行测试。

[tool: execute_command · git -C d:/repos/CodeWiki-CN status --short]

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-CN\\pyproject.toml"}]
assistant: 项目用 uv + pytest。先运行测试。

[tool: execute_command · cd d:/repos/CodeWiki-CN; uv run pytest -q 2>&1 | Select-Object -Last 40]
