---
title: "skill-creator 设计方案：从 scenario/notes 编译 SKILL.md 的两区制 Mode C 工具"
type: Query
description: "CodeWiki 自动生成 SKILL 能力的落地设计：产物粒度（scenario 直译 + 精选 notes 补充）、选材触发（prepare 列候选 + 显式指定）、两区制确认闸门（草稿区 repowiki/skills 不生效 → install 到 .codebuddy/skills 生效）、重写加变更记录段。含工具 API、frontmatter schema、与 consolidate_notes 的分工、实施步骤与未决问题。"
generated: { by: codewiki/5.6.0, at: 2026-09-05T15:39:24Z }
stale_after: 2026-12-04
aliases: [skill-creator设计方案]
status: stable
tags: [skill, 设计, mode-c, 确认闸门, 他山之石]
metadata:
  related_modules: ["codewiki/mcp/tools"]
  source_refs: ["wiki/comparisons/自动生成SKILL可行性-wikiskill闭环-vs-CodeWiki编译复用.md"]
  code_fingerprint: sha256:829467a7f49459ddf16d1711753a335b7338eb7409360e8d30565d9f78d11621
---
# skill-creator 设计方案：从 scenario/notes 编译 SKILL.md 的两区制 Mode C 工具

## 问题描述

承 [自动生成SKILL可行性-wikiskill闭环-vs-CodeWiki编译复用](../comparisons/自动生成SKILL可行性-wikiskill闭环-vs-CodeWiki编译复用.md) 的定档（方案 C 半闭环，MVP = 单向编译器），本页回答「具体长什么样」：

1. 工具如何选材、如何触发、如何落盘；
2. **如何在 SKILL.md 会被 IDE 即时发现的现实下，仍然守住「落盘必经确认闸门」**；
3. 技能的更新、退役与可检索性如何保证；
4. 与既有 `consolidate_notes`（L2 场景块）如何分工而不重叠。

## 调研过程

已核对的现有实现（依据本次代码核对）：

- **`codewiki/mcp/tools/note_consolidation.py`** — 平行工具模板：Mode C `prepare`/`submit`、容量分档预警（red/orange/yellow）、溯源互链（scene `source_notes` ⇄ note `consolidated_into`）、软删除标记 `[DELETED]`、submit 后重建索引、cascade hint 提醒而非自动执行（:344-398 prepare，:400-600 submit，:43-97 聚合系统提示）
- **`codewiki/mcp/tools/note_types.py`** — note_type 权威表，schema `conventions.note_types` 按 key 覆盖（:36-77 默认表，:93-128 合并逻辑）
- **`repowiki/wiki/scenarios/对话蒸馏管线与raw暂存区.md`** — L2 场景块章节骨架：工作场景/适用条件/核心 SOP/判断逻辑/禁忌与反模式/关键事实依据（:23-53）
- **`.codebuddy/skills/grilling/SKILL.md`** — CodeBuddy 技能最小 frontmatter = `name` + `description`（:1-4）
- 缺口：`lint_wiki` 只扫 repowiki 内 md，`.codebuddy` 不进索引不进 lint；无技能目录写入器

关键洞察：scenario 的章节骨架（SOP / 判断逻辑 / 禁忌）**已经是 SKILL.md 正文所需结构**，`description` 天然对应「适用条件」——不复用就是重造一次聚合。

## 方案权衡

### 权衡一：产物粒度与素材来源

| 选项 | 代价 |
|---|---|
| (a) scenario 直译 | 依赖 L2 已聚合，覆盖面取决于 consolidation 频率 |
| (b) 跨主题重新聚合 notes | 重做 consolidate 已做的聚类，逻辑漂移 |
| (c) 按 note_type 精选 | 覆盖面窄 |

**选定 (a) 为主 + (c) 为补充**：scenario 是主素材；未被任何 scenario 吸收的高价值 `pitfall`/`lesson`/`decision` 单条笔记允许作为独立素材（复用 `_pending_confirmed_notes` 同类扫描，按 `metadata.compiled_into` 排除已编译的）。

### 权衡二：选材与触发

- (a) prepare 列候选 → agent 挑：与 consolidate_notes 完全同构，人始终在环
- (b) 用户显式指定 `topic`/`sources`：可控性强
- (c) 全自动按阈值挑选：**违反 Doctrine「触发永远显式」**，排除

**选定 (a) + (b) 并存，无默认自动触发。**

### 权衡三：落盘与确认闸门（核心）

- (a) **两区制**：草稿落 `repowiki/skills/`（不生效、进索引、进 lint），确认后 install 到 `.codebuddy/skills/`（生效）
- (b) 单区 + `status: draft` 标记：草稿期技能**已被 IDE 发现并可触发**，闸门形同虚设——否决
- (c) 即刻生效靠事后回滚：坏技能已污染行为——否决

