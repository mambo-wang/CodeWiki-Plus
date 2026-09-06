# WikiSkill 论文与 wikiskill 源码精读

> 调研对象：
> - 论文：WikiSkill: Compiling Agent Experience into Persistent Knowledge for Skill Evolution（arXiv:2608.27454，Google Research + Virginia Tech）
> - 开源源码：github.com/ashutoshsinghpr7/wikiskill（v0.1.4，commit 02fac2c，2026-09-02），浅克隆于 `.research-competitors/wikiskill/`
>
> 编制日期：2026-09-06
> 定位：为 skill-creator 设计方案（`repowiki/wiki/queries/skill-creator设计方案.md`）补充一手事实。既有两份文档（可行性对比 + 设计方案）已覆盖架构定档与工具形态；本文只挖它们没写透的细节：实验数字、prompt 原文、门控代码、skill-impact.md 确切格式、SKILL.md 产物结构、退役/冲突/去重机制现状。

---

## 0. 与既有两份文档的增量

既有文档已覆盖：三层架构（raw/wiki/skills）、四角色闭环、`R_val > R_best` 严格门控 + git 回滚、"wiki 不暴露给执行者"消融（63.7%→60.9%）、工程极简（无向量库）、三档方案定档（方案 C 半闭环）。本文新增的一手事实：

1. **论文 Table 1/2/3/4/5/6/7 全部具体数字**：五模型 × 五基准主结果、跨模型迁移矩阵（含负迁移案例）、四配置消融全表（既有文档只引了 63.7→60.9 一个数字）、门控接受率（创建 ~26-52%、编辑 ~13-36%）、接受时点分布（early/mid/late）、各基准 train/val/test 划分规模、优化器 API 调用复杂度。
2. **技能目录是双文件结构**：`SKILL.md` + `PURPOSE.md`（溯源文件独立，不塞 frontmatter）——既有文档与 CodeWiki 设计稿均未提及。
3. **Skill Proposer / Wiki Maintainer 的 prompt 全文**（论文附录 E.2/E.3 + 源码 `prompts.py` 逐字版），含"必须读至少 4 条失败 trace""replace 目标必须是短小片段"等可移植纪律。
4. **skill-impact.md 条目的确切格式**（harness 程序化追加的 markdown 结构，含内嵌完整被拒提案 JSON）。
5. **门控代码的工程语义**：`accepted = r_val > prev_best` 的确切位置、patch 三种操作对 target 的 exact-substring 校验、`git reset --hard + clean -fd` 回滚、`no_action` 也是一种合法提案。
6. **隔离 profile 机制**：wikiskill 用 Hermes 原生技能加载（symlink 重建）而非论文的系统提示全量注入——实现路径与论文不同但语义等价。
7. **RUNS.md 六次真实运行记录**：至今所有 live 门控全是拒绝/no_action，零次现场接受；每次迭代成本 $0.086-$0.25；框架曾通过自己的 maintainer 诊断出自身 bug。
8. **退役/去重/冲突机制的真相**：论文与源码都没有技能退役机制；去重全靠 prompt 纪律；论文 Limitations 明确承认"无自动 wiki 修剪"与"严格门控排除中性提案"两个缺口——直接对应 CodeWiki 设计稿的 Q10/Q11。
9. **demo bench 的"陷阱任务"设计**（生成时 assert 双 bug 不互补、防幻影评分的强制新鲜沙箱），是自建技能验证基准的可借鉴样板。
10. **XStack18 公众号原文未获取**（见下节），本文全部结论来自论文 HTML 全文与源码。

## 0.1 一手资料获取情况

| 资料 | 状态 | 说明 |
|---|---|---|
| 论文摘要页 + HTML 全文 | 已获取 | arxiv.org/abs 与 /html/2608.27454，HTML 全文约 95KB 纯文本，含全部表格与附录 A-E |
| wikiskill 源码 | 已获取 | `git clone --depth 1` 一次成功（走全局代理），v0.1.4，全部 Python 约 3000 行 + 8 个 SKILL.md + docs/ |
| XStack18 公众号文章 | **未获取** | WebSearch 两轮（"XStack18 WikiSkill"）未找到原文或可靠转载；搜到的均为其他作者的第三方解读（CSDN/博客园/头条等），非 XStack18 出品，本文不引用。既有对比文档当时用过该文内容，如需原文需另行人工获取 |

源码行号以本仓 `.research-competitors/wikiskill/` 下实际读取为准（下文统称 `wikiskill/`，即该克隆内相对路径）。

---

## 1. 论文实验数据（既有文档未捕获的部分）

### 1.1 主结果 Table 1（§4.2，五模型 × 五基准）

全部为三次独立完整演化运行的测试集平均（论文 §4.1）：

