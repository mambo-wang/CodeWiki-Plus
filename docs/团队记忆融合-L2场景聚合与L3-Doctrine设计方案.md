# 团队记忆融合 · 阶段二：L2 场景聚合与 L3 项目 Doctrine 设计方案

> 本文是 [`team-memory-fusion-feasibility.md`](./team-memory-fusion-feasibility.md) 可行性评估的下一阶段落地设计，借鉴对象为 TencentDB-Agent-Memory（下称 TAM）的 code/work 模式分层记忆管线，机制分析见 [`TencentDB-Agent-Memory-记忆提取机制分析.md`](./TencentDB-Agent-Memory-记忆提取机制分析.md)。
> 范围：只含设计，不含实现。日期：2026-08-17。

## 一句话结论

**L0/L1 已随阶段一落地（capture_conversation / distill_conversation / 任务记忆），本阶段补齐 L2（场景聚合）与 L3（项目 Doctrine）两层**：新增 `consolidate_notes` 与 `refresh_doctrine` 两个 Mode C 工具，把碎片笔记升级为有限数量的工作方法场景块，再压缩为一份 ≤1200 字的项目操作原则；触发沿用"计数器信号 + 显式调用"形态，不引入任何常驻调度与向量依赖。预计总工作量 **2–3 人周**。

---

## 1. 背景与现状

### 1.1 阶段一已完成的 TAM 对齐

代码注释已明确按 TAM 门控对齐（`_should_capture_l0`、`_should_extract_l1`），当前分层现状：

| TAM 层级 | TAM 实现 | CodeWiki-CN 现状 | 差距 |
| :--- | :--- | :--- | :--- |
| L0 原始对话 | l0-recorder（JSONL + SQLite 索引） | ✅ `capture_conversation` → `raw/`（sha256 去重、session supersede、宽松质量门） | 无 |
| L1 原子记忆 | LLM 提取四类工作记忆 + 两阶段去重 | ⚠️ `distill_conversation` → notes（7 类型、draft 闸门、严格质量门） | 去重只有标题 Jaccard（阈值 0.6），`merge` 仅追加 provenance 不合并正文；无 priority 评分、无情境切分 |
| L2 场景块 | 沙箱 LLM agent 维护 ≤15 个方法场景块 | ⚠️ 无实体。仅 `note_clusters` lint（同模块同类型 ≥3 条报 info）+ `consolidate` prompt 手动合并指引 | **无聚合产物、无容量管理、无热度、全靠 agent 自觉** |
| L3 项目原则 | Team Operating Doctrine（≤1200 字、六维度、持续压缩） | ❌ 完全缺失 | 无 |
| 分层召回 | L3+L2 稳定注入 system、L1 hybrid 检索 | ✅ `query_wiki` 渐进式阅读（overview/directory/detail）+ `retrieval_stats.db` 热度统计 | overview 模式未注入高层知识 |

### 1.2 核心问题

1. **笔记扁平堆积**：confirmed 笔记随时间线性增长，同主题碎片分散在多个文件，agent 检索到的是零散点状知识而非结构化方法；
2. **合并只有信号没有管道**：`note_clusters` 报出聚类、`get_prompt('consolidate')` 给了四步手动指引，但没有任何工具承载合并的状态流转（哪些笔记已被吸收、计数器归零、溯源记录），全靠宿主 agent 自觉，实际不会稳定发生；
3. **没有"项目级原则"载体**：AGENTS.md 靠人工维护，无法从已确认的 decision/pitfall/lesson 中自动演化；每个新接手的 agent 都要重新踩一遍已有共识；
4. **蒸馏质量缺纪律**：`_DISTILL_SYSTEM` 没有 priority 分档（低价值笔记照收）、没有情境标签（为聚合铺路）、缺少"个人建议≠团队决策""AI 输出须被采纳"等归因约束。

---

## 2. 目标与非目标

### 2.1 目标

1. 建立 **L2 场景块层**：把 confirmed 笔记聚合为 ≤15 个"工作方法场景块"（SOP、判断逻辑、禁忌、原则、经验），UPDATE-first、容量受控、热度可观测；
2. 建立 **L3 Doctrine 层**：一份 ≤1200 字的项目操作原则（Project Operating Doctrine），从 L2 与 confirmed 笔记持续压缩演化，作为"自动演进的 AGENTS.md 内核"；
3. 提升 **L1 蒸馏质量**：提取纪律进 prompt、priority 分档、情境标签、两阶段去重（BM25 召回 + agent 判定）；
4. 全链路保持**现有设计约束**：工具无状态不内嵌 LLM、永不自动蒸馏、人工确认闸门、零依赖检索、确定性门控。

