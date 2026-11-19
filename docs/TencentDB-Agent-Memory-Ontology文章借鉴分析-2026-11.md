# TencentDB-Agent-Memory「Ontology」文章借鉴分析（2026-11）

- **来源**：腾讯技术工程公众号《不只是Memory：Ontology如何让Coding Agent越用越懂项目？》，2026-11-13 17:36，https://mp.weixin.qq.com/s/2IUREDltOXzXECO7tWIoPA
- **附带开源仓**：TencentCloud/TencentDB-Agent-Memory（原 Tencent/ 组织，已 301 改名；30.8k stars，TypeScript，默认分支 feat/server_team，MIT）
- **调研任务**：他山之石 · 2026-11-13 · 方法：文章精读 + 开源仓 README 核对 + 本仓代码逐项证伪 + 实测扫描
- **前情**：本仓 2026-08-12 已源码级调研其 MemoryCore L0-L3 蒸馏管线（笔记已吸收进场景块《对话蒸馏管线与raw暂存区》）；2026-08-26 竞品分层定其为「直接竞品，最值得盯防」（笔记 stable）。本文是**已知竞品的增量更新**，不是新对象。

## 一、文章核心内容

1. **本体（Ontology）定位**：与 Schema/CodeGraph/知识图谱/RAG 的分工——补的是「找到知识之后，判断它在说哪个对象、什么条件下成立、能支持哪步推断」。反对「所有边都叫相关」的图谱。
2. **RSI 三层框架**：执行内迭代 / 跨任务自改进 / 改进过程的自改进。引用 Reflexion、Agent Workflow Memory、Darwin Gödel Machine、Skill∞（arXiv 2610.35434，已核实存在）。「允许改进方法 ≠ 允许改低评分标准」，评分放在自改进范围之外 + 独立审查。
3. **EvoOntology**（arXiv 2609.15779，ruc-datalab，已核实存在）：本体拆 Content/Schema/Tool；失败先归因（内容缺失 / 工具暴露不合适 / Schema 无法表达），每个候选只做一层局部修改，同模型同验证集同预算配对比较，达幅度才保留；最终测试前本体冻结。
4. **腾讯内部实践**：四类记忆资产（Chat Memory/Wiki/CodeGraph/Skill）+ 三层互索引图谱（工程事实 / 项目语义 / bug_fixed 经验层）。跨仓边靠 API/消息/Schema 契约核对，不凭同名符号；事件与经验分离（一次事件支持多条经验）；渐进式披露且**关键前提必须跟摘要一起出现**；图遍历有预算与停止条件。
5. **更正传播**：旧结论被替代后，引用它的摘要/Skill/测试假设应进入「待复核」状态；原事件不删但不再以已确认规则指导新任务。
6. **召回≠生效**：仅靠召回日志不能确定经验生效；稳定约束应落到对象映射、测试断言或动作前检查。
7. **初步结果**：内部 Bug 定位试验 58%→65%（+7pp）。作者自陈：不能换算完整研发效率、不能单独归因语义层；评测要信息源 parity、已知故障找回 vs 未知 Bug 迁移分开报告、时间切分、排除目标补丁及间接关系泄漏。

## 二、事实核对（文档站是宣传口径，代码是事实口径）

- **开源仓 README 只有四资产 + L0→L3 分层蒸馏 + BM25/向量/RRF + Proxy 零代码注入 + ACL**；文章核心的三层本体图谱、bug_fixed、58→65% 实验**均未出现在开源仓**，属内部实践叙述，本次无法代码核对（验证缺口，明示）。
- README 口径的基准是 PersonaMem 48%→76%（用户理解任务），与文章的 Bug 定位 58→65% 是两回事，不可混引。
- 竞品动态更新：组织改名 Tencent→TencentCloud；stars 19.9k（2026-08）→30.8k（2026-11）；v2→v3 数据迁移工具；Proxy 走 base URL 重定向的 LLM 代理注入（与本仓 hooks+MCP 通道不同，服务端前提，不借）。
- 文章引用的两篇预印本均真实存在（见文末链接）。

