# 代码图谱能力增强 Backlog（对标 CodeGraph / Grapify / CBM）

> 生成日期：2026-08-24
> 范围：基于与 CodeGraph（suatkocar/codegraph）、Grapify、codebase-memory-mcp（CBM）三款代码知识图谱工具的能力对照审计，识别出 CodeWiki-CN 已有技术底座（Tree-sitter + SQLite + 传递影响分析）上可补齐的 3 项需求 + 2 项可选增强。

## 背景

CodeWiki-CN 已具备与主流代码图谱工具同源的技术底座：

- **AST 解析**：Tree-sitter，10 种语言（Python/Java/TS/JS/Go/C/C++/C#/PHP/Kotlin，`codewiki/src/be/dependency_analyzer/analyzers/`）
- **关系提取**：函数级调用图、跨文件符号解析、框架路由提取（Spring/Express/FastAPI/Go/JS/MQ，`analyzers/route_extractors/`）
- **图算法**：`transitive_impact`（BFS 传递闭包）、`detect_cycles`、`compute_pagerank`、`find_isolated_nodes`（`topo_sort.py`）
- **影响半径**：`analyze_impact` MCP 工具（depended_by/depends_on/both、max_depth、最短调用链、模块级聚合、高风险组件识别）——能力已覆盖 codegraph `impact` 且更细
- **CBM 集成**：`cbm_integration.py` 委托 `trace_path` / `get_architecture` / `detect_changes` / `search_graph`，结果增强 `analyze_impact` / `analyze_repo`

对标审计后确认的差距集中在**工程闭环**与**检索层**，而非图算法本身。

## 目录

