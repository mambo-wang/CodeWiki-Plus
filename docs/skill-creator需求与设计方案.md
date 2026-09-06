# skill-creator 需求与设计方案

> 把已确认知识编译成 SKILL.md 行为指令资产：MVP 单向编译器 + 回流接口设计。
>
> 编制日期：2026-09-06 · 状态：**已实施**（T1-T5 落地于 issues #24-#28，commits b12e98c/3db4827/64fb95e/e08dae6/c1beee9；闭环验证 #29 完成——真实素材全链 prepare→submit→lint→install→flag→revise→drift→reinstall 实测通过。用户文档：`docs/skill-creator使用指南.md`）
>
> 前置文档（本方案的输入，本文不重复其论证）：
> 1. `repowiki/wiki/comparisons/自动生成SKILL可行性-wikiskill闭环-vs-CodeWiki编译复用.md` — 三档方案定档（方案 C 半闭环，MVP = 单向编译器）
> 2. `repowiki/wiki/queries/skill-creator设计方案.md` — 工具形态初稿（四 mode、两区制、防碎片纪律、Q10/Q11 未决）
> 3. `docs/WikiSkill论文与wikiskill源码精读.md` — 一手事实补充（论文 Table 1-7 全表、源码工程细节、退役/冲突/去重现状）
> 4. `docs/adr/0004-skill-scenario-split-two-zone-gate.md` — 本方案催生的架构决策
>
> 本文职责：整合上述输入 + 2026-09-06 grill 拷问九问（Q1-Q9）的收敛结论，形成
> 唯一的**实施输入**——后续 to-spec / 工单拆解以本文为准。

## 1. 目标与非目标

**目标**：让 CodeWiki 的知识管线长出「自动生成 SKILL」能力——已确认知识
（scenario + 精选 notes）经宿主 agent（Mode C）编译为 SKILL.md 草稿，人工确认后
install 到生效区，被宿主 IDE 自动发现并改变 agent 行为；试用反馈经既有通道回流，
支撑技能修订迭代。

**非目标**：

- 不建自动评分门控（无 held-out 基准；且 wikiskill 六次 live 运行零接受、$0.09/迭代
  的数据表明弱模型下自动门控收益存疑——精读报告 §2.7）
- 不编 Inference Agent 编排（那是重做 wikiskill；CodeWiki 的采集管线天然回流）
- 不做跨工作区技能迁移（wikiskill transfer 的对应物，暂无需求）

## 2. 范围（Q1/Q2 收敛）

**本次实施（MVP）**：

1. `skill_creator` 工具（四 mode：prepare / submit / install / retire）
2. 草稿区 `repowiki/skills/` 目录与词汇层（schema page_types.skill）
3. SKILL.md lint 规则与容量控制
4. 素材过期联动、漂移检测（lint 检查）
5. 有效性反馈通道接线（flag_issue 复用）

**本次只设计不实施（回流迭代，Phase 2）**：

6. 回流接口——用生成的 SKILL 跑真实任务 → 采集管线吸收 → 再提炼改进。MVP 落地时
   保证回流**数据有落点**（见 §4.4），迭代编排不做。

**明确不做**：自动评分、自动触发编译（Doctrine「触发永远显式」）、生效区自动同步。

**素材边界（2026-09-06 补）**：任务记忆（task memories）**不作 skill 素材**——它是
直写落盘不经确认的进度知识（ADR-0002），直取等于给最高风险产物开免检通道；通用
经验若值得变 skill，蒸馏双轨时本就该落成 note（正道 = 重新蒸馏 raw / 手动
`ingest_note` 过闸门）。Phase 2 可评估任务记忆作 prepare 的**发现信号**（高频主题
提示「值得蒸馏」），只借信号不借内容。

## 3. 领域词汇

见 `CONTEXT.md` 「skill」词条（2026-09-06 入表）。核心分轨一句话：**scenario 是
检索知识（agent 查阅），skill 是行为指令（IDE 触发）**；与 `consolidate_notes` 的
分工表沿用设计稿（上游 scenario → 下游 skill，source_refs 回链）。

