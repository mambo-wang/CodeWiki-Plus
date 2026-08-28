# 多仓 Harness 工作区：集中式 Wiki 布局设计方案

> 适用版本：CodeWiki-Plus v5.6.0+（`init_workspace` 新增 `layout` 参数）
> 状态：设计定稿（待评审）
> 关联文档：《多仓Harness工作区-管理模型与MCP工具》（v5.5.0，下称《管理模型》）

## 1. 背景与动机

v5.5.0 确立了多仓 Harness 工作区模型：一个独立的 harness 主仓库承载产品级资产，业务代码仓以独立 git clone 挂在其子目录下，**每个业务仓各自维护自己的 `repowiki/`，与代码同仓演进**。这个"同仓"布局是该模型的默认形态，其核心信条是"wiki 与它描述的代码同仓演进"。

然而不同产品线对知识组织的诉求并不一致：

- 有些团队更看重**统一、可集中检索的知识库**，而非同仓演进——他们希望产品级与全部业务仓知识落在同一个可检索库里，一跳直达；
- 关联业务仓共享同一套领域词汇，**同名实体在各仓含义一致**，按仓切片反而把词汇表撕碎；
- 同仓演进带来的提交归属、上游同步成本，并非每个团队都愿意承担。

因此本方案引入**第二种布局模式——集中式（`centralized`）**：所有知识（产品级 + 各业务仓）统一落入 harness 的 `repowiki/`，业务仓目录内不再存在 `repowiki/`。两种模式在 **`init_workspace` 时一次性选择**，此后登记、建仓、分析、检索、写入全部按模式自动路由。

本方案**不改变**《管理模型》的三大结构性机制（git 隔离、提交纪律、分支松耦合），只改变知识产物的落点。

## 2. 两种布局模式总览

| 维度 | `colocated`（默认＝现状） | `centralized`（本方案） |
|------|---------------------------|--------------------------|
| Wiki 落点 | 各业务仓自己的 `repowiki/` | 全部汇入 harness 的 `repowiki/` |
| 业务仓目录 | 含 `repowiki/` | 纯代码，**无** `repowiki/` |
| 检索跳数 | 两跳（产品级 → 仓库级） | 一跳（整个 `repowiki/`，可按 `repo=` 过滤） |
| 提交归属 | wiki 随业务仓提交 | wiki 随 harness 仓提交 |
| 运行时数据 | 各仓 `repowiki/` 内 | 工作区根共享（见 §8） |
| 移除业务仓 | 业务仓目录带走自身知识 | 删 `wiki/modules/<仓名>/` + 清共享池来源标 |
| 兼容性 | 完全等同 v5.5.0 | 新增模式，需显式选择 |

**选择机制**：`init_workspace(layout=...)`。默认 `colocated`——不传参数时行为与现状逐字节一致，零迁移成本、零破坏。

## 3. 集中模式的文件结构

```
CodeWiki-Plus-Harness/              ← harness 主仓库（独立 git）
├── repowiki/                        ← 唯一知识库，随 harness 仓提交
│   ├── .meta/
│   │   ├── workspace.json           ← 布局配置（本方案唯一新增的机器可读文件）
│   │   └── task_bindings/           ← 会话-任务绑定（现状，位置不变）
│   ├── schema.yaml                  ← 文档约定（结构同现状，见 §12.7）
│   ├── wiki/
│   │   ├── overview.md              ← 工作区总览 + 跨服务拓扑（analyze_workspace 产出）
│   │   ├── index.md
│   │   ├── repo-map.md              ← 仓库导航页（一跳检索入口）
│   │   ├── modules/                 ← ★ 唯一按仓分区
│   │   │   ├── codewiki-plus/
│   │   │   ├── webapp/
│   │   │   └── .../
│   │   ├── sources/                 ← 共享池，frontmatter repo: 标来源
│   │   ├── entities/                ← 共享池，frontmatter repos: 标来源
│   │   ├── concepts/                ← 共享池
│   │   ├── comparisons/             ← 共享池
│   │   └── queries/                 ← 共享池
│   ├── notes/                       ← 共享笔记池，frontmatter repo: 可选
│   ├── tasks/                       ← 共享运行时（见 §8）
│   ├── raw/                         ← 共享运行时
│   └── conversations/               ← 共享运行时
├── AGENTS.md                        ← 工作区约定（集中模式变体，见 §7、§12.2）
├── bootstrap.ps1 / .sh              ← 登记表仍是唯一仓清单事实源（不变）
├── .gitignore
├── codewiki-plus/                   ← 业务仓 1（独立 clone，无 repowiki/）
├── webapp/                          ← 业务仓 2（独立 clone，无 repowiki/）
└── ...
```

