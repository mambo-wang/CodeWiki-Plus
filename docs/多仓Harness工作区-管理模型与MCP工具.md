# 多仓 Harness 工作区：管理模型与 CodeWiki 工具支持

> 适用版本：CodeWiki-Plus v5.5.0+（新增 `init_workspace` / `add_workspace_repo` / `remove_workspace_repo` 工具）
> 状态：设计落地说明

## 1. 背景与问题

当一个产品线由多个相互关联的代码仓库组成（例如：工具链本体仓 + 配套 WebApp 仓 + 文档仓 + 未来更多业务仓）时，常见的组织方式各有利弊：

| 方式 | 问题 |
|------|------|
| 全部塞进一个"大仓"（monorepo） | 仓库越来越大、权限难隔离、各业务提交互相牵连 |
| 各自独立仓库、互不关联 | 缺少一个"产品级"的入口来承载跨仓约定、产品知识、一键初始化 |
| 在某个业务仓里放"公共约定" | 该业务仓被污染：上游同步冲突、提交历史混杂、其他仓无法独立复用 |

CodeWiki 的多仓 **Harness 工作区**模型正是针对这些问题：**用独立的一个 harness 主仓库承载产品级资产，业务代码仓以独立 git clone 挂在其子目录下，git 层面完全隔离，不是 submodule。**

### 1.1 候选方案盘点：为什么选独立 clone 工作区

除上表三种组织方式外，多仓管理还有几个常见候选。它们的落选不是能力问题，而是与本项目四个核心诉求不匹配：harness 不入业务仓、提交不打架、分支松耦合（各仓自由选主线/个人分支，harness 仓固定不频繁变动）、跨仓知识分层检索。逐一盘点：

**git submodule（业务仓作为 harness 仓的子模块）**

submodule 在父仓里只存两样东西：指向子仓某个 commit 的 gitlink 指针和 `.gitmodules` 配置。它擅长的是**钉快照**，不是**活跃开发**：子仓永远 detached HEAD 在某个历史 commit 上，日常改动要先切分支、提交后先 push 子仓再回父仓 bump 指针，顺序错了父仓就引用一个远端不存在的 SHA；父仓钉住的版本天然滞后于子仓分支前进。

- 落选根因：submodule 的本质是"父仓把子仓钉死在某个版本"，与"分支松耦合"诉求**直接相反**——它带来的只有指针负担，换不来任何本场景需要的东西（我们不需要版本组合快照）。
- 适合的场景：**发布版本组合锁定**（如 v2.3 = 前端A@abc123 + 后端B@def456 的一组可复现 commit）、引用第三方依赖库的特定版本。即"钉住"本身就是需求的场合。

**Google repo / meta / gitslave 等多仓批量工具**

`repo` 为 AOSP/Gerrit 生态而生，核心价值是 `repo sync` 批量同步、`repo start` 跨仓开同名分支、manifest.xml 版本组合管理、大规模 onboarding 标准化（新人一条命令拉齐全部仓库）。`meta`（npm 生态）、`gitslave`（主从传播）是轻量等价物。

- 落选根因：一是评审闭环断裂——`repo upload` 走 Gerrit，不认 GitHub PR，引入 repo 后"批量 git 操作"变顺但最后一公里仍要逐仓 `gh pr create`，体验只顺了一半；二是它解决的问题（几十人并行、批量分支操作一致性强制）在 10 人规模收益低于工具链迁移与培训成本；三是"各仓分支互不感知"恰恰是本模型的诉求，与批量工具"同进同退"的设计取向相反。
- 适合的场景：大团队（几十人以上）、**跨仓需求占比高**（一个月内超过三成的需求横跨多仓）、使用 Gerrit 评审流、需要 manifest 精确复现任意历史组合的合规场景。

**朴素脚本工作区（N 个普通 clone + 批量脚本）**

一个产品根目录下放各仓的普通 clone，配一个几十行的批量 status/pull/checkout/push 脚本。零依赖、零学习成本、出问题都是普通 git 问题。

- 定位：本模型的**底座就是它**。当团队小（单人或两三人）、无产品级知识沉淀需求时，纯脚本工作区已够用，不必引入 harness 仓。
- 升级路径：一旦出现"跨仓约定要有归属地""产品级知识要版本化共享""Agent 要有统一检索入口"这些诉求，就升级为本模型——harness 仓 ≈ 脚本工作区 + 产品级知识层 + Agent 约定层。升级是平滑叠加，不需要重构。

**子仓 wiki 集中生成到 harness 仓 repowiki（集中式知识放置）**

曾讨论过的变体：让业务仓的代码 wiki 统一生成在 harness 的 repowiki 下，换取业务仓"纯净"。