## 4. 机制设计

### 4.1 工具形态：`skill_creator` 四 mode

新文件 `codewiki/mcp/tools/skill_creator.py`，`registry.py` 注册。沿用
`note_consolidation.py`（Mode C 先例，`codewiki/mcp/tools/note_consolidation.py:344`
起 prepare / `:400` 起 submit）的骨架：

| mode | 入参 | 行为 |
|---|---|---|
| `prepare` | `topic?`, `sources?`, `limit?` | 返回候选素材（未编译 scenario + 精选 notes）、草稿区与生效区技能索引、冲突预检、容量预警、**该技能名下 open issues**（Q3 回流素材）、正文写作系统提示 |
| `submit` | `report.skills[]` | frontmatter 校验、路径安全、落草稿区、溯源互链、`revisions` 追加、索引重建、计数器归零 |
| `install` | `name` | 草稿 → `.codebuddy/skills/<name>/SKILL.md`，写 `installed_at`，**仅用户确认后调用** |
| `retire` | `name`, `reason` | 标记 deprecated + 从生效区 uninstall，正文保留（审计） |

相对设计稿初稿的增量：

- **prepare 吸收 open issues**：候选素材中，对既有技能聚合其名下 flag_issue 的
  open 问题作为修订输入（复用 `codewiki/mcp/tools/issue_tracker.py:66`
  handle_flag_issue 的数据，不新开通道——Doctrine「单点收敛」）。
- **允许空产出**：`no_action` 是合法轮次（wikiskill 先例：`harness.py:140-147`）。
  submit 报告可以为空（"素材不足，不值得编译"），不视为失败。

### 4.2 目录、frontmatter 与 install 剥离（Q8 收敛）

```
repowiki/skills/<name>/SKILL.md      # 草稿区：进索引进 lint、不生效
.codebuddy/skills/<name>/SKILL.md    # 生效区：IDE 自动发现
```

**溯源单文件自包含**（Q8 定档 (a)，否决 wikiskill 双文件 PURPOSE.md 方案）：草稿区
frontmatter 承载全部管理信息，膨胀由既有 `fold_private_metadata`
（`codewiki/src/frontmatter.py:203`）折叠吸收。理由：草稿区消费者是 lint 与 agent，
自包含优先；drift 比对（§4.5）只算一个文件。

```yaml
---
name: <slug>
description: <触发条件 + 具体行动，一句话>     # 写法规范见 §4.3
type: Skill
status: draft            # draft | stable | deprecated
generated: { by: codewiki/<ver>, at: <ts> }
stale_after: <date>
metadata:
  summary: <40 字内>
  source_refs: [wiki/scenarios/xxx.md, notes/yyy.md]
  revisions: [{ at, reason, source }]          # 每次修订追加；信息密度对齐 skill-impact.md
  installed_at: <ts>
  installed_to: .codebuddy/skills/<name>/
  installed_hash: <规范化内容哈希>             # install 时写入，drift 检测用（§4.5）
---
```

**install 剥离**：生效区只保留 `name` / `description` / 正文——`type`/`status`/
`generated`/`stale_after`/`metadata.*` 全部剥离（SKILL.md 会被宿主全量读入上下文，
管理元数据在那里是纯 token 浪费；wikiskill 的 PURPOSE.md 独立文件正是出于同一动机，
精读报告 §3.3 启示①）。生效区文件由 install 程序化生成，**不允许**在生效区直接编辑。

### 4.3 写作规范（吸收 wikiskill 产物实测经验）

1. **description = 条件 + 行动**：wikiskill 五个真实演化产物的 description 全部如此
   （如 "ripgrep/search_files silently skips binary-detected files — verify empty
   search results with grep -a / file / xxd before concluding 'not found'"），
   比抽象概括更利于 IDE 触发判定（精读报告 §3.2）。