**选定 (a)。** 代价是多一个 install 动作，但这份代价正是「宿主级安装是用户动作，工具不代劳」的落地。

### 权衡四：更新与退役

- (a) 整份重写：丢 diff 历史
- (b) unified diff patch：保留演化证据但实现重（wikiskill 的 edit_skill）
- (c) 重写 + frontmatter `metadata.revisions` 变更记录段

**选定 (c)**：保住 wikiskill「改动可审计」的价值（`skill-impact.md` 的意义所在），不引入 diff 引擎。退役沿用 `reject_note` 同款语义。

### 与 consolidate_notes 的分工

| | consolidate_notes | skill_creator |
|---|---|---|
| 产物 | `wiki/scenarios/*.md`（知识层，检索消费） | `SKILL.md`（行为层，agent 指令消费） |
| 消费方 | agent 主动 `query_wiki` | IDE 按 description 自动触发 |
| 关系 | 上游 | 下游单向（source_refs 回链 scenario） |

**不合并**：一个是检索知识，一个是行为指令，语义与消费链路都不同。

## 决策结论

### 工具形态

**新工具 `skill_creator`**（`codewiki/mcp/tools/skill_creator.py` + `registry.py` 注册），四种 mode：

| mode | 入参 | 行为 |
|---|---|---|
| `prepare` | `topic?`, `sources?`, `limit?` | 返回候选素材（未编译 scenario + 精选 notes）、草稿区与生效区技能索引、冲突预检、容量预警、正文写作系统提示 |
| `submit` | `report.skills[]` | frontmatter 校验、路径安全、落草稿区、溯源互链（skill `source_refs` ⇄ 素材 `compiled_into`）、`revisions` 追加、索引重建、计数器归零 |
| `install` | `name` | 草稿 → `.codebuddy/skills/<name>/SKILL.md`，写 `installed_at`/`installed_to`，**仅在用户确认后调用** |
| `retire` | `name`, `reason` | 标记 deprecated + 从生效区 uninstall，正文保留（不删，留审计） |

`submit` 的报告条目：`{name, action(created|updated|retired), source_refs[], summary?, revision_note?}`。

### 目录与 frontmatter

```
repowiki/skills/<name>/SKILL.md      # 草稿区：不生效、进索引、进 lint
.codebuddy/skills/<name>/SKILL.md    # 生效区：IDE 自动发现
```

草稿区 frontmatter（OKF v0.2 风格）：

```yaml
---
name: <slug>
description: <触发条件一句话——IDE 据此决定是否调用>
type: Skill
status: draft            # draft | stable | deprecated
generated: {by: codewiki/<ver>, at: <ts>}
stale_after: <date>
metadata:
  summary: <40 字内>
  source_refs: [wiki/scenarios/xxx.md, notes/yyy.md]
  revisions: [{at, reason, source}]
  installed_at: <ts>     # install 后写入
  installed_to: .codebuddy/skills/<name>/
---
```

### 选材与防碎片纪律（沿用 consolidate 的成功约束）

1. 默认 UPDATE，不 CREATE；拿不准就 UPDATE
2. 每批最多新建 **1** 份技能
3. 新建前必须读 ≥2 份最相似现有技能，确认无处可归
4. 冲突预检：name/description 相似度（复用 Jaccard 思路，不用向量）
5. 容量硬顶（建议 12，类比 `max_scenarios`=15）：红=先合并，橙=只 UPDATE

### 实施步骤（代码层，尚未动工）

1. `schema.yaml` 增 `page_types.skill`（directory: `skills`，required_sections: 工作场景/适用条件/核心 SOP/判断逻辑/禁忌与反模式）——让 lint/路由感知草稿技能
2. `note_types.py` 同款权威表思路：新增 skill 资产声明（freshness/容量/合并策略）
3. `codewiki/src/config.py` 增 `SKILLS_DIR`（草稿区）与生效区常量
4. 实现 `skill_creator.py`（4 mode），复用 `store.locked_rmw` + frontmatter round-trip 辅助 + `aggregation_state`
5. 正文写作系统提示（自包含 / 可归因 / SOP 化 / 禁绝对路径与密钥）
6. SKILL.md lint：description 非空含触发条件、name 合规、正文长度上限、无敏感串
7. `tests/` 补用例；`registry.py` 注册后跑全量测试

### 未决问题（下一轮 grill 收敛）

1. **Q10 回流验证**：半闭环的「技能有效」如何判定——人工试用反馈落到哪（note？`flag_issue`？技能 frontmatter 增 `effectiveness` 字段？）
2. **Q11 lint 与容量**：SKILL.md 必检规则清单、容量上限取值、草稿区是否纳入 `lint_wiki` 扫描

**本页为设计定档，代码未动。**
