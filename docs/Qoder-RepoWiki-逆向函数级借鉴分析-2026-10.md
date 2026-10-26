# Qoder RepoWiki 逆向报告（函数级版）的借鉴评估

> 评估日期：2026-10-25
> 被评估对象：`/Users/kirito/WORK_rea/qoder-repowiki/REPORT.md`（2026-10-24 函数级更新版）
> 方法：grill-with-docs 一轮六问，全部按推荐拍板；结论前先回代码核对本仓现状
> 产物：本文 + [ADR-0020](adr/0020-update-path-operator-plan-and-job-state.md)

---

## 0. 结论摘要

报告 §9 给了 5 条可借鉴点。结合本仓代码核对，实际去向如下（候选必有去向，排除必填原因）：

| 候选 | 去向 | 落到哪 | 优先级 |
|---|---|---|---|
| §9.1 run 级状态机 | **absorbed（改造）** | 生成状态收敛到 `job`（`.meta/job.json`）+ 分级续跑 | P1 |
| §9.2 增量门显式化 | **partial** | 降级**原因码** + 阈值先 `observe`；不抄 9 码全集 | P2 |
| §9.3 预算先选档 | **deferred** | 确定性估算，等算子计划落地后再挂 | P3 |
| §9.4 计划-算子分离 | **absorbed** | 更新路径算子计划（确定性 diff 产出、可重放） | P1 |
| §9.5 配置诊断回传 | **partial** | `schema.yaml` 诊断列表；不引入 `wiki_plan.yaml` | P2 |
| （报告未单列）分级续跑与降级留痕 | **absorbed** | `persisted / partial / as_leaf / rebuild` + `degraded[]` | P1 |
| §3.2 `wiki_run / wiki_article / wiki_artifact` 表 | **excluded** | 本仓已有三处真源，第四处违反单点收敛 | — |
| §4.3 LLM 预算选档 agent | **excluded** | 与 Doctrine「成本可见性优先于新造能力」冲突 | — |
| §4.3 atlas 三阶段流水线 / decision agent | **excluded** | 本仓是工具层，orchestrator 在宿主 Agent | — |
| §5 云端复用 / 配额 / 上传重试 | **excluded** | 产品模型不同；本仓团队协作走 git，不走中心服务 | — |

一句话：**值得借的是"生成状态可观察 + 更新算子化"，不是 atlas 的表结构，也不是它的 agent 编排。**

---

## 1. 取证可信度复核

在把结论搬进本仓之前，先核对了报告的取证方法本身。

**已验证成立**

- `decideCardsPullStrategy → version_ok`：`pseudo/annotated/cosy_deepwiki.decideCardsPullStrategy.c` 两处返回点（`:126`、`:137`）都是 `&DAT_102788105`，该地址即字符串池首 `version_ok`，成立。
- `decideWikiPullStrategy` 的 5 个返回常量：`:68` / `:70` / `:84` / `:87` / `:93` / `:101` 六处返回点全部是**池首指针**，分别以 `timestamp_ahead_pull` / `skipped_exists` / `incremental_pull` / `no_local_pull` / `skipped` 开头。按 Go `string` 的 ptr+len 双元组判读，这 5 个名字可信。
- `decideInternalMode`（`pseudo/annotated/cosy_atlas_service.decideInternalMode.c`）：确实按 `Progress.SnapshotForJSON` 里值为 `"done"` 的 4 字节项、以及构建记录 `+0x40` 的 kind 字节（`== 2`）分派，三态返回值成立；`runBuildPipeline` 里也存在 `resume_persisted` 的 addTag 字面量。报告 §7 说"枚举名未证实"是诚实的保守标注。
- `runBuildPipeline` / `runUpdatePipeline` 的直接调用边（阶段集合）可信；报告已把"先后次序"单列 §7，没有把推断写成 seen。

**判读时注意的一条方法边界**