**切线规则（一句话）**：

> 只有 `modules` 按仓分区；其余所有页型（`sources`/`entities`/`concepts`/`notes`/`comparisons`/`queries`）一律进共享池，用 frontmatter `repo:`/`repos:` 标注来源。

**为什么这样切**：`modules` 是唯一"锚定代码结构"的页型——一页对应一段仓内目录树，天然必须按仓隔离。其余页型都是"命名对象/经验知识"，在关联业务仓共享领域词汇的前提下（同名实体含义一致），它们属于产品线级共享层，按仓切片只会制造重复与割裂。

### 3.1 为什么 sources 也进共享池而非分区

`sources`（代码引用页）虽锚定文件路径，但其价值在"这份引用说明了什么"，而非路径本身。两个仓都有 `src/config.py` 的同名冲突，靠**来源标注 + 页名规范**（页名携带仓前缀或由 `repo:` 字段消歧）解决，不必上升为目录隔离。这与 entities 的处理完全一致，换来切线规则的极简。

### 3.2 平铺分区，不设 `repos/` 中间层

早期草案曾用 `repowiki/repos/<仓名>/wiki/modules/` 的"仓包"结构。定稿改为 `repowiki/wiki/modules/<仓名>/` 的平铺分区，理由：

- 集中模式下真正需要按仓隔离的只有 `modules`，为单一页型单开一层 `repos/<仓名>/wiki/` 属于"wiki 里再套 wiki"，冗余；
- 平铺后整棵树只有一个 `wiki/`，共享层与隔离层同处一套命名空间，心智模型最简单；
- `wiki/modules/<仓名>/` 中仓名位于 `modules/` 之下，不会与 `wiki/` 根下的 `entities`、`notes` 等兄弟目录冲突。

代价：移除业务仓时不再有单一"仓包"可整体搬走，需删 `wiki/modules/<仓名>/` 一个分区目录 + 清理共享池中带 `repo: <仓名>` 的来源标（见 §13）。代价很小。

## 4. 配置与持久化

**`repowiki/.meta/workspace.json`**（本方案唯一新增的机器可读工作区配置）：

```json
{ "wiki_layout": "centralized" }
```

设计约束：

- **仓清单不进此文件**。`repos` 登记表继续以 `bootstrap.sh`/`bootstrap.ps1` 脚本内的表为唯一事实源（《管理模型》现状），本方案不动登记表结构、不动其正则锚点。
- **无逐仓覆盖字段**。布局是工作区级单一选择（见 §14 决策 Q2），因此配置只有一个标量字段。
- **落点选 `.meta/`**：该目录已是工作区级机器状态的落点（`task_bindings/`、`analyze_workspace` 跨仓产物），随 harness 仓提交；不用 `.codewiki/`（那是分析缓存与大结果侧通道，不入提交），也不用 `schema.yaml`（其语义是文档格式约定，不宜混入结构配置）。

**读取约定（探测与回退规则）**：所有工具在解析 `output_dir` / 路由前，先向上探测工作区根并读取 `workspace.json`。探测必须遵守四条护栏，保证**单库场景与未登记目录零影响**：

1. **探测信号只认 `workspace.json`**：自 `repo_path` 向上只找 `repowiki/.meta/workspace.json`（或 `<目录>/.meta/workspace.json`），到文件系统根即止；bootstrap 登记表**不作为**探测信号（无 workspace.json 的目录＝v5.5.0 工作区或普通目录，本就该走现状路径），仅用于下述成员校验。
2. **命中后必须成员校验**：找到 `workspace.json` 后，还需确认当前仓目录名在该工作区的 bootstrap 登记表中；未登记（如用户手动 clone 进工作区目录的无关仓库）→ 视为非成员，走单库现状路径，**不被劫持**到集中路由。
3. **三态回退**：未找到 workspace.json（含单库场景）、找到但非成员、值为 `colocated` —— 一律走现状路径（`repo_path/repowiki`），行为与 v5.5.0 逐字节一致。
4. **探测结果进程内缓存**：每次 `output_dir` 解析不重复向上遍历（深嵌套单库目录不付反复探测的性能税）。

