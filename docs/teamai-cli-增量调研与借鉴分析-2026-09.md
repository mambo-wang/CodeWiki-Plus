# teamai-cli 增量调研与借鉴分析（2026-09-10）

> 增量对象：**Tencent/teamai-cli** @ `9e7adc7`（2026-09-10），本地克隆 `D:\repos\teamai-cli`
> 基线：`docs/teamai-cli-调研与借鉴分析.md`（2026-08-21，v0.20.0）
> 视角：自上次借鉴以来，哪些新合入值得 CodeWiki 借鉴
>
> 调研方法：`git log --since=2026-08-21`（250 个 commit）+ CHANGELOG（0.21.0 / 0.22.0 / 0.23.0 / Unreleased）
> + 新增设计文档与关键源码实读。所有论断落到 `文件:行号`，相对 teamai-cli 仓库根。

---

## 0. 增量概览

| 项 | 上次（2026-08-21） | 本次（2026-09-10） |
|---|---|---|
| 版本 | v0.20.0 | v0.23.1 / v0.24.0-beta.5 |
| 新增提交 | — | **250** |
| 新增设计文档 | — | `data-directory-layout.md`、`multi-project-management.md`、`gitcode-provider.md` |
| 主线工作 | Harness 分发 + 经验知识库 | **数据布局重构（#374）** + **多项目维度（#375）** + **摩擦信号与度量（#336/#368）** |

一句话：这 20 天 teamai 把力气花在了**工程地基**（数据分区、锁、多项目隔离）和**信号采集**（摩擦、成本、趋势）上，
恰好是上次调研结论中 CodeWiki 最缺的两块（使用信号闭环、生命周期数据）。

---

## 1. 数据分区 + 双锚点 + 原子锁（#374）— 工程价值最高

**问题**：机器数据（实测 18MB：团队仓 clone 12MB + 技能资源 4.1MB + 索引 1.8MB）堆在业务仓 `.teamai/`，
导致工作区残留、子目录/ worktree 失明、多项目数据混在一个全局目录。
**解法**：迁到 `~/.teamai/projects/<slug>/`，业务仓零残留。

### 1.1 slug 用哈希而非路径转义

- `slug(anchor) = <safe-basename>-<sha256(normalized anchor)[:16]>` — `src/utils/partition.ts:105-112`
- 明确论证 8 hex（32 bit）不安全：**针对目标 slug 构造第二原像不到一秒**，会把两个项目的 config/state/env 静默合并；
  64 bit 把碰撞搜索推到 ~2^32 次哈希之外 — `src/utils/partition.ts:96-104`
- 大小写归一化要探测**锚点所在卷**而非 HOME（两者可能在不同卷、不同大小写敏感性）；
  探测失败回退「区分大小写」（保守：永不合并两个不同锚点）— `src/utils/partition.ts:25-85`

### 1.2 两个锚点必须分开

```
projectAnchor = git worktree list --porcelain 首项   → 主检出，全 worktree 共享 → 分区身份
workspaceRoot = git rev-parse --show-toplevel         → 当前检出，逐 worktree 不同 → 资源落点
```
- 资源必须写 `workspaceRoot`：AI 工具（Claude/Codex/CodeBuddy/OpenCode）只从启动目录向上扫到**当前**仓库根，
  没有工具会顺着 `git-common-dir` 找回主检出，且 gitignore 文件不会出现在新 worktree — `docs/designs/data-directory-layout.md:29-48`
- **不能用 `git-common-dir`**：`--separate-git-dir` 下 common dir 在检出之外（如 `gitdirs/proj.git`），
  其父目录被不相关仓库共享会撞车；且它在主仓返回相对路径 `.git` — `docs/designs/data-directory-layout.md:50-66`

### 1.3 原子锁（旧实现是 check-then-write）

- `O_EXCL` 独占创建，payload `{pid, startedAt, owner}`（随机 owner token）
- `EEXIST` 时只回收**陈旧**锁（pid 已死 / 内容不可解析），回收过程**串行化在原子创建的哨兵之后**并以 rename 落盘，
  避免多个回收者都以为自己拿到了锁；活锁持有者直接返回 busy