2. **正文骨架沿用 scenario 五段**：工作场景 / 适用条件 / 核心 SOP / 判断逻辑 /
   禁忌与反模式——与论文三段式（When to Apply / When NOT to Apply / Instructions）
   天然对齐（精读报告 §3.3 对比表）。
3. **关键事实依据段带量化回链**：不止 source_refs 路径，正文证据段应带
   note 标题 + 关键结论（wikiskill Evidence 段带任务 ID + 分数 + 命中率的做法值得
   抄，精读报告 §3.2）；CodeWiki 的对应物是「依据：notes/xxx.md 的 Y 结论」。
4. **正文长度上限 8KB**（Q4 定档；Anthropic 官方技能普遍 1-3KB，8KB 已宽，超限
   说明该拆分或该引用 scenario 而非复述）。
5. **禁绝对路径与密钥**（lint 强制）。

### 4.4 有效性回流（Q10 收敛）

**负面反馈 = flag_issue**：试用发现问题 → 对该技能草稿/生效条目 `flag_issue`
（issue_type 建议 `skill-ineffective`）；`skill_creator prepare` 聚合该技能名下
open issues 作为修订素材（§4.1）。修订闭环：flag → prepare（看到 issue）→
submit（revisions 记录 reason）→ install。

**正面反馈 = 沉默即默认**：好用 = 不 flag 不 retire，无额外机制（避免为「点赞」
再造一条通道；usage 信号无数据源——IDE 不回报技能触发次数）。

**素材过期联动（Q5 收敛）**：技能 `source_refs` 指向的素材若被后续 consolidate
更新、retire 或 deprecate，lint_wiki 将该技能标记 `possibly_stale`（复用既有对端
新鲜度语义：ADR-0003 的"素材变没变"时间线），提示人决定 revise / retire。不自动
触发修订（Doctrine「触发永远显式」）。

### 4.5 lint 规则与容量（Q4/Q5/Q6 收敛）

草稿区纳入 `lint_wiki` 扫描（进索引就进 lint，不留法外之地）。SKILL.md 专项检查：

| 规则 | 级别 | 说明 |
|---|---|---|
| name slug 合规 | error | slugify 后与目录名一致 |
| description 非空且含触发条件语义 | error | 「条件 + 行动」结构（§4.3-1） |
| frontmatter 完整 | error | status / source_refs 必填 |
| 正文 ≤ 8KB | error | 超限拒收 |
| 无敏感串 | error | 绝对路径、密钥 pattern |
| 修订必有 revisions | error | updated 条目 revisions 非空 |
| 素材过期联动 | warning | source_refs 素材 deprecated/已删 → possibly_stale（§4.4） |
| 漂移检测 | warning | 草稿区规范化哈希 ≠ `installed_hash` → "草稿已修订，生效区仍旧版，建议 reinstall"（§4.2） |

**漂移不自动修复**（Q6 收敛）：install 后草稿再修订，生效区不自动覆盖——"生效是
用户动作"（定档第 5 条）。lint 暴露 + prepare 提示，reinstall 由人决定。

**规范化哈希**：install 剥离了管理元数据，drift 比对不能比整文件 content_hash——
草稿区算「name + description + 正文」的规范化哈希存入 `installed_hash`，lint 比较该
值。

**容量硬顶 12 份**（类比 `max_scenarios`=15，`codewiki/mcp/tools/aggregation_state.py:94`）：
红（≥12）= 先合并再新建；橙（≥9）= 只 UPDATE。防碎片纪律沿用设计稿：默认 UPDATE、
每批最多新建 1 份、新建前读 ≥2 份最相似技能、name/description Jaccard 冲突预检
（wikiskill 的 create 同名静默覆盖是反面教材，精读报告 §4.2；retire + 冲突预检是
竞品缺失的必需项，精读报告 §4.1）。

### 4.6 索引但不可召回（Q7 收敛，显式设计约束）

