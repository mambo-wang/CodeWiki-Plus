# 多仓 Harness 工作区：Wiki 增量更新设计方案

> 适用版本：集中式布局（v5.6.0+）之上的增量能力，实现版本待定
> 状态：设计定稿（待实现）
> 关联文档：《多仓Harness工作区-管理模型与MCP工具》（下称《管理模型》）、《多仓Harness工作区-集中式Wiki布局设计方案》（工单 08）

## 1. 背景与动机

`analyze_workspace` 当前是**全量操作**：colocated 布局下逐仓重跑 `analyze_repo`（全量解析建图），centralized 布局下 `generate_repo_wikis` 默认关闭、仅重建跨仓拓扑。工作区一旦包含多个业务仓，"代码变了一点 → 想同步 wiki"的成本与首次生成几乎相同。

而 wiki 生成的真实成本不在解析（确定性 CPU 活，有 SQLite 缓存兜底），在 **LLM 改写**：全量流程会让 agent 倾向于重写全部模块页，既贵又容易冲刷人工修订。增量更新的目标因此是两条：

1. **未变更的仓整仓跳过**——解析、拓扑、清单全免；
2. **变更的仓只改写受影响的模块页**——改写范围由确定性清单给出，未列出的页面不碰。

设计约束（沿用团队 Doctrine）：不新增工具、不新增参数（零配置，判断内置）；新逻辑先找已有收敛点；工具只做确定性事，LLM 改写留在调用方 agent。

## 2. 现状盘点：增量三件套已存在

单仓层的增量更新链已经闭环，本方案**全部复用，不重建**：

| 环节 | 已有收敛点 | 说明 |
|------|-----------|------|
| 锚点 | `<output_dir>/.meta/metadata.json` 的 `generation_info.commit_id` | 上次分析时的 HEAD sha——无需新造锚点文件 |
| 变更检测 | `analyze_repo` 返回的 `changes` 字段（`_detect_doc_changes`） | git prev..cur + worktree diff → `changed_files` → `affected_modules` / `cascade_modules` / `overview_stale`；metadata 存在时自动返回 |
| 改写流程 | `_prompt_incremental_update`（prompt `incremental-update`） | 按 affected_modules 读最新代码 + 现有文档 → `edit_doc_file`/`write_doc_file` → `lint_wiki(stale_refs)` → `close_session` 重建索引 |

定位澄清（讨论中走过的弯路，记录在案）：

- **`analyze_changes` 不是 wiki 增量缝**。它是 post-change 的爆炸半径分析（review/回归测试建议用），不刷新图与路由，也不产出模块级改写清单的完整语义（无 cascade/overview 判定）。
- **`watch_repo` 不是 wiki 增量缝**。它服务于会话内依赖图的后台同步。
- **`analyze_repo` 重跑不等于"全量生成 wiki"**。解析建图是全量，但 wiki 正文改写范围由 `changes.affected_modules` 限定——"增量"的收益在改写层，解析层靠"未变更仓跳过"省掉。

拓扑层同样有现成归属缝：`workspace_routes.json` 按 `repo_name` 归属、`cross_service_links.json` 按 `client_repo`/`server_repo` 归属、`infra_services.json` 按 `source_path` 归属——`_cleanup_analysis_artifacts` 的按仓过滤器可直接复用于"跳过仓的拓扑复用"。

## 3. 设计：三档分派（零参数）

`analyze_workspace` 内部对每个登记仓做三档分派，判定条件全部可推导、确定、可安全降级：

**档 1 — 未变更仓跳过。** 前置检查只碰 git：`HEAD == metadata.generation_info.commit_id` 且 worktree 干净 → 跳过 `analyze_repo`；该仓 routes/links/infra 从 `.meta` 拓扑缓存按归属过滤复用；links 与 overview 从合并后的 routes 集合重算（匹配活，不碰代码解析）。dirty 判定的 untracked 噪音过滤与 `_detect_git_from_meta` 同哲学：仓内 `repowiki/`（colocated wiki 未提交时）与 `.codewiki/` 下的未跟踪文件不算脏，其余未跟踪/修改文件算脏。

**档 2 — 变更仓增量。** HEAD 变化或 worktree 脏 → 重跑 `analyze_repo`（解析全量、routes 天然新鲜，拓扑正确性零风险），返回 `changes/affected_modules`；agent 按 `incremental-update` 流程只改写清单内页面。worktree 脏时 changes 检测天然包含未提交 diff；锚点（commit_id）由 analyze_repo 落盘，提交前后语义自洽。

**档 3 — 无 wiki 仓全量。** 无分析缓存（metadata.json + module_tree.json 缺失）→ 现状全量流程（全量分析 + 全量文档流程）。

**档 4 — deferred（centralized 首跑闸门保留）。** centralized 布局下无锚点且未开 `generate_repo_wikis` 的仓不跑 per-repo 分析（仅跨仓拓扑，现状闸门），避免首跑默认重活；`generate_repo_wikis=true` 或锚点存在后按档 2/3 走。

**降级 posture**：有缓存但锚点不可用（commit_id 缺失、commit unreachable、mtime 回退也失败）→ 该仓安全降级为档 3，绝不拿脏清单做增量改写。

返回形态：per-repo 结果条目透传 `changes`（含 `affected_modules` / `cascade_modules` / `overview_stale` / `no_changes`）与 `mode`（`skipped` / `incremental` / `full`），供调用方 agent 分派改写。