Go 把相邻字符串常量放进同一池，所以"池中第二个及以后"的字面量需要 ptr 偏移或 len 佐证，不能按注释里的拼接串直接认领。本次抽查的返回点都是池首，不受影响；但后续如果有人引用 `DAT_1027b5249` 里的 `timestamp_ahead_pull` 段，必须回到调用点确认 ptr 偏移。

**未独立复核**

- 增量门 9 个决策码与日志串的"成对"关系（报告称字符串表成对，我只核了 `IncrementalGate.Evaluate` 存在与调用点，没有逐分支复验）。
- 预算 agent 的档位选择行为（只核到 `resolveBuildBudget` / `runBudgetAgent` 的函数存在）。

这两项不影响本仓结论，因为对应的借鉴项一个是 partial、一个是 deferred。

---

## 2. 本仓现状（代码核对）

### 2.1 四个真实缺口

> 以下四项是评估当天（2026-10-25）的现状。第 1、2 项已在 P1-2 修复（见 §6），第 3、4 项仍待做。

1. **`overview.md` 是全局短路信号**（已修）
   `caw_backend.py:232-235` 与 `pydantic_ai_backend.py:72-74`：只要 overview 已存在，**所有模块 agent 直接提前返回**。续跑语义退化为"overview 在 = 全在"，缺页永远不会补。

2. **失败被吞，仍以成功退出**（已修）
   `documentation_generator.py:226-228` 对单模块异常只 `continue`；随后照常生成 overview 并写 `metadata.json`（`:44-77`）。外部看到的是"生成成功"，实际缺模块。

3. **`--update` 时新模块永远进不来**
   `cli/commands/generate.py:142-201` 的 `_invalidate_affected_modules` 只删受影响的 `<module>.md`；而 `documentation_generator.py:350-353` 只要 `first_module_tree.json` 存在就跳过重聚类。仓库里新增一个顶层模块，更新路径永远不会为它建树。

4. **Web 端重启丢 processing 作业**
   `src/fe/background_worker.py:73-74` 只装载 `completed` 状态，`processing` 作业被静默丢弃。

### 2.2 已有的机制（不要重复造）

| 机制 | 位置 | 说明 |
|---|---|---|
| `DocumentationJob` | `cli/models/job.py:74-104` | 有 job_id/status/timestamp/error，但**仅存内存**（`cli/adapters/doc_generator.py`） |
| `.meta/metadata.json` | `src/be/documentation_generator.py:44-77` | 只有 timestamp / 模型 / commit_id / 文件清单，**无状态、无阶段、无 attempt** |
| `.meta/module_tree.json` + `first_module_tree.json` | `mcp/tools/module_tree.py:130-131` | 工作副本 + 不可变快照；`processing_order.json` 叶优先序 |
| `.meta/page_manifest.json` | `mcp/tools/page_manifest.py:47-103` | 页面→文件基线 + `source_fingerprint`，**是写后基线不是计划** |
| `.codewiki/analysis_cache.db` | `mcp/cache.py` | components / fingerprints / deps / 检索表，**没有 run/job 表** |
| 增量判定 | `mcp/tools/analysis.py:114-155` | `incremental` 布尔 + `cache.is_fresh()`（组件数 > 0）+ 直接 commit diff（`cache.py:941-985`），无祖先检查 |
| 多仓模式 | `mcp/tools/workspace_analyzer.py:521-530` | `skipped / incremental / full / deferred` 四态，已有枚举雏形 |
| 变更原因回传 | `mcp/tools/analysis.py:347` | `changes.json` 已落盘，含 `method`（git/fingerprint/mtime） |

### 2.3 架构前提：工具层，不是流水线

atlas 每个阶段是"一张 agent 图 + BuildPrompt/ParseOutput/Stage 三件套"，服务端自持 LLM。本仓恰恰相反：MCP 工具做确定性收集与落盘，推理交给宿主 Agent 按 `get_prompt` 工作流调用。因此：

- 照抄 decision agent / budget agent，会在现有工作流之外长出**第二个 orchestrator**；
- 能借的是**数据形状与状态词汇**，不能借的是**自驱流水线**。

