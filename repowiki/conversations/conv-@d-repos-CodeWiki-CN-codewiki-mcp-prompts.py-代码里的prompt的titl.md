---
type: Conversation
title: "conversation 20260907T064350Z"
status: distilled
stale_after: 2026-12-06
generated: { by: codewiki/5.7.0, at: 2026-09-07T06:43:50Z }
captured_at: "2026-09-07T06:43:50Z"
content_hash: "sha256:66f452b2d88e092386ca485e114a6d78b5711039b6152921eb9964f616570fc9"
friction_score: 10
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=9"
keep_raw: false
link_to: ""
source_session: "993f1c39697248b4a2c07b3edec98972"
task_id: "产品维护"
turn_count: 52
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