### 2.2 非目标（明确不借鉴 TAM 的部分）

| TAM 组件 | 不借鉴原因 |
| :--- | :--- |
| Redis 定时器 / TimerScanner / PipelineWorker / 分布式锁 | CodeWiki 是无状态 MCP 工具链、宿主 IDE 驱动，无常驻服务；引入调度基础设施违反零配置哲学 |
| 每 N 轮对话自动触发的推送模式 | 违反"采集与蒸馏严格分离、永不自动蒸馏"约束；改用计数器信号 + 显式调用 |
| 向量 embedding 检索 | 零依赖 BM25 是本项目卖点（手写 BM25 + SQLite + jieba 可选）；两阶段去重的召回级用现有 BM25 即可 |
| Skill 资产体系（版本快照/乐观锁/资源文件） | 远期 backlog；L2/L3 落地后已覆盖大部分经验沉淀需求 |
| 多租户隔离 / ACL / Memory Hub | 单仓库工具，无此需求 |

---

## 3. 总体设计

### 3.1 分层数据流

```text
【已有（阶段一）】
IDE 对话 ──capture_conversation──▶ repowiki/raw/（L0，暂存区，不进检索）
                                        │ distill_conversation（显式、Mode C）
                                        ▼
                              repowiki/notes/（L1，status=draft）
                                        │ confirm_note（人工闸门）
                                        ▼
                              confirmed 笔记（status=stable）

【本阶段新增】
confirmed 笔记 ──consolidate_notes（显式、Mode C）──▶ wiki/scenarios/*.md（L2 场景块，≤15 个）
                                                            │ refresh_doctrine（显式、Mode C）
                                                            ▼
                                                  wiki/doctrine.md（L3，≤1200 字）
                                                            │
                                                            ▼
                                        query_wiki(mode=overview) 注入 / AGENTS.md 引用
```

### 3.2 设计原则（与 TAM 的取舍对照）

| 原则 | TAM 做法 | 本项目适配 |
| :--- | :--- | :--- |
| LLM 在哪里 | 服务端自持 LLM，异步管线 | **宿主 agent 即 LLM**，工具只做协议与确定性簿记（Mode C：prepare → agent 读文件推理 → submit） |
| 触发 | 阈值 + 空闲定时器 + 级联状态机（推送） | **计数器信号 + 显式调用 + 主动提醒**（拉取）：`wiki_stats` / `get_task_context` 露出计数器；confirm_note 越线时工具返回结构化提醒，agent 须先询问用户、经同意才执行（§4.5.2）；对齐既有 `pending_raw_count` 模式 |
| 合并判定 | 向量/FTS 粗召回 + 批量 LLM 精判 | **BM25 粗召回（工具侧）+ agent 精判**（agent 本身就是 LLM，判定零成本） |
| 写保护 | 沙箱目录 + 软删标记 + 备份回滚 | 复用 `write_doc_file`/`edit_doc_file` 既有能力 + `[DELETED]` 软删约定 + lint 兜底 |
| 评审闸门 | 无（全自动） | **保留确认闸门**：L2/L3 产物默认 draft，沿用 confirm_note / 新增 confirm 语义 |

### 3.3 目录与路由扩展

```text
repowiki/
├── wiki/
│   ├── scenarios/            # 【新增】L2 场景块（page_type: scenario）
│   │   ├── 团队记忆-SOP与禁忌.md
│   │   └── 发布流程-方法与判断.md
│   ├── doctrine.md           # 【新增】L3 项目 Doctrine（单文件）
│   └── ...（modules/entities/concepts/... 不变）
├── notes/                    # L1（不变）
├── raw/                      # L0（不变）
└── .meta/
    └── aggregate_state.json  # 【新增】聚合计数器与时间戳
```