---

## 3. 采纳项

### 3.1 P1：生成状态收敛到 job（借用 §9.1，改造落地）

**名词**：复用 `job`，不引入 `run`。本仓已有 `job`（`cli/models/job.py`）、`session`（会话绑定，ADR-0006）、`task`（任务记忆），第四个近义词只会增加歧义。

**存储**：`.meta/job.json`，单文件、原子写（tmp + rename），在状态迁移点写入，而不是只在结束时写。

```yaml
job_id: "<uuid>"
surface: "mcp"              # mcp | cli
phase: "analyzed"           # analyzing | analyzed | planned | generating | finalizing | done | degraded | failed
attempt: 2
resume: "partial"           # persisted | partial | as_leaf | rebuild
base_commit: "<sha>"
started_at: "..."
updated_at: "..."
pages: {planned: 42, written: 38, missing: ["foo"]}   # key = page stem
degraded:                   # 降级留痕（对应 atlas 的 stage.degraded）
  - {stage: "module", code: "module_failed", detail: "foo: <错误摘要>"}
artifacts:                  # 只存指针，不复制内容
  meta_dir: ".meta"
  module_tree: ".meta/module_tree.json"
  page_manifest: ".meta/page_manifest.json"
  change_plan: ".meta/change_plan.json"
  metadata: ".meta/metadata.json"
```

关键约束：

- **不新增 SQLite 表**。`wiki_run / wiki_article / wiki_artifact` 是对应 atlas 单库设计的；本仓的模块树、页面基线、元数据已经在文件里，再建表就是第四处真源。
- **`artifacts` 只存指针**。job 是"这次生成长什么样"的账本，不是内容的第二副本。
- **`metadata.json` 保留**，作为对外摘要，新增 `job_id` 字段指回账本。
- **MCP 路径是唯一真源**。CLI 老管线（README 标注"仍然可用"）只修 2.1 的缺口 1、2，不承诺断点续跑。账本的创建与关闭只在 MCP 路径；legacy 管线遇到已有账本时只追加页面写入与 `degraded`，不创建、不关闭——避免一次 `codewiki generate` 就把 MCP 的续跑状态覆盖成"完成"。

### 3.2 P1：分级续跑（借用报告 §7 旁证的思路，不抄枚举名）

atlas 的 `decideInternalMode` 本质是"按进度快照决定续跑档位"，而不是布尔"有没有产出"。本仓的对应设计：

| 档位 | 触发 | 行为 |
|---|---|---|
| `persisted` | job 存在且 `base_commit` 匹配 | 从 `phase` 续跑，已写页面跳过 |
| `partial` | job 存在但 `pages.missing` 非空 | 只补缺失页，不重写已完成的 |
| `as_leaf` | 父模块聚合失败 | 产出叶页并记 `degraded: parent_aggregate_failed`，不再无限重试 |
| `rebuild` | `base_commit` 不匹配或 job 损坏 | 全量重建（并记原因） |

硬性要求：**`overview.md` 不再作为全局短路信号**。续跑粒度是页面，不是 overview。（P1-2 已落地：两个 backend 共用一个 `module_page_present` 判定，父模块页同理。）

### 3.3 P1：更新路径算子计划（借用 §9.4）

**算子集固定四类**（先收敛，后续按需扩）：

| 算子 | 触发（确定性） | 必填 |
|---|---|---|
| `add_subtree` | 变更文件映射到的组件不属于任何模块 | `slug` / `scope` / `parent` |
| `replan_subtree` | 模块的组件集变化超过阈值（默认 >50% 或模块被清空） | `module` / `reason` |
| `delete_subtree` | 模块下所有组件文件都已消失 | `module` |
| `update_page` | 页面 `source_fingerprint` 变化 | `page` / `reason` |

设计要点：