- `releaseLock()` 只删 on-disk owner 与本进程 token 匹配的锁 — `docs/designs/data-directory-layout.md:76-94`

### 1.4 迁移与反查

- 旧布局自动迁移：非破坏性备份（git-ignored）、可恢复中断的迁移、clone 后 smoke-check — `CHANGELOG.md:10`
- slug 是单向哈希，分区内 `anchor` 文件是**唯一反查通道**（init 与 migration 都写）— `src/utils/partition.ts:128-148`

### 对 CodeWiki

> **修正（2026-09-10 复核本仓代码后）**：初稿称「缺三件套」，不准确。
> ① 锁：本仓 `codewiki/src/store.py:166-189` 用 OS 文件锁（Unix `flock`、Windows 在线程锁临界区内 unlink），
> 锁集中在 `.meta/locks/<sha256[:20]>.lck`——**比 teamai 的 `O_EXCL + owner token + 陈旧回收` 更强**
> （flock 崩溃自动释放，后者是没有 flock 时的替代品，需要自己检测陈旧）。
> ② 身份解析：hooks 优先取宿主注入的 `*_PROJECT_DIR` 环境变量（`codewiki/hooks/task_session_start.py:82`、
> `capture_session_end.py:127`），属「显式参数 > 布局推导」，比从文件系统推导 anchor 更靠前。
> ③ 分区：他们的目标是「机器数据搬出业务仓」，而我们的 repowiki 是**随代码版本化的资产**
> （`git_sync` 要提交推送），搬出去等于砍掉主线——模型相反。
> 结论见 §6 处置表：**excluded**。

---

## 2. 摩擦信号从 CodeBuddy transcript 确定性提取（#336）— 补上次结论的缺口

上次结论②：「把使用信号接进排序与生命周期，CodeWiki 的 `retrieval_stats.db` 只写不读」。
这次 teamai 把信号采集做实了，且**全部是客观痕迹，不靠 LLM 自评**。

### 2.1 信号定义

| 信号 | 含义 | 判定 |
|---|---|---|
| `interrupt` | 用户打断 | user 消息文本以 `[Request interrupted by user` 开头 |
| `toolReject` | 人拒绝工具 | `tool_result.is_error=true` 且命中拒绝标记 |
| `toolError` | 工具真失败 | `is_error=true` 且**不是**用户拒绝 → AI 被迫重试，强信号 |

- 定义与区分理由 — `src/dashboard-collector.ts:124-134`
- 判定时把「用户拒绝」与「真失败」分开计数 — `src/dashboard-collector.ts:384-390`

### 2.2 CodeBuddy 的特殊路径（对本项目最直接可用）

`index.json` 只是骨架（tokens + prompt 列表），**摩擦信号必须从 `messages/*.json` blob 读**：

- `toolReject`：`role==='assistant'` 的 blob，`extra` 是 **JSON 字符串**（需二次解析）→ `extra.toolStatus[callId]`，
  `status==='cancelled'` 且 `result.errorMessage` 含固定串 `User rejected this command`
  → 该固定串是 CodeBuddy 用户拒绝专用，天然排除系统自动取消（UNFINISHED TOOL / MalformedToolArgs）与中断残留
- `toolError`：`role==='tool'` 的 blob，`message` 二次解析 → `message.content[]` 中 `isError===true` 的元素；
  已执行与被拒绝的工具都是 `isError===false`，所以只计真执行错误
- 有界扫描：blob 上限 `CODEBUDDY_BLOB_MAX_COUNT=2000`，文件超 `INTERVENTION_SCAN_MAX_BYTES` 直接放弃返回 0，
  保证 Stop hook 不卡 — `src/dashboard-collector.ts:596-725`

### 对 CodeWiki