- `codewiki/src/config.py::PAGE_TYPE_DIRS` 增加 `'scenario': 'scenarios'`；`schema.yaml` 的 `page_types` 可覆盖目录名（`page_router.get_page_type_dir` 已支持 override，无需改路由逻辑）；
- `doctrine.md` 不加进 `WIKI_SYSTEM_FILES`——它应当可被 `query_wiki` 检索到；
- 场景块与 doctrine 均走 OKF v0.2 frontmatter（`type: Scenario` / `type: Doctrine`，`generated.by` 记宿主 agent actor，`status` 三态、`stale_after`、`verified` 事件与现有笔记完全一致）。

---

## 4. 详细设计

### 4.1 L1 蒸馏质量增强（纯 prompt + schema 扩展）

**`_DISTILL_SYSTEM` 增补五条提取纪律**（借鉴 TAM work 模式 prompt，改写为 CodeWiki 语境）：

1. **独立完整**：每条笔记跳出当前对话仍能理解，禁用"这个/那个/上面说的"等指代；
2. **准确归因**：某人建议 ≠ 项目决策；只有明确拍板/采纳/已验证的事实才写成确定结论，未确认内容写"正在讨论…"；
3. **归纳合并**：强关联的多轮讨论合并为一条，不碎片化；
4. **AI 输出处理**：AI 生成的方案只有被用户采纳或经实践验证才可提取；
5. **低价值丢弃**：寒暄、一次性请求、代码里显而易见的信息一律不提取。

**distilled JSON schema 扩展**（向后兼容，均为可选字段）：

```json
{
  "notes": [{
    "title": "...", "note_type": "...", "related_modules": [],
    "tags": [], "content": "...",
    "priority": 85,        // 【新增】0-100；<70 工具侧直接丢弃并回报
    "scene": "围绕发布流程排查超时问题"   // 【新增】情境标签，存入 metadata.scene，供 L2 分组
  }],
  "memories": []
}
```

- `priority` 映射现有 `severity`：≥90 → high、70-89 → medium、<70 丢弃（TAM 的三档直接移植；severity 已有 BM25 2× boost，无需改检索）；
- `scene` 落入 frontmatter `metadata.scene`，consolidate 时作为分组提示。

### 4.2 L1 去重升级：BM25 候选召回 + agent 判定

现状：`_find_existing_note` 只做标题 Jaccard（`_DEDUP_THRESHOLD=0.6`），命中后 `merge` 仅追加 `source_conversations`，不合并正文。

**升级为两段式 submit**（对齐 TAM"粗召回 + 精判"，召回级换成现有 BM25）：

1. **阶段一（工具侧，确定性）**：submit 收到 distilled notes 后，先以 `title + content 首段` 构造查询走现有 `wiki_search`（scope=notes，top-3）召回候选，连同 Jaccard 结果一起返回：
   - 无候选或相似度低于阈值 → 直接 ingest（行为与现状一致）；
   - 有候选 → 该条笔记**暂不落盘**，响应中返回 `conflicts: [{draft, candidates: [{file, title, score}]}]`；
2. **阶段二（agent 判定，四操作）**：agent 读候选笔记原文后重新 submit，为冲突条目指定动作（借鉴 TAM 四操作）：
   - `store`：确认是新知识，照常 ingest；
   - `skip`：已有笔记更好，丢弃草稿；
   - `update`：同一事实新版更优，**以新内容覆盖旧笔记正文**（保留 frontmatter，追加 `verified` 事件，版本号走 OKF `generated.at`）；
   - `merge`：互补不矛盾，**合并正文**——旧笔记正文 + 新增小节 + `## Sources` 记录双方来源（修复现状"merge 不合并正文"的缺口）。
3. 超时/agent 未二次提交时，冲突草稿按 `dedup="suppress"` 现状兜底，不阻塞其余条目。

### 4.3 L2：`consolidate_notes` 工具与场景块

**定位**：把 `note_clusters` 的"信号"和 `consolidate` prompt 的"手动指引"升级为一个有状态承载的 Mode C 工具。**聚合输入是 confirmed 笔记**（draft 不参与，避免未评审知识进入上层）。

**工具协议**（与 distill_conversation 对称的 prepare/submit）：