- **生产端确定性**：输入 = changed files + module tree + page manifest + base commit，产出 `.meta/change_plan.json`。同一组输入必须产出同一份计划（可回放、可测试）。
- **LLM 只在无法确定性推导处介入**：新模块的 slug / 标题（`add_subtree` 的命名），且候选 >1 时才调用。其余一律不调 LLM——避免"规划"变成第二个 agent 的入口。
- **执行器逐算子落账**：每个算子有 `op_id`，执行状态（`pending / done / failed / skipped`）写回计划文件；失败不中断其余算子，整体 `phase=degraded`。重放时跳过 `done`。
- **顺序**：先 `delete_subtree` → 再 `add_subtree`（父先于子）→ `replan_subtree` → `update_page`。
- **与 `page_manifest` 的关系**：manifest 是"已写成什么样"的基线，计划是"接下来要改什么"，两者不合并。

### 3.4 P2：增量降级原因码 + 阈值 observe（借用 §9.2 的一半）

现有 `changes.method` 回答"怎么比的"（git / fingerprint / mtime），缺的是"**为什么没走增量**"。新增 `changes.reason`：

`no_changes` / `incremental` / `full_anchor_missing` / `full_cache_missing` / `full_no_common_ancestor` / `full_non_git_no_snapshot` / `full_commit_lost` / `full_too_many_files` / `full_too_many_commits`

- 写进已有的 `changes.json`（`analysis.py:347`），不改响应形状，只加字段。
- 引入 `analyze.incremental.max_files` / `max_commits` 两个阈值，**首版 `observe`**：只记录 `would_downgrade: true` + 计数，不改变行为。晋级 `enforce` 需要离线数据证明"降级省下的钱 > 多生成的钱"。
- 不做祖先检查就先不给 `full_no_common_ancestor` 编码——目前是直接 commit diff（`cache.py:941-985`），编码一个永远不会触发的值只会制造假信号。

### 3.5 P2：`schema.yaml` 诊断列表（借用 §9.5 的做法，不引入第二种配置格式）

现状：`page_router.py:60-69` 解析失败直接 `{}`，等于静默关掉页面路由；`prompt_server.py:194-205` 遇未知 `doc_type` 静默回退。

改为 `(data, diagnostics)` 双返回：

```json
{"code": "yaml_parse_error", "path": "repowiki/schema.yaml", "line": 12, "message": "..."}
```

- 错误码：`schema_missing` / `yaml_parse_error` / `unknown_doc_type` / `unknown_section` / `directory_collision`。
- **fail-open**：诊断不阻断生成，作为 warning 回传给 `init_wiki` 与生成前的预检响应（与"写入检查 fail-open"同一纪律）。
- **不引入 `wiki_plan.yaml`**：本仓的项目级配置是 `<output_dir>/schema.yaml`，再支持一套 Qoder 的配置格式就是双源漂移。

---

## 4. 延后项

**确定性预算估算**（报告 §9.3 的降级版）

不引入 LLM budget agent。等算子计划落地后，用计划本身算代价：`ops` 数量 × 单页平均 token → 在 `analyze_repo` / 计划响应里报"本次预计 N 页 / M tokens"。只报不用，符合 Doctrine「成本可见性优先于新造能力」。

现在不做的原因：没有算子计划时，估算只能按文件数拍脑袋，误差大于价值。

---

## 5. 排除项与理由

| 排除 | 理由 |
|---|---|
| `wiki_run / wiki_article / wiki_artifact` 表结构 | 概念已被 job + 既有三处真源覆盖；单点收敛优先。`wiki_article` 的 `parent_id/slug/depth/ordering` 形状若将来需要，加在 `page_manifest` 条目上，不建新表 |
| LLM 预算选档 agent | 成本可见性优先；且会引入一个只在生成前跑一次的 LLM 依赖 |
| atlas 三阶段流水线 / decision agent | 工具层不做 orchestrator；宿主的 `get_prompt` 工作流已是编排入口 |
| `wiki_plan.yaml` 兼容 | 第二种项目级配置格式，必然双源 |
| 云端复用 / 配额扣减 / 卡片上传重试 | 产品模型不同：本仓团队协作走 git + `sync_metadata` 等价物，没有中心服务 |
| 报告 §9.3 的"失败回退文件计数" | 回退逻辑本身可借，但不值得单独为它建 agent；并入第 4 节的确定性估算 |