| 模型 | 方法 | LiveMath | SealQA | SpreadSheet | OfficeQA | ALFWorld | Avg |
|---|---|---|---|---|---|---|---|
| Qwen-3.5-4B | No skill / Trace2Skill / EvoSkill / SkillOpt / **WikiSkill** | 29.1 / 31.5 / 41.7 / 48.7 / **49.7** | 32.5 / 37.6 / 37.3 / 33.3 / **39.4** | 14.6 / 17.5 / 18.6 / 14.0 / **21.1** | 30.2 / 31.0 / 29.5 / 34.5 / 28.5 | 24.4 / 42.8 / 41.5 / 45.3 / **53.7** | 26.2 / 32.1 / 33.7 / 35.2 / **38.5** |
| Qwen-3.5-9B | 同上序 | 28.2 / 33.1 / 58.1 / 48.7 / **56.3** | 26.3 / 36.9 / 34.5 / 29.4 / **43.1** | 24.3 / 26.5 / 35.4 / 29.0 / **33.6** | 35.9 / 38.4 / 34.9 / 38.0 / **40.5** | 34.7 / 48.8 / 48.5 / 55.7 / **63.4** | 29.9 / 36.7 / 42.3 / 40.2 / **47.4** |
| Qwen-3.6-27B | 同上序 | 33.9 / 36.3 / 57.3 / 51.9 / **61.9** | 27.5 / 37.3 / 32.9 / 34.5 / **41.6** | 40.8 / 53.3 / 59.5 / 53.2 / **81.7** | 42.1 / 54.3 / 52.5 / 54.8 / **53.7** | 52.8 / 55.5 / 64.2 / 59.2 / **77.6** | 39.4 / 47.3 / 53.3 / 50.7 / **63.3** |
| Gemma-4-31B | 同上序 | 33.9 / 32.3 / 29.8 / 40.1 / **56.7** | 30.6 / 37.7 / 38.4 / 36.1 / **41.2** | 48.3 / 58.5 / 56.4 / 63.1 / **68.0** | 43.3 / 43.2 / 39.9 / 44.4 / 44.2 | 50.4 / 57.2 / 52.6 / 61.9 / **64.4** | 41.3 / 45.8 / 43.4 / 49.1 / **54.9** |
| Gemini-3.5-Flash | 同上序 | 33.0 / 41.9 / 44.6 / 49.7 / **72.6** | 29.4 / 44.3 / 43.6 / 28.2 / **44.7** | 50.5 / 56.0 / 55.4 / 66.1 / **76.6** | 48.6 / 50.0 / 51.2 / 49.8 / **60.7** | 85.9（各法相同，见下） | 49.5 / 55.6 / 56.1 / 55.9 / **68.1** |

关键注记（论文 §4.1/§4.2.1）：

- WikiSkill 平均分对五个模型分别比"各模型最强竞品"高 **3.3 / 5.1 / 10.0 / 5.8 / 12.0 分**。
- 基线方法不稳定：EvoSkill 在 Qwen-9B LiveMath 大涨（28.2→58.1）却把 Gemma-4-31B 打降（33.9→29.8）；SkillOpt 把 Gemini Flash 的 SealQA 打降（29.4→28.2）。WikiSkill 是唯一全模型 Avg 第一且多数模型-数据对不劣化的方法。
- Gemini-3.5-Flash 在 ALFWorld 上所有方法同分 85.9，因为它在验证集上 S0 就拿了 100%，触发 Algorithm 1 的 `R_best=1.0` 提前终止——**演化从未发生**。这也导致它在跨模型迁移表（Table 2）里作为技能源标注 "−"。
- 数据集敏感性：LiveMath 全模型受益（+20.6 ~ +39.6）；OfficeQA 最难受益——Qwen-3.5-4B 反而微降（30.2→28.5），原因是小模型在长上下文里执行不了多步检索工作流，回退默认读文档行为（§4.2.1）。

### 1.2 跨模型迁移 Table 2（§4.2.2）——含负迁移证据

技能源 = Qwen-3.5-4B / Qwen-3.6-27B / Gemini-3.5-Flash 三种，被测模型五种的完整矩阵（节选关键数字）：

- **他模型技能优于自进化技能**：Qwen-3.5-9B 用 Qwen-27B 技能在 SpreadSheet 拿 50.5%（无技能 24.3%，自进化 33.6%）；Gemma-4-31B 用 Qwen-27B 技能在 LiveMath 拿 73.7%（无技能 33.9%，自进化 56.7%）。
- **小模型技能也能惠及大模型**：Qwen-3.5-4B 技能把 Gemma-4-31B 的 LiveMath 提到 73.1%、ALFWorld 提到 66.9%。
- **负迁移实锤**：Qwen-3.5-4B 的 SpreadSheet 技能把 Gemini-3.5-Flash 从 50.5% **打到 18.1%**。论文错误分析归因两点：①小模型技能编码了低层 workaround（单行 Python 命令、字符串转换规则），帮助小模型避免执行失败，却**约束强模型使用端到端完整脚本**；②碎片化诊断流程引入冗余工具调用，耗尽强模型的交互预算。
- **"发现"与"执行"是两种能力**：Qwen-3.5-4B 的 OfficeQA 技能把自己从 30.2 降到 28.5，却把 Qwen-3.6-27B 从 42.1 提到 52.9（§4.2.2）。这为 CodeWiki 半闭环设计（强模型提炼、宿主执行）提供了论文级依据。

### 1.3 消融 Table 3（§5.1）——四配置全表，不止 63.7→60.9

用 Gemini-3.5-Flash，独立开关"Inference Agent 训练 rollout 时 wiki 可见"（IA）与"Skill Proposer wiki 可见"（SP）。SP 关闭时连 Wiki Maintainer 一并移除（消除跨迭代知识积累）。四配置 + 无技能基线（Avg over 4 基准）：

| IA wiki | SP wiki | LiveMath | SealQA | SpreadSheet | OfficeQA | Avg |
|---|---|---|---|---|---|---|
| —（No skill） | — | 33.0 | 29.4 | 50.5 | 48.6 | 40.4 |
| 是 | 否 | 43.8 | 42.0 | 44.4 | 51.0 | **45.3** |
| 否 | 否 | 51.3 | 38.4 | 49.9 | 55.2 | **48.7** |
| 是 | 是 | 64.8 | 42.8 | 80.2 | 55.6 | **60.9** |
| 否（默认） | 是 | 72.6 | 44.7 | 76.6 | 60.7 | **63.7** |