```text
consolidate_notes(mode="prepare")
  → 返回：
    - pending_notes：自上次聚合后新增/变更的 confirmed 笔记清单（file + title + type + scene + 摘要）
    - scenarios_index：现有场景块清单（filename + summary + heat + 容量计数 "N / 15"）
    - capacity_warning：红（≥15，必须先 MERGE）/ 橙（=14，禁 CREATE）/ 黄（≥12，优先 UPDATE）
    - system_prompt：场景聚合指引（见 4.3.2）
    - file-side-channel：正文走磁盘，agent 用 view_repo_file 按需读

consolidate_notes(mode="submit", report={...})
  → agent 报告本次操作：created/updated/merged/deleted 的场景文件 + 每个场景吸收的 source_notes
  → 工具侧确定性簿记：
    - 校验场景文件存在、frontmatter 合法、容量 < 上限
    - 写溯源：场景 frontmatter.source_notes ← 吸收清单；被吸收笔记 frontmatter 追加 consolidated_into
    - 更新 .meta/aggregate_state.json（计数器归零、时间戳）
    - rebuild BM25 索引
```

**4.3.1 场景块文件格式**（借鉴 TAM scene-format，适配 OKF）：

```markdown
---
type: Scenario
title: 团队记忆-SOP与禁忌
status: stable
generated: { by: reference_agent/claude-sonnet-4, at: 2026-08-17T10:00:00Z }
stale_after: 2026-11-15
metadata:
  heat: 4
  summary: 记忆蒸馏与笔记评审的标准流程、常见错误与边界条件
  source_notes: [notes/2026-08-01-distill-dedup.md, notes/2026-08-10-confirm-gate.md]
---
## 工作场景
（适用于哪类任务/模块，可复用在哪里）
## 适用条件
## 核心 SOP
（最重要章节：流程步骤，每条附判断依据）
## 判断逻辑
（决策标准、取舍原因）
## 禁忌与反模式
## 关键事实依据
（可为空；只保留支撑方法的事实）
## 演化记录
（只记方法/规则变化，不记普通进展）
```

单文件 ≤1500 字符（与 TAM 一致）；正文写作要求直接沿用 TAM work 模式 L2 prompt 的准则——**提炼方法而非流水账，禁止写成日报/清单/画像**。

**4.3.2 聚合策略**（写入 prepare 返回的 system_prompt）：

- 优先级 **UPDATE > MERGE > CREATE**，"默认策略是 UPDATE"；CREATE 前必须先读至少 2 个最相似场景确认无法融入，每批最多新建 1 个；
- 合并优先级：工作对象高度重叠 > 同一工作流链路 > 同一方法体系 > heat 最低；
- **heat 规则**：新建=1，更新 +1，合并取和 +1；heat 同时与 `retrieval_stats.db` 的 hit_count 互为参照（检索热度高的场景优先保留）；
- **软删**：删除场景的唯一方式是写 `[DELETED]` 标记文件，submit 时工具侧清理（禁止空文件、禁止 ARCHIVE 等替代标记）；
- 文件名规范沿用 lint 现有约束（无空格/标点，CJK 允许），冲突由工具侧报回而非静默改名；
- **冲突处理**：新旧知识矛盾时记入"演化记录"或标注待确认，不直接覆盖——与 consolidate prompt 现有 Duplicate/Superseded/Complementary/Contradictory 四分类对齐。

**4.3.3 评审闸门**：新建场景块默认 `status=draft`（query_wiki 标注 `[unconfirmed]`），`confirm_note` 扩展支持 scenario 文件确认；被完全吸收的源笔记由 agent 显式 `reject_note(reason='consolidated into <scenario>')`（沿用现有工具与 consolidate prompt 第 4 步，保持"被吸收"可追溯）。

**4.3.4 lint 扩展**：`lint_wiki` 新增两项检查——`scenario_capacity`（超容量报错）、`scenario_orphan`（无 source_notes 且 90 天未检索的场景，info 级，建议复核或退役）。

### 4.4 L3：`refresh_doctrine` 工具与项目 Doctrine

**定位**：一份全项目共享的操作原则文档 `wiki/doctrine.md`——**不是项目总结、不是进度记录、不是场景索引**，而是让任何 agent/新成员面对新任务时知道"如何判断、如何执行、如何避错"。这是 TAM Team Operating Doctrine 的直接移植，也是本项目"自动演进的 AGENTS.md 内核"。

**工具协议**（同为 prepare/submit）：