## 三、候选处置表（12 项：1 absorbed 已落地 / 3 deferred / 8 excluded）

| # | 候选 | 本仓证据 | 处置 | 理由 |
|---|------|----------|------|------|
| 1 | 更正传播 / 溯源背撑 | `wiki_lint.py` 全文无 source_notes/compiled_into 检查；`note_lifecycle.py:138-170` reject 只改自身状态；实测扫描见 §四 | **absorbed（已落地 2026-11-19）** | 结构性缺口代码确认 + 3 条断链实测命中；与 supermemory derives/isLatest、llm-wiki-compiler freshness（均 deferred）三源收敛。落地：`provenance_backstop` 检查（第 27 项，warning，双向）+ skill_lint 委托共享 helper + 两处 submit 存在性校验 + 2 个损坏场景 frontmatter 修复；grill-me Q1-Q12 裁决记录见处置笔记「裁决与落地」节 |
| 2 | 笔记级适用条件/不适用条件 + 前提随摘要披露 | `prompts.py:1144-1152` 笔记模板只有背景/核心/原因/影响范围；场景块与技能骨架已有「适用条件」章节（prompts.py:1450,1501）；check/by_file 摘要无前提字段（note_query.py:696-708） | deferred | 模板级小改，但无实测误用实例；等负反馈语料（negative_examples 通道已存在）再动 |
| 3 | 失败归因分层（内容/工具/Schema） | `friction.py` 只计数信号（correction×20+interrupt×20+repeat×15）；`outcome_report.py:30,64-67` 二元结果+自由文本 | deferred | 归因属调用方推理（本仓哲学），可作 distill/consolidate prompt  guidance；并入负反馈主线，不单独立项 |
| 4 | 评测卫生方法论 | 本仓无检索质量 eval（okf_regression_test 是 handler 契约回归）；supermemory 调研已把 MemoryBench 归质量量化主线 | deferred（归质量量化主线参考项） | 信息源 parity 对照、已知找回 vs 未知迁移分报、时间切分、排除间接泄漏、评测前冻结——是该主线启动时的设计输入，按「调研归任务参考项不主动推送」留档此处 |
| 5 | 三层互索引 / 任意层进入 | by_file 代码→笔记（note_query.py:603-767，claude-mem 借鉴）；hop 0-3 图扩展（note_query.py:843）；模块树/依赖/analyze_impact；wiki+notes | excluded | 结构等价已有，独立收敛互证 |
| 6 | 跨仓契约核对不凭同名符号 | `cross_service.py` links=client_repo/server_repo/method/path/route_key，按 HTTP 路由契约匹配 + unmatched_routes 诊断 | excluded | HTTP 契约已等价；消息/Schema 契约扩展属多仓工作区参考项，无实测需求 |
| 7 | 事件 vs 经验分离 | raw/（事件）与 notes/（经验）双轨已分离；蒸馏去重合并 | excluded | 已有等价；表现/根因/补丁三位置区分可并入候选 2 的模板 guidance |
| 8 | 召回≠生效 → 断言级强制检查 | hit→adopted→outcome 三级遥测（outcome_report.py:1-17）；confidence weak/strong/shadow + verification 证据（note_lifecycle.py:79-116） | excluded | 过程证据已覆盖；「候选不能凭流畅升事实」= 确认闸门+证据分级已实现；断言级强制与「推理在调用方」前提相反 |
| 9 | RSI 评分外置 / 独立审查 | wikiskill 定档「不建自动评分门控」；确认闸门对等；技能两区制；doctrine「依赖升级勿顺手放宽 lint」 | excluded | 哲学等价，独立收敛互证；Skill∞ meta-skill ≈ 技能提取 Q10 回流验证（已 deferred） |
| 10 | 渐进式披露 + 预算停止 | check 模式、by_file 层 1、est_tokens、expand max_chars≤20000、hop≤3、注入只列 3 条最新笔记（hindsight 索引抑制已吸收） | excluded | 已有等价 |
| 11 | 四资产 / L0-L3 蒸馏 | 2026-08-12 源码级调研笔记（已吸收）+ 08-26 竞品分层笔记（stable） | excluded | 已调研过；本次仅登记竞品动态（§二） |
| 12 | 概念卡 / 本体第四层 | CONTEXT.md glossary + ADR + 冲突一等对象（ADR-0007）+ notes 已承担；文章自己也说「本体不需要成为第四层」 | excluded | 新资产类型违反单点收敛与容量纪律 |

