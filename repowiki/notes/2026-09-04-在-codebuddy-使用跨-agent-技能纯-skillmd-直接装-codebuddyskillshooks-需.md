---
type: decision
title: 在 CodeBuddy 使用跨 Agent 技能：纯 SKILL.md 直接装 ~/.codebuddy/skills/，hooks 需 CLI/插件市场、Native
  Pack 无 codebuddy target
tags:
- codebuddy
- decision
- juliusbrussee
metadata:
  date: 2026-09-04
  task_id: 他山之石
  severity: medium
  source_ref: conversations/conv-https-github.com-JuliusBrussee-caveman.git-研究下这个技能是如何生效的-a51ed2.md
  scene: 他山之石-caveman研究
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.5.1
  at: 2026-09-04 06:00:37+00:00
stale_after: '2027-09-05'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:31Z'
---

## Background

调研外部仓库 JuliusBrussee/caveman（省 token 技能）的生效机制后，用户追问「在 CodeBuddy 中如何使用」。环境探测与官方文档核实（2026-09-04）：本机无 `codebuddy` CLI，但 `~/.codebuddy/skills/` 存在且正是当前会话技能（ponytail、archify 等）的存放地，`~/.codebuddy/plugins/` 是 IDE 插件市场缓存；CodeBuddy 文档确认插件层有意兼容 Claude Code。

## CodeBuddy 兼容性边界（实测/文档核实）

| caveman 机制 | CodeBuddy 支持 | 说明 |
|---|---|---|
| 纯 `SKILL.md` 技能（`skills/caveman/`） | ✅ 完全支持 | 放 `.codebuddy/skills/`，AI 按 frontmatter `description` 自动触发或 `/caveman` 手动触发 |
| Claude Code Plugin hooks（`SessionStart` 每会话注入） | ⚠️ 需 CLI/插件市场 | 文档称兼容 `.claude-plugin/`、`marketplace.json`、`${CLAUDE_PLUGIN_ROOT}`、`SessionStart`/`UserPromptSubmit` hooks，但需 CLI 或 GUI 安装；且 caveman hook 脚本状态目录写死 `~/.claude`，有兼容风险 |
| `caveman claude` 本地代理（输入压缩） | ❌ 不适用 | Native Pack 宿主目标表 `NATIVE_ACTIVATION` 无 codebuddy（只覆盖 claude/codex/hermes/gemini/opencode/aider 等 30+ Agent） |
| `/caveman-*` TOML slash 命令 | ❌ 不一定 | CodeBuddy 的 `commands/` 只认旧版 Markdown 命令，不认新版 `.toml` |

## Decision/正确做法

把 caveman 当**普通 Skill** 安装即可，无需 hook 状态机：复制源码 `skills/<id>/SKILL.md` 到 `$HOME/.codebuddy/skills/<id>/SKILL.md`（caveman 及配套 caveman-commit/review/help），**新开会话生效**。触发方式：自动（说 "talk like caveman" 命中 description 触发词）或手动 `/caveman`、`/caveman ultra`；退出用 SKILL.md Boundaries 声明的退出词（"stop caveman"/"normal mode"）。

## Rationale

- caveman 核心价值全在 `SKILL.md` 一份文件（风格规则 + 档位 + 退出语义），其 Persistence/Boundaries 段落自声明"本会话持续生效直到说 stop"，无 hook 也能靠模型遵循规则执行。
- 与 Claude Code 插件版唯一差别：档位切换（lite/full/ultra）无 hook 持久化状态，长会话自动压缩后可能漂回啰嗦风格——此时再说一次 `/caveman ultra` 即可恢复。

## 注意事项

结论基于官方文档 + 本机环境探测（无 CLI），具体版本行为可能变化；多宿主分发的通用做法是：规则单事实源写 SKILL.md，各宿主按自身支持能力（hooks/commands 格式）裁剪分发，不能假设宿主间能力一致。
