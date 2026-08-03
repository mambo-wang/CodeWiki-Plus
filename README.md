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
  <a href="https://github.com/FSoft-AI4Code/CodeWiki"><img alt="Upstream: CodeWiki" src="https://img.shields.io/badge/upstream-FSoft--AI4Code%2FCodeWiki-orange?style=flat-square" /></a>
</p>

<p align="center">
  <a href="#zh"><strong>中文</strong></a> | <a href="#en"><strong>English</strong></a>
</p>

---

<a id="zh"></a>

## 中文

### 这个项目是什么？

CodeWiki-Plus 是 [FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki) 的增强分支，核心改动是**让 CodeWiki 无需配置任何大模型 API，直接由 AI IDE（CodeBuddy、Cursor、Claude Desktop 等）自身的模型驱动 Wiki 文档生成**，并在此基础上构建了完整的知识管理引擎。

### 为什么要做这个改造？

原版 CodeWiki 是一个非常优秀的仓库级文档生成框架，它通过 Tree-sitter AST 解析、依赖图构建、拓扑排序等工具链实现高质量的代码文档生成。但它有一个使用门槛：**必须自行配置 LLM API**（申请 API Key、选择 provider、处理模型兼容性），且整个生成过程是黑盒的，用户无法中途干预。

实际上，CodeWiki 的核心工具链——AST 解析、依赖图、Mermaid 校验——完全不需要 LLM。真正需要 LLM 智能的 4 个环节（模块聚类、文档撰写、子模块递归、总览合成），恰好是 AI IDE 的 Agent 最擅长做的事情。

因此，我们将 CodeWiki 的 MCP Server 从"黑盒式一键生成"拆分为**26 个细粒度工具**，让它退化为纯工具链服务器。AI IDE 的 Agent 通过 MCP 协议调用这些工具，用自己的推理能力完成全部文档生成工作：

```
改造前：
  IDE → generate_docs(repo) → [CodeWiki 内部调用 LLM API] → 结果

改造后：
  IDE Agent → analyze_repo → read_code → (Agent 自己推理) → write_doc → overview
              ↑ 纯工具       ↑ 纯工具    ↑ IDE 自身模型      ↑ 纯工具
```

### 相比原版 CodeWiki 的增强

| 能力维度 | 原版 CodeWiki | CodeWiki-Plus |
|----------|--------------|---------------|
| LLM 配置 | 必须自行配置 API Key | 零配置，IDE 自身模型驱动 |
| 生成模式 | 黑盒一键生成 | 26 个细粒度工具，Agent 全程可控 |
| 文档质量 | 通用描述 | Evidence-Based 断言（代码引用 + 置信度） |
| 生成效率 | 所有组件同等处理 | 代码路由分类，boilerplate 仅保留签名 |
| 上下文精度 | 模块内组件 | BFS 1-hop 调用图扩展 + 约束索引表 |
| 增量更新 | 文件级 Git diff | 方法级 content_hash 精确检测 |
| 知识管理 | 无 | 结构化 Wiki + 笔记飞轮 + 外部文档管理 |
| 搜索能力 | 无 | BM25 + wikilink 图谱多跳 + 渐进式阅读 |
| 跨服务分析 | 无 | Monorepo 子服务检测 + 跨服务调用追踪 |
| 质量保障 | 无 | 11 项 lint 检查 + health score + 问题追踪 |

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

> **开发者选项**：如需从源码安装（获取最新未发布改动）：
> ```bash
> git clone https://github.com/mambo-wang/CodeWiki-Plus.git
> cd CodeWiki-Plus
> pip install -e .
> ```

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

配置完成后，CodeBuddy 的 MCP 工具列表中应出现 `codewiki` 相关的 26 个工具。

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

所有工具均不需要 LLM 配置，由 IDE Agent 通过 MCP 协议调用。MCP Server 内置 **instructions**（能力概览与工作流指南）、**12 个工作流 Prompt**（覆盖初始化、生成、增量、搜索、质检、跨服务等全流程）和 **6 个 Resource**（wiki-catalog / module-tree / index-status 等）。

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

**知识管理（7 个）：**