既有文档只引了 63.7→60.9（默认 vs IA 开）。完整表额外揭示：

- **IA 开 wiki 在两种 SP 配置下都有害**：无 SP 时 48.7→45.3（-3.4），有 SP 时 63.7→60.9（-2.8）。即"执行者看 wiki 抄答案"的代价是独立于提案质量的。
- **SP 无 wiki（48.7）比无技能基线（40.4）仍高 8.3 分**——即便没有持久知识层，"看 trace 提案 + 验证门控"本身就有收益；wiki 层再叠加 +15.0 分。
- LiveMath 对该消融最敏感（51.3→72.6）。

### 1.4 门控接受率与技能/模式统计 Table 4（§5.2）——skill-creator 最直接的参照数字

按模型（全基准平均）：

| 模型 | 技能创建（提案/接受） | 技能编辑（提案/接受） | 技能均长（行） | 模式创建 | 模式编辑 | 模式均长（行） |
|---|---|---|---|---|---|---|
| Qwen-3.5-4B | 3.1 / 1.6 | 4.9 / 1.3 | 126.2 | 8.8 | 18.4 | 48.2 |
| Qwen-3.5-9B | 4.6 / 1.4 | 3.4 / 0.7 | 128.6 | 7.3 | 10.9 | 26.6 |
| Qwen-3.6-27B | 4.4 / 1.5 | 3.6 / 0.8 | 118.9 | 6.5 | 17.9 | 47.7 |
| Gemma-4-31B | 4.8 / 1.3 | 3.2 / 0.8 | 45.1 | 6.3 | 13.7 | 23.7 |
| Gemini-3.5-Flash | 2.3 / 1.2 | 5.7 / 1.1 | 81.2 | 8.9 | 7.0 | 18.1 |

按基准（全模型平均）：LiveMath 技能最短（84.6 行）模式最少（4.4 个）；SpreadSheet 技能最长（142.5 行）模式最多（9.8 个）。

可换算的**接受率**：创建接受率 26%~52%（Gemini-Flash 2.3→1.2 ≈ 52%；Qwen-4B 3.1→1.6 ≈ 52%；Qwen-9B 4.6→1.4 ≈ 30%）；编辑接受率仅 **13%~36%**（Qwen-9B 3.4→0.7 ≈ 21%；OfficeQA 3.3→0.3 ≈ 9%）。注意这是"每次完整演化（含多次迭代）累计"的计数，且分母含被拒提案——即**提案过半被拒是常态**，被拒内容进 wiki 供下轮复用正是论文的复利主张。模式页（wiki patterns）的创建与编辑**全部保留、从不回滚**（Table 4 注）。

### 1.5 接受时点分布 Table 5（附录 A.2）——"技能数量演化曲线"的代理

按演化阶段（early = 迭代 0-1，mid = 2-4，late = 5-7）统计被接受更新占比：

| 按模型 | Early | Mid | Late |
|---|---|---|---|
| Qwen-3.5-4B / 9B / 27B | 39% / 52% / 43% | 39% / 30% / 40% | 21% / 19% / 17% |
| Gemma-4-31B / Gemini-Flash | 52% / 50% | 37% / 46% | 11% / 4% |

| 按基准 | Early | Mid | Late |
|---|---|---|---|
| LiveMath / SealQA / SpreadSheet / OfficeQA / ALFWorld | 44% / 39% / 41% / 58% / 55% | 42% / 33% / 48% / 26% / 34% | 14% / 28% / 11% / 16% / 10% |

结论：约四到六成接受发生在前两轮，但 mid/late 仍持续有接受（SealQA 最持续：mid 33% + late 28%）——说明**技能提炼不是一轮收敛**，多轮回流的半闭环设计有数据支撑。演化总长为 K≤8 次迭代（late 段定义到迭代 7）。

### 1.6 数据划分 Table 6 与实现细节（附录 B/C/D）

| 基准 | 交互 | Train / Val / Test | 工具 |
|---|---|---|---|
| LiveMath | 单步 | 35 / 18 / 124 | 无（直接推理） |
| SealQA | 多步 | 16 / 10 / 85 | web_search, read_file |
| SpreadSheet | 多步 | 80 / 40 / 280 | bash |
| OfficeQA | 多步 | 50 / 24 / 172 | glob, grep, read |
| ALFWorld | 多步 | 39 / 18 / 134 | 模拟器合法动作 |

- 验证集极小（10-40 题）是共性（沿袭 SkillOpt/EvoSkill 设置），论文承认这会给门控决策引入噪声，对策是三次完整演化取平均 + paired bootstrap 显著性检验（1000 次，p<0.05，附录 C）。
- **轨迹分层采样**（附录 C）：每迭代最多 8 条 trace（≤5 失败 + ≤3 成功），单条执行日志注入 prompt 前截断到 **15,000 字符**。
- **优化器调用复杂度**（附录 D，Table 7）：WikiSkill 全批处理（B=N_train），每迭代 1（maintainer）+ T_ReAct（proposer ReAct 轮数，实测 10-20）次调用，对训练集大小是 **O(1)**；对比 Trace2Skill O(N_train)、EvoSkill/SkillOpt O(N_train/B)。Proposer 不预采样 trace、按需 read_file 是达成 O(1) 的关键。

### 1.7 Limitations（论文自述缺口，直接对应 CodeWiki Q10/Q11）