---

## 6. 落地顺序与验收

| 步骤 | 内容 | 验收（可自动化） | 状态 |
|---|---|---|---|
| P1-1 | `.meta/job.json` + 状态迁移写入 | 生成中途 `kill -9`，二次运行走 `partial` 而非全量；job 文件可解析 | 已落地（`codewiki/mcp/tools/job_state.py` + `tests/test_job_state.py`） |
| P1-2 | 修两个洞：overview 全局短路、异常被吞 | 删除某模块页后重跑，该页被补齐；模块失败时退出码非 0，且已存在 job 账本时 `phase=degraded`、`degraded[]` 记 `module_failed` | 已落地（`src/be/backend.py:module_page_present` + `documentation_generator.py:ModuleGenerationError` + `tests/test_generation_gaps.py`） |
| P1-3 | 算子计划（先 MCP，再抽公共函数给 CLI） | 新增顶层模块后更新，产生 `add_subtree` 且新页生成；同输入两次计划字节一致 | 已落地（MCP；`codewiki/mcp/tools/change_plan.py` + `module_tree.py:save_module_tree` + `doc_writer.py` 写入即结账 + `close_session.py` 收尾 + `cluster_modules.py:module_tree_coverage_gap` + `tests/test_change_plan.py`） |
| P2-1 | `changes.reason` + 阈值 observe | `changes.json` 含 reason；超大 diff 只记 `would_downgrade`，行为不变 | 待做 |
| P2-2 | schema 诊断列表 | 损坏的 `schema.yaml` 返回诊断而非 `{}`；生成不中断 | 待做 |
| P3 | 预算估算 | 计划响应含预计页数/token，不改变行为 | 待做 |

P1-1 是纯增量（只写文件、不改判定），应最先落地，用来给后面所有步骤提供可观察底座。P1-2 之后，缺页可补、失败可见：跳过粒度从"整轮"收到"单页"，单模块异常聚合为 `ModuleGenerationError`，CLI 以非 0 退出，legacy 管线把失败与页面写入镜像进**已存在**的账本（它不创建、不关闭账本）。

`resume` 已接进 MCP 生成流程：`analyze_repo` 的 `job` 字段返回档位与 `missing_pages`（缺失页 key），`generate-wiki` 工作流据此只补缺失页（`partial`）、无缺页时直接去收尾（`persisted`）、基线变动时全量重建（`rebuild`）。CLI 侧没有账本，靠页面级跳过获得同样的粒度。

P1-3 之后，MCP 第二次及以后的 `save_module_tree` 返回 `change_plan`：树未变且仍属同一 job 时重放原计划（不重置状态），否则按 changed files + 新树 + `page_manifest` 重新产计划，删除算子由 Python 立即执行，其余算子等 `write_doc_file`/`edit_doc_file` 落页时逐条置 `done`；本次尝试的欠账集合（`pages.planned_keys`）改为计划要求的页，避免未触及的模块被误判缺失。CLI 尚未消费计划：`--update` 仍是页面删除 + 缓存树覆盖率缺口触发的重聚类，抽公共层留待 P1-3 的第二片。

---

## 7. 与既有约束的关系

- **单点收敛**：job 不复制模块树/页面基线；算子计划的生成函数先落 MCP（`change_plan.py`），CLI 抽公共层是后续片。
- **不静默失败**：`degraded[]` 是这条纪律在生成路径上的落点；不再用"warn 后继续"代替。
- **tri-state gate**：增量阈值先 `observe`，与 `low_adoption`、draft 笔记同一纪律。
- **候选必有去向**：本文第 0 节表格即为本轮候选的完整去向。
- **成本可见性优先**：预算估算延后，先让计划本身可见。
