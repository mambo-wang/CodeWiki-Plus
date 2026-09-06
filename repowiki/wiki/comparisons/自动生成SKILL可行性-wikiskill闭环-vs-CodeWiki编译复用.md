---
title: "自动生成 SKILL 可行性：wikiskill 闭环 vs CodeWiki 编译复用"
type: Comparison
description: "调研 WikiSkill（arXiv:2608.27454 开源实现）与论文解读后，评估 CodeWiki 知识管线能否承载「自动生成 SKILL」能力：三档方案对比（全闭环/单向编译/半闭环），定档为半闭环起步、MVP 先做单向编译器。"
generated: { by: codewiki/5.6.0, at: 2026-09-05T15:20:04Z }
stale_after: 2026-12-04
aliases: [自动生成SKILL可行性-wikiskill闭环-vs-CodeWiki编译复用]
status: stable
tags: [skill, 他山之石, 可行性, wikiskill, 经验编译]
metadata:
  related_modules: ["codewiki/mcp/tools"]
  source_refs: ["arXiv:2608.27454", "https://github.com/ashutoshsinghpr7/wikiskill"]
  code_fingerprint: sha256:829467a7f49459ddf16d1711753a335b7338eb7409360e8d30565d9f78d11621
---
# 自动生成 SKILL 可行性：wikiskill 闭环 vs CodeWiki 编译复用

## 背景与目标

「他山之石」任务下调研两个外部对象，判断 CodeWiki-CN 能否实现「自动生成 SKILL」：

1. **wikiskill 开源项目**（ashutoshsinghpr7/wikiskill，arXiv:2608.27454 的 faithful 实现，Hermes Agent 后端，兼容 Claude Code/Codex/Copilot CLI）
2. **论文解读文章**（XStack18 转载，介绍 Google Research + Virginia Tech 的 WikiSkill 框架）

目标不是复刻 wikiskill，而是判断：**CodeWiki 既有的知识管线（对话→蒸馏→笔记→确认→L2 场景→L3 doctrine）能否作为地基，长出「自动生成 SKILL」能力**，以及该长成什么形态。

## 候选方案

### 方案 A：WikiSkill 全闭环（外部参照）

进化闭环：`Inference Agent(跑任务产轨迹) → Wiki Maintainer(蒸馏成 wiki/patterns) → Skill Proposer(每次一个原子提案) → 门控(git 回滚，R_val > R_best 才接受)`。

- 三层空间：`skills/`(可回滚)、`wiki/`(永不回滚)、`raw/`(不可变)
- 隔离 profile 门控、skill-impact.md 审计链、demo bench 22 个自动评分任务（13 train / 9 val）
- 论文核心洞察：① Wiki 不暴露给执行者（防抄答案，轨迹质量 63.7%→60.9%）② 知识发现与执行解耦（强模型进化、弱模型执行）③ 被拒提案是下轮素材（复利效应）
- 工程极简：文件系统 + LLM 工具调用 + 50-100 行 Python 编排，无向量库

### 方案 B：单向编译器（CodeWiki 最短路径）

把已确认知识（confirmed notes + wiki/scenarios）编译成 SKILL.md 草稿 → 走既有确认闸门 → 落 `.codebuddy/skills/<name>/`。

- 沿 Mode C「prepare→宿主 agent 当 LLM→submit 确定性簿记」协议（distill_conversation / note_consolidation / doctrine 三先例）
- 门控 = 既有 draft→confirm_note 确认闸门 + 人工试用，不建自动评分

### 方案 C：半闭环（推荐落点）

在 B 之上加回流：用生成的 SKILL 跑真实任务 → 任务记忆/对话被现有采集管线吸收 → 再提炼改进 SKILL。

- 复用 CodeWiki 天然回流（SessionEnd 采集、任务记忆、supersede 增量重捕），无需 Inference Agent 编排与自动评分器
- 「经验复利」在人的确认闭环里发生，而非自动门控

## 对比分析

### 目标产物格式

两者一致：SKILL.md + name/description frontmatter，Anthropic Agent Skill 规范兼容。wikiskill 蒸馏的技能可直接装 `~/.claude/skills/`；CodeWiki 产物同理落 `.codebuddy/skills/`（本仓已实证纯 SKILL.md 直接安装可行）。

### 能力差距对照表

