# ADR-0020: 生成状态收敛到 job，更新路径采用算子计划

- 状态：已接受
- 日期：2026-10-25
- 决策人：用户（grill-with-docs 一轮六问，按推荐拍板）
- 关联：`docs/Qoder-RepoWiki-逆向函数级借鉴分析-2026-10.md` · ADR-0005（增量决策静默边界）· ADR-0009（supersede 与写入检查）

## 背景

Qoder CN RepoWiki 的函数级逆向报告给出了 5 条可借鉴点。经代码核对，本仓在生成/更新路径上有四个真实缺口：

1. `overview.md` 存在即让所有模块 agent 提前返回（`src/be/caw_backend.py:232-235`、`src/be/pydantic_ai_backend.py:72-74`），缺页不会补；
2. 单模块异常被 `continue` 吞掉后仍以成功退出（`src/be/documentation_generator.py:226-228`）；
3. `--update` 只删受影响 `.md`（`cli/commands/generate.py:142-201`），而 `first_module_tree.json` 存在即跳过重聚类（`documentation_generator.py:350-353`），新模块永远进不来；
4. Web 端重启丢弃 `processing` 作业（`src/fe/background_worker.py:73-74`）。

现有状态载体：`DocumentationJob` 仅存内存；`metadata.json` 只有时间戳与文件清单；`module_tree.json` / `page_manifest.json` 分别是模块树与页面写后基线；SQLite 里没有 run/job 表。

## 决策

### 1. `job` 是生成状态的唯一真源（Q2/Q3）

命名复用 `job`，**不引入 `run`**——本仓已有 `job` / `session` / `task` 三个名词，第四个近义词只会增加歧义。

- 持久化到 `.meta/job.json`，单文件、原子写，在状态迁移点写入而非只在结束时写。
- 字段：`job_id` / `surface`(mcp|cli) / `phase` / `attempt` / `base_commit` / `pages{planned,written,missing}` / `degraded[]` / `artifacts`。
- `artifacts` **只存指向既有文件的指针**，不复制模块树、页面基线或计划正文。
- 不新增 SQLite 表；`metadata.json` 保留为对外摘要，新增 `job_id` 指回账本。
- 账本永不入库：`.gitignore` 与 `TEAM_LAYOUT_REBUILDABLE_FILES` 登记之外，写入路径的
  `auto_stage` 对 `job.json` 硬跳过——旧仓库的 .gitignore 可能早于本 ADR，不能指望它。
- **MCP 路径是唯一真源**；CLI 老管线只修缺口 1、2，不承诺断点续跑。账本的创建与关闭只发生在 MCP 路径；legacy 管线（`src/be/documentation_generator.py`）遇到已有账本时只追加页面写入与 `degraded` 记录，**不创建也不关闭**——否则一次 `codewiki generate` 会把 MCP 的续跑状态覆盖成"完成"。

### 2. 续跑按档位，`overview` 不再是全局短路（Q5）

档位：`persisted`（job 与 `base_commit` 均匹配）/ `partial`（补 `pages.missing`）/ `as_leaf`（父模块聚合失败，产出叶页并记降级）/ `rebuild`（锚点不匹配或 job 损坏）。

续跑粒度是**页面**。`overview.md` 是否存在只影响 overview 页自身，不影响模块 agent 的调度。缺失页 key 通过 `analyze_repo` 的 `job.missing_pages` 交给宿主 Agent，`generate-wiki` 工作流据此只补缺失页。任何降级都写入 `degraded[]`，不靠日志。

### 3. 更新路径用算子计划，执行器逐算子落账（Q5）

- 算子集固定四类：`add_subtree` / `replan_subtree` / `delete_subtree` / `update_page`。
- 生产端**确定性**：输入 = changed files + module tree + page manifest + base commit，产出 `.meta/change_plan.json`；同输入必得同计划。
- LLM **只在无法确定性推导处介入**（新模块的 slug/标题，候选 >1 时），其余不调 LLM。
- 执行器按 `delete → add（父先于子）→ replan → update` 顺序执行；每算子有 `op_id` 与 `pending/done/failed/skipped`，失败不中断其余算子，重放跳过 `done`，整体 `phase=degraded`。
- 计划与 `page_manifest` 不合并：一个是"接下来改什么"，一个是"已写成什么样"。
- **落地状态（2026-10-26）**：MCP 路径已实现（`codewiki/mcp/tools/change_plan.py`）。`save_module_tree` 在树未变且 job 未换时重放原计划，否则重建并立即执行删除；`write_doc_file`/`edit_doc_file` 落页即把对应算子置 `done`；`close_session` 把未执行的 `pending` 结算为 `failed`（页仍缺失）或 `skipped`，并以「本次尝试未完成算子数」参与 `finish_job` 的降级判定（不复用历史 `degraded[]`，避免恢复后永远无法回到 `done`）。本次尝试的 `pages.planned_keys` 由计划驱动，未触及的既有页不再被误判为缺失。顺带修复 `first_module_tree.json` 缓存挡新模块的问题：`module_tree_coverage_gap` 非空即重聚类。CLI 尚未消费计划（仍只有页面删除 + 覆盖率缺口重聚类），抽公共函数留给下一片。

### 4. 增量降级原因码，阈值先 observe（Q4）

`changes.reason` 与既有 `changes.method` 分工：method 说"怎么比的"，reason 说"为什么没走增量"。

- 先启用能真实触发的原因码：`no_changes` / `incremental` / `full_anchor_missing` / `full_cache_missing` / `full_non_git_no_snapshot` / `full_commit_lost` / `full_too_many_files` / `full_too_many_commits`。
- `full_no_common_ancestor` 暂不编码——当前是直接 commit diff，没有祖先检查，编码一个永不触发的值只会制造假信号。
- 文件数/提交数阈值首版 `observe`：只记 `would_downgrade`，不改行为。晋级 `enforce` 须用离线数据证明收益。

### 5. 配置诊断列表取代静默 `{}`（Q6）

`schema.yaml` 解析改为 `(data, diagnostics)` 双返回，错误码 `schema_missing` / `yaml_parse_error` / `unknown_doc_type` / `unknown_section` / `directory_collision`；诊断 fail-open（warning 回传，不阻断生成）。**不引入 `wiki_plan.yaml`**——第二种项目级配置格式必然双源。

### 6. 明确排除

- `wiki_run / wiki_article / wiki_artifact` 表结构：概念已被 job + 既有三处真源覆盖，不建第四处。
- LLM 预算选档 agent：延后为确定性估算，等算子计划落地后再挂。
- atlas 式三阶段流水线 / decision agent：本仓是工具层，编排归宿主 Agent。

## 后果

- 正面：中断可续、缺页可补、新模块可进树、降级可见；全部基于文件，无新依赖。
- 代价：引入第四个状态文件（`.meta/job.json`），必须靠"job 只存指针与状态、不存内容"这条约束防止它变成第四份真源；CLI 与 MCP 共用计划生成函数需要一次抽公共层。
- 风险：`pages.missing` 与 `page_manifest` 可能漂移——以 manifest 为准，job 的 missing 是派生视图，写入前重算。

## 复核

- 为什么不抄 `wiki_run` 表：本仓三处真源已在文件层、可被 git 管理，SQLite 表会带来"哪个是真的"的新问题。
- 为什么不引入 `run`：`job` 已在 CLI/Web 两层表示"一次生成"，改名只会制造迁移成本。
- 为什么阈值先 observe：与 `low_adoption`、draft 笔记同一纪律（tri-state gate），且"降级省下的钱 > 多生成的钱"尚未被数据证明。