| 工具 | 用途 |
|------|------|
| `query_wiki` | BM25 全文搜索 + wikilink 图谱多跳扩展 + **渐进式阅读**（mode=overview/directory/detail）；返回 source_type 标注 |
| `ingest_note` | 将开发笔记归档到 notes/，支持 8 种类型 + aliases + source_ref；默认写入为 candidate 状态 |
| `confirm_note` | 将 candidate 笔记升级为 confirmed（正式领域知识） |
| `reject_note` | 否决 candidate 笔记，后续 query_wiki 不再返回 |
| `ingest_source` | 导入第三方文档到 `raw/sources/`，注册到 `source_registry.json` |
| `retract_source` | 撤回已导入的外部文档（flag_stale / remove_refs 两种模式） |
| `batch_ingest` | 批量导入：一次调用处理多个笔记/文档 |

**质量保障（2 个）：**

| 工具 | 用途 |
|------|------|
| `lint_wiki` | 文档-代码一致性检查：**11 项检查**（含 unsupported_claims 无证据断言检测） |
| `flag_issue` | 标记 Wiki 质量问题，驱动 health score 计算 |

**跨服务分析（1 个）：**

| 工具 | 用途 |
|------|------|
| `query_cross_service` | 查询跨服务调用关系（HTTP + MQ），支持 by_service / by_method / by_path / trace 过滤 |

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
// 导入外部文档
{ "name": "rfc-7519-jwt", "source_type": "rfc", "source_path": "/path/to/rfc7519.txt",
  "description": "JWT 规范", "related_pages": ["auth-module"] }

// 撤回外部文档（两种模式）
{ "source_name": "rfc-7519-jwt", "mode": "flag_stale" }    // 标记过期，保留文件
{ "source_name": "rfc-7519-jwt", "mode": "remove_refs" }   // 删除文件，清理所有引用
```

#### 文档健康检查

`lint_wiki` 提供 **16 项检查**，覆盖结构完整性和内容质量：

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
| `okf_conformance` | OKF v0.2 合规审计：缺失 type/frontmatter、旧版状态词、verified 格式错误、stale_after 过期、缺 okf_version |

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

MCP Server 内置 **12 个工作流 Prompt**，在 AI IDE 中通过 Prompt 面板直接触发，Agent 自动编排多工具调用：

| Prompt 名称 | 面向场景 | 核心步骤 |
|-------------|----------|----------|
| `init-wiki` | 新项目初始化 Wiki 工作区 | init_wiki 创建目录 + schema.yaml → 自定义 purpose → 验证 AGENTS.md |
| `generate-wiki` | 完整文档生成流水线 | analyze_repo → 聚类 save_module_tree → 逐模块 write_doc → overview → lint → close_session |
| `code-analysis` | 仅分析代码结构，不生成文档 | analyze_repo → list_components → list_dependencies → 缓存到 SQLite |
| `incremental-update` | 代码变更后增量更新文档 | analyze_repo（增量检测）→ 识别 stale 组件 → 选择性重生成 → close_session |
| `workspace-analysis` | 多仓库工作区分析 | analyze_workspace → 逐仓库生成 Wiki → RouteNode 跨服务匹配 → Mermaid 拓扑图 |
| `cross-service-trace` | 跨服务调用链追踪 | query_cross_service → RouteNode 静态匹配 → trace_path 多跳语义追踪 → 架构诊断 |
| `impact-review` | 修改影响范围评估 | analyze_impact（BFS 传递性遍历）→ 模块级聚合 → 高风险组件识别 → 调用链路输出 |
| `architecture-review` | 架构审查与热点分析 | 依赖图分析 → 核心层/服务层/应用层识别 → Top 5 热点 → 耦合风险 → 入口点 |
| `extract-knowledge` | 外部文档知识提取 | ingest_source 导入 → extraction_scan 候选提取 → 实体/概念页面生成 → wikilink 图谱 |
| `search-wiki` | 知识库搜索策略指引 | query_wiki（BM25）→ 图谱多跳扩展 → 渐进式阅读（overview → directory → detail） |
| `quality-check` | Wiki 质量全面检查 | lint_wiki（11 项检查）→ health_score → flag_issue 标记 → 修复建议 |
| `ingest-note` | 经验知识归档 | ingest_note（8 种类型）→ candidate 状态 → confirm/reject 流转 → BM25 索引 |

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

Agent 调用 `lint_wiki`，返回 11 项诊断报告和 health_score。

**场景 8：跨服务调用分析**

```
分析这个 monorepo 里各服务之间的调用关系。
```

Agent 调用 `analyze_repo`（自动检测子服务）→ `query_cross_service(filter_type="all")`。

### 支持的其他 AI IDE

除 CodeBuddy 外，任何支持 MCP stdio 协议的 AI IDE 均可使用：

**Cursor**：在 Settings → MCP 中添加相同的 Server 配置。

**Claude Desktop**：在 `~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）中添加 MCP 配置。