## 5. 模式命名与参数

`init_workspace` 新增参数：

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `layout` | 否 | `colocated` | 知识布局模式：`colocated`（wiki 与代码同仓）｜`centralized`（wiki 集中到父仓） |

命名取 `colocated`/`centralized` 而非 `repo`/`hub`：这对词精确刻画了本质区别——**wiki 是与代码同处，还是集中于父仓**——且与"一跳/两跳"检索语义自然对应，自解释性强。默认值取 `colocated` 即现状，保证向后兼容。

## 6. 工具行为矩阵

`colocated` 列全部等于现状，凡未列出的行为一律不变。

| 工具 | `centralized` 模式下的行为 |
|------|----------------------------|
| `init_workspace` | 建共享骨架（§3 树形）+ 写 `.meta/workspace.json` |
| `add_workspace_repo` | 登记 + 克隆；建 `wiki/modules/<名>/` 骨架 + 更新 `repo-map.md`；**不**建仓内 `repowiki/`；移除业务仓 `AGENTS.md` 的 CodeWiki 块 |
| `init_wiki` / `analyze_repo` | `modules` → `wiki/modules/<名>/`；`sources`/`entities`/`concepts`/`notes` 等 → 共享池并打 `repo:`/`repos:` 标 |
| `analyze_workspace` | 跨仓拓扑照做；去除对 `<仓>/repowiki` 的硬编码，按 `layout` 从 `wiki/modules/<名>/` 读；新增 `generate_repo_wikis` 选择（§10） |
| `query_wiki` | 一跳检索整个 `repowiki/`；新增可选 `repo=<名>` 过滤，收敛到"适用于该仓的知识"＝该仓分区 + 带该仓标的共享项 + 全局项（§7.1） |
| `query_cross_service` | 仍读 `.meta/`，不变 |
| `ingest_note` / `write_doc_file` | 按页型路由：`module` → 仓分区，其余 → 共享池（带来源标） |
| `capture_conversation` / `distill_conversation` / `task_manager` | `output_dir` 解析到工作区根，`tasks`/`raw`/`conversations` 共享（§8） |
| `lint_wiki` | 新增 layout-violation 检查（§12.6） |

## 7. 检索路由

- **`colocated`**：两跳，完全同《管理模型》现状——第一跳查父仓 `repowiki`，命中后下钻业务仓 `repowiki`。
- **`centralized`**：**一跳**。`query_wiki` 直接检索工作区唯一 `repowiki/`，覆盖产品级 + 全部业务仓；传 `repo=<名>` 时收敛到"**适用于该仓的知识**"——`wiki/modules/<名>/` + 带该仓标的共享项 + 全局项（§7.1）。`repo-map.md` 仍是导航页，但角色从"第二跳入口"变为"仓清单与分区索引"。

**`output_dir` 与 `repo=` 的分工（二者不冗余）**：`output_dir` 是**目录级定位**——指向 `repowiki/wiki/modules/<名>/` 即只查该仓 modules 分区（沿用 `colocated` 第二跳的既有机制，轻量场景用它即可）。但 `output_dir` 是单一路径，无法同时覆盖"该仓 modules + 适用于该仓的共享池知识"（分散在不同目录）。`repo=` 补的正是这个缺口：按**仓身份**聚合 `wiki/modules/<名>/` 与适用于该仓的共享池页——frontmatter `repo:`/`repos:` 含 `<名>`，**或无范围标的全局页**（§7.1）。这恰是 `colocated` 模式"下钻某仓 `repowiki/` 拿全部知识"在集中模式下的等价物——集中模式把一仓的适用知识拆进了"分区 + 共享池"多处，单靠 `output_dir` 聚不拢。因此：只要 modules 用 `output_dir`，要"适用于该仓的全部"用 `repo=`。

### 7.1 范围模型：改某个仓时该查什么

共享池知识的范围用 frontmatter 表达，共三种：

