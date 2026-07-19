<p align="center">
  <img src="img/logo-banner.png" alt="CodeWiki-CN" width="700" />
</p>

<h1 align="center">CodeWiki-CN</h1>

<p align="center">
  <strong>用 AI IDE 驱动的代码仓库文档生成工具</strong><br>
  <strong>AI IDE-Driven Code Documentation Generator</strong>
</p>

<p align="center">
  <a href="https://python.org/"><img alt="Python version" src="https://img.shields.io/badge/python-3.12+-blue?style=flat-square" /></a>
  <a href="./LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg?style=flat-square" /></a>
  <a href="https://github.com/FSoft-AI4Code/CodeWiki"><img alt="Upstream: CodeWiki" src="https://img.shields.io/badge/upstream-FSoft--AI4Code%2FCodeWiki-orange?style=flat-square" /></a>
</p>

<p align="center">
  <a href="#zh"><strong>中文</strong></a> | <a href="#en"><strong>English</strong></a>
</p>

---

<a id="zh"></a>

## 中文

### 这个项目是什么？

CodeWiki-CN 是 [FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki) 的中国社区分支，核心改动是**让 CodeWiki 无需配置任何大模型 API，直接由 AI IDE（CodeBuddy、Cursor、Claude Desktop 等）自身的模型驱动 Wiki 文档生成**。

### 为什么要做这个改造？

原版 CodeWiki 是一个非常优秀的仓库级文档生成框架，它通过 Tree-sitter AST 解析、依赖图构建、拓扑排序等工具链实现高质量的代码文档生成。但它有一个使用门槛：**必须自行配置 LLM API**（申请 API Key、选择 provider、处理模型兼容性），且整个生成过程是黑盒的，用户无法中途干预。

实际上，CodeWiki 的核心工具链——AST 解析、依赖图、Mermaid 校验——完全不需要 LLM。真正需要 LLM 智能的 4 个环节（模块聚类、文档撰写、子模块递归、总览合成），恰好是 AI IDE 的 Agent 最擅长做的事情。

因此，我们将 CodeWiki 的 MCP Server 从"黑盒式一键生成"拆分为**16 个细粒度工具**，让它退化为纯工具链服务器。AI IDE 的 Agent 通过 MCP 协议调用这些工具，用自己的推理能力完成全部文档生成工作：

```
改造前：
  IDE → generate_docs(repo) → [CodeWiki 内部调用 LLM API] → 结果

改造后：
  IDE Agent → analyze_repo → read_code → (Agent 自己推理) → write_doc → overview
              ↑ 纯工具       ↑ 纯工具    ↑ IDE 自身模型      ↑ 纯工具
```

### 前置条件

- **Python 3.12+**
- **Node.js**（用于 Mermaid 图表校验，不安装则图表校验会静默跳过）
- 一个支持 MCP 的 AI IDE（CodeBuddy、Cursor、Claude Desktop 等）

### 快速开始（以 CodeBuddy 为例）

整个过程只需 4 步，不需要任何 API Key。

**第 1 步：安装 CodeWiki-CN**

```bash
git clone https://github.com/mambo-wang/CodeWiki-CN.git
cd CodeWiki-CN
pip install -e .
```

验证安装：

```bash
python -c "from codewiki.mcp.server import server; print('MCP Server OK')"
```

**第 2 步：配置 MCP Server**

在 CodeBuddy 的 MCP 设置中添加以下配置（通常在设置界面的"工具"或"MCP"板块）：

```json
{
  "mcpServers": {
    "codewiki": {
      "command": "python",
      "args": ["-m", "codewiki.mcp.server"],
      "cwd": "/你的路径/CodeWiki-CN",
      "timeout": 36000000
    }
  }
}
```

> 将 `/你的路径/CodeWiki-CN` 替换为你实际克隆 CodeWiki-CN 的绝对路径。

配置完成后，CodeBuddy 的 MCP 工具列表中应出现 `codewiki` 相关的 18 个工具（16 个细粒度 + 2 个遗留）。

**第 3 步：配置技能（Skill）**

本项目已预置 CodeBuddy 技能文件：

```
skills/codewiki-wiki-generator/SKILL.md
```

使用前需将该技能文件夹拷贝到 CodeBuddy 的技能目录下：

```bash
cp -r skills/codewiki-wiki-generator .codebuddy/skills/
```

该技能定义了 Wiki 生成的 5 阶段工作流（分析 → 聚类 → 逐模块文档 → 总览 → 清理），当你在 Agent 对话中提及"生成文档"或"Wiki"时，CodeBuddy 会自动加载这些指令。

**第 4 步：在 Agent 模式中输入提示词**