## 四、实测缺口详情（候选 1）

**扫描方法**：解析 11 个场景块 frontmatter `source_notes`（124 条引用）与 6 个技能草稿 `source_refs`（20 条引用），逐条回查源笔记状态；区分「吸收性退役」（reject_reason 含聚合/吸收等词，正常设计）与「纠错性退役/降回 draft/文件缺失」。

**结果**：
- 场景块：118 吸收性退役 + **3 断链** + 3 正常；技能：13 正常 + 7 吸收性退役；
- 反向：131 条带下游链接的笔记中 113 吸收性退役 + 18 正常，**0 条纠错性失效**；
- 3 条断链均为**文件名截断**（真实文件存在，引用被截短），与 2026-09-19「confirm_note 中文长标题截断」pitfall 同根因家族：
  - `IDE-Hook采集链路方法.md` → `notes/2026-09-07-userpromptsubmit-的-ide-hook`（实际文件更长）
  - `发布与依赖治理方法.md` → `notes/2026-08-26-uv-工具链两坑`
  - `发布与依赖治理方法.md` → `notes/2026-09-08-windows-powershell-下-git-add-中文路径会静默失败导致-commit`

**结论**：「更正传播」机制缺口是结构性的（reject/confirm 不触碰下游、lint 不读溯源字段），但当前 0 实例（语料年轻，退役几乎全是吸收性）；**溯源断链是当下实测缺口（3 条）且无任何检查覆盖**。

**建议落地形态**（待用户裁决）：`lint_wiki` 新增 provenance 背撑检查——场景块 `source_notes` / 技能 `source_refs` / 笔记 `consolidated_into`/`compiled_into` 指向的文件缺失、或源笔记处于非吸收性 deprecated、或降回 draft 时，报 warning 提示复核。纯确定性簿记、hint-only、不改任何闸门，完全符合本仓哲学；顺带覆盖未来纠错传播实例。完整的「退役时给下游盖待复核章」暂缓，等出现实例再做。

## 五、总体判断

文章最有价值的不是「本体」概念本身（本仓 glossary+ADR+冲突对象+notes 已承担其职责），而是两点工程纪律：**①知识更正要沿溯源传播到下游产物；②评测要防信息源不对称与答案泄漏**。前者在本仓测出了真实断链，后者是质量量化主线的现成设计输入。其余候选延续本任务历史规律：多数已有等价（独立收敛互证），服务端/重运行时取向与本仓前提相反。

## 参考链接

- 文章：https://mp.weixin.qq.com/s/2IUREDltOXzXECO7tWIoPA
- 开源仓：https://github.com/TencentCloud/TencentDB-Agent-Memory
- EvoOntology：https://arxiv.org/abs/2609.15779 （代码 https://github.com/ruc-datalab/EvoOntology）
- Skill∞：https://arxiv.org/abs/2610.35434
- 本仓前情笔记：`notes/2026-08-12-tencentdb-agent-memory-四层记忆金字塔逐层蒸馏-触发式调度.md`（deprecated，已吸收）、`notes/2026-08-26-github-竞品分层调研tencentdb-agent-memory-为直接竞品llm-wiki-家族为理念源头.md`（stable）