**其他 IDE**：指定 `command: "codewiki"`, `args: ["mcp"]` 即可。

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

本项目的核心工具链（Tree-sitter AST 解析、依赖图构建、拓扑排序、Mermaid 校验）全部来自 [FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki) 上游项目。以下开源项目的设计思路对我们产生了重要影响：

- [codebase-memory-mcp](https://github.com/nicobailon/codebase-memory-mcp) — SQLite 持久化缓存架构、跨会话复用、三层降级模式
- [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki) — 结构化知识层设计、页面类型路由、交叉链接
- [Tencent/WeKnora](https://github.com/Tencent/WeKnora) — 外部文档管理、文档健康检查、自适应分块思路
- [CodingHub](https://github.com/mambo-wang/CodingHub) — MCP Server 最佳实践（instructions / prompts / resources）

我们在上游基础上将 MCP Server 从黑盒模式拆分为 **26 个细粒度工具**，并新增结构化 Wiki、Evidence-Based 断言、代码路由分类、知识飞轮、渐进式阅读、方法级增量检测、monorepo 跨服务分析等能力。

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

CodeWiki-Plus is an enhanced fork of [FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki) that enables **zero-LLM-config Wiki generation** driven entirely by AI IDEs (CodeBuddy, Cursor, Claude Desktop, etc.) via MCP (Model Context Protocol), plus a full knowledge management engine.

### Why this fork?

The original CodeWiki is an excellent repository-level documentation framework. However, it requires users to configure their own LLM API (API key, provider, model selection), and the generation pipeline runs as a black box with no user intervention.

In practice, CodeWiki's core toolchain—Tree-sitter AST parsing, dependency graph construction, topological sorting, and Mermaid validation—does not need an LLM at all. The 4 stages that do require LLM intelligence (module clustering, document writing, sub-module recursion, and overview synthesis) are exactly what AI IDE Agents excel at.

We refactored CodeWiki's MCP Server from a "one-click black box" into **26 fine-grained tools**, turning it into a pure toolchain server. The AI IDE's Agent calls these tools via MCP and uses its own reasoning to complete all documentation work:

```
Before:
  IDE → generate_docs(repo) → [CodeWiki calls LLM API internally] → result

After:
  IDE Agent → analyze_repo → read_code → (Agent reasons) → write_doc → overview
              ↑ pure tool     ↑ pure tool  ↑ IDE's own model ↑ pure tool
```

### Enhancements over upstream CodeWiki

| Dimension | Upstream CodeWiki | CodeWiki-Plus |
|-----------|------------------|---------------|
| LLM config | Must configure API key | Zero-config, IDE model driven |
| Generation mode | Black-box one-click | 26 fine-grained tools, full Agent control |
| Doc quality | Generic descriptions | Evidence-Based assertions (code quotes + confidence) |
| Generation efficiency | All components equal | Code routing: boilerplate gets signature-only |
| Context precision | Intra-module components | BFS 1-hop call graph + constraint index table |
| Incremental update | File-level Git diff | Method-level content_hash detection |
| Knowledge management | None | Structured Wiki + note flywheel + external docs |
| Search | None | BM25 + wikilink graph multi-hop + progressive reading |
| Cross-service | None | Monorepo sub-service detection + call tracing |
| Quality assurance | None | 11 lint checks + health score + issue tracking |

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

> **For developers** (latest unreleased changes):
> ```bash
> git clone https://github.com/mambo-wang/CodeWiki-Plus.git
> cd CodeWiki-Plus
> pip install -e .
> ```

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

All tools require zero LLM config. The IDE Agent invokes them via MCP. The server includes built-in **instructions**, **12 Workflow Prompts** (covering init, generation, incremental update, search, quality check, cross-service analysis), and **6 Resources**.

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
| `get_prompt` | Retrieve prompt templates (16 prompt_types) |
| `close_session` | Close session, build BM25 index + wikilink graph, write metadata |

**Knowledge Management (7):**

| Tool | Purpose |
|------|---------|
| `query_wiki` | BM25 search + wikilink graph multi-hop + **progressive reading** (mode=overview/directory/detail); source_type annotation |
| `ingest_note` | File structured notes (8 types) with aliases + source_ref; default candidate status |
| `confirm_note` | Promote candidate note to confirmed knowledge |
| `reject_note` | Reject candidate note, exclude from future searches |
| `ingest_source` | Import third-party docs into `raw/sources/` |
| `retract_source` | Retract imported docs (flag_stale / remove_refs) |
| `batch_ingest` | Batch import multiple notes/sources in one call |

**Quality Assurance (2):**

| Tool | Purpose |
|------|---------|
| `lint_wiki` | Doc-code consistency: **11 checks** (incl. unsupported_claims evidence detection) |
| `flag_issue` | Flag quality issues, drives health score |

**Cross-Service Analysis (1):**

| Tool | Purpose |
|------|---------|
| `query_cross_service` | Query cross-service calls (HTTP + MQ), filter by service/method/path/trace |

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

### Progressive Reading Protocol

`query_wiki` supports three consumption modes:

| mode | Returns | Use case |
|------|---------|----------|
| `overview` | Repo-level summary (< 500 tokens) | First contact with project |
| `directory` | By-type page directory (< 800 tokens) | Locate target module/entity |
| `detail` | Full page content | Deep reading |
| default | BM25 snippet results | Keyword search |

### Workflow Prompts

The MCP server includes **12 built-in workflow prompts** that can be triggered from the AI IDE's prompt panel. The Agent automatically orchestrates multi-tool calls:

| Prompt | Scenario | Core Steps |
|--------|----------|------------|
| `init-wiki` | Initialize Wiki workspace for a new project | init_wiki (dirs + schema.yaml) → customize purpose → verify AGENTS.md |
| `generate-wiki` | Full documentation generation pipeline | analyze_repo → cluster → per-module write_doc → overview → lint → close_session |
| `code-analysis` | Analyze code structure only (no docs) | analyze_repo → list_components → list_dependencies → cache to SQLite |
| `incremental-update` | Update docs after code changes | analyze_repo (incremental) → detect stale → selective regeneration → close_session |
| `workspace-analysis` | Multi-repo workspace analysis | analyze_workspace → per-repo Wiki → RouteNode cross-service matching → Mermaid topology |
| `cross-service-trace` | Cross-service call chain tracing | query_cross_service → RouteNode matching → trace_path multi-hop → architecture diagnosis |
| `impact-review` | Change impact assessment | analyze_impact (BFS transitive) → module aggregation → high-risk identification → call paths |
| `architecture-review` | Architecture review & hotspot analysis | Dependency graph → layer identification → Top 5 hotspots → coupling risks → entry points |
| `extract-knowledge` | External document knowledge extraction | ingest_source → extraction_scan → entity/concept pages → wikilink graph |
| `search-wiki` | Knowledge base search strategy | query_wiki (BM25) → graph multi-hop expansion → progressive reading |
| `quality-check` | Comprehensive Wiki quality check | lint_wiki (11 checks) → health_score → flag_issue → fix suggestions |
| `ingest-note` | Experience knowledge archiving | ingest_note (8 types) → candidate status → confirm/reject → BM25 index |

### Supported Languages

Python, Java, JavaScript, TypeScript, C, C++, C#, Kotlin, Go, PHP

### Acknowledgements

The core toolchain (Tree-sitter AST parsing, dependency graph, topological sort, Mermaid validation) comes from [FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki). Influenced by:

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