1. **全量注入、不评估检索/触发**——"随着技能数量增长，检索与触发会变得重要，本文未覆盖"。
2. **严格 `>` 门控排除中性提案**——可能存在"当场不涨、后续有用"的提案被拒；更宽松的接受准则是 future work。
3. **无自动 wiki 修剪机制**——模式页/日志/diff 持续累积，长演化下可能必须修剪。
4. 未覆盖超长时程任务（数百动作级）与单次 rollout 内的在线技能调整。

### 1.8 对 skill-creator 有直接影响的论文事实（既有文档未写）

- **技能目录 = 双文件**（§3.1 Skills Layer）：`SKILL.md`（完整技能内容）+ `PURPOSE.md`（"映射回促成其创建/修改的 wiki patterns"）。溯源不进 frontmatter，独立成文件。
- 技能正文约定三段式：**When to Apply + When NOT to Apply + Instructions**（附录 E.3 finish() 格式）；PURPOSE.md 三段式：**Origin + Patterns Addressed + Evolution History**。
- 维护者对 pattern 页的结构约定：**PROBLEM → ROOT CAUSE → FIX**，每页 10-30 行；index.md 每 pattern 一行，格式固定为 `[name](wiki/patterns/name.md): PROBLEM + ROOT CAUSE + FIX in one or two sentences`（附录 E.2）——index 条目质量被论文称为"wiki 最重要部分"，因为它决定读者是否点开全文。
- 维护者**每迭代可建/改 pattern 数量无硬性上限**，"由维护者根据 trace 与 wiki 现状自行判断"（§3.2.2）；去重靠 prompt 纪律（"Do NOT create duplicate patterns"）。
- Proposer 的 ReAct 工具只有两个：`read_file` 与 `finish(proposal)`（附录 E.3）；源码版加了 `write_file` 写提案 JSON。
- trace 路径别名：workspace 把 `read_file("traces/<task_id>")` 自动映射到 `raw/` 下的执行日志（附录 E.3 末注）。
- `skill-impact.md` 由**外层 harness 程序化追加**（不是 agent 写的），记录提案元数据、目标技能名、unified diff、验证分、接受结果（§3.2.4）——审计链是机制保证而非 agent 自觉。

---

## 2. wikiskill 源码工程细节

### 2.1 代码地图（全部 ~3000 行 Python）

| 文件 | 行数 | 职责 |
|---|---|---|
| `wikiskill/harness.py` | 179 | Algorithm 1 编排（evolve 主循环） |
| `wikiskill/gating.py` | 183 | 提案应用/回滚/git 管理/验证 rollout/持久状态 |
| `wikiskill/prompts.py` | 142 | 三角色 prompt 模板（自述"adapted from paper Appendix E, extracted verbatim from the arXiv HTML"） |
| `wikiskill/bench.py` | 461 | demo 基准生成（22 任务，含陷阱任务） |
| `wikiskill/cli.py` | 273 | init/status/evolve/gate/compare/transfer/run-task/maintain/propose/reset 十个子命令 |
| `wikiskill/wiki.py` | 61 | wiki 骨架 + 追加写入 + 独立 git 仓库 |
| `wikiskill/scoring.py` | 62 | 四种确定性 grader |
| `wikiskill/tasks.py` | 109 | tasks.json 校验 + 沙箱物化 |
| `wikiskill/traces.py` | 72 | raw 层不可变 trace 存储 |
| `wikiskill/transfer.py` | 79 | 跨工作区技能拷贝 |
| `wikiskill/compare.py` | 168 | 配对精确二项检验（McNemar 类） |
| `wikiskill/backends/*` | ~1100 | Hermes（参考实现）/ Claude Code / Codex / Copilot 四后端 |
| `skills/` | — | 3 个框架技能（proposer/maintainer/evolve）+ 5 个真实演化产物 |
| `docs/RUNS.md` | — | 六次真实运行日志（见 §2.7） |

### 2.2 Skill Proposer 的 prompt 模板原文（`wikiskill/prompts.py:82-120`）

逐字结构（变量插值处用 `<>` 标注）：

```
You are the Skill Proposer in a WikiSkill evolution loop (iteration <it>).

Load the `wikiskill-proposer` skill and follow it exactly.

WORKSPACE: <ws>
- Wiki: <ws>/wiki/ (index.md, skill-impact.md, patterns/, log.md)
- Raw traces: <ws>/raw/traces/iter-<NN>/ (full execution logs, read any trace you need via read_file)
- Active skills: <ws>/skills/active/

Training rollout summary this iteration:
<按 score 升序排列的任务表：id [split] score=... : title>

Rules (from the paper's Appendix E.3):
1. Read wiki/index.md FIRST, then wiki/skill-impact.md (contains full content of
   rejected proposals — DO NOT repeat rejected approaches).
2. Read relevant pattern pages, then read at least 4 execution traces for failed
   tasks to diagnose root causes. Traces can be long — read selectively
   (search_files for errors, read tails); do not read every line.
3. Decide: create (new skill), patch (existing skill), or no_action.
4. Write your proposal JSON to: <ws>/runs/proposals/iter-<NN>.json
   Create/patch skills under <ws>/skills/active ONLY via the proposal file;
   the harness applies it. [...]
   WRITE EARLY — leave enough turns to finish the file before the cap.

Proposal JSON schema (write the file with write_file):
{"action": "create", "name": "snake_case", "skill_md": "full SKILL.md with YAML frontmatter + When to Apply + When NOT to Apply + Instructions", "purpose_md": "Origin + Patterns Addressed + Evolution History"}
{"action": "patch", "name": "existing-skill", "edits": [{"op": "append"|"replace"|"insert_after", "target": "exact text", "content": "..."}]}
{"action": "no_action"}
Prefer patching over creating when a skill is partially correct. Keep skills
concise and actionable. If no change is warranted, write {"action": "no_action"}.
```

