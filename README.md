<p align="center">
  <img src="img/logo-banner.png" alt="CodeWiki-Plus" width="700" />
</p>

<h1 align="center">CodeWiki-Plus</h1>

<p align="center">
  <strong>用 AI IDE 驱动的代码仓库文档生成与知识管理工具</strong><br>
  <strong>AI IDE-Driven Code Documentation Generator & Knowledge Engine</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/codewiki-plus/"><img alt="PyPI" src="https://img.shields.io/pypi/v/codewiki-plus?style=flat-square&label=PyPI" /></a>
  <a href="https://python.org/"><img alt="Python version" src="https://img.shields.io/badge/python-3.12+-blue?style=flat-square" /></a>
  <a href="./LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg?style=flat-square" /></a>
</p>

<p align="center">
  <a href="#zh"><strong>中文</strong></a> | <a href="#en"><strong>English</strong></a>
</p>

---

<a id="zh"></a>

## 中文

### 专栏文章

「迎风追日 / WanderingBug」公众号发布的本项目系列技术专栏，欢迎阅读：

- [专栏开篇词：从代码文档到 AI 知识引擎](https://mp.weixin.qq.com/s/WpjiDAs62_81mytBWUsDQw)（2026-07-26）
- [第 2 篇：双层 Prompt 架构同时服务人和模型](https://mp.weixin.qq.com/s/1lNjR_SsrU5Fw2NKnkxnMA)（2026-08-01）
- [第 3 篇：零依赖检索设计](https://mp.weixin.qq.com/s/T7r-ojyWC-YOpM_U5BNbEw)（2026-08-06）
- [第 4 篇：知识写入方式全景](https://mp.weixin.qq.com/s/V90mghqB5wttKd25eXA-Pw)（2026-08-09）
- [第 5 篇：OKF 0.2 规范介绍和实战](https://mp.weixin.qq.com/s/Dt748cHQCa7mfz1PEvgS6g)（2026-08）
- [第 6 篇：借助 HOOKS 机制实现跨会话记忆和任务管理](https://mp.weixin.qq.com/s/flsqORauNo0Th1v8G4Ceng)（2026-08）
- [第 7 篇：记忆/经验分层提取——自生长的团队知识库](https://mp.weixin.qq.com/s/s253xe5LiUmgdfDo3XxAbg)（2026-08）
- [第 8 篇：四维代码评审——让踩过的坑自动变成 CHECKLIST](https://mp.weixin.qq.com/s/wH_mjG5IL-0qo_qDFpODuw)（2026-08）



### 这个项目是什么？

CodeWiki-Plus 是一个由 AI IDE（CodeBuddy、Cursor、Claude Desktop 等）自身模型驱动的仓库知识引擎：**无需配置任何大模型 API**，即可完成 Wiki 文档生成，并在此基础上提供检索、笔记、任务记忆、团队遥测等完整知识管理能力。

项目最初 fork 自 [FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki) 并在其工具链（Tree-sitter AST 解析、依赖图构建、拓扑排序、Mermaid 校验）基础上独立演进，现已发展为架构定位不同的独立项目——详见[致谢](#致谢)。

### 为什么要做这个改造？

原版 CodeWiki 是一个非常优秀的仓库级文档生成框架，它通过 Tree-sitter AST 解析、依赖图构建、拓扑排序等工具链实现高质量的代码文档生成。但它有一个使用门槛：**必须自行配置 LLM API**（申请 API Key、选择 provider、处理模型兼容性），且整个生成过程是黑盒的，用户无法中途干预。

实际上，CodeWiki 的核心工具链——AST 解析、依赖图、Mermaid 校验——完全不需要 LLM。真正需要 LLM 智能的 4 个环节（模块聚类、文档撰写、子模块递归、总览合成），恰好是 AI IDE 的 Agent 最擅长做的事情。

因此，我们将 CodeWiki 的 MCP Server 从"黑盒式一键生成"拆分为**40 个细粒度工具**，让它退化为纯工具链服务器。AI IDE 的 Agent 通过 MCP 协议调用这些工具，用自己的推理能力完成全部文档生成工作：

```
改造前：
  IDE → generate_docs(repo) → [CodeWiki 内部调用 LLM API] → 结果

改造后：
  IDE Agent → analyze_repo → read_code → (Agent 自己推理) → write_doc → overview
              ↑ 纯工具       ↑ 纯工具    ↑ IDE 自身模型      ↑ 纯工具
```

### 与上游 CodeWiki 的差异

| 能力维度 | 上游 CodeWiki | CodeWiki-Plus |
|----------|--------------|---------------|
| LLM 配置 | 必须自行配置 API Key | 零配置，IDE 自身模型驱动 |
| 生成模式 | 黑盒一键生成 | 40 个细粒度工具，Agent 全程可控 |
| 文档质量 | 通用描述 | Evidence-Based 断言（代码引用 + 置信度） |
| 生成效率 | 所有组件同等处理 | 代码路由分类，boilerplate 仅保留签名 |
| 上下文精度 | 模块内组件 | BFS 1-hop 调用图扩展 + 约束索引表 |
| 增量更新 | 文件级 Git diff | 方法级 content_hash 精确检测 |
| 知识管理 | 无 | 结构化 Wiki + 笔记飞轮 + 外部文档管理 |
| 任务记忆 | 无 | 跨会话任务上下文 + 任务记忆暂存确认 |
| 搜索能力 | 无 | BM25 + wikilink 图谱多跳 + 渐进式阅读 |
| 跨服务分析 | 无 | Monorepo 子服务检测 + 跨服务调用追踪 |
| 质量保障 | 无 | 18 项 lint 检查 + health score + 问题追踪 |

### 前置条件

- **Python 3.12+**
- **Node.js**（用于 Mermaid 图表校验，不安装则图表校验会静默跳过）
- 一个支持 MCP 的 AI IDE（CodeBuddy、Cursor、Claude Desktop 等）

### 快速开始（以 CodeBuddy 为例）

整个过程只需 3 步，不需要任何 API Key。

**第 1 步：安装 CodeWiki-Plus**

```bash
pip install codewiki-plus
```

验证安装：

```bash
codewiki --version
```

> **开发者选项**：如需从源码开发（获取最新未发布改动），推荐使用 [uv](https://docs.astral.sh/uv/) 按 `uv.lock` 精确复现开发环境（`pyproject.toml:106` `tool.uv.default-groups = ["dev"]` 已包含 dev 工具）：
> ```bash
> git clone https://github.com/mambo-wang/CodeWiki-Plus.git
> cd CodeWiki-Plus
> uv sync --frozen              # 按 uv.lock 复现完整开发环境（含 dev 依赖，hatchling 构建）
> uv run codewiki --version     # 通过 uv 环境运行 CLI
> uv run pytest tests/ -q       # 运行测试（addopts 已移除 --cov，无需覆盖）
> # 需要覆盖率时：uv run pytest --cov=codewiki --cov-report=term-missing
> ```
> 没有 uv 时也可 `pip install -e .[dev]`，但依赖解析不受 `uv.lock` 锁定。

**第 2 步：配置 MCP Server**

在 CodeBuddy 的 MCP 设置中添加以下配置（通常在设置界面的"工具"或"MCP"板块）：

```json
{
  "mcpServers": {
    "codewiki": {
      "command": "codewiki",
      "args": ["mcp"],
      "maxOutputLength": 500000,
      "timeout": 36000000
    }
  }
}
```

配置完成后，CodeBuddy 的 MCP 工具列表中应出现 `codewiki` 相关的 40 个工具。

**第 3 步：在 Agent 模式中输入提示词**

打开 CodeBuddy 的 Agent 模式，用 CodeBuddy 打开你要生成文档的目标项目，然后输入：

```
帮我分析当前仓库并生成 Wiki 文档，输出到 repowiki 目录。请使用中文撰写文档。
```

Agent 会自动按照以下流程工作：

```
阶段 1: 调用 analyze_repo → 得到组件索引、叶节点列表
        （自动检测 monorepo 子服务，构建跨服务调用关系）
  ↓
阶段 2: 调用 get_prompt("cluster") 获取聚类规则
        调用 read_code_components 阅读源码
        自主推理，将组件分组为 3-8 个逻辑模块
        调用 save_module_tree 保存聚类结果
  ↓
阶段 3: 按叶优先顺序逐模块生成文档
        每个叶模块：read_code → 分析推理 → write_doc_file
        （prompt 自动注入 BFS 调用上下文 + 约束索引表 + 业务规则提取指令）
        每个父模块：读取子文档 → 合成总览 → write_doc_file
  ↓
阶段 4: 生成仓库总览 overview.md
  ↓
阶段 5: 调用 close_session 释放资源，构建搜索索引
```

生成的文档结构：

```
repowiki/
├── wiki/                        # LLM Wiki 结构化知识库
│   ├── overview.md              #   仓库总览（从这里开始阅读）
│   ├── index.md                 #   自动生成的文档目录索引（按类型分区）
│   ├── log.md                   #   操作日志（记录每次写入/编辑）
│   ├── schema.yaml              #   项目文档规范（含 purpose 定位 + page_types 路由表 + 代码路由规则）
│   ├── modules/                 #   模块文档（含组件约束索引表 + Evidence-Based 断言）
│   │   ├── module1.md
│   │   └── module2.md
│   ├── entities/                #   实体页面（类、接口、数据库表等）
│   ├── concepts/                #   概念页面（设计模式、业务概念等）
│   ├── sources/                 #   外部文档摘要（第三方文档导入）
│   ├── comparisons/             #   对比分析页面
│   └── queries/                 #   研究查询页面
├── raw/
│   └── sources/                 #   第三方文档原始文件
├── notes/                       # 开发知识笔记（支持 candidate→confirmed→rejected 状态流转）
│   ├── decision-xxx.md          #   架构决策记录
│   ├── pitfall-xxx.md           #   踩坑记录
│   ├── workaround-xxx.md        #   临时方案
│   └── ...
├── tasks/                       # 任务记忆（跨会话长线工作上下文）
│   ├── .index.json              #   任务索引
│   └── <task_id>/               #   task.md + memories.md + pending-memories.json
├── .meta/
│   ├── project.json             #   项目映射（repo_path/output_dir/cache_db 路径）
│   ├── symbol_map.json          #   符号→源文件映射（SQLite 主存储的 JSON 兼容副本）
│   ├── issues.json              #   质量问题追踪（health score 依据）
│   ├── source_registry.json     #   外部文档注册表
│   ├── cross_service_links.json #   跨服务调用拓扑（monorepo）
│   └── overview_refs.json       #   overview 引用模块列表（精确 stale 判定）
├── module_tree.json             # 模块层级结构
├── first_module_tree.json       # 初始聚类结果
└── metadata.json                # 生成元数据
```

### MCP 工具速查

所有工具均不需要 LLM 配置，由 IDE Agent 通过 MCP 协议调用。MCP Server 内置 **instructions**（能力概览与工作流指南）、**21 个工作流 Prompt**（覆盖初始化、生成、增量、搜索、质检、跨服务、团队记忆融合、任务记忆等全流程）和 **6 个 Resource**（wiki-catalog / module-tree / index-status 等）。

**代码分析（6 个）：**

| 工具 | 用途 |
|------|------|
| `analyze_repo` | 分析仓库，构建依赖图，返回组件索引；支持 SHA256 增量 + 方法级 content_hash 精确检测；自动检测 monorepo 子服务 |
| `analyze_workspace` | 扫描多仓库工作区，为每个子仓库独立生成 Wiki，顶层生成跨服务总览 |
| `list_components` | 组件索引查询，支持摘要模式和前缀过滤 |
| `list_dependencies` | 查询组件/模块依赖关系，支持分页、方向过滤、高影响力组件排名 |
| `read_code_components` | 根据组件 ID 读取源码 |
| `view_repo_file` | 查看仓库原始源文件内容，支持行范围截取 |

**文档生成管线（6 个）：**

| 工具 | 用途 |
|------|------|
| `write_doc_file` | 创建 .md 文档（自动 Mermaid 校验 + 交叉链接注入 + page_type 路由）；支持无 session 模式 |
| `edit_doc_file` | 编辑文档（替换/插入/撤销） |
| `save_module_tree` | 保存模块聚类结果 |
| `get_processing_order` | 获取叶优先的文档生成顺序 |
| `get_prompt` | 获取各阶段的提示词模板（含 16 种 prompt_type） |
| `close_session` | 关闭会话释放资源，构建 BM25 索引 + wikilink 图谱，写入生成元数据 |

**知识管理（10 个）：**

| 工具 | 用途 |
|------|------|
| `query_wiki` | BM25 全文搜索 + wikilink 图谱多跳扩展 + **渐进式阅读**（mode=overview/directory/detail）；返回 source_type 标注 |
| `ingest_note` | 将开发笔记归档到 notes/，支持 8 种类型 + aliases + source_ref；默认写入为 candidate 状态 |
| `confirm_note` | 将 candidate 笔记升级为 confirmed（正式领域知识） |
| `reject_note` | 否决 candidate 笔记，后续 query_wiki 不再返回 |
| `batch_set_status` | 批量流转笔记状态（确认/否决多条笔记一次完成） |
| `ingest_source` | 导入第三方文档到 `raw/sources/`，注册到 `source_registry.json` |
| `retract_source` | 撤回已导入的外部文档（flag_stale / remove_refs 两种模式） |
| `batch_ingest` | 批量导入：一次调用处理多个笔记/文档 |
| `init_wiki` | 初始化 Wiki 工作区目录结构与项目级 schema.yaml |
| `wiki_stats` | Wiki 知识库统计（页面数、笔记状态分布、覆盖率概览） |

**质量保障（2 个）：**

| 工具 | 用途 |
|------|------|
| `lint_wiki` | 文档-代码一致性检查：**18 项检查**（含 unsupported_claims 无证据断言检测、low_adoption 低采纳检测） |
| `flag_issue` | 标记 Wiki 质量问题，驱动 health score 计算 |

**跨服务分析（1 个）：**

| 工具 | 用途 |
|------|------|
| `query_cross_service` | 查询跨服务调用关系（HTTP + MQ），支持 by_service / by_method / by_path / trace 过滤 |

**工作区管理（3 个）：**

| 工具 | 用途 |
|------|------|
| `init_workspace` | 把当前目录初始化（或重新同步）为多仓 harness 工作区：生成 bootstrap 克隆脚本（登记表）、.gitignore、repo-map 导航骨架、AGENTS.md 工作区约定（两跳检索路由、提交纪律）与产品级 repowiki；首次初始化必须先征询用户选择知识布局（colocated/centralized）再带 layout 调用——不传时返回 needs_layout_decision 且不写任何产物，布局持久化到 repowiki/.meta/workspace.json（两种布局都写）；重跑零配置幂等——痕迹齐备（bootstrap 脚本 + .gitignore + repowiki 骨架）时为 clone-only 接管：只补克隆未克隆的业务仓（存量缺配置顺带补写）、不触碰其他文件；骨架有缺失才补齐产物并强制刷新约定块；业务仓登记走 add_workspace_repo |
| `add_workspace_repo` | 按克隆 URL 向工作区登记业务仓（目录名自动取仓库名）：事务式同步 bootstrap.sh/ps1 登记表、.gitignore、repo-map.md 四处，默认顺带 git clone（失败只警告、不回滚登记）；同名同 URL 重登记为空操作 |
| `remove_workspace_repo` | 按子目录名移除业务仓登记（bootstrap 表、.gitignore、repo-map.md 四处），按仓归属过滤 analyze_workspace 的跨仓分析缓存（.meta routes/links/infra 与生成的 overview），并删除本地目录（不可恢复） |

**团队记忆融合（2 个）：**

| 工具 | 用途 |
|------|------|
| `capture_conversation` | 采集对话转录到 repowiki/raw/，仅落盘不蒸馏，支持 session 覆盖去重 |
| `distill_conversation` | 蒸馏 raw 对话为 Wiki 笔记：Mode C prepare → Agent 提取 → submit 入库（status=draft），需 confirm_note 确认 |

**任务管理（12 个）：**

| 工具 | 用途 |
|------|------|
| `create_task` | 创建长线任务（task_id 由标题 slugify 生成，不可变、不允许重名） |
| `list_tasks` | 列出任务，支持 status 过滤（active / completed） |
| `get_task` | 查看单个任务详情 |
| `get_task_context` | 拉取任务描述 + 记忆 + 关联笔记，作为继续工作的上下文；返回 pending_raw_count 提示补蒸馏 |
| `set_session_task` | 将当前会话绑定到任务，后续采集/蒸馏自动携带 task_id |
| `add_task_memory` | 手动向任务追加进度记忆 |
| `stage_task_memories` | 暂存候选任务记忆（待确认） |
| `list_pending_memories` | 列出待确认的任务记忆 |
| `confirm_task_memories` | 确认暂存记忆，落盘到任务 memories.md |
| `reject_task_memories` | 否决暂存记忆 |
| `complete_task` | 完成任务 |
| `delete_task` | 删除任务（级联删除任务目录与绑定，但不删已打 task_id 标签的笔记） |

> 另有 2 个遗留工具（`generate_docs`、`get_module_tree`）保留向后兼容，需先通过 `codewiki config set` 配置 LLM API。

### 文档生成质量增强

CodeWiki-Plus 在 Prompt 层和引擎层做了系统性优化，显著提升生成文档的精度和效率。

#### Evidence-Based 业务断言

生成模块文档时，Prompt 要求 LLM 对每条业务规则提供代码证据：

```markdown
### 业务规则

- **订单金额不可为负** [confidence: 0.95]
  > evidence: `OrderService.java:L142` — `if (amount < 0) throw new BizException(...)`
  > reason: 创建订单时强制校验金额非负
```

`lint_wiki` 新增 `unsupported_claims` 检查：当页面中超过 30% 的业务断言缺少 evidence 时报告警告，帮助识别潜在的 LLM 幻觉。

#### 组件约束索引表

每个模块文档自动生成结构化的约束索引表，方便 LLM 消费者快速定位：

```markdown
### Component Constraint Index

| Component | Type | Key Constraints | Dependencies |
|-----------|------|-----------------|--------------|
| OrderService | business | 金额校验、状态机流转 | PaymentClient, OrderRepo |
| OrderDTO | boilerplate | 字段映射 | — |
```

#### 代码路由分类

`analyze_repo` 阶段自动将组件分为三类，差异化处理：

| 分类 | 典型组件 | 处理方式 |
|------|----------|----------|
| `business` | Service, Controller, Job, Handler | 完整源码注入 LLM，生成详细文档 |
| `boilerplate` | DTO, VO, Entity, Config, Mapper | 仅注入签名 + 字段列表，模板化输出 |
| `infra` | Util, Helper, Factory, Interceptor | 摘要级描述 |

典型 Java/Spring 仓库可减少 30%+ 的 LLM token 消耗。用户可在 `schema.yaml` 的 `code_routing` 配置节自定义分类规则。

#### BFS 调用图上下文

文档生成 Prompt 中自动注入 1-hop 调用上下文（`<CALL_CONTEXT>` 块），为每个核心组件附带直接调用者/被调用者的签名摘要，帮助 LLM 理解跨模块关系：

```
<CALL_CONTEXT>
## Neighbors of OrderService.createOrder
- [caller] PaymentController.initiatePayment(PaymentRequest req)
- [callee] InventoryClient.deductStock(String skuId, int qty)
</CALL_CONTEXT>
```

### 增量更新

`analyze_repo` 内置三层增量优化：

**变更检测**：首次生成后再次调用时，自动比对上次生成状态：

- **Git 策略（优先）**：通过 `git diff` 比对当前 HEAD 与上次生成时的 commit，识别变更文件
- **SHA256 指纹策略（回退）**：通过文件内容哈希（前 64KB）+ mtime 双重检测变更

**方法级精确检测**：文件变更后，逐组件比较 `content_hash`（SHA256 前 16 位），只有真正变化的方法/类才被标记为 stale。`get_stale_components()` 返回 added / modified / deleted 三类变更列表，支持级联失效关联的 Wiki 页面。

**选择性重解析**：仅重新解析变更文件，未变更文件的组件直接从 SQLite 缓存加载合并。`skip_file_paths` 参数贯穿全链路（DependencyGraphBuilder → DependencyParser → AnalysisService → CallGraphAnalyzer）。

**Overview stale 精确判定**：通过解析 overview.md 中的链接提取引用模块列表（持久化到 `.meta/overview_refs.json`），只有当 overview 实际引用了受影响模块时才标记为 stale。

### Monorepo 跨服务分析

`analyze_repo` 自动检测 monorepo 中的子服务（5 阶段启发式：docker-compose → Dockerfile → 构建清单 → 约定目录 → Spring Boot），为每个子服务分配独立标签，在依赖图上运行 CrossServiceMatcher 识别 HTTP/MQ 跨服务调用关系。

```
检测流程：
  docker-compose.yml 服务定义
  → Dockerfile 构建目标
  → pom.xml / build.gradle / package.json 构建清单
  → src/main, app/, cmd/ 等约定目录
  → Spring Boot @SpringBootApplication 入口

输出：
  .meta/cross_service_links.json  — 跨服务调用拓扑
  query_cross_service 工具可按 service/method/path/trace 维度查询
```

### 知识飞轮

笔记系统遵循 OKF v0.2 的 draft → stable → deprecated 生命周期，确保 LLM 自动沉淀的知识经过研发确认：

```
LLM 发现跨功能约束
  → ingest_note(status=draft) 写入 notes/
  → query_wiki 返回时标注 [unconfirmed]
  → 研发确认：confirm_note → 升级为 stable 并记录 verified 审核事件
  → 研发否决：reject_note → 标记 deprecated，不再被搜索返回（保留记录）
```

旧版词汇（candidate/confirmed/rejected/superseded）在读取端自动归一化，存量笔记无需立即迁移。

### 团队记忆融合（Team Memory Fusion）

借鉴 Team-Agent-Memory 的"从对话中提取可检索经验"能力，融合进知识飞轮，让 Agent 与研发的日常对话也能沉淀为可检索的实践经验。

**核心工具：**

- `capture_conversation`：将对话转录采集到 `repowiki/raw/`（仅落盘、不蒸馏），支持 session 覆盖去重。可由 IDE 的 SessionEnd 事件自动触发（默认关闭，通过 `team-memory-hook` Prompt 启用）。
- `distill_conversation`：将 raw 对话蒸馏为结构化 Wiki 笔记（标题/类型/关联模块）。采用 Mode C 协议——`prepare` 取出 transcript+system prompt → Agent 自行提取 → `submit` 交回 `distilled` JSON，全程无状态、不自动发生。产出入库为 `status=draft`，需 `confirm_note` 确认才成正式知识。

**关键约束：**

- 自动采集 Hook 只落 raw，永不自动蒸馏；蒸馏须显式调用 `distill_conversation`。
- `repowiki/raw/` 是暂存区，不进 `query_wiki` 检索；蒸馏完成后由工具自动清理（除非 `keep_raw`）。
- 触发形态为 **both**：手动命令（主）+ IDE Hook（可选）。
- 自动采集/任务引导 Hook 接线支持 **CodeBuddy（`.codebuddy/`）、Qoder（`.qoder/`）、Claude Code（`.claude/`）**，启用时运行 `codewiki install-hooks --repo-path <repo>` 自动检测项目根目录存在哪些 IDE 配置目录，检测到哪些就为哪些接线（拷贝 hook 脚本与 distill-worker subagent、幂等合并 settings.json、写入 AGENTS.md 引导段）；采集脚本对事件载荷做了通用化处理。显式 `--ide <name>` 默认要求该 IDE 配置目录已存在——仓库只为实际在用的工具接线；确需为尚未初始化的工具创建配置目录时，须显式加 `--create-dir`（防止 Agent 代跑命令时越权新建 `.qoder`/`.claude` 等目录）。

**隐私语义（T2 团队遥测）：** `query_wiki` 的检索命中与 `capture_conversation` 的采纳记录会以 `user_id`（优先 `CODEWIKI_USER` 环境变量，回退 `git config user.name` / 系统登录名）署名写入 `repowiki/.meta/telemetry/<user_id>.jsonl` 并随仓库共享——此前这是 gitignore 的本机私有数据。`user_id` 不做鉴权（信任模型与 confirm 闸门一致：能提交即团队可信成员），仅作命名空间；不愿以 git 真名署名的成员可用 `CODEWIKI_USER` 设置花名，或在 `schema.yaml` 中设 `conventions.telemetry.enabled: false` 退回纯本机模式（写入 `repowiki/.meta/telemetry-local/`，已 gitignore，聚合逻辑不变）。

### 任务记忆（Task Memory）

任务记忆解决"长线工作跨会话断片"的问题：一个任务往往持续数天、横跨多个会话，Agent 每次重启都要从零了解"上次做到哪了"。任务记忆与 Wiki 笔记互补——**Wiki 笔记沉淀跨任务的通用经验，任务记忆保存任务范围内的进度知识**（本次做了什么、下一步、待办）。

**工作流：**

```
会话开始：
  list_tasks(status="active") → 选择关联已有任务或新建
  → set_session_task 绑定会话（后续采集自动携带 task_id）
  → get_task_context 拉取任务描述 + 记忆 + 关联笔记
  → 若 pending_raw_count > 0：委托「蒸馏 worker」subagent 后台补蒸馏，不阻塞开始工作

会话过程中：
  distill_conversation 双轨产出：
    notes    → 通用知识笔记（走 confirm_note 评审）
    memories → 任务进度记忆（先暂存 pending）
  → confirm_task_memories 确认后落盘 memories.md
```

**存储结构：**

```
repowiki/
├── tasks/
│   ├── .index.json           # 任务索引
│   └── <task_id>/
│       ├── task.md           # 任务描述
│       ├── memories.md       # 已确认的任务记忆（追加式原子写）
│       └── pending-memories.json  # 待确认记忆暂存
└── .meta/
    └── task_bindings/        # 会话 ↔ 任务绑定
```

**关键约束：**

- task_id 由标题 slugify 生成且不可变；同名任务被拒绝；无重命名（删除后重建）。
- 任务记忆先暂存、经 `confirm_task_memories` 确认后才落盘，与笔记评审闸门对齐。
- 可选的 IDE SessionStart Hook（默认关闭）在会话开始时自动提示关联任务。

### 渐进式阅读协议

`query_wiki` 支持三种消费模式，让 Agent 按需逐层深入，避免一次性加载过多内容：

| mode | 返回内容 | 适用场景 |
|------|----------|----------|
| `overview` | 仓库级摘要（< 500 token） | Agent 初次接触项目，快速了解全貌 |
| `directory` | 按类型分区的页面目录（< 800 token） | 定位目标模块/实体 |
| `detail` | 指定页面完整内容 | 深入阅读特定文档 |
| 默认 | BM25 snippet 搜索结果 | 关键词检索 |

```
Agent 消费路径：
  query_wiki(mode=overview) → 了解项目
  → query_wiki(mode=directory) → 找到目标页面
  → query_wiki(query="xxx", expand=true) → 深入阅读
```

### 存储架构

CodeWiki-Plus 采用 **SQLite 主存储 + JSON 兼容副本** 的双层架构：

**SQLite（`{repo}/.codewiki/analysis_cache.db`）**：组件索引（含 content_hash）、文件指纹、依赖关系、BM25 搜索索引（token 级倒排）、符号映射（symbol_map）、路由表均存储在 SQLite 中，支持高效查询和增量更新。

**JSON 兼容副本（`output_dir/.meta/`）**：`symbol_map.json`、`module_tree.json` 等保留精简 JSON 副本，供外部工具直接读取。

**持久化项目映射（`.meta/project.json`）**：`analyze_repo` 执行后自动写入 `repo_path`、`output_dir`、`cache_db` 的绝对路径映射。这使得 `query_wiki`、`ingest_note` 等知识管理工具在**无活跃 session** 时也能通过 `project.json` 定位 SQLite 数据库，走 BM25 索引搜索。

```
搜索路径优先级：
  活跃 session.cache → .meta/project.json → cache_db → SQLite BM25
                     ↘ 回退：output_dir.parent/.codewiki/analysis_cache.db
                     ↘ 最终回退：.meta/search_index.json（全量遍历）
```

### LLM Wiki 知识系统

除了文档生成，CodeWiki-Plus 还内置了 LLM Wiki 知识管理能力，让生成出的 Wiki 持续演进为项目的活知识库。

#### 结构化知识库布局

所有 Wiki 内容按页面类型（page type）组织在 `wiki/` 子目录下，由 `page_router.py` 统一路由：

| 页面类型 | 目录 | 说明 |
|----------|------|------|
| `module` | `wiki/modules/` | 模块文档（含约束索引表 + Evidence-Based 断言） |
| `entity` | `wiki/entities/` | 实体页面：类、接口、数据库表、配置项等 |
| `concept` | `wiki/concepts/` | 概念页面：设计模式、业务概念、架构风格等 |
| `source` | `wiki/sources/` | 外部文档摘要：导入的第三方文档 |
| `comparison` | `wiki/comparisons/` | 对比分析：技术选型、方案比较等 |
| `query` | `wiki/queries/` | 研究查询：调研结论、问题排查记录等 |

`write_doc_file` 工具的 `page_type` 参数指定类型即可自动路由到正确目录。

#### schema.yaml 与配置

`schema.yaml` 是项目的文档"宪法"，包含项目定位（`purpose` 字段）、命名规范、必需章节、文档维度、lint 设置、**page_types 路由表**、以及 **code_routing 代码路由规则**。CodeWiki-Plus 安装目录下的 `schema.yaml` 是与语言无关的默认模板，首次 `analyze_repo` 时会读取它生成项目级 `schema.yaml`。

**自定义**：将安装目录的 `schema.yaml` 拷贝到项目的 output_dir（如 `repowiki/schema.yaml`）并修改，即可覆盖默认值；增量更新时自动合并保留自定义字段。

#### 交叉链接与别名

- **交叉链接注入**：`write_doc_file` 根据组件级依赖关系自动在文档末尾注入"相关模块"章节（Depends on / Used by），通过 `schema.yaml` 中的 `auto_crosslink` 开关控制
- **别名（aliases）**：文档 frontmatter 中可声明 `aliases` 列表，搜索时别名获得 **3× BM25 权重提升**
- **来源引用（source_refs）**：正文中使用 `[^src:name:line_range]` 标记第三方文档出处

#### 来源类型标注

`query_wiki` 搜索结果为每条结果标注 `source_type`，帮助 Agent 判断信息可信度：

| source_type | 含义 | 消费建议 |
|-------------|------|----------|
| `auto_generated` | 来自 wiki/ 目录，代码分析自动生成 | 可直接引用 |
| `developer_note` | 来自 notes/ 目录，人工/LLM 沉淀 | 检查时效性和确认状态 |
| `ingested_source` | 来自 ingest_source 导入的外部文档 | 注意版本时效 |

#### 外部文档管理

通过 `ingest_source` 和 `retract_source` 管理第三方文档（API 文档、设计规范、RFC 等）的完整生命周期：

```json
// 导入外部文档（必填 source_ref：源文件的绝对路径）
{ "name": "rfc-7519-jwt", "source_type": "rfc", "source_ref": "/path/to/rfc7519.txt",
  "description": "JWT 规范", "related_pages": ["auth-module"] }

// 撤回外部文档（两种模式，必填 name：ingest_source 注册的标识）
{ "name": "rfc-7519-jwt", "mode": "flag_stale" }    // 标记过期，保留文件
{ "name": "rfc-7519-jwt", "mode": "remove_refs" }   // 删除文件，清理所有引用
```

#### 文档健康检查

`lint_wiki` 提供 **18 项检查**，覆盖结构完整性和内容质量：

| 检查项 | 说明 |
|--------|------|
| `stale_refs` | 引用了已不存在的组件 |
| `broken_links` | 断链（wikilink 指向不存在的页面） |
| `undocumented` | 高影响力组件缺少文档 |
| `cycles` | 模块间循环依赖 |
| `coverage` | 文档覆盖率不足 |
| `orphan_pages` | 没有任何页面链接到的孤立页面 |
| `no_outlinks` | 没有链接到任何其他页面的死端页面 |
| `missing_aliases` | 实体页面缺少 aliases 声明 |
| `stale_sources` | 引用了已撤回外部文档的页面 |
| `overview_stale` | overview.md 引用了已变更的模块 |
| `unsupported_claims` | 业务断言缺少代码证据（>30% 触发警告） |
| `superseded_pages` | 标记为已取代（superseded/deprecated）的页面 |
| `isolated_components` | 零依赖零被依赖的孤立组件 |
| `stale_notes` | 超过 90 天且 60 天内未被检索的已确认笔记 |
| `note_clusters` | 同模块同类型笔记 ≥3 条，建议合并 |
| `low_adoption` | 高频召回（≥5 次）但零采纳的 stable 笔记——内容相关但不够 actionable，建议按「步骤/命令/预期结果」重写 |
| `okf_conformance` | OKF v0.2 合规审计：缺失 type/frontmatter、旧版状态词、verified 格式错误、stale_after 过期、缺 okf_version |
| `scenario_capacity` | L2 场景块数量达到/超过容量上限（error/warning 分级），需先 MERGE 腾位再新增 |
| `scenario_orphan` | 无来源标注（metadata.source_notes）且长期未被检索的孤儿场景块，可能冗余或过时 |

`lint_wiki` 返回 **health_score**（0-100），计算方式为 `100 - Σ(error×10 + warning×3 + info×1)`。

#### OKF v0.2 兼容

生成的 Wiki 遵循谷歌 [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog) v0.2 规范，每个 Markdown 页面携带标准化 frontmatter：

- **type（必填）**：页面类型，如 `Module` / `Entity` / `Concept` / `Source`，由 `write_doc_file` 自动注入
- **generated**：`{ by: codewiki/5.2.0, at: <ISO-8601> }` 生产者溯源（actor 约定：`<tool>/<version>`、`human:<id>`、`process:<id>`）
- **status**：生命周期状态 `draft → stable → deprecated`，笔记默认 draft，经 `confirm_note` 确认后升级为 stable
- **stale_after**：知识保鲜期（默认 90 天，`schema.yaml` 的 `conventions.default_stale_days` 可调），过期由 lint 提示复核
- **verified**：`confirm_note` 追加 `{by, at}` 审核事件，支撑 machine-confirmed / human-reviewed 信任分级
- **sources**：引用外部文档时自动从 source_registry.json 生成 `{id, resource, title}` 列表
- `wiki/index.md` 声明 `okf_version: "0.2"` 并采用 §8 列表格式，`log.md` 采用 §9 按日期分组格式

存量旧版 Wiki 可用一次性迁移脚本升级：`python scripts/migrate_okf.py <repowiki目录>`（幂等、可 `--dry-run` 预览）。

#### 全文搜索

`query_wiki` 搜索能力：

- **BM25 排序** + jieba 中文分词
- **类型过滤**：`type_filter` 限定搜索范围（module/entity/concept/source/comparison/query）
- **作用域前缀**：`scope` 支持目录前缀（如 `wiki/entities`、`notes`）
- **权重增强**：aliases 3× boost、severity 2× boost
- **图谱多跳扩展**：`hop`（0-3）沿 wikilink 有向边 BFS 发现关联页面，`decay` 控制衰减
- **深度阅读**：`expand=true` 返回完整页面内容（≤ 3000 字符）
- **渐进模式**：`mode=overview/directory/detail` 分层消费
- **状态过滤**：自动跳过 rejected 笔记，candidate 标注 [unconfirmed]

#### 提示词模板

`get_prompt` 支持 **16 种 prompt_type**：

| prompt_type | 用途 |
|-------------|------|
| `cluster` | 模块聚类规则 |
| `system_complex` / `system_leaf` | 文档生成系统指令（含 Evidence-Based + 约束索引表） |
| `user` | 用户 prompt 模板（含代码路由 + BFS 上下文） |
| `overview_module` / `overview_repo` | 总览合成 |
| `entity_page` / `concept_page` | 实体/概念页面生成 |
| `source_summary` | 外部文档摘要 |
| `comparison_page` / `query_page` | 对比分析 / 研究查询 |
| `taxonomy_plan` | Wiki 分类体系规划 |
| `extraction_scan` | 源码实体/概念候选提取 |
| `wiki_query` / `wiki_ingest` / `wiki_lint_report` | 知识管理工作流 |

#### 工作流 Prompt

MCP Server 内置 **20 个工作流 Prompt**，在 AI IDE 中通过 Prompt 面板直接触发，Agent 自动编排多工具调用：

| Prompt 名称 | 面向场景 | 核心步骤 |
|-------------|----------|----------|
| `init-wiki` | 新项目初始化 Wiki 工作区 | init_wiki 创建目录 + schema.yaml → 自定义 purpose → 验证 AGENTS.md |
| `init-workspace` | 初始化多仓 harness 工作区 | 询问用户选知识布局 → init_workspace(layout=...) 生成 bootstrap 脚本 + .gitignore + repo-map + 工作区约定 → 克隆业务仓 → 逐个登记后按需 init_wiki/analyze_repo → analyze_workspace |
| `add-workspace-repo` | 登记业务仓到工作区 | add_workspace_repo 事务式同步 bootstrap 登记表/.gitignore/repo-map → git clone → 建仓库级 Wiki |
| `generate-wiki` | 完整文档生成流水线 | analyze_repo → 聚类 save_module_tree → 逐模块 write_doc → overview → lint → close_session |
| `code-analysis` | 仅分析代码结构，不生成文档 | analyze_repo → list_components → list_dependencies → 缓存到 SQLite |
| `incremental-update` | 代码变更后增量更新文档 | analyze_repo（增量检测）→ 识别 stale 组件 → 选择性重生成 → close_session |
| `workspace-analysis` | 多仓库工作区分析 | analyze_workspace → 逐仓库生成 Wiki → RouteNode 跨服务匹配 → Mermaid 拓扑图 |
| `cross-service-trace` | 跨服务调用链追踪 | query_cross_service → RouteNode 静态匹配 → trace_path 多跳语义追踪 → 架构诊断 |
| `impact-review` | 修改影响范围评估 | analyze_impact（BFS 传递性遍历）→ 模块级聚合 → 高风险组件识别 → 调用链路输出 |
| `architecture-review` | 架构审查与热点分析 | 依赖图分析 → 核心层/服务层/应用层识别 → Top 5 热点 → 耦合风险 → 入口点 |
| `extract-knowledge` | 外部文档知识提取 | ingest_source 导入 → extraction_scan 候选提取 → 实体/概念页面生成 → wikilink 图谱 |
| `search-wiki` | 知识库搜索策略指引 | query_wiki（BM25）→ 图谱多跳扩展 → 渐进式阅读（overview → directory → detail） |
| `quality-check` | Wiki 质量全面检查 | lint_wiki（18 项检查）→ health_score → flag_issue 标记 → 修复建议 |
| `ingest-note` | 经验知识归档 | ingest_note（8 种类型）→ candidate 状态 → confirm/reject 流转 → BM25 索引 |
| `team-memory-hook` | 对话自动采集管理 | 检查状态 → 启用（注册 SessionEnd 事件）/ 关闭 → 验证 |
| `distill-conversations` | 对话蒸馏提取经验 | prepare 取 transcript → Agent 提取知识 → submit 去重入库 → confirm/reject 评审 |
| `task-workflow` | 任务记忆完整工作流 | 会话开始关联任务 → 补蒸馏 → get_task_context → 工作中沉淀 memories → confirm 落盘 |

### 使用场景示例

**场景 1：生成仓库文档**

```
帮我分析当前仓库并生成 Wiki 文档，输出到 repowiki 目录。请使用中文撰写文档。
```

**场景 2：增量更新**

```
代码有改动，帮我更新受影响的模块文档。
```

Agent 调用 `analyze_repo`，自动检测变更文件和 stale 组件，只重新生成受影响的模块。

**场景 3：搜索项目知识**

```
搜索项目中关于"订单状态机"的所有知识。
```

Agent 调用 `query_wiki(query="订单状态机", hop=1)`，返回相关文档 + 图谱关联页面。

**场景 4：沉淀开发经验**

```
记录一个踩坑：Redis 连接池在高并发下偶尔超时，根因是 maxTotal 设置过低。
```

Agent 调用 `ingest_note(note_type="pitfall", status="candidate")`，写入笔记待确认。

**场景 5：确认/否决知识**

```
确认 notes/pitfall-redis-connection-pool.md 这条笔记。
```

Agent 调用 `confirm_note(note_file="pitfall-redis-connection-pool.md")`，升级为正式知识。

**场景 6：导入外部文档**

```
把 docs/stripe-api-reference.md 导入 Wiki，关联支付模块。
```

**场景 7：检查文档健康度**

```
检查一下 Wiki 文档的健康状况。
```

Agent 调用 `lint_wiki`，返回 18 项诊断报告和 health_score。

**场景 8：跨服务调用分析**

```
分析这个 monorepo 里各服务之间的调用关系。
```

Agent 调用 `analyze_repo`（自动检测子服务）→ `query_cross_service(filter_type="all")`。

**场景 9：跨会话延续长线任务**

```
继续上次的"支付重构"任务。
```

Agent 调用 `list_tasks` 找到任务 → `set_session_task` 绑定会话 → `get_task_context` 恢复上下文（做了什么、下一步），若有未蒸馏对话委托「蒸馏 worker」subagent 后台补蒸馏（不阻塞），然后无缝继续工作。

### 支持的其他 AI IDE

除 CodeBuddy 外，任何支持 MCP stdio 协议的 AI IDE 均可使用：

**Cursor**：在 Settings → MCP 中添加相同的 Server 配置。

**Claude Desktop**：在 `~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）中添加 MCP 配置。

**其他 IDE**：指定 `command: "codewiki"`, `args: ["mcp"]` 即可。

### 团队记忆 Hook 的智能体支持矩阵

对话采集 Hook（team-memory-hook）按家族归并支持多种智能体（注册表 `codewiki/hooks.yaml`，家族格式：claude = settings.json、cursor/codex = hooks.json）：

| 智能体 | 家族 | 支持等级 |
|--------|------|----------|
| `codebuddy` | claude | 已验证 |
| `qoder` | claude | 已验证 |
| `claude-code` | claude | 已验证 |
| `codex-cli` | codex | 理论支持 |
| `cursor` | cursor | 理论支持（采集降级：stop 事件不带 transcript，仅事件信封） |
| `gemini-cli` | claude | 理论支持 |
| `trae` | claude | 理论支持 |
| `windsurf` | claude | 理论支持 |
| `kilocode` | claude | 理论支持 |
| `opencode` | claude | 理论支持 |

"已验证"指日常使用背书；"理论支持"指家族归并推导、未经真机验证——接线后请按 team-memory-hook prompt 的模拟事件步骤验证。不支持 hook 的运行时可用 `capture_conversation` MCP 工具手动采集。

**无 MCP 环境的检索**：`codewiki query "<关键词>"` CLI 命令输出 Agent 友好的定界文本块（与 query_wiki 同一引擎），配合 `codewiki/agents/wiki-recall.md` subagent 定义（拷入各工具的 agents 目录），任何能执行 shell 命令的 Agent 均可消费团队知识库。

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

支持 OpenAI、Anthropic、Azure OpenAI、AWS Bedrock 以及 Claude Code / Codex 订阅模式（此模式的历史用法可参考[上游项目 README](https://github.com/FSoft-AI4Code/CodeWiki)）。

### 支持的语言

Python、Java、JavaScript、TypeScript、C、C++、C#、Kotlin、Go、PHP

### 致谢

CodeWiki-Plus 的核心工具链（Tree-sitter AST 解析、依赖图构建、拓扑排序、Mermaid 校验）源自 [FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki)，本项目在其基础上独立演进，感谢原作者团队的开拓性工作。以下开源项目的设计思路对我们产生了重要影响：

- [codebase-memory-mcp](https://github.com/nicobailon/codebase-memory-mcp) — SQLite 持久化缓存架构、跨会话复用、三层降级模式
- [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki) — 结构化知识层设计、页面类型路由、交叉链接
- [Tencent/WeKnora](https://github.com/Tencent/WeKnora) — 外部文档管理、文档健康检查、自适应分块思路
- [CodingHub](https://github.com/mambo-wang/CodingHub) — MCP Server 最佳实践（instructions / prompts / resources）

我们在上游基础上将 MCP Server 从黑盒模式拆分为 **40 个细粒度工具**，并新增结构化 Wiki、Evidence-Based 断言、代码路由分类、知识飞轮、渐进式阅读、方法级增量检测、monorepo 跨服务分析、团队记忆融合、任务记忆等能力。

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

<p align="center">
  <img src="img/thankyou.png" alt="Thank You" width="700" />
</p>

---

<a id="en"></a>

## English

### What is this project?

CodeWiki-Plus is a repository knowledge engine driven entirely by the AI IDE's own model (CodeBuddy, Cursor, Claude Desktop, etc.) via MCP (Model Context Protocol): **zero LLM configuration** for Wiki generation, plus a full knowledge management engine on top — retrieval, notes, task memory, and team telemetry.

The project originated as a fork of [FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki) and has since evolved independently on top of its toolchain (Tree-sitter AST parsing, dependency graph construction, topological sort, Mermaid validation) into a standalone project with a different architectural focus — see [Acknowledgements](#acknowledgements).

### Why not just use the original?

The original CodeWiki is an excellent repository-level documentation framework. However, it requires users to configure their own LLM API (API key, provider, model selection), and the generation pipeline runs as a black box with no user intervention.

In practice, CodeWiki's core toolchain—Tree-sitter AST parsing, dependency graph construction, topological sorting, and Mermaid validation—does not need an LLM at all. The 4 stages that do require LLM intelligence (module clustering, document writing, sub-module recursion, and overview synthesis) are exactly what AI IDE Agents excel at.

We refactored CodeWiki's MCP Server from a "one-click black box" into **40 fine-grained tools**, turning it into a pure toolchain server. The AI IDE's Agent calls these tools via MCP and uses its own reasoning to complete all documentation work:

```
Before:
  IDE → generate_docs(repo) → [CodeWiki calls LLM API internally] → result

After:
  IDE Agent → analyze_repo → read_code → (Agent reasons) → write_doc → overview
              ↑ pure tool     ↑ pure tool  ↑ IDE's own model ↑ pure tool
```

### Differences from upstream CodeWiki

| Dimension | Upstream CodeWiki | CodeWiki-Plus |
|-----------|------------------|---------------|
| LLM config | Must configure API key | Zero-config, IDE model driven |
| Generation mode | Black-box one-click | 40 fine-grained tools, full Agent control |
| Doc quality | Generic descriptions | Evidence-Based assertions (code quotes + confidence) |
| Generation efficiency | All components equal | Code routing: boilerplate gets signature-only |
| Context precision | Intra-module components | BFS 1-hop call graph + constraint index table |
| Incremental update | File-level Git diff | Method-level content_hash detection |
| Knowledge management | None | Structured Wiki + note flywheel + external docs |
| Task memory | None | Cross-session task context + pending-confirm task memories |
| Search | None | BM25 + wikilink graph multi-hop + progressive reading |
| Cross-service | None | Monorepo sub-service detection + call tracing |
| Quality assurance | None | 17 lint checks + health score + issue tracking |

### Prerequisites

- **Python 3.12+**
- **Node.js** (for Mermaid diagram validation; without it, validation is silently skipped)
- An MCP-compatible AI IDE (CodeBuddy, Cursor, Claude Desktop, etc.)

### Quick Start (CodeBuddy Example)

3 steps, no API key needed.

**Step 1: Install CodeWiki-Plus**

```bash
pip install codewiki-plus
```

Verify:

```bash
codewiki --version
```

> **For developers** (latest unreleased changes) — [uv](https://docs.astral.sh/uv/) is recommended to reproduce the dev environment exactly as locked by `uv.lock` (`tool.uv.default-groups = ["dev"]` includes dev tools):
> ```bash
> git clone https://github.com/mambo-wang/CodeWiki-Plus.git
> cd CodeWiki-Plus
> uv sync --frozen              # reproduce the full dev environment from uv.lock (hatchling build)
> uv run codewiki --version     # run the CLI inside the uv-managed environment
> uv run pytest tests/ -q       # run tests (no --cov in addopts; no override needed)
> # with coverage: uv run pytest --cov=codewiki --cov-report=term-missing
> ```
> Without uv, `pip install -e .[dev]` still works, but dependency resolution is not locked by `uv.lock`.

**Step 2: Configure MCP Server**

Add the following to your CodeBuddy MCP settings:

```json
{
  "mcpServers": {
    "codewiki": {
      "command": "codewiki",
      "args": ["mcp"]
    }
  }
}
```

**Step 3: Prompt your AI Agent**

Open the target project in CodeBuddy, switch to Agent mode, and enter:

```
Analyze the current repository and generate Wiki documentation into the repowiki directory. Write docs in English.
```

The Agent follows a 5-stage pipeline:

```
Stage 1: Call analyze_repo → get component index, leaf nodes
         (auto-detects monorepo sub-services, builds cross-service topology)
Stage 2: Call get_prompt("cluster") for clustering rules
         Read source code, reason about grouping, call save_module_tree
Stage 3: Document each module leaf-first
         Leaf modules: read_code → reason → write_doc_file
         (prompt auto-injects BFS call context + constraint index + business rules extraction)
         Parent modules: read child docs → synthesize → write_doc_file
Stage 4: Generate repository overview (overview.md)
Stage 5: Call close_session to free resources, build search index
```

### MCP Tools

All tools require zero LLM config. The IDE Agent invokes them via MCP. The server includes built-in **instructions**, **19 Workflow Prompts** (covering init, generation, incremental update, search, quality check, cross-service analysis, team memory fusion, task memory), and **6 Resources**.

**Code Analysis (6):**

| Tool | Purpose |
|------|---------|
| `analyze_repo` | Parse repo, build dependency graph; SHA256 incremental + method-level content_hash; monorepo sub-service detection |
| `analyze_workspace` | Scan multi-repo workspace, generate per-repo Wikis with cross-service overview |
| `list_components` | Component index query with summary mode and prefix filtering |
| `list_dependencies` | Query dependencies with pagination, direction filtering, high-impact ranking |
| `read_code_components` | Read source code by component ID |
| `view_repo_file` | View raw source file content with optional line range |

**Documentation Pipeline (6):**

| Tool | Purpose |
|------|---------|
| `write_doc_file` | Create .md docs with Mermaid validation + crosslink injection + page_type routing; sessionless mode |
| `edit_doc_file` | Edit docs (str_replace / insert / undo) |
| `save_module_tree` | Persist module clustering results |
| `get_processing_order` | Get leaf-first documentation order |
| `get_prompt` | Retrieve prompt templates (23 prompt_types) |
| `close_session` | Close session, build BM25 index + wikilink graph, write metadata |

**Knowledge Management (10):**

| Tool | Purpose |
|------|---------|
| `query_wiki` | BM25 search + wikilink graph multi-hop + **progressive reading** (mode=overview/directory/detail); source_type annotation |
| `ingest_note` | File structured notes (8 types) with aliases + source_ref; default candidate status |
| `confirm_note` | Promote candidate note to confirmed knowledge |
| `reject_note` | Reject candidate note, exclude from future searches |
| `batch_set_status` | Batch transition note statuses (confirm/reject multiple at once) |
| `ingest_source` | Import third-party docs into `raw/sources/` |
| `retract_source` | Retract imported docs (flag_stale / remove_refs) |
| `batch_ingest` | Batch import multiple notes/sources in one call |
| `init_wiki` | Initialize Wiki workspace directories and project-level schema.yaml |
| `wiki_stats` | Wiki statistics (page counts, note status distribution, coverage overview) |

**Quality Assurance (2):**

| Tool | Purpose |
|------|---------|
| `lint_wiki` | Doc-code consistency: **18 checks** (incl. unsupported_claims evidence detection, low_adoption utility check, and L2 scenario hygiene) |
| `flag_issue` | Flag quality issues, drives health score |

**Cross-Service Analysis (1):**

| Tool | Purpose |
|------|---------|
| `query_cross_service` | Query cross-service calls (HTTP + MQ), filter by service/method/path/trace |

**Workspace Management (3):**

| Tool | Purpose |
|------|---------|
| `init_workspace` | Initialize (or re-sync) the current directory as a multi-repo harness workspace: generates bootstrap clone scripts (registration table), .gitignore, repo-map navigation skeleton, workspace conventions in AGENTS.md (two-hop retrieval routing, commit discipline) and the product-level repowiki. FIRST init requires an explicit knowledge-layout choice (colocated/centralized) — ask the user, then pass layout=<choice>; without it the tool returns needs_layout_decision and writes nothing. The layout is persisted to repowiki/.meta/workspace.json for BOTH layouts. Re-runs are zero-config and idempotent — when every init trace is present (bootstrap scripts + .gitignore + repowiki skeleton) a re-run is clone-only: it fetches just the uncloned business repos (backfilling a missing layout config) and touches nothing else; missing skeletons are repaired and the conventions block refreshed only in that case. Register business repos via add_workspace_repo |
| `add_workspace_repo` | Register a business repo by clone URL (directory name derived from the repo name): transactionally updates the bootstrap.sh/ps1 tables, .gitignore and repo-map.md, then git-clones by default (clone failure only warns, registration is kept). Re-registering the same name+URL is a no-op |
| `remove_workspace_repo` | Deregister a business repo by subdirectory name (bootstrap tables, .gitignore, repo-map.md), scrub the repo from analyze_workspace caches (.meta routes/links/infra and the generated overview), and delete the local clone directory (irreversible) |

**Team Memory Fusion (2):**

| Tool | Purpose |
|------|---------|
| `capture_conversation` | Capture conversation transcripts to repowiki/raw/ (persistence only, no distillation); session-level supersede dedup |
| `distill_conversation` | Distill raw conversations into Wiki notes: Mode C prepare → Agent extracts → submit (status=draft); requires confirm_note |

**Task Management (12):**

| Tool | Purpose |
|------|---------|
| `create_task` | Create a long-running task (task_id slugified from title, immutable, no duplicates) |
| `list_tasks` | List tasks with status filtering (active / completed) |
| `get_task` | Inspect a single task |
| `get_task_context` | Fetch task description + memories + related notes as working context; reports pending_raw_count for catch-up distillation |
| `set_session_task` | Bind the current session to a task; subsequent captures/distillations carry task_id automatically |
| `add_task_memory` | Manually append a progress memory to a task |
| `stage_task_memories` | Stage candidate task memories (pending confirmation) |
| `list_pending_memories` | List pending task memories |
| `confirm_task_memories` | Confirm staged memories, persist to the task's memories.md |
| `reject_task_memories` | Reject staged memories |
| `complete_task` | Mark a task complete |
| `delete_task` | Delete a task (cascades task dir and bindings, but keeps tagged notes) |

> 2 legacy tools (`generate_docs`, `get_module_tree`) retained for backward compatibility.

### Documentation Quality Enhancements

#### Evidence-Based Assertions

Module documentation prompts require LLM to provide code evidence for each business rule:

```markdown
### Business Rules

- **Order amount must be non-negative** [confidence: 0.95]
  > evidence: `OrderService.java:L142` — `if (amount < 0) throw new BizException(...)`
  > reason: Enforced validation on order creation
```

`lint_wiki` includes `unsupported_claims` check: warns when >30% of business assertions lack evidence.

#### Code Routing

Components are classified into three categories for differentiated processing:

| Category | Typical Components | Treatment |
|----------|-------------------|-----------|
| `business` | Service, Controller, Job, Handler | Full source injected to LLM |
| `boilerplate` | DTO, VO, Entity, Config, Mapper | Signature + fields only, template output |
| `infra` | Util, Helper, Factory, Interceptor | Summary-level description |

Reduces LLM token consumption by 30%+ on typical Java/Spring repos. Customizable via `code_routing` in `schema.yaml`.

#### BFS Call Context

Prompts auto-inject 1-hop call context (`<CALL_CONTEXT>` block) with caller/callee signatures for each core component.

### Incremental Updates

Three layers of incremental optimization:

- **Git strategy (preferred)**: `git diff` against stored commit
- **SHA256 fingerprint (fallback)**: Content hash + mtime dual detection
- **Method-level detection**: Per-component `content_hash` comparison; only truly changed methods trigger re-generation. `get_stale_components()` returns added/modified/deleted lists for cascade wiki invalidation.

### Monorepo Cross-Service Analysis

`analyze_repo` auto-detects sub-services via 5-stage heuristics (docker-compose → Dockerfile → build manifests → convention dirs → Spring Boot), assigns independent labels, and runs CrossServiceMatcher for HTTP/MQ call relationships.

### Knowledge Flywheel

Notes follow the OKF v0.2 draft → stable → deprecated lifecycle:

```
LLM discovers cross-cutting constraint
  → ingest_note(status=draft)
  → query_wiki annotates [unconfirmed]
  → Developer confirms: confirm_note → promoted to stable, records a verified event
  → Developer rejects: reject_note → marked deprecated, excluded from search (record preserved)
```

### Team Memory Fusion

Inspired by Team-Agent-Memory's "extract retrievable experience from conversations", this capability is fused into the Knowledge Flywheel so day-to-day dialog between the Agent and developers also becomes retrievable practical knowledge.

**Core tools:**

- `capture_conversation`: Capture conversation transcripts into `repowiki/raw/` (persistence only, no distillation); supports session-level supersede dedup. Can be triggered automatically by the IDE's SessionEnd event (off by default; enable via the `team-memory-hook` prompt).
- `distill_conversation`: Distill raw conversations into structured Wiki notes (title/type/related modules). Uses Mode C protocol — `prepare` returns transcript + system prompt → Agent extracts → `submit` returns the `distilled` JSON. Fully stateless, never runs automatically. Output is ingested as `status=draft` and requires `confirm_note` to become live knowledge.

**Key constraints:**

- The automatic capture hook only writes raw; it never distills. Distillation must be invoked explicitly via `distill_conversation`.
- `repowiki/raw/` is a staging area excluded from `query_wiki`; it is cleaned up after distillation automatically (unless `keep_raw`).
- Trigger form is **both**: manual command (primary) + IDE hook (optional).
- The capture / task-guidance hooks are wired for **CodeBuddy (`.codebuddy/`), Qoder (`.qoder/`) and Claude Code (`.claude/`)**. To enable, run `codewiki install-hooks --repo-path <repo>`: it auto-detects which IDE config dirs exist in the project root and wires each one found (copies the hook scripts and the distill-worker subagent, idempotently merges `settings.json` hook registrations, and upserts the AGENTS.md task-guidance section). The capture script parses generic event payloads. Explicit `--ide <name>` requires that IDE's config dir to already exist — a repo is wired only for tools actually used in it; to deliberately create a not-yet-initialised config dir you must pass `--create-dir` (guards against agents conjuring `.qoder`/`.claude` dirs in repos that never used those tools).

**Privacy semantics (T2 team telemetry):** `query_wiki` retrieval hits and `capture_conversation` adoption records are written to `repowiki/.meta/telemetry/<user_id>.jsonl` (committed to the repo) under a `user_id` resolved from the `CODEWIKI_USER` env var, falling back to `git config user.name` / the OS login name — this data used to be a gitignored local file. The `user_id` is not an auth mechanism (trust model equals the confirm gate: anyone who can commit is a trusted teammate), it is a namespace only. Members who prefer not to sign telemetry with their git name can set a pseudonym via `CODEWIKI_USER`, or set `conventions.telemetry.enabled: false` in `schema.yaml` to fall back to local-only mode (written to `repowiki/.meta/telemetry-local/`, gitignored; aggregation is unchanged).

### Task Memory

Task Memory solves the "cross-session amnesia" problem for long-running work: a task often spans days and multiple sessions, and the Agent normally restarts from zero. Task Memory complements Wiki notes — **Wiki notes capture cross-task general knowledge, while task memories hold task-scoped progress** (what was done, what's next, todos).

**Workflow:**

```
Session start:
  list_tasks(status="active") → pick an existing task or create one
  → set_session_task binds the session (captures carry task_id automatically)
  → get_task_context restores description + memories + related notes
  → if pending_raw_count > 0: catch-up distillation before working

During the session:
  distill_conversation produces two tracks:
    notes    → general knowledge notes (confirm_note review)
    memories → task progress memories (staged as pending first)
  → confirm_task_memories persists them to memories.md
```

**Storage layout:**

```
repowiki/
├── tasks/
│   ├── .index.json                # task index
│   └── <task_id>/                 # task.md + memories.md + pending-memories.json
└── .meta/
    └── task_bindings/             # session ↔ task bindings
```

**Key constraints:**

- task_id is slugified from the title and immutable; duplicate titles are rejected; no rename (delete and recreate).
- Task memories are staged first and only persisted after `confirm_task_memories`, aligned with the note review gate.
- An optional IDE SessionStart hook (off by default) can prompt task association at session start.

### Progressive Reading Protocol

`query_wiki` supports three consumption modes:

| mode | Returns | Use case |
|------|---------|----------|
| `overview` | Repo-level summary (< 500 tokens) | First contact with project |
| `directory` | By-type page directory (< 800 tokens) | Locate target module/entity |
| `detail` | Full page content | Deep reading |
| default | BM25 snippet results | Keyword search |

### Workflow Prompts

The MCP server includes **21 built-in workflow prompts** that can be triggered from the AI IDE's prompt panel. The Agent automatically orchestrates multi-tool calls:

| Prompt | Scenario | Core Steps |
|--------|----------|------------|
| `init-wiki` | Initialize Wiki workspace for a new project | init_wiki (dirs + schema.yaml) → customize purpose → verify AGENTS.md |
| `init-workspace` | Initialize a multi-repo harness workspace | Ask the user for the knowledge layout → init_workspace(layout=...) (bootstrap scripts + .gitignore + repo-map + conventions) → clone repos → register each repo, then init_wiki/analyze_repo on demand → analyze_workspace |
| `add-workspace-repo` | Register a business repo into a workspace | add_workspace_repo (transactional sync of bootstrap tables/.gitignore/repo-map) → git clone → build repo-level Wiki |
| `generate-wiki` | Full documentation generation pipeline | analyze_repo → cluster → per-module write_doc → overview → lint → close_session |
| `code-analysis` | Analyze code structure only (no docs) | analyze_repo → list_components → list_dependencies → cache to SQLite |
| `incremental-update` | Update docs after code changes | analyze_repo (incremental) → detect stale → selective regeneration → close_session |
| `workspace-analysis` | Multi-repo workspace analysis | analyze_workspace → per-repo Wiki → RouteNode cross-service matching → Mermaid topology |
| `cross-service-trace` | Cross-service call chain tracing | query_cross_service → RouteNode matching → trace_path multi-hop → architecture diagnosis |
| `impact-review` | Change impact assessment | analyze_impact (BFS transitive) → module aggregation → high-risk identification → call paths |
| `architecture-review` | Architecture review & hotspot analysis | Dependency graph → layer identification → Top 5 hotspots → coupling risks → entry points |
| `extract-knowledge` | External document knowledge extraction | ingest_source → extraction_scan → entity/concept pages → wikilink graph |
| `search-wiki` | Knowledge base search strategy | query_wiki (BM25) → graph multi-hop expansion → progressive reading |
| `quality-check` | Comprehensive Wiki quality check | lint_wiki (18 checks) → health_score → flag_issue → fix suggestions |
| `ingest-note` | Experience knowledge archiving | ingest_note (8 types) → candidate status → confirm/reject → BM25 index |
| `team-memory-hook` | Conversation capture hook management | Check status → enable (register SessionEnd event) / disable → verify |
| `distill-conversations` | Conversation distillation | prepare fetch transcripts → Agent extracts → submit ingest → confirm/reject review |
| `task-workflow` | Full task memory workflow | Associate task at session start → catch-up distillation → get_task_context → accumulate memories → confirm |

### Supported Languages

Python, Java, JavaScript, TypeScript, C, C++, C#, Kotlin, Go, PHP

### Acknowledgements

The core toolchain (Tree-sitter AST parsing, dependency graph, topological sort, Mermaid validation) originated from [FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki); CodeWiki-Plus has evolved independently on top of it — many thanks to the original authors. Influenced by:

- [codebase-memory-mcp](https://github.com/nicobailon/codebase-memory-mcp) — SQLite persistent cache, cross-session reuse
- [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki) — Structured knowledge layer, page type routing
- [Tencent/WeKnora](https://github.com/Tencent/WeKnora) — External doc management, health checks
- [CodingHub](https://github.com/mambo-wang/CodingHub) — MCP Server best practices

Paper: [CodeWiki: Evaluating AI's Ability to Generate Holistic Documentation for Large-Scale Codebases](https://arxiv.org/abs/2510.24428)

---

## License

MIT

---

<p align="center">
  <img src="img/thankyou.png" alt="Thank You" width="700" />
</p>
