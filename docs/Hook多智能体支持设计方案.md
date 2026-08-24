# Hook 多智能体支持设计方案（家族归并 + 检索分发包）

> 来源：teamai-cli 31 agent 覆盖机制的评估（对话拷问定稿，2026-08-24）。
> 日期：2026-08-24 · 状态：**设计定稿（未实施）** · 预计工作量：**第一步约 1 人日**
> 定位：当前唯一在推进的工作项。无真实被卡用户，属预研储备——但与"遥测参数校准 / promote 数据验证"（须等数据积累）不同，本包不依赖积累，随时可做。

---

## 一、问题与决策摘要（拷问定稿）

当前 hook 体系支持 3 个智能体（CodeBuddy / Qoder / Claude Code），实现方式是 team-memory-hook prompt 里的"三 IDE 散文说明"——三者恰好都读 Claude 格式（settings.json + PascalCase 事件），**我们已经无意中用了家族复用**，但没有把它显式化。要支持更多智能体，参考 teamai 的机制层（不参考其 CLI 分发协议）。

经四轮拷问定稿的四个关键决策：

| # | 决策 | 结论 |
|---|------|------|
| 范围 | hooks 扩展单做还是绑定检索分发？ | **绑定成包**。hooks 负责收（采集/摩擦提示/任务引导），CLI 检索负责放（无 MCP 环境的 query）。单做 hooks 会产出"能收不能放"的半吊子 |
| 形态 | reconcile 谁执行？ | **两步走**。第一步：hooks.yaml 声明 + prompt 注册表化（不新增 CLI 命令面）；第二步（触发条件：理论支持用户反馈接线出错）：`codewiki hooks inject/remove` CLI 化 |
| 验收 | 怎么算支持？ | **不做真机实测**。CodeBuddy/Qoder/Claude Code 标"已验证支持"（日常使用背书）；注册表其余工具标"理论支持（家族归并推导）"，谁先用谁验证 |
| 兼容 | Cursor 事件名变更史？ | 声明中事件字段用**数组**结构留容错位（一个逻辑事件多个候选物理 key），第一步只填当前已知 key，不写探测逻辑 |

---

## 二、teamai 机制层的四条经验与借鉴边界

| teamai 机制 | 内容 | 本方案取舍 |
|------------|------|-----------|
| **家族归并** | 31 个 agent 归并进 3 个 hook 格式家族（Claude settings.json / Cursor hooks.json / Codex hooks.json），`CLAUDE_TO_CURSOR_EVENTS` 事件名映射表，不支持的事件静默跳过 | ✅ 核心借鉴。AGENT_FAMILIES 注册表 + 事件映射 |
| **非破坏 reconcile** | 每个 reconcile 保留用户已有配置，`isManaged` 按 command 里的 marker 识别自家 hook，remove 只清自己 | 语义借鉴进 prompt 指引（"保留已有无关配置"从散文变为强约束步骤）；代码化留给第二步 |
| **安装探测** | `detectHomeInstalledAgents` 扫 `~/.<id>/` 存在性，只向已装工具注入 | ✅ 借鉴。探测**项目内**家族配置目录（.codebuddy/.cursor/...），有才接，不凭空创建 |
| **声明→分发分离** | hooks/hooks.yaml 一份声明，落盘按家族转格式 | 借鉴一半：建声明文件（随包分发、用户可查支持列表），但分发由 MCP prompt 驱动 Agent 执行，不建 CLI 编排命令 |

**不借鉴**：teamai 的 pull/push 分发协议、孤儿分支、roles——为"知识资产与业务仓分仓"设计的基建，我们 repowiki 随业务仓走，无此问题。

**覆盖上限的诚实声明**：teamai 覆盖 31 工具的根基是 skills 目录层（放文件即生效，零适配）；我们在 hooks 层对齐，上限由"多少智能体支持生命周期 hooks"决定——行业现状约 6-8 个家族，不是 31。

---

## 三、hooks.yaml 声明文件设计

包内新文件 `codewiki/hooks.yaml`（随包分发，与 schema.yaml 同为先例模式）：

```yaml
# CodeWiki hook 智能体支持注册表
# 家族归并：每个智能体归入一个 hook 格式家族，适配只发生在家族层。
# 事件字段为数组：一个逻辑事件的候选物理 key（版本容错位，当前只填已知 key）。

version: 1

families:
  claude:                      # Claude 格式：settings.json + PascalCase 事件
    config_file: settings.json # 相对于智能体配置目录
    events:
      session_start: [SessionStart]
      session_end: [SessionEnd]

  cursor:                      # Cursor 格式：hooks.json + camelCase 事件
    config_file: hooks.json
    events:
      session_start: [sessionStart]
      session_end: [stop]      # Cursor 无 SessionEnd，用 stop 事件（注意：
                               # stop 不带 transcript_path，采集降级为事件信封）

  codex:                       # Codex 格式：hooks.json + 嵌套 matcher 结构
    config_file: hooks.json
    events:
      session_start: [SessionStart]
      session_end: [SessionEnd]

agents:
  # ── 已验证支持（日常使用背书）──
  - id: codebuddy
    family: claude
    config_dir: .codebuddy
    verified: true
  - id: qoder
    family: claude
    config_dir: .qoder
    verified: true
  - id: claude-code
    family: claude
    config_dir: .claude
    verified: true

  # ── 理论支持（家族归并推导，未经真机验证）──
  - id: cursor
    family: cursor
    config_dir: .cursor
    verified: false
  - id: codex-cli
    family: codex
    config_dir: .codex
    verified: false
  - id: gemini-cli
    family: claude             # 待验证的归并假设
    config_dir: .gemini
    verified: false
  - id: trae
    family: claude
    config_dir: .trae
    verified: false
  - id: windsurf
    family: claude
    config_dir: .windsurf
    verified: false
  - id: kilocode
    family: claude
    config_dir: .kilocode
    verified: false
  - id: opencode
    family: claude
    config_dir: .opencode
    verified: false
```