打开 CodeBuddy 的 Agent 模式，用 CodeBuddy 打开你要生成文档的目标项目，然后输入：

```
帮我分析当前仓库并生成 Wiki 文档，输出到 repowiki 目录。请使用中文撰写文档。
```

Agent 会自动按照以下流程工作：

```
阶段 1: 调用 analyze_repo → 得到 session_id、组件索引、叶节点列表
  ↓
阶段 2: 调用 get_prompt("cluster") 获取聚类规则
        调用 read_code_components 阅读源码
        自主推理，将组件分组为 3-8 个逻辑模块
        调用 save_module_tree 保存聚类结果
  ↓
阶段 3: 按叶优先顺序逐模块生成文档
        每个叶模块：read_code → 分析推理 → write_doc_file
        每个父模块：读取子文档 → 合成总览 → write_doc_file
  ↓
阶段 4: 生成仓库总览 overview.md
  ↓
阶段 5: 调用 close_session 释放资源
```

生成的文档结构：

```
repowiki/
├── wiki/                        # LLM Wiki 结构化知识库
│   ├── overview.md              #   仓库总览（从这里开始阅读）
│   ├── index.md                 #   自动生成的文档目录索引（按类型分区）
│   ├── log.md                   #   操作日志（记录每次写入/编辑）
│   ├── schema.yaml              #   项目文档规范（含 page_types 路由表）
│   ├── purpose.md               #   项目用途说明（可选，增强搜索相关性）
│   ├── modules/                 #   模块文档
│   │   ├── module1.md
│   │   └── module2.md
│   ├── entities/                #   实体页面（类、接口、数据库表等）
│   ├── concepts/                #   概念页面（设计模式、业务概念等）
│   ├── sources/                 #   外部文档摘要（第三方文档导入）
│   ├── comparisons/             #   对比分析页面
│   └── queries/                 #   研究查询页面
├── raw/
│   └── sources/                 #   第三方文档原始文件
├── notes/                       # 开发知识笔记
│   ├── decision-xxx.md          #   架构决策记录
│   ├── pitfall-xxx.md           #   踩坑记录
│   ├── workaround-xxx.md        #   临时方案
│   └── ...
├── .meta/
│   ├── issues.json              #   质量问题追踪（health score 依据）
│   └── source_registry.json     #   外部文档注册表
├── module_tree.json             # 模块层级结构
├── first_module_tree.json       # 初始聚类结果
└── metadata.json                # 生成元数据
```

### MCP 工具速查

所有工具均不需要 LLM 配置，由 IDE Agent 通过 MCP 协议调用：

**文档生成管线（8 个）：**

| 工具 | 用途 |
|------|------|
| `analyze_repo` | 分析仓库，构建依赖图，返回组件索引；支持增量更新检测 |
| `read_code_components` | 根据组件 ID 读取源码 |
| `write_doc_file` | 创建 .md 文档（自动 Mermaid 校验 + 自动交叉链接注入） |
| `edit_doc_file` | 编辑文档（替换/插入/撤销） |
| `save_module_tree` | 保存模块聚类结果 |
| `get_processing_order` | 获取叶优先的文档生成顺序 |
| `get_prompt` | 获取各阶段的提示词模板（含 10 个 Wiki 知识管理模板） |
| `close_session` | 关闭会话释放资源，写入生成元数据 |

**LLM Wiki 知识管理（8 个）：**

| 工具 | 用途 |
|------|------|
| `list_dependencies` | 查询组件/模块依赖关系，支持分页、方向过滤、高影响力组件排名 |
| `lint_wiki` | 文档-代码一致性检查：9 项检查（过期引用、断链、未覆盖组件、循环依赖、覆盖率、孤立页面、无出链、缺少别名、过期外部源） |
| `ingest_note` | 将开发笔记（决策/经验/架构/修复/踩坑/临时方案）归档到 notes/ 目录，支持严重级别、根因分析、来源引用、别名 |
| `query_wiki` | 全文搜索已生成文档和归档笔记，支持类型过滤（`type_filter`）、作用域前缀、上下文摘要 |
| `ingest_source` | 导入第三方文档（API 文档、设计规范等）到 `raw/sources/`，注册到 `source_registry.json` |
| `retract_source` | 撤回已导入的外部文档：`flag_stale` 标记过期或 `remove_refs` 删除并清理引用 |
| `batch_ingest` | 批量导入：一次调用处理多个笔记/文档，支持 `items` 列表和 `items_file` 文件路径 |
| `flag_issue` | 标记 Wiki 质量问题（broken_link/missing_doc/inconsistent 等），写入 `issues.json`，驱动 health score 计算 |

