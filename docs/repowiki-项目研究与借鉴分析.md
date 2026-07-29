# RepoWiki 项目研究与借鉴分析

> 研究日期：2026-07-29
> 研究对象：
> - **RepoWiki**（`D:\repos\RepoWiki`，GitHub: he-yufeng/RepoWiki，v0.2.1）：开源 DeepWiki 替代品，Python CLI + Web UI，为任意代码库生成 wiki 文档
> - **CodeWiki-CN**（`D:\repos\CodeWiki-CN`）：Python MCP 服务器，tree-sitter 解析 + LLM 文档生成 + 知识库管理
>
> 资料来源：RepoWiki 完整源码（`git clone --depth 1`），所有结论均标注源码文件路径。

---

## 一、执行摘要（TL;DR）

| 维度 | RepoWiki | CodeWiki-CN |
|------|----------|-------------|
| 定位 | 面向人类阅读的 wiki 生成器（DeepWiki 替代） | 面向 AI Agent 的 MCP 文档工具服务器 |
| 交付形态 | CLI + Web UI + 自包含 HTML | MCP server（25 工具）+ CLI |
| 代码解析 | 正则 import 解析（6 语言）+ 文件级元数据 | tree-sitter AST（11 语言）+ 函数/类级组件 |
| 模块分组 | 按顶层目录硬分组 | LLM 提示词驱动聚类 / Leiden（via CBM） |
| 文档生成 | 4 步 LLM 管线（概览→模块→架构→阅读指南） | 多轮 LLM（模块树→子模块文档→overview） |
| 排名/导航 | PageRank + 阅读路径 | 无（依赖 Agent 自行导航） |
| 搜索/问答 | TF-IDF 检索 + 终端 chat | BM25 + jieba + hop 扩展 |
| 增量更新 | 内容 hash 缓存（跳过未变更） | Git diff + 文件指纹 + SQLite 增量 |
| 输出格式 | Markdown / JSON / 自包含 HTML | Markdown wiki/ + notes/ |
| 依赖 | Python + SQLite（零外部服务） | Python + SQLite + 可选 CBM/CodeGraph |
| 代码量 | ~2500 行 Python + ~800 行 TS 前端 | ~15000+ 行 Python |

**核心结论**：

1. RepoWiki 是一个**轻量、完整、面向终端用户**的 wiki 生成器，代码量小（~2500 行），架构简洁，5 分钟可读完全部源码。
2. 其**PageRank 阅读路径**、**自包含 HTML 导出**、**终端 chat 问答**是 CodeWiki-CN 目前缺失的面向人类体验的特性。
3. 代码解析能力远弱于 CodeWiki-CN（正则 vs tree-sitter，文件级 vs 函数级），模块分组是硬编码目录分组而非智能聚类。
4. 增量更新只有内容 hash 缓存，**没有真正的增量重生成**（README 明确列为 Roadmap 未实现）。
5. 最值得借鉴的是**产品体验层**的设计（阅读指南、多格式导出、敏感文件过滤），而非核心分析能力。

---

## 二、项目概览

### 2.1 基本信息

- **作者**：Yufeng He（he-yufeng）
- **版本**：0.2.1（PyPI 已发布）
- **许可**：MIT
- **Python**：>=3.10
- **核心依赖**：click, rich, litellm, pydantic, aiosqlite, networkx, numpy
- **可选依赖**：fastapi + uvicorn（Web）、pytest + ruff（dev）

（来源：`pyproject.toml` 第 32-53 行）

### 2.2 项目定位

README_CN.md 第 14 行：

> "开源 DeepWiki 替代品 — 从终端或浏览器为任意代码仓库生成完整 wiki 文档。"

与 DeepWiki/deepwiki-open 的对比表（README_CN.md 第 18-28 行）突出：
- `pip install` 即用（无 Docker）
- 原生支持本地仓库
- CLI 优先
- 多格式导出（Markdown / JSON / HTML）
- PageRank 阅读指南
- 终端问答

### 2.3 目录结构