```text
refresh_doctrine(mode="prepare")
  → 返回：当前 doctrine 全文、变化场景清单（updated > last_doctrine_time）、
    confirmed 笔记统计（总数/新增数）、触发原因、system_prompt

refresh_doctrine(mode="submit", content="...")
  → 工具侧校验：≤1200 字（超则拒绝并回报）、frontmatter 注入、
    原子写入、更新计数器
```

**内容规范**（system_prompt 核心，直接移植 TAM TEAM_MEMORY_SYSTEM_PROMPT 并改写）：

- **六维度**：SOP / Principle（长期原则）/ Decision Logic（取舍标准）/ Boundary（不能做的事）/ Anti-pattern / Agent Rule；
- **写入前五条过滤**：通用性、完整性（脱离原对话可理解）、可执行性、稳定性、精炼性——任一不满足则不写入；
- **增量五策略**：强化（佐证已有原则）/ 补充 / 修正（旧原则被推翻）/ 重构（整体压缩重写）/ 不改（只有低层事实时不动）；**持续压缩，不追加**；
- **严格禁止**：超 1200 字、项目化碎片、流水账、低层名词堆积（文件/PR/版本号除非代表可复用范式）、个人画像、无证据推测；
- **输出模板**：`Operating Thesis`（一句话核心原则）+ Core Principles / Reusable SOPs / Decision Logic / Boundaries & Anti-patterns / Agent Rules 五章 + 尾部统计行（更新时间/来源场景数/记忆总数）。

**消费入口**（两条，均低成本）：

1. `query_wiki(mode="overview")` 在现有仓库摘要前注入 doctrine 全文 + 场景导航（filename + heat + summary 一行一条，借鉴 TAM Scene Navigation 的渐进式披露）；
2. `generate-wiki` / `init-wiki` 工作流 prompt 增加指引：doctrine 存在时写入 AGENTS.md 的引用段（一行链接 + "项目操作原则以 wiki/doctrine.md 为准"），不自动改写 AGENTS.md 正文（人工资产，保持边界）。

### 4.5 计数器触发与主动提醒（替代 TAM 的定时器级联）

#### 4.5.1 计数器状态

`.meta/aggregate_state.json`（原子写，沿用任务记忆的 tmp + os.replace 模式）：

```json
{
  "notes_since_last_consolidation": 12,
  "notes_since_last_doctrine": 34,
  "last_consolidation_at": "2026-08-10T...",
  "last_doctrine_at": "2026-07-28T...",
  "last_doctrine_note_count": 80,
  "last_hinted_counter": { "consolidation": 10, "doctrine": 0 }
}
```

- `confirm_note` / `batch_set_status`（确认方向）成功时两个计数器 +1（只有 confirmed 知识才驱动上层聚合，保持评审闸门语义）；
- `consolidate_notes(submit)` / `refresh_doctrine(submit)` 成功时对应计数器归零；
- **露出点**：`wiki_stats` 响应新增 `aggregation` 段；`get_task_context` 在现有 `pending_raw_count` 旁并列返回两个计数器；`task-workflow` 与 `distill-conversations` 工作流 prompt 增加一句"计数器 ≥ 阈值时建议先聚合"；
- 默认阈值：consolidate ≥10、doctrine ≥50（对齐 TAM `triggerEveryN=50`；doctrine 频率刻意低于 consolidate，保证压缩的是"场景"而非"笔记"），`schema.yaml` 可调。

#### 4.5.2 confirm_note 联动的主动提醒（防遗忘设计）

计数器是被动的露出信号，用户很可能想不起来去查。因此叠加一层"越线主动提醒"：**工具侧做确定性判断并提示宿主 agent 询问用户，但绝不替用户执行聚合**。

**触发时机与判定（工具侧，纯规则）**：`confirm_note` / `batch_set_status`（确认方向）成功时，响应追加 `aggregation_hint` 段：

```json
{
  "ok": true,
  "aggregation_hint": {
    "consolidation_due": true,
    "doctrine_due": false,
    "counters": { "notes_since_last_consolidation": 12, "notes_since_last_doctrine": 34 },
    "message": "自上次聚合以来已确认 12 条笔记（阈值 ≥10），建议执行 consolidate_notes。请询问用户是否现在聚合。"
  }
}
```

