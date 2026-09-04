---
type: architecture
title: caveman 技能生效机制：SKILL.md 单事实源经三条加载链路注入各 Agent 上下文
tags:
- '691'
- architecture
- juliusbrussee
metadata:
  date: 2026-09-04
  task_id: 他山之石
  severity: medium
  source_ref: conversations/conv-https-github.com-JuliusBrussee-caveman.git-研究下这个技能是如何生效的.md
  scene: 他山之石-caveman研究
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.5.1
  at: 2026-09-04 04:13:37+00:00
stale_after: '2027-09-04'
origin: conversation
reject_reason: 用户审阅后判定不需要此条笔记
verified:
- by: codewiki/5.5.1
  at: '2026-09-04T04:25:35Z'
---

## Background

调研目标仓库 https://github.com/JuliusBrussee/caveman ，回答「技能如何生效」。沿 `skills/` → `.claude-plugin/` → `src/hooks/` → `proxy` 全链路核实源码。caveman 是一个「省 token」的 Agent 技能 + 代理项目：输出压缩走 Skill、输入压缩走本地 Proxy。

## 结论（一句话）

caveman 本质是**多宿主分发的提示词注入系统**：规则本体只写一份 `SKILL.md`，通过三条不同加载链路把文本塞进各 Agent 上下文——**Claude Code Plugin hooks（主链路）**、**CLI/Proxy 的 Native Pack（wrapper 链路）**、**通用 skills 目录（手动/跨 Agent 链路）**。真正「生效」的动作是 hook 在运行时把 SKILL.md 规则作为隐形系统上下文反复注入。

## 链路 1：Claude Code Plugin（官方安装方式）

`claude plugin marketplace add JuliusBrussee/caveman` + `plugin install` 后，`.claude-plugin/` 两个文件决定加载：`marketplace.json` 声明插件存在；`plugin.json` 不声明任何 skill，**只声明两个 hook**：

- SessionStart → `src/hooks/caveman-activate.js`
- UserPromptSubmit → `src/hooks/caveman-mode-tracker.js`

核心机制：**SessionStart hook 的 stdout 会被当作「隐藏系统上下文」注入会话**（README 原话：SessionStart stdout is injected as hidden system context — Claude sees it, users don't）。`caveman-activate.js` 的逻辑：

1. 从 hook 标准输入 JSON 读 `source`/`cwd`/`session_id`，判定事件是 `startup`/`clear`（重算默认档）还是 `resume`/`compact`/`fork`（读本会话已存档档位，防止自动压缩把用户中途选的档位悄悄重置——对应 issue #691）。
2. `off` 档直接输出 `OK`，不注入任何规则。
3. 否则**运行时读取单一事实源 `skills/caveman/SKILL.md`** → 剥掉 YAML frontmatter → 按当前档位过滤 intensity 表格和示例行（只留 `lite`/`full`/`ultra` 等对应行，省 token）→ 输出 `CAVEMAN MODE ACTIVE — level: <档位>`。
4. 档位持久化到 `~/.claude/.caveman-sessions/<session_id>.mode`（per-session；`.caveman-active` 只是兼容 mirror），并清理过期 session。

第 2 个 hook `caveman-mode-tracker.js` 在每轮用户提问前跑一次：识别 `/caveman lite|full|...` 命令与自然语言触发词，通过 `hookSpecificOutput.additionalContext` 输出**每轮强化提醒**。

**这套设计解决的关键痛点**：上下文压缩（compaction）会把规则剪出上下文、模型随之漂回啰嗦风格——所以 SessionStart 对 `compact` 事件也触发、规则全量重注入；UserPromptSubmit 再每轮补一句轻量提醒，双保险。

## 链路 2：Native Pack（CLI / `caveman claude` wrapper）

另一套「行为约束 skill」注入系统：一个 `native-core.md`（强制核心规则，预算 560 tokens）+ 6 个按任务分类激活的 skill（`investigate-first`/`lean-build`/`migration`/`safe-refactor`/`surgical-patch`/`verify-and-stop`）。

`skills/compile.mjs` 是编译闸门：校验 frontmatter 名称必须匹配目录名、禁止 `TODO`/`FIXME`/`not implemented` 等标记（用 `"TO"+"DO"` 字符串拼接规避源码内自检）、校验 instruction 字节预算、强制冲突技能成对声明且 precedence 不同。产物落到：CLI 的 `.generated.ts`、proxy 的 `native-pack.generated.json`、`skills/generated/<target>/pack.json`。

关键设计是**同一个 pack 按宿主映射到不同的注入事件**（NATIVE_ACTIVATION）：claude=SessionStart + UserPromptSubmit；codex=developer_instructions + SessionStart；hermes=pre_llm_call；gemini=BeforeAgent；opencode=experimental.chat.system.transform；aider=read_only_conventions。这些 skill 不走「每轮全量注入」，而是带 `task_types`/`entry_condition`/`stop_condition`/`precedence` 的**分类激活**（classify 后按任务类型挑选注入），由本地 Go 代理（`proxy/internal/nativepack`）在合适时机注入——只注入当前任务需要的规则，省 token。

## 链路 3：通用 skills 分发

`skills/<id>/` 每个是标准 skill：`SKILL.md`（YAML frontmatter 的 `description` 写触发场景 + markdown 正文规则）+ 可选 `scripts/`。Claude Code 下还有 `commands/*.toml`（`description` + `prompt` 模板）供命令面板调用。

## 加载链路抽象对照（本仓库可借鉴）

| 层 | caveman 实现 | 通用机制 |
|---|---|---|
| 规范源 | `skills/<id>/SKILL.md` 只写一份 | 任何 Agent 的 SKILL.md |
| 声明 | `registry.json`（delivery/suites/task_types/预算） | 注册表描述投递面 |
| 编译闸门 | `compile.mjs`（校验 + 生成各宿主产物） | build-time validation |
| 宿主映射 | `NATIVE_ACTIVATION`（同 pack → 各 Agent 事件） | 多宿主激活点适配表 |
| 注入机制 | SessionStart stdout = 隐藏上下文 / additionalContext / developer_instructions / chat.system.transform… | 各家「事件 hook」注入 |
| 常驻方式 | core 常驻 + 分类 skill 按任务激活 | core vs on-demand |

## 适用范围

对未来做「多宿主技能注入」或「hook 防御性加载」设计（如本仓库技能分发体系）有直接参照价值；详细可复用工程模式见关联笔记。
