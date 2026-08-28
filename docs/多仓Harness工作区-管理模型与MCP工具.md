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

### 4.1 `init_workspace` — 初始化工作区

把**当前目录**（或显式 `workspace_path`）初始化为多仓 harness 工作区，只建骨架、不做业务仓登记：

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `workspace_path` | 否 | 当前目录 | 工作区根目录（必须已存在，不代建） |
| `output_dir` | 否 | `<workspace>/repowiki` | 产品级 repowiki 目录 |
| `refresh_conventions` | 否 | `false` | 强制刷新 AGENTS.md 工作区约定块 |
| `with_readme` | 否 | `true` | 无 README.md 时生成骨架 |

**产物**：

- `bootstrap.sh` / `bootstrap.ps1`：幂等克隆脚本（空登记表，登记走 `add_workspace_repo`）
- `.gitignore`：业务仓目录 + 通用忽略（**不忽略** `repowiki/`——产品级知识与跨仓分析产物入库）
- `repowiki/wiki/repo-map.md`：仓库导航骨架
- `AGENTS.md`：工作区约定块（两跳检索路由、提交纪律、分支策略、知识写入路由、新仓接入清单）
- 产品级 repowiki 目录结构与 `schema.yaml` 等模板（复用 `init_wiki` 能力）

**幂等语义**：bootstrap 脚本、repo-map、README、schema.yaml 重跑不覆盖；约定块默认保留（`refresh_conventions=true` 才刷新）。

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
| `delete_dir` | 否 | `false` | 同时删除本地 clone 目录（不可恢复） |

同样事务式清理四处登记；**默认保留本地目录**——注意目录被移除 `.gitignore` 条目后，harness 仓 `git status` 会看到它，需手动删除或重新忽略。未登记的 name 是安全错误，不影响其他业务仓。

### 4.4 配套工作流 Prompt

MCP Server 内置三个 Prompt（IDE Prompt 面板可直接触发）：

| Prompt | 场景 |
|--------|------|
| `init-workspace` | 初始化工作区 → 逐个登记业务仓 → 逐仓建 Wiki → 跨仓分析 |
| `add-workspace-repo` | 按 URL 登记 + 克隆业务仓 → 校验四处同步 → 建该仓 Wiki |
| `remove-workspace-repo` | 确认删除范围 → 移除登记 → 校验清理结果 |

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