> 另有 2 个遗留工具（`generate_docs`、`get_module_tree`）保留向后兼容，需先通过 `codewiki config set` 配置 LLM API。

### 增量更新

`analyze_repo` 内置增量检测，首次生成后再次调用时，会自动比对上次生成状态：

- **Git 策略（优先）**：通过 `git diff` 比对当前 HEAD 与上次生成时的 commit，识别变更文件
- **Mtime 策略（回退）**：非 Git 仓库通过文件修改时间检测变更

检测到的变更会映射到受影响的模块（`affected_modules`）和需要级联刷新的父模块（`cascade_modules`），Agent 只需重新生成受影响的模块文档，而非全量重写。

### LLM Wiki 知识系统

除了文档生成，CodeWiki-CN 还内置了 LLM Wiki 知识管理能力，让生成出的 Wiki 持续演进为项目的活知识库。

#### 结构化知识库布局

所有 Wiki 内容按页面类型（page type）组织在 `wiki/` 子目录下，由 `page_router.py` 统一路由：

| 页面类型 | 目录 | 说明 |
|----------|------|------|
| `module` | `wiki/modules/` | 模块文档（原有文档自动迁移到此目录） |
| `entity` | `wiki/entities/` | 实体页面：类、接口、数据库表、配置项等 |
| `concept` | `wiki/concepts/` | 概念页面：设计模式、业务概念、架构风格等 |
| `source` | `wiki/sources/` | 外部文档摘要：导入的第三方文档 |
| `comparison` | `wiki/comparisons/` | 对比分析：技术选型、方案比较等 |
| `query` | `wiki/queries/` | 研究查询：调研结论、问题排查记录等 |

`write_doc_file` 工具新增 `page_type` 参数，Agent 写入文档时指定类型即可自动路由到正确目录。

#### schema.yaml 与 page_types 路由表

`schema.yaml` 是项目的文档"宪法"，包含命名规范、必需章节、文档维度、lint 设置，以及 **page_types 路由表**（定义每种页面类型的目录和 frontmatter 字段）。`config.yaml`（CodeWiki-CN 安装目录下）提供与语言无关的默认配置，首次 `analyze_repo` 时会读取它生成项目级 `schema.yaml`。

**自定义**：修改 CodeWiki-CN 的 `config.yaml` 改变全局默认值；修改某个项目的 `schema.yaml` 只影响该项目（增量更新时自动合并保留自定义字段）。

#### 交叉链接与别名

- **交叉链接注入**：`write_doc_file` 根据组件级依赖关系自动在文档末尾注入"相关模块"章节（Depends on / Used by），通过 `schema.yaml` 中的 `auto_crosslink` 开关控制
- **别名（aliases）**：文档 frontmatter 中可声明 `aliases` 列表，搜索时别名获得 **3× BM25 权重提升**，大幅提高同义词、缩写的命中率
- **来源引用（source_refs）**：正文中使用 `[^src:name:line_range]` 标记第三方文档出处，确保知识可追溯

#### 外部文档管理

通过 `ingest_source` 和 `retract_source` 管理第三方文档（API 文档、设计规范、RFC 等）的完整生命周期：

```json
// 导入外部文档
{ "name": "rfc-7519-jwt", "source_type": "rfc", "source_path": "/path/to/rfc7519.txt",
  "description": "JWT 规范", "related_pages": ["auth-module"] }

// 撤回外部文档（两种模式）
{ "source_name": "rfc-7519-jwt", "mode": "flag_stale" }    // 标记过期，保留文件
{ "source_name": "rfc-7519-jwt", "mode": "remove_refs" }   // 删除文件，清理所有引用
```

原始文件存储在 `raw/sources/`，摘要页面生成在 `wiki/sources/`，注册信息保存在 `.meta/source_registry.json`。

#### 知识笔记增强

`ingest_note` 新增 3 种笔记类型和结构化字段：

| 新增 note_type | 说明 |
|----------------|------|
| `pitfall` | 踩坑记录，含 severity（critical/high/medium/low）和 root_cause |
| `known_issue` | 已知问题，可关联 source_ref |
| `workaround` | 临时方案，标注适用条件和替代路径 |

所有笔记支持 `aliases`（别名）和 `source_ref`（来源引用）字段。

#### 批量操作

`batch_ingest` 支持一次调用处理多个笔记或外部文档，减少 Agent 的往返调用次数：

```json
{
  "items": [
    { "item_type": "note", "note_type": "decision", "title": "选择 PostgreSQL", "content": "..." },
    { "item_type": "source", "source_type": "api_doc", "source_path": "/path/to/api.md", "name": "payment-api" }
  ]
}
```

也支持通过 `items_file` 参数传入 JSON 文件路径，适合大批量导入。所有项目统一在最后重建索引。