- 落选根因：违反 **one .git = one repowiki** 原则，四笔代价都不便宜——
  1. **漂移**：harness 描述的是生成那一刻的子仓快照，子仓天天前进，wiki 立刻过时；`analyze_repo` 的增量更新依赖 repo 与 output_dir 同仓绑定，跨仓后闭环断裂。
  2. **分支错配**：子仓个人开发分支上生成的 wiki，会随 harness 的固定分支共享给全团队，描述别人拉不到的代码状态。
  3. **检索分层稀释**：产品级 repowiki 索引混入上千组件级模块文档，第一跳检索噪音陡增，两跳路由的边界糊掉。
  4. **lint 失配**：harness 的 `lint_wiki` 拿模块文档对照 harness 自己的代码检查，对着不存在的代码报警。
- 适合的场景：仅当业务仓必须绝对纯净**且**接受文档不随代码演进（如一次性归档、交付快照文档）时才考虑；业务仓自己 `.gitignore` 掉 repowiki（wiki 留本地、不团队共享）是代价更小的折中。

**选型速查**：数两个数——上月跨仓需求占比、团队规模。联动开发不足一成或团队三五人，纯脚本工作区够用；占比超三成、团队十几人以上且用 Gerrit，考虑 repo；需要版本组合快照（发布锁定），submodule 补位；需要产品级知识分层与 Agent 检索入口，本模型。

## 2. 管理模型

### 2.1 结构

```
CodeWiki-Plus-Harness/          ← harness 主仓库（独立 git，提交稳定）
├── repowiki/                   ← 产品级 Wiki：产品概述、各业务仓业务概述、仓库导航
│   └── wiki/repo-map.md        ← 仓库导航页（第二跳检索入口）
├── AGENTS.md                   ← Agent 工作约定（两跳检索路由、提交纪律）
├── bootstrap.ps1 / .sh         ← 一键初始化：克隆全部业务子仓
├── README.md
├── codewiki-plus/              ← 业务仓 1（独立 clone，harness 的 git 不追踪）
├── webapp/                     ← 业务仓 2（独立 clone）
└── ...
```

关键特征：

- **目录上是父子，git 上是隔离**：每个业务仓带自己的 `.git`；harness 仓通过 `.gitignore` 显式排除所有业务仓目录，业务代码**物理上无法**被提交进 harness 仓。
- **harness 仓只存"怎么干活"**：产品级知识（repowiki）、跨仓协作约定（AGENTS.md）、基础设施脚本（bootstrap）——不存放任何业务仓的内部实现细节。
- **知识分层，两跳检索**：
  1. 第一跳查 harness 的 `repowiki`，得到产品概述与仓库导航（`repo-map.md`）；
  2. 命中业务仓后，下钻到该业务仓自己的 `repowiki` 获取模块/实体/笔记等深度知识。

### 2.2 三个结构性机制

1. **git 隔离（`.gitignore` 红线）**：新增业务仓必须在 `.gitignore` 登记 `/<目录>/`，否则 `git add .` 会把业务仓作为 embedded repository（裸 gitlink）误提交。这是"提交不打架"的结构性保证，不依赖人的自觉。
2. **提交纪律**：业务代码只在业务仓内提交；harness 仓只提交 harness 资产。
3. **分支松耦合**：各业务仓自由选择主线或个人开发分支，harness 仓分支固定、互不感知、无需同步。

## 3. 独立 Harness 仓库的好处

| 好处 | 说明 |
|------|------|
| **不污染业务代码仓** | 业务仓保持"纯代码"状态：可干净地跟随上游（fetch/rebase/PR）、提交历史只含业务变更、CI/代码评审不受 harness 资产干扰 |
| **一对多管理多个关联业务仓** | 一个 harness 仓 = 一个产品线的统一入口。`bootstrap.sh/ps1` 一键克隆全部业务子仓；新增业务仓只需一次登记（工具自动同步四处文件） |
| **产品级知识与仓库级知识分层** | 产品概述、跨仓协作约定放 harness；模块文档、pitfall、decision 放各业务仓自己的 repowiki——wiki 与它描述的代码同仓演进，互不干扰 |
| **Agent 协作约定有归属地** | skill、rule、command、AGENTS.md 等"怎么干活"的资产属于产品线而非某个业务仓，放在 harness 仓可跨仓复用、随产品线统一演进 |
| **结构性防错** | `.gitignore` + 提交纪律让"误提交业务代码"在机制上不可能发生，而不是靠事后提醒 |
| **跨仓分析有落点** | `analyze_workspace` 的工作区级总览与跨服务拓扑（overview.md + `.meta/`）直接写入 harness 的 `repowiki/`，与产品级知识同库、可被 `query_wiki`/`query_cross_service` 检索 |
| **新仓接入成本极低** | 接新业务仓 = 一次 `add_workspace_repo` 调用（登记 + 克隆），无需手工改四个文件 |