| frontmatter | 范围 | 例 |
|-------------|------|-----|
| 无 `repo:`/`repos:` | 产品线全局，对所有仓生效 | "全线统一用 ruff 做单一格式化器" |
| `repo: X` | 仅适用于仓 X | "codewiki-plus 必须 `uv sync --frozen`" |
| `repos: [a, b]` | 适用于指定多仓 | 两仓间接口约定 |

**修改仓 X 时，检索范围既不是"只查该仓"也不是"查所有"，而是"适用于 X"**：

- "只查该仓"会漏掉全局约定——产品线级编码规范对每个仓都生效；
- "查所有"会混入他仓无关内容——`webapp` 的单仓约定与修改 `codewiki-plus` 无关。

因此 `repo=X` 返回：`wiki/modules/X/` + frontmatter `repo:`/`repos:` **包含** `X` 的共享池页 + **所有无范围标的全局页**。典型场景即仓 X 的编码规范与架构决策：单仓规范打 `repo: X` 入库、按需命中；产品线规范不打标、自动随每个 `repo=` 查询带入。

### 7.2 AGENTS.md 与共享池：规范与决策的两个载体

编码规范、架构决策有两个载体，分工互补：

- **AGENTS.md 管"始终生效"**：harness 的 AGENTS.md 承载产品线约定，业务仓的 AGENTS.md 承载仓内约定，在对应目录工作时**自动加载进上下文**，无需查询。集中模式下仅移除业务仓 AGENTS.md 内的 CodeWiki 引用块，仓自身的约定内容保留。
- **共享池管"可查可溯"**：`decision`/`note` 类沉淀供按需深挖（"当初为什么选 ruff？""这个坑的来龙去脉？"），并享有采纳统计与新鲜度机制。

因此改仓 X 时，规范本身已在上下文（两级 AGENTS.md 自动加载），`query_wiki(repo=X)` 用于捞更深的决策依据与历史脉络。

**AGENTS.md 约定块变体**：`write_workspace_conventions` 按 `layout` 生成对应文本——集中模式下，知识写入路由表、检索指引改写为一跳 + 平铺路径；同时**移除业务仓 `AGENTS.md` 内的 CodeWiki 引用块**（集中模式下业务仓已无 `repowiki/`，该块会成为死引用）。

## 8. 运行时数据：工作区级共享

`tasks/`（任务记忆）、`raw/`（对话蒸馏原料）、`conversations/`（蒸馏归档）、`.meta/task_bindings/`（会话绑定）在集中模式下一律落在 **`repowiki/` 根**，**不按仓分片**。

**理由**：任务与会话天然是工作区尺度的——一个任务完全可能横跨两个业务仓，一条对话也可能同时涉及多仓。按仓分片会制造"这条对话算哪个仓"这类没有好答案的问题。

**实现成本极低**：现有代码中这些路径全部是"`output_dir` 根 + 固定相对常量"（`src/config.py`），相对结构硬编码但根可配。因此只需把运行时工具的 `output_dir` 路由到工作区根，整套数据自动跟随，路径常量一行不改。

## 9. 共享实体池的写入与冲突策略

`entities` 进共享池后，`analyze_repo` 分析仓 A 产出 `Task.md`、之后仓 B 也产出 `Task.md` 时的策略：

- **直写共享池，后写覆盖**；
- frontmatter `repos: [a, b]` **累积**来源（覆盖正文，但来源只增不减）；
- 风险：薄的再分析覆盖厚的旧版本——由 freshness 机制暴露（`stale_after` + 新鲜度检查），不做写入时拦截。

不选两段式晋升（分析产物先落暂存区、确认后晋升）：那会给每个实体加一道人工闸，吃掉集中模式的自动化红利。也不选"集中模式不自动产实体"：那等于放弃实体层自动化。

## 10. `analyze_workspace` 与 `generate_repo_wikis`

集中模式下 `analyze_workspace` 新增参数：

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `generate_repo_wikis` | 否 | `false` | 是否顺带为各业务仓生成代码 wiki（即逐仓跑 `analyze_repo`，落 `wiki/modules/<名>/`） |