与论文附录 E.3 的差异：论文版 proposer 只有 `read_file` + `finish(proposal)` 两工具、提案经 finish() 提交；源码版改为 `write_file` 写 JSON 到固定路径（`runs/proposals/iter-NN.json`），由 harness 读取应用（`prompts.py:74-86` 的 `propose_step`，`harness.py:74`）。训练摘要表按分数升序排列（最差的排最前），是源码新增的引导。

**提案原子粒度**：一次提案恰好作用于**一个**技能（create 或 patch 三选一），patch 的 edits 列表可含多个操作但都落在同一文件上（`gating.py:67-105`）。`no_action` 是一等合法结果，不触发验证 rollout，也写进 skill-impact.md（`harness.py:140-147`，`prompts.py:128-129`）。

配套的框架技能 `skills/wikiskill-proposer/SKILL.md`（装进 proposer agent 的 profile，`harness.py:17` 的 `FRAMEWORK_SKILLS`）把同一规程展开成 SKILL.md 形态，其中 patch 纪律明确："`replace`/`insert_after` targets must be short, specific text present in the file. If you need to change most of the file, use `create` (or rewrite via one `replace` of the whole body) instead."

### 2.3 Wiki Maintainer 的 prompt（`wikiskill/prompts.py:48-79`）

核心约定：读失败 trace 做根因分析、也读成功 trace 保住有效行为；"traces can be very long. Do NOT read every line... Reading selectively leaves budget for writing"；**"WRITE EARLY, edit later"**（`prompts.py:73`——源码实测教训：25 轮预算够分析不够写，见 §2.7 Run 2）；pattern 页 10-30 行；index.md 整体重写、每 pattern 一行；**"Do not touch the skills directory — that is the Skill Proposer's job"**（`skills/wikiskill-maintainer/SKILL.md`，职责隔离写进技能）。维护者 prompt 只提供采样后的 manifest（≤8 条路径），不像 proposer 可自主探索。

### 2.4 门控判定代码（R_val/R_best 的确切计算与比较）

- **R 的计算**：`gating.py:169-174` `mean_score` = 各任务得分（0.0/1.0）的算术平均，round 到 4 位小数。得分来自 `scoring.py:32-60` 的四种确定性 grader（exact / contains / json_field / code_stdout），异常（缺文件、JSON 解析失败、超时 60s）一律 0.0 不 crash。
- **比较与接受**：`harness.py:159` `accepted = r_val > prev_best`——严格大于，代码就这一行；接受则 `gating.py:119-122` `accept_commit`（git add -A + commit "accept iter-k R=<r_val>"）并更新 `state["r_best"]`；拒绝则 `gating.py:107-110` `rollback` = `git reset --hard -q` + `git clean -fd -q`（在 `skills/active` 仓库内）。
- **R_best 初值**：首次 evolve 先跑空技能基线验证（`harness.py:115-121`），`baseline` 与 `r_best` 都设为该值；`R_best==1.0` 提前终止（`harness.py:124-126`，`--no-early-stop` 是 dev 旋钮）。
- **提案应用**：`gating.py:67-105` `apply_proposal`——create 写 `SKILL.md` + 可选 `PURPOSE.md`；patch 的 `replace`/`insert_after` 要求 target 是文件中的**精确子串**，找不到抛 `ValueError`（`gating.py:91,97`）——即提案应用是全有或全无：一个 edit 失败整个 apply 抛异常（evolve 循环未捕获时会终止迭代）。
- **持久状态**：`runs/state.json`（`gating.py:24-37`）记录 domain/baseline/r_best/next_iter/history；history 每条含 iter/train_mean/r_val/accepted/proposal 描述——**这正是"技能数量演化曲线"的数据源**，`wikiskill status` 直接打印（`cli.py:53-62`）。
- **防幻影评分**（源码实测教训固化为代码）：每次 rollout 前强制重新物化沙箱、删除任务规格之外的所有文件（`gating.py:141-147` 调 `tasks.py:80-105` `materialize(force=True)`）；session 首行 `tool_call_count==0` 判定为启动失败并打警告（`gating.py:127-133`）。

### 2.5 skill-impact.md 的确切格式（`prompts.py:123-142`）

文件骨架由 `wiki.py:33-50` `ensure` 创建（初始内容 `# Skill Impact\n\n_No proposals yet._\n`），之后**只追加**（`wiki.py:52-56` `append_skill_impact`）。每条由 `gate_outcome_entry` 生成，确切结构：

```markdown
### iter-<NN> — ACCEPTED|REJECTED (R_val=<r_val>, R_best=<prev_best|—>)

Proposal: <create|patch> `<name>`
Proposal file: `runs/proposals/iter-<NN>.json` (re-run collisions possible — full content embedded below)

```diff
<unified diff，来自 gating.skill_diff()>
```

Full proposal content (paper: rejected proposals must remain visible to future proposers):

```json
<完整提案 JSON，含 skill_md/purpose_md 全文，json.dumps indent=2>
```

Validation: <r_val> > R_best → accepted, skills committed.
（或）
Validation: <r_val> ≤ R_best → skills rolled back; wiki retained.
```

`no_action` 时只写头两行（`prompts.py:128-129`）。**注意**：完整提案 JSON 内嵌的原因是提案文件按迭代命名，重跑会互相覆盖（"re-run collisions possible"）——审计链不能依赖可变路径。diff 由 `gating.py:113-116` `git diff` 生成。

### 2.6 wiki/ 目录组织与三层落盘

workspace 布局（`harness.py:34-48` `init_workspace`）：