#### 文档健康检查

`lint_wiki` 从 5 项扩展为 **9 项检查**，新增的 4 项 LLM Wiki 检查：

| 检查项 | 说明 |
|--------|------|
| `orphan_pages` | 没有任何页面链接到的孤立页面 |
| `no_outlinks` | 没有链接到任何其他页面的死端页面 |
| `missing_aliases` | 实体页面缺少 aliases 声明 |
| `stale_sources` | 引用了已撤回（retracted）外部文档的页面 |

`lint_wiki` 返回结果包含 **health_score**（0-100），计算方式为 `100 - Σ(error×10 + warning×3 + info×1)`。`index.md` 顶部也会展示当前健康分数。

#### 质量问题追踪

`flag_issue` 工具用于标记 Wiki 中的质量问题，写入 `.meta/issues.json`。每个 issue 使用 FNV-1a 哈希生成稳定 ID（基于 `type::page_path`），重复标记会自动增加 `occurrences` 计数。问题严重级别直接影响 health score。

#### 全文搜索增强

`query_wiki` 搜索能力全面升级：

- **类型过滤**：`type_filter` 参数限定搜索范围（module/entity/concept/source/comparison/query）
- **作用域前缀**：`scope` 参数支持目录前缀（如 `wiki/entities`、`notes`）
- **BM25 权重增强**：aliases 3× boost、severity 2× boost
- **外部文档搜索**：`include_sources` 参数控制是否包含已导入的第三方文档

#### 提示词模板

`get_prompt` 新增 7 个页面类型模板，总计 **10 个 Wiki 知识管理模板**：

| prompt_type | 用途 |
|-------------|------|
| `entity_page` | 生成实体页面（类、接口、数据库表） |
| `concept_page` | 生成概念页面（设计模式、业务概念） |
| `source_summary` | 生成外部文档摘要页面 |
| `comparison_page` | 生成对比分析页面 |
| `query_page` | 生成研究查询页面 |
| `taxonomy_plan` | 规划 Wiki 分类体系和页面类型分布 |
| `extraction_scan` | 扫描源码提取实体/概念候选列表 |

#### 自动索引与日志

每次写入/编辑/归档操作自动更新 `wiki/index.md`（按类型分区的文档目录）和 `wiki/log.md`（操作日志）。索引顶部展示 health score 和各类型页面统计。

### 如何使用 LLM Wiki 知识层

以下是常见使用场景的 Agent 对话示例：

**场景 1：生成实体页面**

```
帮我生成 PaymentService 类的实体页面，用中文写。
```

Agent 会自动调用 `get_prompt("entity_page")` 获取模板，分析代码组件，然后调用 `write_doc_file`（`page_type: "entity"`）写入 `wiki/entities/payment-service.md`。

**场景 2：导入第三方文档**

```
把 docs/stripe-api-reference.md 作为外部文档导入 Wiki，关联支付模块。
```

Agent 调用 `ingest_source`，将原始文件存入 `raw/sources/`，注册到 `source_registry.json`，然后在 `wiki/sources/` 生成摘要页面。后续 `query_wiki` 搜索时会包含此文档。

**场景 3：记录踩坑经验**

```
记录一个踩坑：Redis 连接池在高并发下偶尔超时，根因是 maxTotal 设置过低，临时方案是翻倍 maxTotal。
```

Agent 调用 `ingest_note`（`note_type: "pitfall"`），自动提取 severity、root_cause，写入 `notes/pitfall-redis-connection-pool.md`。

**场景 4：批量导入多个笔记**

```
把这次技术评审的 5 条决策记录批量导入 Wiki。
```

Agent 调用 `batch_ingest`，一次处理所有 items，最后统一重建索引。

**场景 5：按类型搜索**

```
搜索所有概念页面中关于"依赖注入"的内容。
```

Agent 调用 `query_wiki`（`query: "依赖注入"`, `type_filter: "concept"`），只在 `wiki/concepts/` 目录中搜索。

**场景 6：检查 Wiki 健康度**

```
检查一下 Wiki 文档的健康状况。
```

Agent 调用 `lint_wiki`（`checks: ["stale_refs", "broken_links", "orphan_pages", "missing_aliases"]`），返回诊断报告和 health_score。

### 支持的其他 AI IDE

除 CodeBuddy 外，任何支持 MCP stdio 协议的 AI IDE 均可使用：

**Cursor**：在 Settings → MCP 中添加相同的 Server 配置。