## 4. 新增 MCP 工具方法

CodeWiki v5.5.0 为这个模型提供了三个开箱即用的 MCP 工具与配套工作流 Prompt。

### 4.1 `init_workspace` — 初始化（或重新同步）工作区

把**当前目录**初始化（或重新同步）为多仓 harness 工作区。**零配置幂等**，重跑按初始化痕迹分两种模式（返回的 `mode` / `mode_reason` / `traces` 字段标明走了哪条）：

- **痕迹齐备 → clone-only 接管**：`bootstrap.sh` / `bootstrap.ps1`（登记表可解析）+ `.gitignore` + `repowiki/` 骨架（`wiki/` + `schema.yaml`）都在，就视为工作区已初始化——重跑**只克隆登记表中尚未克隆的业务仓**（顺带补齐缺失的 `.gitignore` 排除行），不重新生成骨架、不改写 AGENTS.md。典型场景：harness 仓在新机器上克隆后直接重跑，只需把业务仓拉下来。该场景也可直接执行 bootstrap 脚本补克隆（脚本与工具读同一张登记表），无需经过本工具；clone-only 是误调用的兜底。
- **骨架有缺失 → 完整同步修复**：自动沿用已保存的布局、补齐缺失产物、强制刷新约定块，并补克隆（克隆失败只警告，可稍后 `./bootstrap.sh` 或再次重跑补克隆）。

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `output_dir` | 否 | `<workspace>/repowiki` | 产品级 repowiki 目录 |

**产物**：

- `bootstrap.sh` / `bootstrap.ps1`：幂等克隆脚本（登记表，登记走 `add_workspace_repo`）
- `.gitignore`：业务仓目录 + 通用忽略（**不忽略** `repowiki/`——产品级知识与跨仓分析产物入库）
- `repowiki/wiki/repo-map.md`：仓库导航骨架
- `AGENTS.md`：工作区约定块（两跳检索路由、提交纪律、分支策略、知识写入路由、新仓接入清单）
- 产品级 repowiki 目录结构与 `schema.yaml` 等模板（复用 `init_wiki` 能力）

**幂等语义**：

- 知识布局（`colocated`/`centralized`）首次初始化时确定并持久化到 `repowiki/.meta/workspace.json`；两种重跑模式都自动沿用（无配置文件即视为 `colocated`），显式传入冲突值才报错（布局切换是手工迁移）。集中式需在**首次**初始化时显式传 `layout="centralized"`。
- clone-only 接管模式不触碰任何骨架文件与 AGENTS.md；完整同步修复模式下，bootstrap 脚本、repo-map、README、schema.yaml 也只补缺不覆盖，唯约定块**强制刷新**（该块由工具维护，自定义内容请写在标记块外）。
- 登记表中已登记但未克隆的业务仓会被自动 `git clone`（两种模式均执行；逐个执行，单仓超时 600s；失败仅警告不中断）。

### 4.2 `add_workspace_repo` — 登记并克隆业务仓

只需传克隆 URL，**目录名自动取仓库名**（URL 最后一段，去 `.git` 后缀，兼容 SSH 式 `git@host:org/repo.git`）：

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `workspace_path` | 否 | 当前目录 | 工作区根目录 |
| `url` | 是 | — | 业务仓 git 克隆 URL |
| `clone` | 否 | `true` | 登记后立即克隆 |
| `clone_timeout` | 否 | 600 | 克隆超时（秒） |

**事务式同步四处**（预检全部通过才动笔，不会出现"改了一半"）：

1. `bootstrap.sh` 登记表
2. `bootstrap.ps1` 登记表
3. `.gitignore` 增加 `/<name>/`
4. `repowiki/wiki/repo-map.md` 增加导航行 + 小节骨架

然后执行 `git clone`。**克隆失败只警告、不回滚登记**（可稍后 `./bootstrap.sh` 补克隆）。同名同 URL 重复登记是空操作；同名不同 URL 报错且不改动任何文件。

### 4.3 `remove_workspace_repo` — 移除业务仓

按**子目录名**（登记时的目录名）移除：

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `workspace_path` | 否 | 当前目录 | 工作区根目录 |
| `name` | 是 | — | 业务仓子目录名 |

同样事务式清理四处登记，并**删除本地 clone 目录**（不可恢复）——用户要求移除该仓即视为同意删除其本地克隆，工具不再单独确认。未登记的 name 是安全错误，不影响其他业务仓。

