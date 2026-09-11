---
type: pitfall
title: "AGENTS.md 约 79% 内容由生成器托管，直接编辑文件会被 install-hooks 冲掉，持久改动必须改模板或常量"
tags: ["codewiki", "pitfall"]
metadata:
  date: 2026-09-11
  task_id: Cli能力
  related_modules: ["agents_md", "ide_config", "prompts", "hooks"]
  severity: high
  source_ref: "raw\\conv-manually_attached_skills-Please-use-the-use_skill-tool-to-in.md"
  scene: "AGENTS.md 注入内容精简"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.9.0, at: 2026-09-11T01:13:07Z }
stale_after: 2027-03-10
---

## 背景

想精简 AGENTS.md 的常驻内容时，先量了各块归属（2026-09-10 实测，总计 10,175 字符）：

| 块 | 字符 | 占比 | 归属 |
|---|---|---|---|
| `<!-- CodeWiki LLM Wiki -->` | 3,499 | 34% | `codewiki/mcp/tools/agents_md.py`（文案在 `locales/{zh,en}.yaml` 的 `artifacts.agents_md.main`） |
| `<!-- TEAM-MEMORY-TASK -->` | 3,286 | 32% | `codewiki/cli/utils/ide_config.py:249-259`（`install-hooks` 时 upsert），文案源是 `codewiki/mcp/prompts.py` 的 `_TASK_MEMORY_AGENTS_SECTION` |
| `<!-- CODEWIKI-QWENWORK -->` | 1,222 | 12% | `ide_config.py:261-273`，只在 `wiring == "prompt"` 分支写入（`ide_config.py:315-318`） |
| `## Team memory fusion` | 1,713 | 17% | 手写 |
| `## Agent skills` | 395 | 4% | 手写 |

## 正确做法

`_upsert_marked_section`（`agents_md.py:35-59`）的行为是**只替换标记内的内容，标记外原样保留**。所以：

1. **持久生效必须改模板/常量**：改 `agents_md.py`、`ide_config.py` 的常量、`prompts.py` 的 `_TASK_MEMORY_AGENTS_SECTION`、或 `locales/*.yaml`；改一处，所有接线仓库同时生效（本仓实测：该常量 3,286 → 836 字符后，本仓 AGENTS.md 10,175 → 6,473，-36.4%，全量 pytest 924 passed / 2 skipped）。
2. **只有不受生成器管辖的块才能直接改文件**（QwenWork 块只在 prompt 模式写入，hook 模式的 `install-hooks` 不会回冲它，所以那次 1,222 字符可以直接删；删前要确认它不在你的接线分支里）。
3. **验证链路**：改完连续调用两次 upsert——第一次应返回 `True`（替换旧块），第二次 `False`（幂等），并确认其它标记块未被回冲。

## 根因

AGENTS.md 是生成产物而非源文件，但看起来像普通 Markdown，容易被当源文件编辑；改动当下有效，下次 `install-hooks` / `generate` 就被覆盖。

## 风险提示

AGENTS.md 装的是**行为契约**（标注依据、确认闸门、任务关联、不自动蒸馏）。删多了不会报错，只会静默退化——agent 不再标来源、不走过闸门。精简要按「铁律 vs 说明书」切，不能按字数切；细节外移到 MCP prompt（如已有的 `task-workflow`）或 `references/`，AGENTS.md 只留指针。

## 关联

与『弹框工具的 options 条数建议…』同属「注入文案改动」家族，但那条讲**多副本同步**（改哪几处），本条讲**生成器托管与回冲机制**（改文件为什么没用、怎么验证）。