草稿区 `repowiki/skills/` **参与索引构建**（lint、drift 检测、prepare 候选扫描、
容量统计依赖索引），但**不进入 query_wiki 召回排序**。理由：技能消费方是 IDE 自动
触发；若同时可被检索召回，agent 会把 SKILL 正文当知识引用，混淆「检索知识」与
「行为指令」两种语义（ADR-0004 决策 2）。实现上：索引构建含 skills 目录，检索
入口（`wiki_search.search` 的 SearchIndex Protocol 调用侧）按 page_type 过滤排除
skill——过滤收口在 search 入口，与既有 freshness gate 同位置，避免调用方各自为政。

## 5. Q10/Q11 收敛结论（对设计稿未决问题的正式回答）

**Q10 技能有效如何判定**：负面 = flag_issue（§4.4）；正面 = 沉默即默认；素材过期 =
lint possibly_stale。不建 effectiveness 字段（无自动数据源）、不建 skill-impact.md
独立审计文件（revisions + flag_issue 信息量覆盖其子集，Doctrine 单点收敛）。

**Q11 lint 与容量**：规则清单见 §4.5（8 项：6 error + 2 warning）；正文上限 8KB；
容量硬顶 12 / 橙线 9；草稿区纳入 lint_wiki 扫描。

## 6. 验收标准

MVP 验收 = 以下场景全部可用且测试覆盖：

1. `skill_creator(mode="prepare")` 返回候选素材（scenario + 精选 notes + 既有技能
   open issues）、容量与冲突预警，无自动副作用。
2. `submit` 落草稿区，frontmatter 校验失败（缺 status / 正文超 8KB / 敏感串）时
   拒收并报具体规则；成功时溯源互链（技能 source_refs ⇄ 素材 compiled_into）。
3. `install` 产出剥离管理元数据的生效区 SKILL.md，写 installed_at/installed_hash；
   二次调用幂等。
4. 修订后 `lint_wiki` 报 drift warning；素材 retire 后报 possibly_stale warning。
5. `retire` 标记 deprecated 且从生效区移除，草稿正文保留。
6. `query_wiki` 任意查询不召回 skill 类型页面；`lint_wiki` 扫描覆盖草稿区。
7. 全量 pytest 通过 + ruff（0.16.3）零告警；工具接口七处同步完成（§7-8）。

## 7. 实施拆解（建议工单序）

依赖从下往上，阻塞关系如箭头所示：

1. **词汇层**：`repowiki/schema.yaml` 增 `page_types.skill`（directory: `skills`，
   required_sections 沿用五段骨架）；`note_types.py` 同款思路增 skill 资产声明。
   → 阻塞 2/5
2. **配置与目录**：`codewiki/src/config.py` 增 `SKILLS_DIR`（草稿区）与生效区常量
   （`PAGE_TYPE_DIRS` 同处）。→ 阻塞 3
3. **skill_creator 工具**：四 mode 实现，复用 `store.locked_rmw` + frontmatter
   round-trip（`codewiki/src/frontmatter.py`）+ `aggregation_state` 计数器；含
   install 剥离与规范化哈希。→ 阻塞 4/6
4. **lint 扩展**：SKILL.md 八项检查（§4.5）+ possibly_stale 联动 + drift 检测 +
   容量阈值。→ 阻塞 6
5. **检索隔离**：search 入口按 page_type 排除 skill（§4.6）。
6. **仓内闭环验证**：拿真实素材走一轮 prepare→submit→install→flag→revise 全链。
7. **同步与测试**：handler / registry / prompts（正文+注册）/ resources / README
   中英 / docs 设计文档 / tests——七处同步 + 全量测试（本仓接口改动同步纪律）。
8. **回流接线**：prepare 聚合 flag_issue open issues（可与 3 同工单做）。

Phase 2（本次不做）：真实任务回流编排、技能采纳信号、hooks.yaml 家族分发技能资产。

## 8. 风险与已知限制