判定规则：`counter >= threshold && (counter - last_hinted_counter[type]) >= hint_interval`（`hint_interval` 默认 5，`schema.yaml` 可调）。即：越过阈值提醒一次后更新 `last_hinted_counter`；若用户未行动，要再积累 5 条确认才会再次提醒——**避免每次 confirm 都唠叨**。判定成功后同步推进 `last_hinted_counter`。

**Agent 行为契约（prompt 侧硬约束）**：`consolidate-knowledge` 工作流 prompt 与 AGENTS.md 指引中必须写明：

1. 响应中出现 `*_due: true` 时，**先向用户提问**（IDE 提供结构化选择框时优先使用：现在聚合 / 稍后 / 不用提醒），得到同意才继续；**严禁不打招呼直接执行聚合**；
2. 用户选择"稍后/不用"时，本会话不再追问（工具侧 `last_hinted_counter` 已推进，天然抑制重复提醒）；
3. 用户同意即视为设计约束所要求的"显式调用"——触发形态没有变，只是发起者从"用户想起来"变成"工具提醒、用户拍板"。

**级联提醒**：`consolidate_notes(submit)` 成功时，若本次有场景块创建/更新且 `notes_since_last_doctrine >= threshold`，响应同样附带 `doctrine_due` 提示——"刚更新了场景块，建议顺带 refresh_doctrine"。由此形成 confirm → consolidate → doctrine 的自然链条：两步动作可以在同一轮交互里完成，但**每一步都单独经过用户确认**。

**为什么不违反约束**：工具只输出信号与建议文案（纯确定性逻辑），LLM 判断与执行仍然完全在宿主 agent + 用户侧；没有新增任何后台任务，"永不自动蒸馏/聚合"的语义不变——被自动化的只有"记得提醒"这一件事。

### 4.6 溯源链（provenance）

现有基础：笔记已有 `source_conversations` / `origin` / `source_ref`。补全向上两级：

```text
raw 对话行 ──(source_conversations)──▶ L1 笔记
L1 笔记   ──(source_notes / consolidated_into)──▶ L2 场景块
L2 场景块 ──(doctrine frontmatter.source_scenarios + 尾部统计)──▶ L3 Doctrine
```

全部用 frontmatter 双向链接表达（与现有 `source_conversations` 做法一致，不新建独立图存储）；`lint_wiki` 的 `broken_links` 检查天然覆盖断链。

---

## 5. 与现有设计约束的一致性核对

| 既有约束 | 本方案遵守方式 |
| :--- | :--- |
| LLM 外置、工具无状态（Mode C） | 两个新工具均为 prepare/submit 协议，agent 即 LLM，正文走 file-side-channel |
| 永不自动蒸馏/聚合 | 无定时器、无 hook；聚合只由显式调用触发，计数器只是信号 |
| 人工确认闸门 | 场景块与 doctrine 默认 draft，沿用 confirm_note/reject_note 流转 |
| 确定性优先 | 容量校验、计数器、1200 字限制、priority 丢弃均为纯规则；LLM 只做提取与整合 |
| OKF v0.2 | Scenario/Doctrine 页面携带标准 frontmatter，verified 事件与 stale_after 语义不变 |
| 零依赖检索 | 去重召回用现有 BM25；不引入 embedding、不引入新存储（SQLite + JSON 双层架构不变） |
| raw/ 暂存区语义 | 不变，L2/L3 不消费 raw，只消费 confirmed 笔记 |

---

## 6. 接口定义速查

| 工具 | 模式 | 关键参数 | 返回 |
| :--- | :--- | :--- | :--- |
| `consolidate_notes` | prepare | `output_dir` | pending_notes / scenarios_index / capacity_warning / system_prompt |
| `consolidate_notes` | submit | `report: {scenarios: [{file, action, source_notes}], rejected_notes: []}` | 簿记结果、新计数器值 |
| `refresh_doctrine` | prepare | `output_dir` | 当前 doctrine / 变化场景 / 统计 / system_prompt |
| `refresh_doctrine` | submit | `content` | 校验结果、备份路径、新计数器值 |
| `wiki_stats`（扩展） | — | — | 新增 `aggregation` 段（两个计数器 + 时间戳） |
| `get_task_context`（扩展） | — | — | 响应中并列返回聚合计数器 |
| `confirm_note` / `batch_set_status`（扩展） | — | — | 确认成功时响应附带 `aggregation_hint`（越线判定 + 提醒文案，见 §4.5.2） |
| `lint_wiki`（扩展） | — | — | 新增 `scenario_capacity` / `scenario_orphan` 检查 |
| `distill_conversation`（扩展） | submit | distilled notes 增加可选 `priority` / `scene`；冲突时两段式 | 冲突候选清单 / 丢弃回报 |