语义：跨服务拓扑分析（`overview.md` + `.meta/`）**总是执行**；各仓 `modules` 生成是重活，**默认不顺手做**，由 `init-workspace` / 分析工作流 Prompt 把这个选择显式问给用户。`colocated` 模式下该参数被忽略、行为不变（各仓 wiki 本就各自独立生成）。

### 10.1 逐仓并行生成（推荐 subagent 编排）

集中模式下逐仓 `modules` 生成天然适合并行：`wiki/modules/<仓名>/` 按仓分区、目录互不相交，不同仓写入**零冲突**。因此推荐 **Agent 层 subagent 并行编排**——编排 Prompt（`init-workspace` / 分析工作流）为每个业务仓 spawn 一个 subagent、各自调用 `analyze_repo`，取代 `analyze_workspace(generate_repo_wikis=true)` 的单调用串行循环。`generate_repo_wikis` 保留为小工作区或非 Agent CLI 场景的便捷入口。

并发安全性（已核对代码）：

| 资源 | 并行安全性 | 依据 / 处理 |
|------|-----------|-------------|
| 各仓 `wiki/modules/<仓名>/` | ✅ 天然安全 | 目录互不相交，各 subagent 各写各的 |
| `.codewiki/analysis_cache.db` | ✅ 安全 | 已 `journal_mode=WAL` + `synchronous=NORMAL`（`cache.py`:832-834），容忍多进程读写 |
| 共享池 `entities`/`sources`/`concepts`/`notes` | ⚠️ 需加锁 | 两仓可能产同名页（都产 `Task.md`），frontmatter `repos:` 累积是读改写，需文件锁包住 |

每个 subagent 通常各持一个独立 stdio MCP server 实例，故并发边界落在**共享文件系统**，由 WAL + 文件锁兜住。共享池锁复用现成的 `wiki_index.py::_append_with_lock`(:479) 跨平台范式（Unix `fcntl.flock` / Windows `msvcrt.locking`），将其从"追加锁"泛化为通用"读改写锁"（见 §12.8）。

## 11. 典型使用流程（集中模式）

```text
1. init_workspace(layout="centralized")            # 建共享骨架 + 写 workspace.json
2. 对每个业务仓 add_workspace_repo(url=...)         # 登记+克隆，建 wiki/modules/<名>/，不建仓内 repowiki
3. analyze_workspace()                              # 跨服务拓扑 → overview.md + .meta/
   逐仓 modules：每仓一个 subagent 并行调 analyze_repo（§10.1）
   # 小工作区也可 analyze_workspace(generate_repo_wikis=true) 单调用串行完成
4. 日常检索：
   - query_wiki(...)                                # 一跳，覆盖产品级+全部仓
   - query_wiki(repo="codewiki-plus")               # 适用于该仓的知识（该仓标 ∪ 全局）
   - query_cross_service(...)                       # 跨服务调用（不变）
5. 移除业务仓 remove_workspace_repo(name=...)       # 清登记 + 删 wiki/modules/<名>/ + 清共享池来源标
```

## 12. 代码改造点清单

按侦察定位，均在 `codewiki/`（`CW=codewiki/codewiki/`）。

**12.1 配置与初始化**
- `CW/mcp/tools/workspace_bootstrap.py::handle_init_workspace`(:319) — 增 `layout` 参数；写 `.meta/workspace.json`；集中模式建 §3 共享骨架。
- `CW/mcp/tools/workspace_bootstrap.py::handle_add_workspace_repo`(:460) — 集中模式建 `wiki/modules/<名>/` 骨架、不建仓内 `repowiki/`、移除业务仓 `AGENTS.md` CodeWiki 块。登记表四处同步逻辑不变。

**12.2 AGENTS.md 约定块**
- `CW/mcp/tools/agents_md.py::write_workspace_conventions`(:103) — 增 `layout` 参数，按模式生成变体文本；锚点 `<!-- CodeWiki Workspace Conventions -->` 与 `refresh` 语义不变。

**12.3 output_dir 解析与路由（核心）**
- `CW/mcp/workspace_result.py::resolve_session`(:29) 及各工具解析链 — 增加一级"向上探测工作区根 → 读 `.meta/workspace.json`"；集中模式改路由到平铺路径。涉及调用方：
  - `query_wiki`（`knowledge_loop.py`:1585）、`ingest_note`（:504）
  - `analyze_repo`（`analysis.py`:45）
  - `capture_conversation`（`capture_conversation.py`:515，`_resolve_output_dir`:191）、`distill_conversation`（:1444）、`task_manager`（:78）