- **CodeBuddy 技能发现对 install 产物格式的实际兼容性**未实测（MVP 验收场景 3/6
  需真机验证一次）。
- **容量 12 的取值是类比推定**，无运行数据支撑；上线后按 lint 的容量告警频率调整。
- **正面反馈通道缺失**是有意取舍：若未来 IDE 提供技能触发回执，可再评估。
- 半闭环多轮回流的门槛条件（提炼模型够强 + 素材含真实失败，精读报告 §5-5）意味着
  回流质量依赖宿主模型档位，工具层不解决。
- **素材保真度受捕获链路信息损耗制约**（见 §9）：压缩时丢掉的工具操作细节，蒸馏
  永远找不回来——这是 notes/scenarios 素材质量的上游杠杆，影响 skill 生成上限。

## 9. 素材保真度：捕获链路的信息损耗（✅ 方案乙已落地，2026-09-06 收官后实施）

skill 的价值密度取决于素材里「命令-报错-修复对、版本/参数钉子、失败轨迹」的保有量
（wikiskill 演化产物全是此类；论文 Proposer 纪律要求读 ≥4 条失败 trace 诊断根因）。
原现状是这些信息在捕获链路被系统性丢弃：

**丢弃触点清单（2026-09-06 实核，现已全部治理）**：

1. `codewiki/mcp/tools/capture_conversation.py` — ~~`_NOISE_BLOCK_TYPES` 11 类
   块整体丢弃~~ → 改接共享两级消化
2. `codewiki/mcp/_ide_hook.py` — ~~同名集合，IDE hook 采集侧同样过滤~~ → 同款接入
3. `AGENTS.md`「QwenWork 捕获协议」— ~~「丢弃工具调用细节」~~ → 改为「保留关键
   命令原文、报错→修复对、版本/参数钉子；判断标准：换个会话还能复用吗」
4. `tests/test_ide_hook_capture.py` — ~~断言 tool 块被过滤~~ → 断言压缩行 +
   error 片段，新增 tool_digest 专项 3 例
5. distill-worker 剧本 — raw 现已携带 `[tool: …]` / `[tool-error: …]` 行，
   蒸馏可直接提取命令-报错-修复对

**实施（方案乙，共享单点实现 `codewiki/src/tool_digest.py`，stdlib-only）**：

- 纯噪音（thinking/reasoning/system/context）仍无条件丢弃
- tool 调用（tool_use/tool-call/function_call，横杠与下划线两种拼写）保留为
  一行压缩形态：`[tool: 名 · 命令首行]`（≤160 字符），保持原始顺序——顺序即
  「命令→报错→修复」链
- tool 结果仅当疑似错误时保留：is_error 标记或错误指纹（traceback/error/
  failed/permission denied/exit code…）命中 → `[tool-error: 摘录]`（≤200 字符
  追加预算）；成功结果仍丢弃
- 两侧采集路径（capture_conversation + _ide_hook）共享同一实现，永不漂移
- 副产品：P0 设计的 toolError 摩擦信号从「不可得」变为「可扫 raw 检出」
  （P0 文档 §2.1 已加勘误）

**原始改进方向（存档）**：方案甲（指令层压缩准则）与方案乙（代码层两级消化）
原为两档后续工单；实际落地时合并——AGENTS.md 指令层与代码层同批完成，distill-worker
剧本随 AGENTS.md 口径自动继承（剧本引用捕获协议，无需单独改）。

**与 MVP 的关系**：MVP（T1-T6）已先行落地；本项在其后实施，成为回流迭代
（Phase 2）的素材质量地基——从此捕获的会话天然携带命令-报错-修复链。

---

*源设计文档：repowiki/wiki/queries/skill-creator设计方案.md（stable）+
docs/WikiSkill论文与wikiskill源码精读.md（2026-09-06）+ grill Q1-Q9 收敛记录
（2026-09-06 会话）。状态：已实施（MVP #24-#29 + §9 素材保真度均落地）。*