登记之外还有两类清理：

- **集中模式知识清理**：删除该仓的 `wiki/modules/<name>/` 分区；共享池页面按来源标逐页处理——多来源页只移除该仓来源标，唯一来源页保留内容但解除标注，成为孤儿由 `lint_wiki` 的 layout_violations 报告、交人工裁决（工具不静默删知识）。
- **分析产物清理**：`analyze_workspace` 落在 `repowiki/.meta/` 的缓存按仓归属过滤——`workspace_routes.json` 按 `repo_name`、`cross_service_links.json` 按 `client_repo`/`server_repo`、`infra_services.json` 按 `source_path`（compose 文件相对工作区路径，无该字段的旧缓存条目不动），生成的 `overview.md` 同步删除该仓服务行与链接。这些是可再生的缓存而非知识，过滤后 `query_cross_service` 不再返回已移除仓的幽灵路由。

### 4.4 配套工作流 Prompt

MCP Server 内置三个 Prompt（IDE Prompt 面板可直接触发）：

| Prompt | 场景 |
|--------|------|
| `init-workspace` | 初始化（或重跑同步：痕迹齐备时 clone-only 接管补克隆 / 骨架缺失时补齐产物）→ 逐个登记业务仓 → 逐仓建 Wiki → 跨仓分析 |
| `add-workspace-repo` | 按 URL 登记 + 克隆业务仓 → 校验四处同步 → 建该仓 Wiki |
| `remove-workspace-repo` | 移除登记并删除本地目录 → 校验清理结果 |

## 5. 典型使用流程

```text
1. 新建一个空目录（或空 git 仓库）作为 harness 仓
2. 调用 init_workspace                          # 建骨架
3. 对每个业务仓调用 add_workspace_repo(url=...) # 登记 + 克隆
4. 对每个业务仓调用 init_wiki / analyze_repo    # 建仓库级 Wiki
5. 调用 analyze_workspace(workspace_path=...)   # 跨仓分析 → repowiki/overview.md
6. 日常检索：
   - query_wiki(output_dir=<harness根>/repowiki)          # 第一跳：产品级
   - query_wiki(output_dir=<harness根>/<业务仓>/repowiki)  # 第二跳：仓库级
   - query_cross_service(workspace_path=<harness根>)       # 跨服务调用
7. 移除业务仓时调用 remove_workspace_repo(name=...)
```

## 6. 与既有能力的协同

- **`init_wiki`**：单仓 Wiki 初始化，被 `init_workspace` 复用（产品级 repowiki 目录结构 + 模板）；每个业务仓各自跑自己的 `init_wiki`。
- **`analyze_workspace`**：默认输出目录已统一为 `<workspace>/repowiki`，工作区总览（含 Mermaid 跨服务拓扑）与 `.meta/` 跨仓产物直接落入产品级 repowiki，随 harness 仓提交。
- **`query_cross_service`**：自动从 `<workspace>/repowiki/.meta/` 读取跨仓匹配结果（兼容旧的 `workspace-wiki/.meta/` 数据）。
- **`query_wiki`**：两跳检索的检索层，产品级与仓库级 repowiki 均可搜。

## 7. 存量手工工作区接管

此前手工搭建的 harness（如本仓库早期形态：手工 `bootstrap.sh/ps1`、`.gitignore`、`repo-map.md`、AGENTS.md）**可直接被工具接管**：工具以自然语法锚点定位登记表（`declare -A repos=(` / `$repos = [ordered]@{`），无需哨兵注释或迁移。直接调用 `add_workspace_repo(url=...)` 即可把手工登记的仓库补全/接管，后续维护统一走工具。

## 8. FAQ

- **harness 仓和 submodule 有什么区别？** submodule 把子仓指针纳入父仓 git 历史，提交、更新都要联动；本模型业务仓完全独立，父仓只通过 `.gitignore` 排除目录，子仓分支/历史/提交与父仓互不影响。
- **为什么不让 `init_workspace` 一次性登记所有仓库？** 职责分离：`init_workspace` 只建骨架，登记与克隆统一走 `add_workspace_repo`（幂等、可重试、带 clone），两个动词一条职责，心智模型简单。
- **业务仓目录名怎么来的？** 从克隆 URL 最后一段推导（`https://github.com/org/CodeWiki-Plus.git` → `CodeWiki-Plus`）；名字含非法字符（只允许字母、数字、`.`、`_`、`-`）时会报错。
- **跨仓分析产物会不会污染 repowiki？** 不会：`overview.md` 与 `.meta/` 是工作区级资产，与各业务仓自己的 `repowiki/` 完全独立；且随 harness 仓提交，团队共享。