- 探测方式类比 git 找 `.git`：自 `repo_path` 向上**只找 `.meta/workspace.json`**，命中后按 §4 护栏做成员校验（目录名须在 bootstrap 登记表）并缓存结果；bootstrap 登记表仅用于成员校验，不作探测信号。未找到 / 非成员 / `colocated` → 走现状路径（单库场景零影响，§4）。

**12.4 analyze_workspace**
- `CW/mcp/tools/workspace_analyzer.py`(:382) — 去除对子仓 `<仓>/repowiki` 的硬编码，按 `layout` 从 `wiki/modules/<名>/` 读；增 `generate_repo_wikis` 参数。

**12.5 检索**
- `CW/mcp/tools/knowledge_loop.py::query_wiki`(:1585) — 增可选 `repo=` 过滤。

**12.6 Lint**
- `CW/mcp/tools/wiki_lint.py`(:1535 区) — 增 layout-violation：集中模式下业务仓目录出现 `repowiki/` 即告警；并可校验共享池页缺失 `repo:` 来源标。

**12.7 Schema**
- `CW/templates/schema.yaml` — `page_types` 的目录映射**保持目录级、layout 无关**（`module → wiki/modules`）；分区是路由层职责而非 schema 职责，避免 schema 与布局耦合。`NOTES_DIR` 等常量（`src/config.py`:17）不变。

**12.8 并发保障（并行生成配套）**
- `CW/mcp/tools/wiki_index.py::_append_with_lock`(:479) — 将现有跨平台锁（`fcntl.flock`/`msvcrt.locking`）从"仅追加"泛化为通用"读改写锁"，建议抽取到 `src/locks.py` 供复用。
- 共享池页写入路径（`entities`/`sources`/`concepts`/`notes` 的 frontmatter `repos:` 累积）用该锁包住读改写，保证多 subagent 并行不竞争；**锁只包集中模式的共享池路径，单库与 colocated 的写入路径不经过锁**，行为不变。
- `analysis_cache.db` 已 WAL（`cache.py`:833），无需改动。

## 13. 兼容性与迁移

- **单库场景零影响（明确声明）**：不经过 `init_workspace` 的独立仓库（自己跑 `init_wiki`/`analyze_repo`）——探测找不到 `workspace.json` 即回退现状路径；`init_wiki` 无新参数、`schema.yaml` 不变、`query_wiki` 的 `repo=` 为可选、`lint_wiki` 新检查仅 centralized 生效、并发锁只包集中模式共享池路径（§4、§12.8）。唯一行为差异是 `output_dir` 解析多一次向上探测，进程内缓存后可忽略。
- **默认 `colocated` = 完全向后兼容**：不传 `layout` 的 `init_workspace` 与 v5.5.0 逐字节一致；存量工作区不受任何影响。
- **v1 不提供迁移工具**：不提供 `migrate_workspace_layout`。已存在的 `colocated` 工作区若要转 `centralized`，手工步骤为：① 各业务仓 `repowiki/wiki/modules/` → 父仓 `wiki/modules/<仓名>/`；② 各仓 `entities`/`notes`/`sources` 等 → 父仓共享池并补 `repo:` 标；③ 各仓运行时数据（`tasks`/`raw`/`conversations`）→ 父仓根；④ 写 `.meta/workspace.json`；⑤ 删各仓 `repowiki/` 与其 `AGENTS.md` CodeWiki 块；⑥ 刷新父仓 `AGENTS.md` 与 `repo-map.md`。
- **存量业务仓已有 `repowiki/` 的情况**：转集中模式时需先决定其知识去留（并入共享库或放弃），工具不自动处置。

## 14. 关键决策记录