```
RepoWiki/
├── src/repowiki/
│   ├── cli.py              # Click CLI（scan/serve/chat/config）
│   ├── config.py           # 配置管理（4 层优先级）
│   ├── core/
│   │   ├── scanner.py      # 文件扫描 + 语言识别（348 行）
│   │   ├── analyzer.py     # 4 步 LLM 分析管线（300 行）
│   │   ├── graph.py        # 依赖图 + PageRank（280 行）
│   │   ├── wiki_builder.py # Wiki 页面组装（255 行）
│   │   ├── rag.py          # TF-IDF 检索（152 行）
│   │   ├── cache.py        # SQLite 缓存（97 行）
│   │   └── models.py       # Pydantic 数据模型（122 行）
│   ├── llm/
│   │   ├── client.py       # litellm 异步封装（96 行）
│   │   └── prompts.py      # 结构化 prompt 模板（225 行）
│   ├── ingest/
│   │   ├── local.py        # 本地目录导入（61 行）
│   │   └── github.py       # git clone 缓存（102 行）
│   ├── export/
│   │   ├── markdown.py     # Markdown 目录导出（54 行）
│   │   ├── json_export.py  # JSON 导出（42 行）
│   │   └── html.py         # 自包含 HTML（203 行）
│   └── server/             # FastAPI web 后端
│       ├── app.py          # 应用工厂
│       ├── models.py       # 请求/响应模型
│       └── routers/        # scan/wiki/chat 路由
├── frontend/               # React + Vite + TailwindCSS + Zustand
└── tests/                  # 7 个测试文件
```

---

## 三、架构分析

### 3.1 数据流

完整管线（`cli.py` 第 117-182 行 `_run_analysis()`）：

```
用户输入（路径/URL）
    │
    ▼
[ingest] ─── local.py / github.py
    │         扫描目录 → FileInfo[] → ProjectContext
    ▼
[scan] ──── scanner.py
    │        过滤二进制/敏感/minified 文件
    │        语言检测（30+ 扩展名映射）
    │        识别 config/entrypoint 文件
    ▼
[graph] ─── graph.py
    │        正则解析 import（6 语言）
    │        构建 networkx DiGraph
    │        PageRank 排名
    ▼
[analyze] ── analyzer.py（4 步 LLM）
    │        1. overview（项目概览）
    │        2. modules（逐模块文档，并发）
    │        3. architecture（架构图 + Mermaid）
    │        4. reading_guide（阅读指南）
    ▼
[build] ─── wiki_builder.py
    │        组装 WikiPage[] + Sidebar
    ▼
[export] ── markdown.py / json_export.py / html.py
             输出到 ./wiki/ 目录
```

### 3.2 核心设计决策

| 决策 | 实现 | 来源 |
|------|------|------|
| 文件级分析（非函数级） | scanner.py 只收集文件元数据 + 前 80 行预览 | `scanner.py` 第 249 行 `preview_lines=80` |
| 正则 import 解析（非 AST） | 6 组正则匹配 import 语句 | `graph.py` 第 14-37 行 `_IMPORT_PATTERNS` |
| 目录分组（非智能聚类） | 按第一级目录名分组，src/lib/pkg 等穿透到第二级 | `analyzer.py` 第 130-147 行 `_group_into_modules()` |
| 内容 hash 缓存 | SHA256 前 24 字符作 key，7 天 TTL | `cache.py` 第 17-19 行 |
| litellm 统一 LLM 接口 | 支持 100+ 提供商，别名映射 | `config.py` 第 18-30 行 `MODEL_ALIASES` |
| 并发控制 | asyncio.Semaphore(5) 限制模块分析并发 | `analyzer.py` 第 45 行 |
| 自包含 PageRank | 手写幂迭代，避免 scipy 依赖 | `graph.py` 第 165-198 行 |

### 3.3 配置系统

4 层优先级（`config.py` 第 48-78 行）：
1. CLI 参数（`-m`, `-l`, `-o`）
2. 环境变量（`REPOWIKI_MODEL`, `REPOWIKI_API_KEY`）
3. 配置文件（`~/.repowiki/config.json`）
4. 提供商专用环境变量（`DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`）

