---
type: lesson
title: skill 与 MCP 工具 1:1 映射的三个陷阱：常驻非零、绕过 schema 校验、放弃工作流粒度
tags:
- lesson
metadata:
  date: 2026-09-11
  task_id: Cli能力
  related_modules:
  - skills
  - mcp
  - cli
  severity: medium
  source_ref: conversations/conv-manually_attached_skills-Please-use-the-use_skill-tool-to-in-83a270.md
  scene: MCP 暴露面收缩方案设计
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.9.0
  at: 2026-09-11 01:14:03+00:00
stale_after: '2027-03-10'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-11T03:55:13Z'
---

## 背景

讨论「用 skill/command 渐进式披露替换 MCP 常驻 schema」时，评估过「49 个能力做成 49 个 skill/command 一比一映射」这个直觉方案。结论是**给 agent 不建议 1:1，给人可以 1:1**（本条为方案讨论中形成的判断，已随方案归档在 `docs/plans/cli-capability-progressive-disclosure.md`，Status: deferred，尚未实施验证）。

## 三个陷阱

1. **常驻不是 0，只是换了计量单位**：官方口径 skill metadata 始终在上下文、约 100 词/个；49 个 ≈ 4,900 词，中文 token 化更差，粗估 7–15k token——与「MCP 收缩到 core 12 个」（6–8k）基本打平甚至更贵。收益来自「描述比 schema 短」，而 1 个薄 skill ≈ 130 token，比 49 个又省两个数量级。
2. **skill 只注入指令、不执行**：1:1 skill + CLI 等于用「模型读散文后自己拼命令行字符串」替换「结构化 schema + IDE 侧校验」——没有必填校验、没有枚举约束，拼错就是 bash 报错。正好撞 Doctrine 的「不绕过 dispatch/schema 校验直连 handler」。
3. **触发是乘法风险**：49 个语义相近的 description（`query_wiki` / `query_cross_service` / `read_code_components`…）互相竞争，每次调用都要过一次 49 选 1，误触发率不是加法是乘法。同时 1:1 把 skill 降级成 MCP 镜像，放弃了 skill 唯一的增量价值——**工作流粒度**（「先 capture → 再 distill → 再 confirm」这类多步流水线是单个工具 description 写不下的）。

## 收敛结论

- **给 agent**：按工作流聚合，**8–12 个 skill**；参数细节丢进 `references/`（第三级按需加载）。常驻 ≈ 1.2k 词。
- **给人**：可以 **1:1 command**，且全部带 `disable-model-invocation: true` → 常驻 0（只 `/name` 手动触发），适合低频、危险、agent 容易搞砸的操作（`compact_task_memories`、`refresh_doctrine`、`retract_source` 这类）。
- **维护**：1:1 意味着每加一个 MCP 工具要同步改 skill/command（49 → 98 处），撞 Doctrine「单点收敛」。除非 skill/command 也从 `registry.py` 自动生成——同一生成器产出 MCP schema / CLI 子命令 / skill-command 三份投影。

## 附：IDE 侧已有的暴露面开关（不用改代码）

| 开关 | 位置 | 粒度 |
|---|---|---|
| MCP server 禁用 | `~/.codebuddy/mcp.json` 每 server `disabled` | 整 server |
| MCP 单工具禁用 | `~/.codebuddy/mcp-disabled-tools.json` 的 `disabledTools` | 单工具 |
| Skill/Command 禁用 | skill frontmatter `disable`；command frontmatter `disable-model-invocation` | 单个 |

## 关联

与 architecture『CodeBuddy Skills 三级渐进披露 + disable-model-invocation / user-invocable 语义相反』配套读：那条讲加载机制与开关语义，本条讲映射粒度怎么选。