## 4. 唯一新缝：centralized 缓存按仓命名空间

**问题**：`metadata.json` / `module_tree.json` 按 output_dir **单数**存放（单仓假设）。colocated 下每仓自有 repowiki，恰好正确；centralized 下所有业务仓共享工作区 repowiki，metadata 被最后分析的仓覆盖，其他仓的增量检测**静默退化**（commit_id 不匹配 → unreachable → mtime 回退也不匹配 → 返回 None → 永远走全量）。

**方案（已实现）**：centralized 布局下按仓命名空间存放，且与 b792349 为 SQLite 缓存/会话工作区建立的命名空间**合一**：

```
<ws>/.codewiki/<仓名>/analysis_cache.db        ← b792349 已落地
<ws>/.codewiki/<仓名>/workspace/               ← b792349 已落地（changes.json 等）
<ws>/.codewiki/<仓名>/metadata.json            ← 本方案接入（增量锚点）
<ws>/.codewiki/<仓名>/module_tree.json         ← 本方案接入
<ws>/.codewiki/<仓名>/first_module_tree.json
```

收敛缝为 `cache.py` 的 `analysis_meta_dir(repo_path, output_dir)` / `resolve_analysis_meta_file(...)`：colocated 返回 `<output_dir>/.meta`（现状不变，团队共享、随 wiki 提交），centralized 成员仓返回 `<ws>/.codewiki/<仓名>/`。锚点写入点两处：`analyze_repo` 步骤 7c（无则建基线、有则更新 overview_stale）与 `close_session`（文档基线）。旧单文件位置作回退读：命名空间缺失时读 `meta_resolve(output_dir, ...)`，归属错配的旧文件下游安全退化（commit 不可达 → 无 changes）。

这是 v1 唯一的缓存层改动；§3 的三档分派、拓扑复用、prompt 复用都建立在它之上。

## 5. Prompt 层收敛

- **`incremental-update` prompt 原样复用**，不改。
- **不新建 analyze-workspace prompt**。增量编排写进《管理模型》§5 典型使用流程：`analyze_workspace` 返回 per-repo `mode`/`changes` 后，`mode=incremental` 的仓逐仓执行 `incremental-update` 流程，`mode=skipped` 的仓不碰，`mode=full` 的仓走全量文档流程。prompt 载体保持最小（MCP prompt 与文档双载体不滥增）。
- 注意事项补一句增量纪律：**只改写 `affected_modules` 清单内的模块页，未列出的页面不碰**（人工修订的生存边界）。

## 6. 非目标与后续优化（记录在案）

- **A2：watch 机制单次增量同步**（变更仓只重解析变化文件，省掉重跑 analyze_repo 的解析成本）。机器现成但"单次触发 + 缓存写回 + 并发竞态"是新缝，收益随仓规模放大；v1 不做，仓规模真正成为痛点时再评估。
- **centralized 共享池页面（entities/concepts）的过时检测**：v1 清单只覆盖模块页 + overview（`overview_stale` 已有精确判定）；共享池页面交给 `lint_wiki` 既有检查，不扩大爆炸半径。
- **显式参数（force / repos 白名单）**：不加。强制全量的语义由"删除该仓命名空间缓存"覆盖（可再生缓存，与 bootstrap 手工路径同哲学）；判断推回调用方只会让 agent 无脑全量，增量名存实亡。
- **新锚点文件（.meta/analysis_state.json）**：不需要——`generation_info.commit_id` 就是锚点。

## 7. 实现任务拆解

1. **centralized 缓存命名空间**：`meta_resolve` 布局感知解析 + analysis.py 读写点切换 + 旧单文件回退读；colocated 零变化。
2. **analyze_workspace 三档分派**：per-repo 前置检查（HEAD vs commit_id + worktree 脏检测，git 本地操作）；跳过仓的拓扑按归属复用、links/overview 合并重算；变更仓重跑 analyze_repo。
3. **结果透传**：per-repo 条目增加 `mode` + `changes`（affected_modules/cascade_modules/overview_stale/no_changes）。
4. **文档同步**：《管理模型》§4.1/§5 增量分支、registry `analyze_workspace` 描述、README 中英文。
5. **测试**：三档分派（colocated + centralized）、centralized 命名空间防静默退化回归（先红后绿）、跳过仓拓扑复用、锚点不可用降级、prompt 渲染。
6. **验证**：全量 pytest + ruff（基线见任务记忆）。

## 8. 决策记录（备选与否决理由）

| 备选 | 否决理由 |
|------|---------|
| 新增增量工具（refresh_workspace 等） | 增量三件套已存在，新工具违反单点收敛 |
| analyze_workspace 加 `force`/`repos` 参数 | 显式参数把"哪些仓变了"推回调用方，agent 会无脑全量；零配置可推导即够 |
| 以 `analyze_changes` 驱动增量 | 定位是 review 爆炸半径，不刷新图/路由，无 cascade/overview 语义 |
| 新造 `.meta/analysis_state.json` 锚点 | `generation_info.commit_id` 已是锚点，重复造轮子 |
| A2 watch 单次增量同步进 v1 | 新缝成本高，解析非主要成本，记为后续优化 |
| 未变更仓仍重跑 analyze_repo（纯改写层增量） | 跳过检查只需 git 本地操作，解析成本可省且无正确性风险 |