模型别名（`config.py` 第 18-30 行）：deepseek, opus, claude, gpt, gpt-mini, gemini, gemini-flash, qwen, kimi, glm, minimax。

---

## 四、核心特性详解

### 4.1 文件扫描与过滤（scanner.py）

**亮点**：
- **敏感文件过滤**（第 37-48 行）：`.env`, `.npmrc`, `.pypirc`, SSH 私钥等默认跳过
- **Minified 检测**（第 186-196 行）：检测单行超长 + 非空行极少 → 跳过，避免浪费 LLM token
- **Config/Entrypoint 识别**（第 102-124 行）：`pyproject.toml`, `package.json`, `main.py`, `App.tsx` 等自动标记，全文送入 LLM
- **`.repowikiignore` 支持**（第 136-176 行）：兼容 `.gitignore` 语法 + 取反规则

**局限**：
- 无 tree-sitter，不做 AST 解析
- 文件上限 1000 个（`max_files=1000`），大仓库会截断
- 预览只取前 80 行（config/entrypoint 除外）

### 4.2 依赖图与 PageRank（graph.py）

**实现**：
- 6 语言正则 import 解析：Python（含相对导入 `..module`）、JS/TS（含 `require()`）、Go、Rust、Java
- Python 相对导入解析（第 268-279 行）：计算前导点数量，回溯源文件目录
- JS/TS 相对模块解析（第 232-243 行）：尝试 `.ts/.tsx/.js/.jsx/index.*` 等后缀
- PageRank 手写幂迭代（第 165-198 行）：alpha=0.85，max_iter=100，tol=1e-6
- 附加分析：入口点检测（in_degree<=1 且 out_degree>0）、孤立文件（dead code）、循环依赖（SCC）

**局限**：
- 正则无法处理动态 import、条件 import、re-export
- Go 解析非常粗糙（只取包路径最后两段）
- 无函数级调用图

### 4.3 LLM 分析管线（analyzer.py + prompts.py）

**4 步分析**：

| 步骤 | Prompt 角色 | 输出结构 | 缓存 key |
|------|------------|---------|----------|
| overview | "senior engineer explaining to new team member" | name, one_liner, description, tech_stack, setup_instructions, key_features | `overview:{tree_hash}` |
| modules | "senior engineer documenting own code" | name, purpose, description, files[{path, purpose, key_symbols}], relationships, key_concepts | `module:{name}:{content_hash}` |
| architecture | "software architect analyzing codebase" | architecture_type, description, components, mermaid_component, mermaid_sequence, data_flow | `arch:{tree_hash}` |
| reading_guide | "mentor helping developer understand codebase" | introduction, steps[{order, title, files, explanation, time_estimate}], tips | `guide:{tree_hash}:{rankings_hash}` |

**Prompt 设计特点**（`prompts.py`）：
- 明确禁止 filler 用语（第 33 行）："Do NOT use filler phrases like 'leveraging', 'utilizing', 'cutting-edge', 'robust', or 'comprehensive'"
- 强制 JSON 输出（第 19-23 行）："Output ONLY valid JSON. No markdown fences, no explanation text"
- 多语言支持（第 9-16 行）：en/zh/ja/ko 四种语言指令
- JSON 提取容错（第 199-224 行）：处理 markdown fence 包裹、前后多余文本

**并发**：模块分析通过 `asyncio.as_completed()` 并发执行，Semaphore(5) 限流。

### 4.4 阅读指南（Reading Guide）

这是 RepoWiki 的**独特卖点**：

1. 先用 PageRank 对文件排名（取 top 20）
2. 将排名 + 模块摘要送入 LLM
3. LLM 生成 5-10 步阅读路径，每步包含：要读哪些文件、看什么、为什么、预估时间

（来源：`analyzer.py` 第 242-300 行，`prompts.py` 第 137-170 行）

### 4.5 TF-IDF 问答（rag.py + cli.py chat 命令）