1. [P1 · 文件监听实时增量同步（watch 模式）](#1-p1--文件监听实时增量同步watch-模式)
2. [P1 · git diff 驱动的变更影响闭环（affected）](#2-p1--git-diff-驱动的变更影响闭环affected)
3. [P2 · 代码符号全文/语义检索](#3-p2--代码符号全文语义检索)
4. [P3 · 死代码扫描与图谱交互可视化（可选）](#4-p3--死代码扫描与图谱交互可视化可选)

***

## 1. P1 · 文件监听实时增量同步（watch 模式）

### 背景

codegraph `--watch` 用跨平台原生文件监听（inotify/FSEvents/ReadDirectoryChangesW）实现代码改动 2 秒内自动更新图谱；CBM 也支持自动同步。CodeWiki-CN 的 `analyze_repo` 只有**手动触发**的增量更新（基于内容哈希跳过未变更文件），代码改完必须显式重跑，Agent 查询到的图谱可能滞后于磁盘状态。

### 问题描述

- `analyze_repo` 增量模式只在上次分析结果存在时跳过未变更文件，没有"代码一改、图谱即新"的机制
- Agent 修改代码后继续查询 `list_dependencies` / `analyze_impact`，可能基于过期图谱给出错误结论（典型风险：改了一个函数签名，影响半径查询还是旧图）
- 无 watch 模式时，长会话中图谱新鲜度完全依赖 Agent 自觉重跑 analyze_repo

### 建议方案

在 `codewiki/mcp/tools/analysis.py` 之上新增 watch 层：

1. 新增 `codewiki/mcp/tools/watch.py`，用 `watchdog`（或 Python 3.13+ `os.scandir` 轮询兜底）监听仓库文件变更
2. 变更事件（modified/created/deleted）→ 收集变更文件集合 → 复用现有增量管线只 re-parse 变更文件 → 更新 SQLite 缓存
3. 去抖合并：300ms 内的连续事件合并为一次批量更新（避免 IDE 保存时多次触发）
4. 暴露 MCP 工具 `watch_repo`（启动/停止监听，返回当前监听状态），或作为 `analyze_repo(watch=true)` 参数
5. 监听状态写入 session，查询类工具返回时附 `graph_stale: bool` 提示（图谱是否落后于磁盘）

### 验收标准

- [ ] 修改单个文件后 ≤3 秒，`list_dependencies` / `analyze_impact` 结果反映新内容（不需要重跑 analyze_repo）
- [ ] 新增/删除文件被正确拾取（组件增减生效）
- [ ] IDE 连续保存（快速多次写入）只触发一次更新（去抖生效）
- [ ] 监听器异常（文件被外部删除等）不崩溃，自动降级为手动模式并记录日志
- [ ] 新增测试：temp_repo 中模拟文件变更 → 断言缓存被增量更新、未变更文件不被重新解析

### 影响面

- **正面**：图谱新鲜度从"手动保证"变为"自动保证"；Agent 改代码后的影响半径查询天然准确；与 codegraph `--watch` 对齐
- **负面**：新增 watchdog 依赖（可做成 optional dependency）；监听进程生命周期管理（session 关闭时须停止）

### 优先级

**P1** — 影响半径类查询的准确性前提。不做的话，Agent 修改代码后所有图查询都可能基于过期数据。

***

## 2. P1 · git diff 驱动的变更影响闭环（affected）

### 背景

codegraph `affected`（结合 git diff 自动筛选受影响文件/测试）、CBM `detect_changes`（symbol 级风险分级）都提供"改了什么 → 影响谁 → 跑哪些测试"的闭环。CodeWiki-CN 目前只有**委托 CBM** 时才有此能力（`cbm_detect_changes`），纯本地场景缺失；且本地 `transitive_impact` 已具备全部图遍历能力，缺的只是 git 入口和测试映射。

### 用户场景（2026-08-24 需求细化）

目标 2：**修改代码后，根据 commit 提交内容或当前未提交变更分析影响范围**。

- 输入形态一：已提交 commit 范围（如 `HEAD~1..HEAD` 或任意两个 commit 之间）
- 输入形态二：**工作区未提交变更**（已暂存 `git diff --cached` + 未暂存 `git diff` + untracked 文件）
- 输出粒度要求：**函数级**（改了一个函数，列出受影响的上下游函数），而非文件级

### 问题描述

- 本地无"git diff → 变更组件 → 传递影响 → 建议回归测试"的原生工具
- CBM 未安装时，用户只能手动把变更文件路径填进 `analyze_impact(file_paths=...)`，且无法自动关联测试
- 现有 `prompts.py::impact_review` 已描述风险分级流程，但没有 git 差异输入
- **关键精度缺口**：变更分析若止步于文件级，会把文件内未改动的函数也误报为变更起点；必须**行级 diff → 函数定位**

### 建议方案

拆分为两个子项（② 行级 diff 解析 + ③ analyze_changes 工具）：

**子项 ② — git diff 行级解析与变更函数定位**：
1. 复用 GitPython（`codewiki/cli/git_manager.py` 已依赖，仅缺 diff 解析）
2. 解析 hunk：`git diff --unified=0` 输出 → 变更行号集合（区分新增/删除行）
3. 函数定位：用组件元数据 `start_line` / `end_line`（Node 模型已有）做区间匹配 → 变更行属于哪个函数
4. 删除行需回退到变更前版本解析（删除行在旧文件的区间里），新增行在现文件区间里

**子项 ③ — analyze_changes MCP 工具**：
1. 输入：`since`（commit 范围，默认 HEAD~1）或 `worktree=true`（工作区未提交变更，含 untracked）
2. 变更函数集合 → `transitive_impact(direction='depended_by')`（已有）→ 受影响组件 + 深度
3. 测试映射：按 `test_*.py` / `*_test.go` / `*Test.java` 等命名约定与目录邻接（同目录/同模块）关联受影响组件的测试文件
4. 输出：变更函数、受影响函数（按深度分组）、建议回归测试列表、风险分级（复用 `impact_review` 的分级标准：direct_dependents 数 + 深度）
5. 与 CBM `detect_changes` 结果可合并（沿用 `merge_cbm_and_local_results` 模式）

### 验收标准

- [ ] `analyze_changes(repo_path, since='HEAD~1')` 返回受影响组件 + 建议测试文件
- [ ] `analyze_changes(repo_path, worktree=true)` 覆盖未提交变更（暂存 + 未暂存 + untracked）
- [ ] 变更定位精确到函数：文件内未改动的函数不进入变更起点集合
- [ ] 无 git 仓库或 HEAD 不存在时给出明确错误而非崩溃
- [ ] 变更涉及测试文件本身时（只改测试不改源码），不误报业务组件受影响
- [ ] 与 CBM `detect_changes` 结果可合并（沿用 `merge_cbm_and_local_results` 模式）
- [ ] 测试：temp git 仓库中制造一次提交 + 一次工作区修改 → 断言变更函数定位正确、受影响组件集合正确、测试映射命中

### 影响面

- **正面**：Agent 改代码后一条命令获得"影响半径 + 回归清单"，与 codegraph `affected` 对齐；可进一步接 CI（输出文件供流水线跑测试）
- **负面**：git 命令执行依赖环境（需 git 可用）；测试映射命名约定需可配置（不同语言不同约定）

### 优先级

**P1** — 用户调研中明确点名的"影响半径"场景的实战闭环，投入产出比高（核心遍历逻辑已存在，主要是 git 入口 + 测试映射，约 200-300 行）。

***

## 3. P2 · 代码符号全文/语义检索

### 背景

CBM `semantic_query`（nomic-embed-code 向量检索）、codegraph（SQLite FTS5 全文索引）都能对**代码符号**做检索；Grapify 提供多模态语义检索。CodeWiki-CN 的 `query_wiki` 检索的是 **wiki 文档**（notes/wiki 目录），无法直接按意图检索**代码组件**——Agent 找函数时仍要 grep 或读文件。

### 问题描述

- `query_wiki` 覆盖 `repowiki/` 下的文档，不覆盖 SQLite 里的代码组件（函数/类）
- 无"按函数名模糊找定义"、"按注释找功能"、"按自然语言找符号"的能力
- 现有 `list_components` 只能按类型/路径过滤，不支持全文/语义

### 建议方案

分两档落地（先全文后语义）：

**档位 1（P2，低成本）— SQLite FTS5 全文索引**：
1. `analyze_repo` 落库时同步构建 FTS5 虚拟表：组件名 + docstring + 源码片段（截断前 200 字符）
2. 新增 MCP 工具 `search_components(repo_path, query, limit=20)`，BM25 排序（SQLite FTS5 内置 `bm25()`）
3. 支持 `name:` / `file:` 前缀过滤（如 `name:AuthService`）

**档位 2（P3，可选）— 语义检索**：
1. 可选加载轻量 embedding（如 `sentence-transformers` 或复用现有模型），对组件 docstring 建向量索引
2. `search_components(semantic=true)` 走向量检索，与 BM25 结果混合排序（RRF）

### 验收标准

- [ ] `search_components` 按关键词命中函数/类（名称、docstring、源码片段），结果含组件 ID + 所在文件 + 命中片段
- [ ] 索引构建不显著拖慢 `analyze_repo`（FTS5 建表 < 全量解析时间的 5%）
- [ ] 增量更新时 FTS5 同步增量（只删改变更文件的符号行）
- [ ] （档位 2）语义查询"找处理登录超时的函数"能返回合理结果

### 影响面

- **正面**：补齐代码图谱工具的检索短板；Agent 找符号从"grep 撞运气"变为"结构化检索"；`query_wiki`（文档）+ `search_components`（代码）形成双检索通道
- **负面**：FTS5 需 SQLite 编译支持（Python 自带 sqlite3 通常含 FTS5，需验证）；语义档位增加依赖体积

### 优先级

**P2** — 检索体验增强，不阻塞图分析正确性；档位 1 成本低、收益直接，建议先做。

***

## 4. P3 · 死代码扫描与图谱交互可视化（可选）

### 背景

codegraph 支持死代码扫描（未被引用符号）；grapify/CBM 提供交互式图谱可视化（graph.html / 3D UI）。CodeWiki-CN 已有 PageRank 与孤立节点检测的近似信号，也有 cytoscape JSON 生成（`call_graph_analyzer.py::generate_cytoscape_format`），但没有面向用户的工具入口和前端页面。

### 建议方案

- **死代码扫描**：新增 `detect_dead_code` 工具 = 零入度（无 caller）+ PageRank 低分 + 非导出（无 `__all__`/`pub`/`export`）组件 → 候选死代码清单（按置信度排序）
- **交互可视化**：`analyze_repo` 或 `analyze_impact` 输出可选 `html=true`，基于现有 cytoscape JSON 生成单文件 `graph.html`（内嵌 cytoscape.js CDN），支持点击节点高亮上下游、按模块着色

### 验收标准

- [ ] `detect_dead_code` 输出候选清单 + 置信度 + 建议人工复核理由
- [ ] `graph.html` 单文件可离线打开，节点可点击展开调用链

### 影响面

- **正面**：重构场景下的"可删代码"线索；可视化降低图谱理解门槛
- **负面**：死代码判定存在误报（动态调用、反射、框架回调），必须标注置信度；HTML 生成增加模板维护

### 优先级

**P3** — 锦上添花，不影响核心查询正确性。

***

_以上需求整理自 2026-08-24 代码图谱工具对标调研（CodeGraph / Grapify / CBM），可作为 CodeWiki-Plus 后续版本 backlog 追踪。_