> **修正（2026-09-10 复核本仓代码后）**：初稿称「`friction_score` 恒为 0，是缺口」，不准确。
> ① 摩擦打分已存在：`codewiki/mcp/tools/friction.py:12`（correction×20 + interrupt×20 + repeat×15 + 规模档，
> `min_user_turns=4` 硬门槛），capture 时写入 frontmatter（`capture_conversation.py:365-381`）。
> ② 工具失败信号**已经在 raw 文本里**：`codewiki/src/tool_digest.py:213-237` 把 `is_error` 的结果
> 保留为 `[tool-error: …]` 行——只是 `friction.py` 没有计数。
> ③ 使用信号闭环已部分存在：`adoption.py`（agent 声明采纳）+ telemetry + usage heat 排序权重。
>
> 因此本项的增量只剩「给 `friction.py` 加一个 `[tool-error: …]` 行计数器」，
> 而**是否值得做要由实测缺口决定**——见 §6.3 探测结果。

---

## 3. 多项目维度：role × project 正交（#375）

- 两个「project」不能混：#374 = **路径分区**（路径→slug 的纯函数，解决*数据放哪*）；
  #375 = **逻辑项目**（admin 在 `manifest/projects.yaml` 定义，解决*知识分发给谁*），一个 path-slug 映射 0..N 逻辑项目
  — `docs/designs/multi-project-management.md:42-55`
- 命名空间取**并集**而非优先级覆盖：「HAI dev」同时需要通用 dev 技能（role）+ HAI 专有知识（project）— 同文档 `:110-120`
- `roles.yaml` 的 learnings 字段**继续忽略**，learnings 命名空间只由 project 提供，否则语义混乱回归 — 同文档 `:68-113`

**向后兼容 pivot（最值得抄的不变量）**：`learnings/` 根目录的 `.md` 永远全员可见，子目录才是项目私有。
今天全平铺 → 零迁移；根目录同时也是跨项目共享经验的天然位置 — 同文档 `:83-99`

**对 CodeWiki（2026-09-10 复核）**：初稿称「可直接采用」，经 grill 判定为 **excluded**（见 §6）——
他们的 `project` 是**分发维度**（谁收到什么，依赖团队仓 + 角色分发形态），
我们的隔离诉求是**归属维度**（哪个仓 / 哪个 `task_id`）：related ≠ same，拿不准就不合并。

---

## 4. 确定性 AST 与 LLM enrich 双轨（#304）

- WASM tree-sitter 是**可选轨道**：`TEAMAI_SKIP_AST=1` 或依赖 `web-tree-sitter` / 语法 wasm 缺失即降级，不阻断主流程
  — `src/wiki-engine/code-knowledge/ast/index.ts:16-33`
- 解析失败**不静默丢弃**，记为 `PARSE_SKIP` gap；只有「解析出错且没产出任何 symbol/import」才计入 skipped
  — 同文件 `:59-79`
- 图谱对账产出结构化分类：`NO_CODE_MAPPING` / `NO_PRODUCT_DOC` / `API_DOC_NO_IMPL` / `CONCEPT_NOT_IMPLEMENTED`
  与冲突 `STATE_MISMATCH` / `COUNT_MISMATCH` / `BEHAVIOR_MISMATCH` — `src/wiki-engine/knowledge-reconciler.ts:41-63`
- 增量暴露为命令：`teamai codebase` 现已暴露 wiki reconciliation 与 deep-enrich（`CHANGELOG.md` Unreleased 之外，见 commit `8bb0548` / `2ddb546`）

**对 CodeWiki**：tree-sitter 我们是主线，可借鉴的是**降级路径 + 失败显式记为 gap**，
以及那套 gap/conflict 分类词汇表——比时间窗判定更能喂给新鲜度/置信度机制。

---

## 5. 其余短平快项