- 文件按空行边界分块（max 30 行/块）
- 纯 TF-IDF + 余弦相似度，无 embedding 服务
- 终端交互：`repowiki chat .` → 索引 → 循环问答
- Web 版：SSE 流式返回 + 引用来源（文件路径 + 行号）

（来源：`rag.py` 全文，`cli.py` 第 236-308 行，`server/routers/chat.py`）

### 4.6 自包含 HTML 导出（export/html.py）

- 单文件 HTML，内嵌 CSS + JS
- Mermaid 图表通过 CDN 加载 mermaid@11 渲染
- 侧边栏导航 + 页面切换（纯 JS，无框架）
- 自带简易 Markdown→HTML 转换器（无外部依赖）

（来源：`export/html.py` 全文，203 行）

### 4.7 Web UI（frontend/ + server/）

- **后端**：FastAPI，3 个路由组（scan/wiki/chat），SSE 进度推送
- **前端**：React + Vite + TailwindCSS + Zustand
- **状态管理**：Zustand + sessionStorage 持久化（projectId + settings）
- **功能**：扫描进度实时显示、wiki 三栏浏览、Mermaid 图表渲染、流式 chat

### 4.8 缓存机制（cache.py）

- SQLite 异步（aiosqlite）
- 两张表：`cache`（key-value + TTL）和 `projects`（项目级数据）
- 缓存 key = 分析类型 + 内容 hash（SHA256 前 24 字符）
- TTL = 7 天
- 全局缓存目录：`~/.repowiki/cache.db`

**注意**：这不是真正的增量更新。它只是"如果输入没变就跳过 LLM 调用"，但**不会只重生成变更的页面**。README 明确将"增量重生成"列为 Roadmap（README_CN.md 第 149 行）。

---

## 五、与 CodeWiki-CN 对比

### 5.1 代码解析深度

| 能力 | RepoWiki | CodeWiki-CN |
|------|----------|-------------|
| 解析器 | 正则表达式 | tree-sitter AST |
| 粒度 | 文件级 | 函数/类/方法级（Node 组件） |
| 语言数 | 6（import 解析）/ 30+（语言检测） | 11（完整 AST 解析） |
| 调用图 | 无 | 有（call_graph_analyzer.py） |
| 路由提取 | 无 | 5 个提取器（py/js/go/java + MQ） |
| 跨服务 | 无 | RouteNode + path_canonicalizer + 匹配 |
| 复杂度 | 无 | TS analyzer 有占位 |

**结论**：RepoWiki 的解析能力远弱于 CodeWiki-CN，不在同一量级。

### 5.2 模块分组策略

| | RepoWiki | CodeWiki-CN |
|---|----------|-------------|
| 方法 | 按顶层目录名硬分组 | LLM 提示词聚类 / Leiden（CBM） |
| 穿透规则 | src/lib/pkg/internal/app → 取第二级 | 无硬编码，由 LLM/算法决定 |
| 来源 | `analyzer.py` 第 130-147 行 | `cluster_modules.py` |

**评价**：RepoWiki 的方法简单但对非标准项目结构（如 monorepo、扁平结构）效果差。CodeWiki-CN 的 LLM 聚类更灵活但消耗 token。

### 5.3 搜索/查询

| | RepoWiki | CodeWiki-CN |
|---|----------|-------------|
| 算法 | TF-IDF + 余弦相似度 | BM25 + jieba 分词 + hop 扩展 |
| 索引对象 | 源码文件（分块） | wiki 文档 + notes |
| 中文支持 | 无（正则 `[a-zA-Z_]\w*`） | jieba 分词 |
| 交互方式 | 终端 chat / Web SSE | MCP 工具调用 |
| 存储 | 内存（每次重建） | SQLite 持久化 |

### 5.4 增量更新

| | RepoWiki | CodeWiki-CN |
|---|----------|-------------|
| 机制 | 内容 hash → 跳过未变更的 LLM 调用 | Git diff + 文件指纹 → 只重解析变更文件 |
| 粒度 | 整个分析步骤（overview/module/arch/guide） | 文件级组件 |
| 真正增量 | **否**（Roadmap 未实现） | **是**（`analysis.py` 第 78-99 行） |
| 缓存位置 | `~/.repowiki/cache.db`（全局） | `.codewiki/analysis_cache.db`（项目级） |