| 维度 | wikiskill（全闭环） | CodeWiki 现状 | 差距 |
|---|---|---|---|
| 素材源 | raw traces（原始轨迹） | notes/scenarios（已蒸馏结构化） | CodeWiki 素材更干净但缺轨迹细节 |
| 蒸馏 | Wiki Maintainer agent | distill_conversation（Mode A/B/C） | 已有等价能力 |
| 提案 | Skill Proposer（自主 ReAct，原子改动） | 无 skill 生成器 | **需新增** |
| 正文写作 LLM | 内嵌 agent | 仓库铁律：工具无状态，LLM 外置 | Mode C 天然适配 |
| 门控 | 自动评分 R_val>R_best + git 回滚 | 人工确认闸门（draft→confirm） | 无自动评分基准是**硬缺口** |
| 审计 | skill-impact.md | notes 生命周期 + aggregation_hint | 可移植 |
| 落盘 | skills/active（受 git 管理） | 无 .codebuddy/skills 写入器 | **需新增** |
| 回流 | 每轮迭代轨迹 | 任务记忆 + raw 采集（SessionEnd/IDE hook） | CodeWiki 已有更强回流 |
| 校验 | — | lint_wiki 只扫 repowiki，不覆盖 .codebuddy | SKILL.md lint **需新增** |

### 可复用的 CodeWiki 骨架（依据本次代码核对）

1. **Mode C 协议**：`distill_conversation.py`、`note_consolidation.py`、`doctrine.py` 三先例，工具负责选材/校验/落盘/溯源，LLM 正文由调用方产出
2. **确认闸门 + 生命周期**：draft→confirm/reject（note_lifecycle.py），草稿技能可复用
3. **聚合/蒸馏纪律**：系统提示里的「自包含/可归因/SOP/判断逻辑/反模式」质量准则 ≈ SKILL.md 正文所需
4. **确定性文件设施**：atomic_write/锁、frontmatter OKF 修补、slugify、冲突预检
5. **分发基建**：hooks.yaml 家族注册 + install_hooks 拷贝管线，可扩展「skills」资产类型
6. **schema 数据驱动**：page_types/note_types 加「skill」类型即可让路由/lint/prompt 感知

### 缺口清单

1. 无 SKILL.md 读写器/技能目录管理器（不写 .codebuddy/skills/）
2. 词汇层无 skill 类型（note_type/page_type 枚举、无技能专用状态机）
3. 无「从经验编译技能」的生成工具/prompt/CLI（consolidate_notes 输出是 scenarios 页，非 SKILL.md）
4. 无 SKILL.md 质量校验/lint、无技能检索/采纳信号
5. 无技能注入/激活执行端（T2/T3 装载是 IDE 原生行为，工具层无代码）
6. 工具侧无 LLM（架构铁律），需配套 spawn 式 worker 剧本（distill-worker.md 可当模板）

## 结论与决策

**结论：能实现。** 且因为知识管线已把「经验→结构化知识」半程走完，CodeWiki 比 wikiskill 更接近「自动生成 SKILL」的前半程（蒸馏已有）；缺口集中在「技能产物类型」与「生成工具」两个新增件，不涉及重构。

**定档（决策，2026-09-05）：**

1. **推荐形态 = 方案 C 半闭环**：单向编译器（B）是 MVP，先验证「notes/scenarios → SKILL.md draft → 人工确认 → 落 .codebuddy/skills/」闭环；生成质量稳定后再接回流迭代（真实任务轨迹经现有采集管线回流，提炼改进 SKILL）
2. **不建自动评分门控、不编 Inference Agent 编排**——那是重做 wikiskill，CodeWiki 无 held-out 基准且确认闸门已承担质量职责
3. **素材源 = confirmed notes + wiki/scenarios**（raw 太噪需先蒸馏；任务记忆是进度型不直接作正文）
4. **生成分工 = Mode C**：宿主 agent/子代理写 SKILL.md 正文，工具做选材/校验/落盘/溯源（守「无状态工具 + LLM 外置」铁律）
5. **落盘先仓库内 .codebuddy/skills/ 闭环**，稳定后再考虑 hooks.yaml 家族分发；宿主级安装是用户动作，工具不代劳
6. 落地顺序：skill 词汇/状态机 → skill-creator 工具（Mode C）→ SKILL.md lint → 仓库内闭环验证 → 回流迭代

**本次只做定档，代码未动。** 是否进入设计/实现，待用户另行拍板。

## 相关参考

- 论文：WikiSkill: Compiling Agent Experience into Persistent Knowledge for Skill Evolution（arXiv:2608.27454）
- 仓库：github.com/ashutoshsinghpr7/wikiskill（Hermes CLI，`wikiskill evolve` 闭环）
- 解读：XStack18《WikiSkill——把 Agent 经验编译成永久知识》
- 本仓相关笔记：2026-09-05-ponytail-生效机制（T1/T2/T3 加载档位）、2026-09-04-caveman-技能生效机制（SKILL.md 三条加载链路）