```
workspaces/<domain>/
├── raw/traces/iter-<NN>/{train,val}/<task>.meta.json + <task>.jsonl   # 不可变（traces.py:40-44 已存在则抛 FileExistsError）
├── wiki/            # 独立 git 仓库（wiki.py:22-31：目录内 git init，每次变更 commit，永不回滚）
│   ├── index.md     # 模式目录，每 pattern 一行
│   ├── log.md       # 时间线日志（wiki.py:58-61 追加）
│   ├── skill-impact.md
│   └── patterns/*.md
├── skills/active/   # 独立 git 仓库（gating.py:45-53，初始提交 "S0: empty skill set"），受门控回滚
├── skills/framework/  # wikiskill-maintainer + wikiskill-proposer 两个框架技能的拷贝
├── bench/tasks/<id>/  # 任务沙箱
├── runs/            # state.json、proposals/、每次 agent run 的 stdout + session.jsonl
└── .hermes-home/    # 隔离 profile（见 2.8）
```

三个 git 仓库的分工是本文最重要的工程事实之一：**skills/active 一个仓（接受=commit，拒绝=reset --hard）、wiki/ 一个仓（只 commit 不回滚，纯审计）、外层 workspace 无仓**。`cmd_reset`（`cli.py:174-182`）清 raw/runs 并回滚技能，但 wiki 不动。

### 2.7 RUNS.md 六次真实运行——live 数据（含全部拒绝记录）

docs/RUNS.md 是作者记录的真实运行（每行对应 workspace 内 runs/ + raw/traces/ 工件，"No fabricated numbers"）：

| Run | 模型 | 基线 S0 | 结果 |
|---|---|---|---|
| 1 | deepseek-v4-flash, 15 轮 | R=1.0 | Algorithm 1 提前停止，正确行为 |
| 2 | 同上, 8 轮（加陷阱任务） | 1.0 → 强制迭代 | 提案 `spec_literal_transform`：R_val=1.0 不大于 R_best → **拒绝**。发现 maintainer 25 轮预算"够分析不够写"的 turn-cap bug |
| 3 | 同上, 60 轮修复版 | 1.0 → 强制 | maintainer 蒸馏出 4 个 pattern 页；提案 `exact-match-sandbox-task`：R_val=0.8889（技能反而伤了 1 题）→ **拒绝** |
| 4 | gemma-3-4b（免费档） | — | **整run作废**：12% session 启动失败（`-m` 路由 bug → HTTP 400），死 session 被旧沙箱残留交付物**幻影评分**。maintainer 的第 5 个 pattern 页 `trace-harness-launch-failure` 自己诊断出了框架 bug |
| 5 | gemini-2.5-flash-lite | 0.6667 | 提案 `find-secret`：R_val=0.4444，两题回归（extract-longest 1.0→0.0、find-biggest 1.0→0.0，"搜索精确字符串"的指引误导了需要**比较**文件的任务）→ **拒绝**。成本 **$0.086/迭代**（31 个真实 session） |
| 6 | 同上, 3 迭代复合实验 | 0.4444 | train 低至 0.2308，6/48 启动失败；仅 iter-03 蒸馏出 1 个 pattern；proposer **no_action**；r_best 保持 0.4444，零技能接受。诚实负结果：**积累需要更强的模型或更健康的 session** |

要点：**截至 v0.1.4，该实现从未在 live 运行中成功接受过一个提案**（作者自述"acceptance remains test-proven, not live-proven"）。论文的接受/复利数字（Table 4/5）依赖更强的 proposer 模型。另：docs/CRON.md 记录每夜 01:00 的 `evolve nightly --iters 1` 定时任务，免费档小模型一次迭代约 1-2 小时。

### 2.8 隔离 profile：与论文不同的实现路径

论文 §3.2.1 是**把技能全文注入系统提示**（full-injection，消除检索/触发失败作为混淆变量）。源码走的是另一条路：`backends/hermes.py:45-63` `bootstrap_profile` 为每个 workspace 建独立 `HERMES_HOME`（拷贝 config/凭证、清空 sessions/memories、`hermes skills opt-out` 关闭捆绑技能种子）；`hermes.py:66-88` `set_active_skills` 在**每次 agent 调用前**把 profile 的 skills/ 重建为 active 集（+ maintainer/proposer 轮次额外加框架技能）的 symlink 集。语义等价（agent 恰好看到 S_k），但机制是宿主原生技能加载而非 prompt 注入——对 CodeWiki 的启示：**"草稿区不生效"用宿主的技能发现机制（profile/symlink 隔离）实现，比改系统提示更干净**。

其他后端同理：Claude Code 用隔离 `CLAUDE_CONFIG_DIR`、Codex 用隔离 `CODEX_HOME`、Copilot 把 active 集 symlink 进沙箱的 `.github/skills/`（README "Agent backends" 节）。

### 2.9 demo bench 的陷阱任务设计（自建验证基准的样板）

`bench.py:337-456` `trap_tasks`：四种"可靠地让朴素 agent 在 S0 失败"的任务（数十换算陷阱、隐含字母过滤、双 bug 调试脚本 ×2）。双 bug 任务在**生成时 assert 两个 bug 不会互相抵消**（`bench.py:411` `assert buggy_val != int(expected), "trap debug-boundary: bugs compensate!"`）——防止"错错得对"让陷阱任务失真。bench 总体 22 任务（13 train / 9 val，seed 42 确定性生成），任务族瞄准经典失败模式：不读全规格、硬编码、朴素解析、不验证输出（`bench.py` 模块 docstring）。"每个任务交付物都是文件，评分无歧义"。`compare` 子命令提供配对 win/loss/tie 表 + 双侧精确二项 p 值（McNemar 类，`compare.py:29-46`），回答"这技能到底有没有用"。