| # | 决策 | 取舍理由 |
|---|------|----------|
| D1 | 切线＝只有 `modules` 按仓分区，其余进共享池 | 关联业务仓共享领域词汇，同名实体同义；`modules` 是唯一锚定代码结构的页型 |
| D2 | 布局是工作区级单一选择，无逐仓覆盖 | 登记表本就无每仓元数据槽位；避免路由逻辑分叉，v1 改动面最小 |
| D3 | 模式落盘 + 全工具自动路由 | 不落盘的"模式"只是口头约定，Agent 每次重猜、最易踩坑 |
| D4 | 集中＝一跳，同仓＝两跳 | 一跳是集中模式的核心红利；由 `layout` 决定，检索层无需人工判断 |
| D5 | 运行时数据进工作区根共享，不按仓分片 | 任务/会话天然是工作区尺度；路径为"根+固定常量"，路由一改即随 |
| D6 | 平铺 `wiki/modules/<仓名>/`，不设 `repos/` 中间层 | 只有 `modules` 需分区，不值得单开一层；单一 `wiki/` 命名空间最简 |
| D7 | `sources` 进共享池不分区 | 同名冲突靠来源标注+页名规范解决，换切线规则极简 |
| D8 | 配置落 `repowiki/.meta/workspace.json` | `.meta/` 已是工作区级机器状态落点且随仓提交；`.codewiki/` 是缓存、`schema.yaml` 是文档约定，均不宜 |
| D9 | 实体直写共享池、后写覆盖、`repos:` 累积来源 | 两段式晋升吃掉自动化红利；覆盖风险交给 freshness 暴露 |
| D10 | `generate_repo_wikis` 默认 `false` | 逐仓 wiki 生成是重活，需显式选择，由工作流 Prompt 向用户呈现 |
| D11 | v1 不提供迁移工具，默认 `colocated` 保兼容 | 迁移涉及采纳计数/绑定路径连续性，v1 性价比低；默认值保证零破坏 |
| D12 | 逐仓 wiki 生成推荐 Agent 层 subagent 并行 | `modules` 按仓分区、目录不相交，天然并行安全；缓存已 WAL；仅共享池读改写需文件锁兜底 |
| D13 | `repo=` 语义＝"适用于该仓"（该仓标 ∪ 全局）；规范类知识由 AGENTS.md 与共享池分工承载 | 全局约定对每仓生效，改仓时漏全局即漏规范；AGENTS.md 自动加载管"始终生效"，共享池管"可查可溯"（§7.1、§7.2） |

## 15. FAQ

- **集中模式是不是回到"大仓"了？** 不是。目录上仍是父子、git 上仍隔离（`.gitignore` 红线、提交纪律不变）；改变的只是知识产物落点。业务仓依旧是纯代码、可独立跟随上游。
- **为什么不把 `entities` 也按仓分区？** 关联业务仓里同名实体含义一致，分区等于把产品线级词汇表撕成碎片；共享池 + `repos:` 来源标才是正确抽象层级。
- **同名 `src/config.py` 的 sources 冲突怎么办？** 页名携带仓前缀或由 `repo:` 字段消歧；检索按 `repo=` 过滤。不为个例冲突引入目录隔离。
- **集中模式下还能用 `query_cross_service` 吗？** 能，且不变——它读 `.meta/` 跨仓匹配产物，与布局无关。
- **`workspace.json` 丢了会怎样？** 视为 `colocated`，回退到 v5.5.0 行为；建议随仓提交、纳入 lint 检查。
- **为什么默认不顺手生成各仓 wiki？** `analyze_workspace` 的拓扑分析与逐仓深度生成是两个成本量级的动作；把重活默认关闭、显式选择，避免一次调用产生意外长耗时。
- **多个 subagent 并行建仓不会写坏共享池吗？** `modules` 按仓分区、目录不相交，天然无冲突；分析缓存已是 WAL。唯一需保护的是共享池同名页的 `repos:` 累积（读改写），用跨平台文件锁包住即可（§10.1、§12.8）。
- **`repo=X` 为什么会连带返回无标的全局项？** 产品线全局知识（跨仓编码规范、全局决策）对每个仓都生效，改仓 X 时漏掉全局项就等于漏掉约定。所以 `repo=X` 的语义是"适用于 X"＝带 X 标 ∪ 全局（§7.1），这正是"在 X 上干活"需要的范围。
- **单库（无工作区）会被向上探测误伤吗？** 不会。探测只认 `workspace.json`，单库找不到即回退现状路径；即便仓库恰好躺在某个工作区目录下但未登记，成员校验（§4 护栏 2）也会放它走单库路径，不会被劫持到集中路由。