### 5.5 输出与交付

| | RepoWiki | CodeWiki-CN |
|---|----------|-------------|
| 格式 | Markdown 目录 / JSON / 自包含 HTML | Markdown wiki/ + notes/ |
| 导航 | _sidebar.md + README.md + HTML 侧边栏 | index.md + schema.yaml |
| 图表 | Mermaid（组件图 + 序列图 + 依赖图） | Mermaid（架构图） |
| Web 查看 | 内置三栏 Web UI | 无（依赖 IDE/Agent） |
| 阅读指南 | PageRank 排名 + LLM 生成路径 | 无 |

### 5.6 产品体验

| | RepoWiki | CodeWiki-CN |
|---|----------|-------------|
| 安装 | `pip install repowiki` | `pip install -e .`（开发模式） |
| 上手 | `repowiki scan .` 一条命令 | 需配置 MCP server + IDE |
| 目标用户 | 开发者（人类） | AI Agent |
| 进度反馈 | Rich spinner + 步骤描述 | MCP 工具返回 |
| 错误处理 | 优雅降级（LLM 失败返回默认值） | 错误 JSON |
| 敏感文件 | 默认过滤 .env/SSH key 等 | 无明确过滤 |

---

## 六、可借鉴点（按优先级排序）

### P0：高价值 + 低难度

#### 6.1 敏感文件过滤

**现状**：CodeWiki-CN 的 scanner 没有明确过滤 `.env`、SSH 私钥等敏感文件。
**RepoWiki 实现**：`scanner.py` 第 37-48 行 `_SENSITIVE_NAMES` 集合 + 第 179-183 行 `_is_sensitive_name()` 函数。
**借鉴方案**：在 CodeWiki-CN 的文件扫描阶段加入相同的敏感文件黑名单。
**实现难度**：极低（~20 行代码）
**来源**：`D:\repos\RepoWiki\src\repowiki\core\scanner.py` 第 37-48, 179-183 行

#### 6.2 Minified/生成文件检测

**现状**：CodeWiki-CN 依赖 exclude_patterns 手动排除。
**RepoWiki 实现**：`scanner.py` 第 186-196 行 `_looks_minified_source()`——检测单行超长（>1000 字符）+ 非空行极少（<=5）或最长行占总长度 50% 以上。
**借鉴方案**：在 tree-sitter 解析前自动跳过 minified 文件，避免浪费解析时间和 LLM token。
**实现难度**：极低（~15 行代码）
**来源**：`D:\repos\RepoWiki\src\repowiki\core\scanner.py` 第 186-196 行

#### 6.3 Prompt 中禁止 filler 用语

**现状**：CodeWiki-CN 的 prompt 没有明确约束输出风格。
**RepoWiki 实现**：`prompts.py` 第 33 行："Do NOT use filler phrases like 'leveraging', 'utilizing', 'cutting-edge', 'robust', or 'comprehensive'. Just describe what things do."
**借鉴方案**：在 CodeWiki-CN 的文档生成 prompt 中加入类似约束，减少 LLM 输出的"废话"。
**实现难度**：极低（修改 prompt 模板）
**来源**：`D:\repos\RepoWiki\src\repowiki\llm\prompts.py` 第 30-35 行

### P1：高价值 + 中难度

#### 6.4 PageRank 阅读指南

**现状**：CodeWiki-CN 生成的 wiki 没有"从哪里开始读"的引导。
**RepoWiki 实现**：
1. 构建 import 依赖图 → PageRank 排名（`graph.py`）
2. 将 top-20 文件排名 + 模块摘要送入 LLM（`analyzer.py` 第 242-300 行）
3. LLM 生成 5-10 步阅读路径，含时间估算

**借鉴方案**：CodeWiki-CN 已有依赖图（`dependency_graphs_builder.py`），可以：
1. 在现有依赖图上跑 PageRank（networkx 已是依赖）
2. 在 overview.md 或单独的 reading-guide.md 中生成阅读路径
3. 利用已有的组件级调用图（比 RepoWiki 的文件级更精确）