### 2.10 transfer：跨工作区技能拷贝（Table 2 的工程对应物）

`transfer.py:26-66`：把 src 的 active 技能整目录拷进 dst 的 active 集；同名默认跳过（`--force` 覆盖，先 rmtree 再 copytree）；在 dst 仓库做一次 git commit，之后 dst 可以用自己的模型跑 `gate` 验证——**拒绝即回滚，与普通提案同语义**（模块 docstring）。没有做任何模型适配或冲突合并。

---

## 3. SKILL.md 产物：frontmatter 与正文结构（vs OKF v0.2）

### 3.1 提案 schema 约定的最小形态

`prompts.py:115` 的提案 schema 只约定：`skill_md` = "full SKILL.md with YAML frontmatter + When to Apply + When NOT to Apply + Instructions"。frontmatter 只要求 `name` + `description`（论文 §2："a unique name and concise description"）。**没有 status/version/lifecycle 字段——生命周期完全外置在 git 提交史 + skill-impact.md 审计链里**。

### 3.2 仓库内 5 个真实演化产物的实际结构

`skills/` 下 5 个技能是 Run 3-5 期间演化出的真实产物（RUNS.md 逐一对得上：spec-literal-execution、script-exec-blocked、search-miss-binary、verify-output-readback、trace-harness-launch-failure），被作者打包随仓分发（仓库兼作 Hermes skills tap）。实际形态：

- frontmatter：`name`、`description`（一句触发条件，含具体工具名与行为指令）+ 打包时加的 `version: 1.0.0`、`license: MIT`、`platforms`、`metadata.hermes.tags/homepage`（后四项是 tap 分发包装，非演化产物内生）。
- 正文骨架实际是 **Problem → Root cause → Fix → Evidence**（不是提案 schema 约定的 When to Apply 三段式——真实产物偏离了 schema，但 Evidence 段保留）。
- **Evidence 段带量化回链**：如 `spec-literal-execution` 写 "FAIL: spec-format2-1 (0.0). PASS: spec-format1-1, spec-format3-1 (1.0) — same duplicate-shaped data"；`script-exec-blocked` 写 "Hit in 3/4 analyzed traces"。任务 ID + 分数 + 对比样本，可追溯到 graded 任务。
- `description` 的写法值得注意：全是"条件 + 具体行动"式，如 "ripgrep/search_files silently skips binary-detected files — verify empty search results with grep -a / file / xxd before concluding 'not found'"。

### 3.3 与 CodeWiki 设计稿 OKF v0.2 frontmatter 的对比

| 字段 | wikiskill 演化产物 | CodeWiki 草稿区设计（skill-creator设计方案） | 差异评注 |
|---|---|---|---|
| name / description | 有（description = 触发条件 + 行动） | 有（同语义） | 一致 |
| type / status / generated / stale_after | 无 | 有（`type: Skill`、`status: draft|stable|deprecated`） | CodeWiki 把生命周期写进 frontmatter；wikiskill 外置到 git + skill-impact.md。CodeWiki 多这套是因为**没有自动门控**，需要文件自描述状态 |
| metadata.source_refs | 无独立文件级字段 | 有（scenario/notes 回链） | wikiskill 用**独立 PURPOSE.md 文件**（Origin + Patterns Addressed + Evolution History）承载同一信息 |
| metadata.revisions | 无 | 有（`{at, reason, source}` 列表） | wikiskill 的等价物是 skill-impact.md 的 unified diff 审计链（外部、含拒绝记录） |
| installed_at / installed_to | 无 | 有 | wikiskill 无两区制：active 即生效 |
| 正文骨架 | When to Apply / When NOT to Apply / Instructions（schema 约定）；实际产物 Problem/Root cause/Fix/Evidence | 工作场景/适用条件/核心 SOP/判断逻辑/禁忌与反模式 | 语义高度同构：When NOT to Apply ≈ 禁忌与反模式；Instructions ≈ SOP；Evidence ≈ 关键事实依据。CodeWiki 的 scenario 骨架与论文约定天然对齐 |
| 溯源粒度 | PURPOSE.md + Evidence 段（任务 ID + 分数） | source_refs + revisions | wikiskill 的 Evidence 带**量化结果**（分数、命中率），CodeWiki 设计稿目前只有路径引用——可借鉴"证据段带任务/场景 ID + 结果数字" |

对 CodeWiki 的两个具体启示：① `PURPOSE.md` 独立文件 vs frontmatter `source_refs`——如果 SKILL.md 会被宿主全量读入上下文，溯源元数据放独立文件可省 token（wikiskill 的选择）；CodeWiki 草稿区进 lint 进索引、不直接生效，frontmatter 方案可行，但 install 到生效区时可考虑剥离冗余元数据。② description 的"条件+行动"写法（wikiskill 产物全部如此）比抽象概括更利于触发判定。

---

## 4. 技能退役、冲突、去重机制现状（对应 Q10/Q11）

### 4.1 退役（retirement）：不存在