**设计要点**：

- `verified` 字段驱动文档与 prompt 的诚实表述：已验证三件套绝不与理论支持混称；
- 事件数组结构（Q8 决策）：第二步 CLI 化若发现版本差异（如 Cursor 事件改名），往数组追加候选 key 即可，数据结构不变；
- **cursor 家族的采集降级须显式声明**：Cursor 无 SessionEnd 等价事件，stop 事件不携带 transcript_path——该家族的会话采集只能落"事件信封"（_ide_hook 已有信封处理路径），完整对话蒸馏不可用。这是理论支持里最需要用户知情的一条；
- 理论支持工具的 family 归并是**待验证假设**（gemini/trae/windsurf 是否真读 claude 格式，接的时候才知道），声明文件里它们的存在本身不构成承诺。

---

## 四、检索分发包（与 hooks 绑定的另一半）

P1 第 8 项原案的落地，范围收窄到与 hooks 包配套的最小形态：

**新增 CLI 子命令 `codewiki query`**：

```
codewiki query "端口冲突" [--output-dir <dir>] [--top 5] [--check] [--depth route|context|lookup]
```

- 复用 query_wiki 的全部检索语义（BM25 + heat + authority + coverage），输出为 **Agent 友好的定界文本块**（`--- codewiki:query:start ---` ... `--- codewiki:query:end ---`），含 matched/missing、usage、adoption_hint——MCP 返回 JSON 的 CLI 文本化投影；
- `--check` 复用 check 预检模式（轻量、不记 stats）；
- 定界文本的意义：无 MCP 的 Agent 环境（任何能跑 shell 的 CLI Agent）把命令输出直接读进上下文，采纳声明约定照常工作（声明注释在对话里，capture 阶段解析，与工具无关）。

**subagent 定义文件**（`codewiki/agents/wiki-recall.md`，随包分发）：一份 prompt 定义"任务开始前先跑 `codewiki query --check` 预检 → 相关则按 depth 检索 → 返回压缩摘要"。放入各家族的 agents 目录即生效（teamai 的目录约定层技巧——我们只对这一个文件用，不做通用 skills 分发）。

**不做**：通用 skills 目录分发、跨工具 MCP 配置分发——检索一条路走 CLI，够用即止。

---

## 五、实施拆解（第一步，约 1 人日）

| 任务 | 内容 | 改动文件 |
|------|------|----------|
| **H1 声明文件** | hooks.yaml（上节 schema）+ 加载函数 | 新增 codewiki/hooks.yaml、codewiki/mcp/tools/hook_registry.py |
| **H2 prompt 注册表化** | team-memory-hook prompt 从"三 IDE 散文"改为"读 hooks.yaml 生成接线指引"：按 family 展开配置写入步骤、按 verified 标注支持等级、cursor 家族附采集降级声明 | codewiki/mcp/prompts.py |
| **H3 探测逻辑** | 扫项目下存在的家族配置目录（.codebuddy/.cursor/.codex/...），prompt 指引"探测到的才接，未探测到的不创建" | hook_registry.py、prompts.py |
| **H4 CLI 检索命令** | `codewiki query` 子命令（定界文本输出、--check、depth）| codewiki/cli.py（或入口模块）|
| **H5 subagent 定义** | wiki-recall.md 定义文件 + 随包分发 | 新增 codewiki/agents/wiki-recall.md |
| **H6 测试与文档** | hooks.yaml 加载/探测单测；CLI 输出格式快照测试；README 支持矩阵表（verified/理论两档） | tests/test_hook_registry.py、tests/test_cli_query.py、README.md |

**验收标准**（第一步）：

- hooks.yaml 覆盖 3 家族 + ≥9 个智能体，verified 标注与 README 支持矩阵一致；
- team-memory-hook prompt 对已验证三 IDE 生成的指引与现状等价（回归：现有接线步骤不丢失）；
- 探测逻辑：有 .cursor 目录的项目生成 cursor 指引、无目录的不生成；
- `codewiki query "关键词"` 在本仓库 repowiki 上返回定界文本块，coverage/usage 字段齐全；
- 全量测试基线保持全绿（当前 292+1）。

**第二步（触发式，不在本期）**：`codewiki hooks inject/remove` CLI 化——marker 识别、非破坏 reconcile 代码化、事件 key 探测。触发条件：理论支持的用户反馈 Agent 手工接线出错。

---

## 六、风险与明确不做

| 风险 | 缓解 |
|------|------|
| 理论支持工具的家族归并假设错误（如 gemini 实际不读 claude 格式） | verified: false 声明在先；prompt 指引接线后必须跑模拟事件验证（沿用现有验证步骤），失败即反馈修订注册表 |
| Cursor 采集降级（stop 无 transcript）影响该家族体验 | 声明文件与 prompt 双处显式告知；该家族标注"采集降级：仅事件信封" |
| Cursor 事件名未来变更 | 事件数组结构已留位；用户反馈后追加候选 key |
| CLI 检索命令与 MCP query_wiki 语义漂移 | CLI 是 handler 的投影层（直接调 handle_query_wiki 转 YAML 文本），不实现第二套检索 |

**明确不做**：真机实测矩阵（Q6）；通用 skills 分发；MCP 配置分发；pull/push 分发协议；孤儿分支。