**实现难度**：中（需要新增一个生成步骤 + prompt 设计）
**来源**：`D:\repos\RepoWiki\src\repowiki\core\graph.py` 第 77-90 行，`analyzer.py` 第 242-300 行

#### 6.5 自包含 HTML 导出

**现状**：CodeWiki-CN 输出 Markdown 目录，需要外部工具（docsify/mkdocs）才能浏览。
**RepoWiki 实现**：`export/html.py`（203 行）生成单文件 HTML，内嵌 CSS + Mermaid CDN + 侧边栏导航。
**借鉴方案**：为 CodeWiki-CN 的 `repowiki/` 输出增加一个 `--format html` 选项，生成可直接分享的单文件。
**实现难度**：中（可参考 RepoWiki 的模板，适配 CodeWiki-CN 的页面结构）
**来源**：`D:\repos\RepoWiki\src\repowiki\export\html.py` 全文

#### 6.6 循环依赖 + 孤立文件检测

**现状**：CodeWiki-CN 的 `wiki_lint.py` 有循环依赖检查，但没有"孤立文件/dead code"检测。
**RepoWiki 实现**：
- `graph.py` 第 135-148 行 `find_isolated_files()`：in_degree=0 且 out_degree=0 的文件
- `graph.py` 第 150-162 行 `find_circular_dependencies()`：SCC > 1 的组件
- `wiki_builder.py` 第 228-253 行：在 Dependencies 页面展示这两类问题

**借鉴方案**：在 CodeWiki-CN 的 `lint_wiki` 工具中增加"孤立组件"检查（无任何依赖关系的组件可能是 dead code）。
**实现难度**：中（需要在依赖图上增加分析逻辑）
**来源**：`D:\repos\RepoWiki\src\repowiki\core\graph.py` 第 135-162 行

#### 6.7 多格式导出（JSON）

**现状**：CodeWiki-CN 只输出 Markdown。
**RepoWiki 实现**：`export/json_export.py`（42 行）输出结构化 JSON，方便程序化消费。
**借鉴方案**：为 CodeWiki-CN 增加 JSON 导出，方便其他工具链（如静态站点生成器）消费 wiki 数据。
**实现难度**：低-中
**来源**：`D:\repos\RepoWiki\src\repowiki\export\json_export.py` 全文

### P2：中价值 + 中-高难度

#### 6.8 终端 Chat 问答

**现状**：CodeWiki-CN 的搜索是 MCP 工具调用（面向 Agent），没有面向人类的交互问答。
**RepoWiki 实现**：`cli.py` 第 236-308 行 `chat` 命令——TF-IDF 索引 + LLM 问答循环。
**借鉴方案**：为 CodeWiki-CN CLI 增加 `codewiki chat` 子命令，复用已有的 BM25 搜索引擎。
**实现难度**：中（需要 CLI 交互循环 + LLM 调用）
**来源**：`D:\repos\RepoWiki\src\repowiki\cli.py` 第 236-308 行

#### 6.9 入口点自动识别

**现状**：CodeWiki-CN 没有明确的"入口点"标记。
**RepoWiki 实现**：`scanner.py` 第 116-124 行——按文件名（main.py, app.py, index.ts...）和目录名（cmd/, bin/, scripts/）识别入口点，在 LLM 分析时给予更高权重。
**借鉴方案**：在 CodeWiki-CN 的组件元数据中增加 `is_entrypoint` 标记，用于阅读指南和架构分析。
**实现难度**：低-中
**来源**：`D:\repos\RepoWiki\src\repowiki\core\scanner.py` 第 116-124, 209-215 行

#### 6.10 模型别名系统

**现状**：CodeWiki-CN 需要配置完整的 LLM base_url + model name。
**RepoWiki 实现**：`config.py` 第 18-30 行——用户只需输入 "deepseek"/"claude"/"gpt" 等别名，自动映射到完整的 provider/model 字符串。
**借鉴方案**：在 CodeWiki-CN 的配置系统中增加模型别名映射。
**实现难度**：低
**来源**：`D:\repos\RepoWiki\src\repowiki\config.py` 第 18-34 行