---

## 7. 分阶段路线图

| 阶段 | 内容 | 改动面 | 工作量 |
| :--- | :--- | :--- | :--- |
| **P1：L1 质量增强** | `_DISTILL_SYSTEM` 五条纪律 + priority/scene 字段 + priority 丢弃门；两段式去重（BM25 召回 + 四操作判定 + merge 合并正文） | `distill_conversation.py`、`knowledge_loop.py` | 3–5 人日 |
| **P2：L2 场景聚合** | `PAGE_TYPE_DIRS` 加 scenario；`consolidate_notes` 工具；场景块格式与聚合 prompt；`aggregate_state.json` 计数器与 confirm_note 联动提醒（§4.5.2）；lint 两项新检查 | `config.py`、新工具文件、`knowledge_loop.py`、`prompt_server.py`、`wiki_lint.py`、`page_router.py` | 5–8 人日 |
| **P3：L3 Doctrine** | `refresh_doctrine` 工具；doctrine prompt（六维度/五过滤/五策略）；`query_wiki(mode=overview)` 注入 doctrine + 场景导航；工作流 prompt 更新 | 新工具文件、`wiki_search.py`、`prompt_server.py` | 3–5 人日 |

验收基线：在本项目自身的 repowiki 上跑通完整闭环——现有 20+ 条笔记 → 聚合出 ≤15 个场景块 → 压缩出 ≤1200 字 doctrine → `query_wiki(mode=overview)` 可见注入 → `lint_wiki` 无新增 error。

## 8. 风险与开放问题

1. **宿主 agent 执行质量参差**：Mode C 把整合智能完全交给宿主 agent，弱模型可能写出流水账式场景块。缓解：system_prompt 内置负面清单 + submit 侧确定性校验（长度、章节骨架、source_notes 非空）+ lint 兜底；必要时提供 `get_prompt('scenario_template')` 示例。
2. **场景块与 modules 文档的边界**：模块文档描述"代码是什么"，场景块描述"这类工作怎么做"，但 agent 可能混淆。缓解：prepare 的 system_prompt 明确"场景块不得复述模块文档内容，只沉淀方法"；scenario 页面模板强制"工作场景/适用条件"开场。
3. **doctrine 与 AGENTS.md 的关系**：只引用不改写（AGENTS.md 是人工资产）。若未来希望双向同步，需另立提案。
4. **两段式去重的交互成本**：冲突条目需要 agent 二次 submit，增加轮次。缓解：无冲突条目不受影响；冲突清单一次返回、可批量判定。
5. **计数器阈值冷启动**：存量 confirmed 笔记多的仓库首次聚合量大。缓解：prepare 支持分批（`limit` 参数），首批优先 note_clusters 已报出的聚类。

---

## 附：与 TAM 机制的移植对照

| TAM 机制 | 本方案对应 | 移植程度 |
| :--- | :--- | :--- |
| L1 work 模式提取原则（归因纪律、宁缺毋滥） | 4.1 蒸馏 prompt 增强 | 全移植（改写语境） |
| 两阶段去重（向量/FTS 召回 + LLM 四操作判定） | 4.2 BM25 召回 + agent 判定 | 召回级降级为 BM25，判定逻辑全移植 |
| L2 沙箱 agent + UPDATE>MERGE>CREATE + 容量/热度/软删 | 4.3 consolidate_notes | 全移植（沙箱改为 view_repo_file 白名单指引） |
| L3 Doctrine（六维度/五过滤/增量五策略/≤1200字） | 4.4 refresh_doctrine | 全移植 |
| triggerEveryN=50 级联触发 | 4.5 计数器信号 + confirm_note 联动提醒 | 降级为拉取式（哲学差异）；主动提醒为原创补充（TAM 无此问题——它是自动触发） |
| generation provenance | 4.6 frontmatter 双向链接 | 轻量化移植 |
| Scene Navigation 渐进披露 | query_wiki overview 注入 | 全移植 |
| Redis 调度 / embedding / 推送触发 / Skill 体系 | — | 不移植（见 §2.2） |