| 合入 | 内容 | 借鉴点 |
|---|---|---|
| #368 | dashboard 新增 `/kb-report` 知识库健康报告页 — `src/dashboard.ts:181-192` | 我们 `lint_wiki` 的 health 只出文本，缺可视化与趋势 |
| #462 / #477 | 会话与成本趋势；「resumed 后失败的 session 要回捞成功数」的口径修正 | 度量口径要有反向修正，否则趋势虚高 |
| #458 / #465 / #476 | learnings 删除跨作用域传播；self 模式 contribute 不清空本地缓存 | 知识删除/归档的传播一致性（我们删除后索引残留是老问题） |
| #378 / #383 / #409 | SKILL.md frontmatter：CRLF/BOM、未闭合 `---` 告警、object 值校验 | 对照自查我们自己的 frontmatter 解析 |
| #380 / #428 / #400 | 声明式团队包安装 `packages install` + npm / Claude plugin 适配器 + 插件变量替换 | skill 安装与分发的声明式形态 |
| #420 / #413 / #462 | Qoder / JoyCode / ZCode 一等公民支持，保留个人规则与原生元数据 | 多宿主适配时「不覆盖用户自有配置」的判定方式 |

---

## 6. 借鉴处置表（2026-09-10 拍板）

### 6.1 判据

**只有实测缺口才做**（Doctrine 归因调优 SOP：先跑探测脚本实测计数，直觉根因必须被数据证伪）。
候选一律落 absorbed / deferred / excluded，**排除必填原因**。

### 6.2 处置

| 合入 | 处置 | 原因 |
|---|---|---|
| #336 摩擦信号升到工具事件级 | **deferred（待实测）** | 数据在 raw 里已有（`tool_digest.py:213-237` 的 `[tool-error: …]`），但缺口未实测；判定见 §6.3 |
| #374 数据分区 + 双锚点 + 原子锁 | **excluded** | 模型相反（我们是「知识随仓库版本化」，他们是「机器数据搬出业务仓」）；锁我们更强（flock）；身份解析我们更靠前（宿主 `*_PROJECT_DIR`）— 详见 §1 修正 |
| #375 role × project 正交 | **excluded** | 他们是**分发维度**、我们是**归属维度**，related ≠ same；且我们没有团队仓分发形态 |
| #304 AST / LLM 双轨 | **excluded** | tree-sitter 在我们是主线不是可选轨道，降级方向相反 |
| #368 KB Health 报告 | **excluded** | 无趋势数据支撑，先有页面等于空壳——成本可见性优先于新造能力 |
| #458/#465/#476 删除传播 | **excluded** | 无真实的删除 / 归档用例（无实测缺口） |
| #380 packages install | **excluded** | 无团队包分发形态，模型不匹配 |
| #378/#383/#409 frontmatter 健壮性 | **不算借鉴项 → 自查 checklist** | CRLF/BOM、未闭合 `---` 告警、object 值校验三条，留作审计我们自家解析器的清单；不立项、不排期 |

**净结果**：8 个候选，0 个直接做、1 个待实测、7 个排除。本轮价值主要在**证伪**：
把初稿夸大的两个「缺口」（摩擦信号、锁）打回原形，并确认 teamai 的知识归属模型与我们相反。

### 6.3 #336 探测结果（2026-09-10 实测）

探测脚本扫 `repowiki/raw/`：统计「含 `[tool-error: …]` 行但 `friction_score == 0`」的会话占比，
阈值 **≥ 20%** 判定为漏检成立。

```
raw 会话总数: 8
frontmatter 无 friction_score 键: 3
含 [tool-error:] 行的会话: 1
其中有 tool-error 但 friction_score==0 (漏检): 0
漏检率（分母 = 含 tool-error 的会话） = 0.0%   → 阈值 20%，未达
```

唯一含 tool-error 的会话（`err=3`）`friction_score=5`，**已被现有打分覆盖，未漏检**。

**结论：#336 → excluded，原因「实测无缺口」。**

⚠️ **样本量警告（不得当作已证否）**：存量 raw 只剩 8 条（其余已蒸馏删除），
含 tool-error 的仅 1 条。0% 的漏检率来自 n=1，**不足以证明没有漏检**，
只能证明「现有样本里没观测到」。若要真正判定，需：
① 积累一段时间不删除 raw（`keep_raw`）后再测；或
② 改用 `repowiki/tasks/` 下已落盘的会话记录做更大样本。
在此之前不立项。

> 落盘分工：本文是「正在想的事」（调研事实 + 处置 + 待测项），存 `docs/`；
> §6.2 中若有机在未来被实测推翻并落地，应以 note 形式沉淀到 `repowiki/notes/`。