### P3：参考价值（不建议直接移植）

#### 6.11 Web UI 三栏浏览器

RepoWiki 的 React 前端（~800 行 TS）提供了完整的 Web 浏览体验。但 CodeWiki-CN 的定位是 MCP 工具服务器（面向 Agent），Web UI 不是核心需求。如果未来需要，可参考其 SSE 进度推送 + Zustand 状态管理模式。

#### 6.12 GitHub URL 直接扫描

`ingest/github.py` 支持直接传入 GitHub URL 进行 shallow clone + 分析。CodeWiki-CN 目前只支持本地路径。但这个功能对 MCP 服务器场景意义不大（Agent 通常已经有本地仓库）。

---

## 七、不适用/不推荐的点

### 7.1 正则 import 解析

RepoWiki 用正则解析 import（`graph.py` 第 14-37 行），这对 CodeWiki-CN 是**降级**。CodeWiki-CN 已有 tree-sitter AST 解析，能提取函数/类/方法级组件和调用关系，正则方案完全不可取。

### 7.2 目录硬分组

RepoWiki 按顶层目录名分组模块（`analyzer.py` 第 130-147 行），这对非标准项目结构效果很差。CodeWiki-CN 的 LLM 聚类（`cluster_modules.py`）或 Leiden 算法（via CBM）远优于此方案。

### 7.3 文件级分析粒度

RepoWiki 只分析到文件级（每个文件一个 purpose + key_symbols），没有函数级文档。CodeWiki-CN 的组件级分析（Node 包含 source_code、start_line、end_line、dependencies）信息密度远高于此。

### 7.4 全局缓存（~/.repowiki/cache.db）

RepoWiki 的缓存是全局的（所有项目共享一个 DB），7 天 TTL 后过期。CodeWiki-CN 的项目级缓存（`.codewiki/analysis_cache.db`）更合理——跟随项目、支持 Git 管理、无 TTL 过期问题。

### 7.5 无 MCP 协议支持

RepoWiki 是面向人类的 CLI/Web 工具，没有 MCP 协议支持。这不是缺陷（定位不同），但意味着它无法直接被 AI Agent 调用。CodeWiki-CN 的 MCP 服务器定位是正确的。

### 7.6 内存中的 RAG 索引

RepoWiki 的 TF-IDF 索引每次 chat 都重建（`rag.py` 的 `index()` 方法），不持久化。对大仓库这会很慢。CodeWiki-CN 的 SQLite 持久化 BM25 索引更优。

---

## 八、RepoWiki 的 Roadmap（未实现，仅参考）

README_CN.md 第 147-153 行列出的后续规划：

1. **增量重生成**：只重生成变更页面（当前未实现，只有 hash 缓存跳过）
2. **交叉引用链接**：模块页之间的符号链接（当前未实现）
3. **更多图表类型**：调用图、数据流图（当前只有依赖图 + LLM 生成的架构图）
4. **静态站点发布**：一键导出 GitHub Pages（当前未实现）

这些方向与 CodeWiki-CN 的 Roadmap 有重叠（增量更新、交叉引用），说明是行业共识。

---

## 九、总结

RepoWiki 是一个**精巧的轻量级 wiki 生成器**，代码质量高、架构清晰、产品体验好。但它的核心分析能力（正则 import、目录分组、文件级粒度）远弱于 CodeWiki-CN。

**对 CodeWiki-CN 最有价值的借鉴不在"分析能力"层面，而在"产品体验"层面**：

1. 阅读指南（PageRank + LLM）——让 wiki 有"入口"
2. 自包含 HTML 导出——让 wiki 可分享
3. 敏感文件/minified 过滤——让分析更干净
4. Prompt 风格约束——让输出更实在
5. 循环依赖/孤立文件可视化——让 wiki 有"诊断"价值

这些都是"最后一公里"的体验优化，实现成本低，用户感知强。