**Claude Desktop**：在 `~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）中添加 MCP 配置。

**其他 IDE**：指定 `command: "python"`, `args: ["-m", "codewiki.mcp.server"]` 即可。

### 原始 CLI 模式（仍然可用）

如果你更习惯命令行一键生成，原始的 CLI 方式完全不受影响。需要先配置 LLM API：

```bash
codewiki config set \
  --provider openai-compatible \
  --api-key YOUR_KEY \
  --base-url https://api.example.com \
  --main-model claude-sonnet-4 \
  --cluster-model claude-sonnet-4

codewiki generate
```

支持 OpenAI、Anthropic、Azure OpenAI、AWS Bedrock 以及 Claude Code / Codex 订阅模式。详见[上游项目 README](https://github.com/FSoft-AI4Code/CodeWiki)。

### 支持的语言

Python、Java、JavaScript、TypeScript、C、C++、C#、Kotlin、Go、PHP

### 致谢

本项目的核心工具链（Tree-sitter AST 解析、依赖图构建、拓扑排序、Mermaid 校验）全部来自 [FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki) 上游项目。LLM Wiki 知识层设计参考了 [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki) 和 [Tencent/WeKnora](https://github.com/Tencent/WeKnora)。我们在上游基础上将 MCP Server 从黑盒模式拆分为 16 个细粒度工具，并新增结构化 Wiki、外部文档管理、批量导入、问题追踪等知识层能力。

上游论文：[CodeWiki: Evaluating AI's Ability to Generate Holistic Documentation for Large-Scale Codebases](https://arxiv.org/abs/2510.24428)

```bibtex
@misc{hoang2025codewikievaluatingaisability,
      title={CodeWiki: Evaluating AI's Ability to Generate Holistic Documentation for Large-Scale Codebases},
      author={Anh Nguyen Hoang and Minh Le-Anh and Bach Le and Nghi D. Q. Bui},
      year={2025},
      eprint={2510.24428},
      archivePrefix={arXiv},
      primaryClass={cs.SE},
      url={https://arxiv.org/abs/2510.24428},
}
```

---

<a id="en"></a>

## English

### What is this project?

CodeWiki-CN is a community fork of [FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki) that enables **zero-LLM-config Wiki generation** driven entirely by AI IDEs (CodeBuddy, Cursor, Claude Desktop, etc.) via MCP (Model Context Protocol).

### Why this fork?

The original CodeWiki is an excellent repository-level documentation framework. However, it requires users to configure their own LLM API (API key, provider, model selection), and the generation pipeline runs as a black box with no user intervention.

In practice, CodeWiki's core toolchain—Tree-sitter AST parsing, dependency graph construction, topological sorting, and Mermaid validation—does not need an LLM at all. The 4 stages that do require LLM intelligence (module clustering, document writing, sub-module recursion, and overview synthesis) are exactly what AI IDE Agents excel at.

We refactored CodeWiki's MCP Server from a "one-click black box" into **16 fine-grained tools**, turning it into a pure toolchain server. The AI IDE's Agent calls these tools via MCP and uses its own reasoning to complete all documentation work:

```
Before:
  IDE → generate_docs(repo) → [CodeWiki calls LLM API internally] → result

After:
  IDE Agent → analyze_repo → read_code → (Agent reasons) → write_doc → overview
              ↑ pure tool     ↑ pure tool  ↑ IDE's own model ↑ pure tool
```

### Prerequisites

- **Python 3.12+**
- **Node.js** (for Mermaid diagram validation; without it, validation is silently skipped)
- An MCP-compatible AI IDE (CodeBuddy, Cursor, Claude Desktop, etc.)

### Quick Start (CodeBuddy Example)

4 steps, no API key needed.

**Step 1: Install CodeWiki-CN**

```bash
git clone https://github.com/mambo-wang/CodeWiki-CN.git
cd CodeWiki-CN
pip install -e .
```

**Step 2: Configure MCP Server**

Add the following to your CodeBuddy MCP settings:

```json
{
  "mcpServers": {
    "codewiki": {
      "command": "python",
      "args": ["-m", "codewiki.mcp.server"],
      "cwd": "/your/path/to/CodeWiki-CN"
    }
  }
}
```

> Replace `/your/path/to/CodeWiki-CN` with the actual absolute path where you cloned CodeWiki-CN.

**Step 3: Configure Skill**

A CodeBuddy skill file is pre-configured at:

```
skills/codewiki-wiki-generator/SKILL.md
```

Copy it to CodeBuddy's skill directory before use:

```bash
cp -r skills/codewiki-wiki-generator .codebuddy/skills/
```

It defines the 5-stage Wiki generation workflow (analyze → cluster → document modules → synthesize overviews → cleanup). CodeBuddy auto-loads it when you mention "generate docs" or "Wiki" in Agent mode.

**Step 4: Prompt your AI Agent**

Open the target project in CodeBuddy, switch to Agent mode, and enter:

```
Analyze the current repository and generate Wiki documentation into the repowiki directory. Write docs in English.
```

The Agent follows a 5-stage pipeline:

```
Stage 1: Call analyze_repo → get session_id, component index, leaf nodes
Stage 2: Call get_prompt("cluster") for clustering rules
         Read source code, reason about grouping, call save_module_tree
Stage 3: Document each module leaf-first
         Leaf modules: read_code → reason → write_doc_file
         Parent modules: read child docs → synthesize → write_doc_file
Stage 4: Generate repository overview (overview.md)
Stage 5: Call close_session to free resources
```

Generated output structure:

```
repowiki/
├── wiki/                        # LLM Wiki structured knowledge base
│   ├── overview.md              #   Repository overview (start reading here)
│   ├── index.md                 #   Auto-generated document index (by-type sections)
│   ├── log.md                   #   Operation log (records every write/edit)
│   ├── schema.yaml              #   Project documentation spec (includes page_types routing table)
│   ├── purpose.md               #   Project purpose statement (optional, boosts search relevance)
│   ├── modules/                 #   Module documentation
│   │   ├── module1.md
│   │   └── module2.md
│   ├── entities/                #   Entity pages (classes, interfaces, DB tables, etc.)
│   ├── concepts/                #   Concept pages (design patterns, business concepts, etc.)
│   ├── sources/                 #   External document summaries (imported third-party docs)
│   ├── comparisons/             #   Comparison analysis pages
│   └── queries/                 #   Research query pages
├── raw/
│   └── sources/                 #   Third-party document original files
├── notes/                       # Development knowledge notes
│   ├── decision-xxx.md          #   Architecture decision records
│   ├── pitfall-xxx.md           #   Pitfall records
│   ├── workaround-xxx.md        #   Workarounds
│   └── ...
├── .meta/
│   ├── issues.json              #   Quality issue tracking (drives health score)
│   └── source_registry.json     #   External document registry
├── module_tree.json             # Module hierarchy structure
├── first_module_tree.json       # Initial clustering result
└── metadata.json                # Generation metadata
```

### MCP Tools

All tools require zero LLM config. The IDE Agent invokes them via MCP:

**Documentation Pipeline (8):**

| Tool | Purpose |
|------|---------|
| `analyze_repo` | Parse repo, build dependency graph, return component index; includes incremental change detection |
| `read_code_components` | Read source code by component ID |
| `write_doc_file` | Create .md docs with automatic Mermaid validation + crosslink injection |
| `edit_doc_file` | Edit docs (str_replace / insert / undo) |
| `save_module_tree` | Persist module clustering results |
| `get_processing_order` | Get leaf-first documentation order |
| `get_prompt` | Retrieve prompt templates for each stage (includes 10 Wiki knowledge management templates) |
| `close_session` | Close session, write generation metadata |

**LLM Wiki Knowledge Management (8):**

| Tool | Purpose |
|------|---------|
| `list_dependencies` | Query component/module dependencies with pagination, direction filtering, and high-impact ranking |
| `lint_wiki` | Doc-code consistency checks: 9 checks (stale refs, broken links, undocumented components, circular deps, coverage, orphan pages, no outlinks, missing aliases, stale sources) |
| `ingest_note` | File structured notes (decisions/lessons/architecture/fixes/pitfalls/workarounds) into notes/ with severity, root cause, source refs, and aliases |
| `query_wiki` | Full-text search across generated docs and ingested notes with type filtering (`type_filter`), scope prefix, and context snippets |
| `ingest_source` | Import third-party docs (API docs, specs, RFCs, etc.) into `raw/sources/`, registered in `source_registry.json` |
| `retract_source` | Retract imported docs: `flag_stale` to mark outdated or `remove_refs` to delete and clean all references |
| `batch_ingest` | Batch import: process multiple notes/sources in one call, supports `items` list and `items_file` path |
| `flag_issue` | Flag Wiki quality issues (broken_link/missing_doc/inconsistent, etc.), written to `issues.json`, drives health score |

> 2 legacy tools (`generate_docs`, `get_module_tree`) are retained for backward compatibility and require `codewiki config set` first.

### Incremental Updates

`analyze_repo` includes built-in change detection. On subsequent calls after the first generation, it automatically compares the current state against the previous run:

- **Git strategy (preferred)**: Compares current HEAD with the stored commit via `git diff` to identify changed files
- **Mtime strategy (fallback)**: For non-Git repos, detects changes by comparing file modification times

Detected changes are mapped to affected modules (`affected_modules`) and parent modules requiring cascade refresh (`cascade_modules`). The Agent only regenerates impacted module docs instead of rewriting everything.

### LLM Wiki Knowledge System

Beyond documentation generation, CodeWiki-CN includes an LLM Wiki knowledge management system that lets the generated Wiki evolve into a living knowledge base.

#### Structured Knowledge Base Layout

All Wiki content is organized by page type under `wiki/` subdirectories, routed by `page_router.py`:

| Page Type | Directory | Description |
|-----------|-----------|-------------|
| `module` | `wiki/modules/` | Module documentation (existing docs auto-migrated here) |
| `entity` | `wiki/entities/` | Entity pages: classes, interfaces, DB tables, config items |
| `concept` | `wiki/concepts/` | Concept pages: design patterns, business concepts, architecture styles |
| `source` | `wiki/sources/` | External document summaries: imported third-party docs |
| `comparison` | `wiki/comparisons/` | Comparison analysis: tech selection, solution trade-offs |
| `query` | `wiki/queries/` | Research queries: investigation conclusions, troubleshooting records |

The `write_doc_file` tool accepts a new `page_type` parameter — the Agent specifies the type and the file is automatically routed to the correct directory.

#### schema.yaml and page_types Routing Table

`schema.yaml` is the project's documentation "constitution" with naming conventions, required sections, documentation dimensions, lint settings, and a **page_types routing table** (defining directory and frontmatter fields for each page type). The `config.yaml` in the CodeWiki-CN installation directory provides language-agnostic defaults; the first `analyze_repo` call reads it to generate a project-level `schema.yaml`.

**To customize**: edit CodeWiki-CN's `config.yaml` to change global defaults; edit a project's `schema.yaml` to customize that project only (user customizations are auto-merged and preserved during incremental updates).

#### Crosslinks and Aliases

- **Crosslink Injection**: `write_doc_file` automatically appends a "Related Modules" section (Depends on / Used by) based on component-level dependencies, controlled by `auto_crosslink` in `schema.yaml`
- **Aliases**: Document frontmatter can declare an `aliases` list — aliases receive **3× BM25 weight boost** in search, greatly improving synonym and abbreviation hit rates
- **Source Refs**: Use `[^src:name:line_range]` inline annotations to mark third-party document provenance, ensuring knowledge traceability

#### External Document Management

Manage the full lifecycle of third-party documents (API docs, design specs, RFCs, etc.) via `ingest_source` and `retract_source`:

```json
// Import external document
{ "name": "rfc-7519-jwt", "source_type": "rfc", "source_path": "/path/to/rfc7519.txt",
  "description": "JWT specification", "related_pages": ["auth-module"] }

// Retract external document (two modes)
{ "source_name": "rfc-7519-jwt", "mode": "flag_stale" }    // Mark outdated, keep file
{ "source_name": "rfc-7519-jwt", "mode": "remove_refs" }   // Delete file, clean all references
```

Original files are stored in `raw/sources/`, summary pages generated in `wiki/sources/`, registration info saved in `.meta/source_registry.json`.

#### Knowledge Note Enhancements

`ingest_note` adds 3 new note types and structured fields:

| New note_type | Description |
|---------------|-------------|
| `pitfall` | Pitfall records with severity (critical/high/medium/low) and root_cause |
| `known_issue` | Known issues, can link to source_ref |
| `workaround` | Workarounds with applicability conditions and alternative paths |

All notes support `aliases` and `source_ref` fields.

#### Batch Operations

`batch_ingest` processes multiple notes or external documents in a single call, reducing Agent round-trips:

```json
{
  "items": [
    { "item_type": "note", "note_type": "decision", "title": "Choose PostgreSQL", "content": "..." },
    { "item_type": "source", "source_type": "api_doc", "source_path": "/path/to/api.md", "name": "payment-api" }
  ]
}
```

Also supports an `items_file` parameter for a JSON file path, ideal for bulk imports. Index is rebuilt once at the end for all items.

#### Documentation Health Checks

`lint_wiki` expands from 5 to **9 checks**, with 4 new LLM Wiki checks:

| Check | Description |
|-------|-------------|
| `orphan_pages` | Pages not linked from any other page |
| `no_outlinks` | Dead-end pages that don't link to any other page |
| `missing_aliases` | Entity pages without aliases declarations |
| `stale_sources` | Pages referencing retracted external documents |

`lint_wiki` returns a **health_score** (0-100), calculated as `100 - Σ(error×10 + warning×3 + info×1)`. The score is also displayed at the top of `index.md`.

#### Quality Issue Tracking

The `flag_issue` tool marks quality issues in the Wiki, writing to `.meta/issues.json`. Each issue uses an FNV-1a hash for a stable ID (based on `type::page_path`), and duplicate flags automatically increment the `occurrences` counter. Issue severity levels directly impact the health score.

#### Full-text Search Enhancements

`query_wiki` search capabilities are fully upgraded:

- **Type filtering**: `type_filter` parameter narrows search scope (module/entity/concept/source/comparison/query)
- **Scope prefix**: `scope` parameter supports directory prefixes (e.g., `wiki/entities`, `notes`)
- **BM25 weight boost**: aliases 3× boost, severity 2× boost
- **External doc search**: `include_sources` parameter controls whether imported third-party docs are included

#### Prompt Templates

`get_prompt` adds 7 new page type templates, totaling **10 Wiki knowledge management templates**:

| prompt_type | Purpose |
|-------------|---------|
| `entity_page` | Generate entity pages (classes, interfaces, DB tables) |
| `concept_page` | Generate concept pages (design patterns, business concepts) |
| `source_summary` | Generate external document summary pages |
| `comparison_page` | Generate comparison analysis pages |
| `query_page` | Generate research query pages |
| `taxonomy_plan` | Plan Wiki taxonomy and page type distribution |
| `extraction_scan` | Scan source code to extract entity/concept candidates |

#### Auto Index & Log

Every write/edit/ingest operation automatically updates `wiki/index.md` (document directory with by-type sections) and `wiki/log.md` (operation log). The index displays the health score and per-type page statistics at the top.

### Using the LLM Wiki Knowledge Layer

Here are common usage scenarios with Agent conversation examples:

**Scenario 1: Generate an entity page**

```
Generate an entity page for the PaymentService class.
```

The Agent calls `get_prompt("entity_page")` for the template, analyzes code components, then calls `write_doc_file` (`page_type: "entity"`) to write to `wiki/entities/payment-service.md`.

**Scenario 2: Import third-party documentation**

```
Import docs/stripe-api-reference.md as an external document, link it to the payment module.
```

The Agent calls `ingest_source`, stores the original file in `raw/sources/`, registers it in `source_registry.json`, then generates a summary page in `wiki/sources/`. Future `query_wiki` searches will include this document.

**Scenario 3: Record a pitfall**

```
Log a pitfall: Redis connection pool occasionally times out under high concurrency, root cause is maxTotal set too low, workaround is to double maxTotal.
```

The Agent calls `ingest_note` (`note_type: "pitfall"`), automatically extracts severity and root_cause, writes to `notes/pitfall-redis-connection-pool.md`.

**Scenario 4: Batch import multiple notes**

```
Batch import these 5 decision records from the tech review into the Wiki.
```

The Agent calls `batch_ingest`, processes all items at once, rebuilds the index once at the end.

**Scenario 5: Search by type**

```
Search for "dependency injection" across all concept pages.
```

The Agent calls `query_wiki` (`query: "dependency injection"`, `type_filter: "concept"`), searching only in `wiki/concepts/`.

**Scenario 6: Check Wiki health**

```
Check the health of the Wiki documentation.
```

The Agent calls `lint_wiki` (`checks: ["stale_refs", "broken_links", "orphan_pages", "missing_aliases"]`), returns a diagnostic report and health_score.

### Other Supported AI IDEs

Any AI IDE supporting MCP stdio protocol works:

**Cursor**: Add the same MCP config in Settings → MCP.

**Claude Desktop**: Add MCP config to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS).

**Others**: Specify `command: "python"`, `args: ["-m", "codewiki.mcp.server"]`.

### Original CLI Mode (Still Available)

The original CLI workflow remains fully functional. Configure LLM API first:

```bash
codewiki config set \
  --provider openai-compatible \
  --api-key YOUR_KEY \
  --base-url https://api.example.com \
  --main-model claude-sonnet-4 \
  --cluster-model claude-sonnet-4

codewiki generate
```

Supports OpenAI, Anthropic, Azure OpenAI, AWS Bedrock, and Claude Code / Codex subscription mode. See [upstream README](https://github.com/FSoft-AI4Code/CodeWiki) for details.

### Supported Languages

Python, Java, JavaScript, TypeScript, C, C++, C#, Kotlin, Go, PHP

### Acknowledgements

The core toolchain (Tree-sitter AST parsing, dependency graph, topological sort, Mermaid validation) comes from the [FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki) upstream project. The LLM Wiki knowledge layer design references [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki) and [Tencent/WeKnora](https://github.com/Tencent/WeKnora). We refactored the MCP Server into 16 fine-grained tools and added structured Wiki, external document management, batch ingest, and issue tracking capabilities on top of the upstream foundation.

Paper: [CodeWiki: Evaluating AI's Ability to Generate Holistic Documentation for Large-Scale Codebases](https://arxiv.org/abs/2510.24428)

---

## License

MIT