- 源码 grep `retire|deprecat|delete_skill|remove_skill` 零命中（唯一 "Deprecated" 是无关的函数注释，`backends/hermes.py:90`）。
- 技能唯一退出路径是**提案被拒**（git 回滚）或 `wikiskill reset`（回滚到上次 commit，`cli.py:174-182`）。已接受的技能**永远不会被主动移除**——只能被后续 patch 逐步改写。
- 论文 Limitations 第 3 条自认："Wiki Layer continuously accumulates... currently lacks an automated mechanism to prune the wiki"，且未提技能修剪。技能侧不膨胀的现实原因是接受率低（Table 4：每次完整演化仅 1.2-1.6 个创建被接受）+ 演化轮数少（≤8）。
- **对 CodeWiki 的参照**：wikiskill 没有解决退役问题，但它的"永不退役 + 外置审计链"之所以没爆炸，靠的是入口严（严格门控）和寿命短（≤8 轮）。CodeWiki 半闭环没有自动门控，入口松，**retire 模式（设计方案已有）不是可选项而是必需**——这是本次核实的最重要结论之一。

### 4.2 冲突（conflict）：机制薄弱，有两处隐患

- `apply_proposal` 的 create 分支对同名目录 `os.makedirs(exist_ok=True)` 后直接覆写文件（`gating.py:74-84`）——**同名 create 静默覆盖既有技能，无冲突检测**。
- `transfer` 对同名技能默认 skip、`--force` 才覆盖（`transfer.py:47-49`）——唯一有名字冲突意识的地方。
- 无语义冲突检测（两个技能给矛盾指引时无任何机制发现）。论文 Limitations 第 1 条承认未评估多技能场景（全量注入 + 技能数少，冲突未成为实验内问题）。
- **对 CodeWiki 的参照**：设计稿的"name/description Jaccard 相似度冲突预检"在 wikiskill 中完全缺失，属于 CodeWiki 超前项；但 wikiskill 的教训（覆盖无声、审计链靠外置 diff 补救）提示**覆盖/更新必须留 diff 或 revisions 记录**。

### 4.3 去重（dedup）：prompt 纪律，非代码机制

- 维护者 prompt："Do NOT create duplicate patterns — update existing ones with new evidence"（附录 E.2）/"Keep the wiki compact; merge overlapping patterns"（`skills/wikiskill-maintainer/SKILL.md`）。
- 提案者 prompt："Prefer patching over creating when a skill is partially correct"（附录 E.3 / `prompts.py:118-119`）+ "DO NOT repeat rejected approaches"（`prompts.py:102-103`）。
- 没有任何程序化去重（无相似度计算、无向量检索）。被拒提案防重发的机制是**把完整被拒 JSON 内嵌进 skill-impact.md** 让下一轮 proposer 读到（`prompts.py:136`）——这是 wikiskill 对"重复提案"问题的唯一结构性答案，且是纯信息性的（靠 LLM 遵守）。
- **对 CodeWiki 的参照**：Q10（技能有效如何判定）在 wikiskill 的对应物是 R_val 数字进 skill-impact.md；CodeWiki 无自动评分，最接近的等价物是把"人工试用反馈/任务结果"结构化回写（设计方案 Q10 的 effectiveness 字段方向），并且 wikiskill 证明**审计链放外部文件、按迭代追加、含完整被拒内容**是可行且被论文要求的形态。

---

## 5. 结论：本次精读对 skill-creator 设计的五条直接输入

1. **产物双文件**（SKILL.md + PURPOSE.md）是论文原生设计；CodeWiki 用 frontmatter source_refs 承载同一信息可行，但 install 时考虑剥离，Evidence/溯源正文带量化结果（任务 ID + 分数/命中率）值得抄。
2. **"更新必须留痕"有论文级依据**：skill-impact.md 是 harness 程序化追加、含 unified diff + 完整被拒提案 + R_val 数字的外置审计链；CodeWiki 的 revisions 字段 + 拒绝记录应达到同等信息密度。
3. **退役是 CodeWiki 的真缺口**（wikiskill 未解决且论文自认未解决），半闭环入口松，retire 模式必须落地；冲突预检（Jaccard）是 CodeWiki 超前项，但 create 覆盖必须显式（wikiskill 的静默覆写是反面教材）。
4. **回流有效性判定可借用 skill-impact 形态**：即使没有自动门控，"每次试用 → 追加一条结构化结果记录（改了什么 / 结果数字 / 接受与否）"就能构成 Q10 需要的判定素材；wikiskill 的 no_action 证明"propose 无变化"也是合法轮次，CodeWiki 的重编译应允许空产出。
5. **多轮回流有数据支撑**（Table 5：39-58% 接受发生在前两轮，但 mid/late 仍占 42-61%），但**门槛条件是 proposer 模型够强 + 素材里有真实失败**（RUNS.md Run 6 的负结果：弱模型 + 高启动失败率下 wiki 断粮、no_action、零积累）——CodeWiki 半闭环的"提炼用强模型、执行交给宿主"与论文 Table 2 的"发现/执行分离"结论一致。

---

## 附：本次引用源清单

- 论文 HTML 全文：arxiv.org/html/2608.27454（摘要、§1-7、Limitations、附录 A-E、Table 1-7、Figure 1-3）
- 源码：`.research-competitors/wikiskill/`（commit 02fac2c，v0.1.4），重点文件 `wikiskill/prompts.py`、`wikiskill/gating.py`、`wikiskill/harness.py`、`wikiskill/wiki.py`、`wikiskill/scoring.py`、`wikiskill/bench.py`、`wikiskill/tasks.py`、`wikiskill/transfer.py`、`wikiskill/compare.py`、`wikiskill/backends/hermes.py`、`skills/*/SKILL.md`、`docs/RUNS.md`、`docs/CRON.md`、`docs/COMPARING.md`、`README.md`
- 未获取：XStack18《WikiSkill——把 Agent 经验编译成永久知识》公众号原文（WebSearch 两轮未找到原文或可靠转载，本文零引用）
