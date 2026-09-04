---
type: Conversation
title: "conversation 20260904T015651Z"
status: distilled
stale_after: 2026-12-03
generated: { by: codewiki/5.5.1, at: 2026-09-04T01:56:51Z }
captured_at: "2026-09-04T01:56:51Z"
content_hash: "sha256:1d6617cb9fd7b4000a6125ae6cb0cfea7471e8070147dce19dbee6decff0c599"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=2"
keep_raw: false
link_to: ""
source_session: "7fbadd84fa88401388e56ffd84e788e0"
task_id: "他山之石"
turn_count: 12
---

# Conversation Transcript

user: https://github.com/JuliusBrussee/caveman.git 研究下这个技能是如何生效的
user: <question>请选择要关联的任务（本次会话将记录到该任务的上下文中）</question>
<answers>
他山之石(研究外部仓库/技能如何生效，符合本次请求)
</answers>
</question_item>
</questions>
</question_answer>
assistant: 用户选择了「他山之石」任务。我先建立会话绑定并拉取任务上下文。
assistant: 建立绑定并拉取「他山之石」任务上下文。
assistant: 绑定完成，任务上下文已拉取（`pending_raw_count=0`，无积压需补蒸馏）。现在开始研究 caveman 仓库。
assistant: caveman 是一个「省 token」的 Agent 技能 + 代理项目（输出压缩走 Skill、输入压缩走本地 Proxy）。用户关心「技能如何生效」，需要深入源码看加载链路。我先把仓库 clone 到工作区临时目录进行研究。
assistant: 克隆成功。现在系统探索技能目录结构。
assistant: 技能组织得很规整。让我读关键文件了解加载链路。
assistant: 核心架构已清晰。继续深挖「加载生效」的关键钩子与插件打包结构。
assistant: `pack.json` 揭示了 Native Pack 格式。现在读激活逻辑与 hook 说明。
assistant: 激活链路基本清晰。补充确认 mode-tracker 的每轮注入格式、commands 布局和 registry 的投递面。
assistant: 研究完成。已克隆源码并沿 `skills/` → `.claude-plugin/` → `src/hooks/` → `proxy` 全链路核实。下面是 caveman「技能如何生效」的完整解析。

## 一句话结论

caveman 本质是**多宿主分发的提示词注入系统**：规则本体只写一份 `SKILL.md`，然后通过三条不同的加载链路把文本塞进各 Agent 的上下文——**Claude Code Plugin hooks（主链路）**、**CLI/Proxy 的 Native Pack（wrapper 链路）**、**通用 skills 目录（手动/跨 Agent 链路）**。真正「生效」的动作是 **hook 在运行时把 SKILL.md 规则作为隐形系统上下文反复注入**。

## 链路 1：Claude Code Plugin（官方安装方式）

`claude plugin marketplace add JuliusBrussee/caveman` + `plugin install` 后，`.claude-plugin/` 两个文件决定加载：

- `marketplace.json` 声明插件存在，`plugin.json` 不声明任何 skill，**只声明两个 hook**：

```8:33:d:\repos\CodeWiki-CN\.caveman-tmp\.claude-plugin\plugin.json
"hooks": {
  "SessionStart": [ { "hooks": [ { "type": "command",
    "command": "node \"${CLAUDE_PLUGIN_ROOT}/src/hooks/caveman-activate.js\"", ... } ] } ],
  "UserPromptSubmit": [ { "hooks": [ { "type": "command",
    "command": "node \"${CLAUDE_PLUGIN_ROOT}/src/hooks/caveman-mode-tracker.js\"", ... } ] } ]
}
```

生效的核心机制是 **SessionStart hook 的 stdout 会被当作「隐藏系统上下文」注入会话**（README 明说 "SessionStart stdout is injected as hidden system context — Claude sees it, users don't"）。`caveman-activate.js` 做的事：

1. 从 hook 标准输入 JSON 读 `source`/`cwd`/`session_id`，判定事件是 `startup/clear`（重算默认档）还是 `resume/compact/fork`（读本会话已存档，防止自动压缩把用户中途选的档位悄悄重置——issue #691）；
2. `off` 档直接输出 `OK`，不注入任何规则；
3. 否则**运行时读取单一事实源 `skills/caveman/SKILL.md`** → 剥掉 YAML frontmatter → **按当前档位过滤** intensity 表格和示例行（只留 `lite/full/ultra/...` 对应那几行，省 token）→ 拼成输出：

```344:404:d:\repos\CodeWiki-CN\.caveman-tmp\src\hooks\caveman-activate.js
// Read SKILL.md — the single source of truth for caveman behavior.
// Candidate locations: $CLAUDE_PLUGIN_ROOT/skills/caveman/SKILL.md …
// 2. ../../skills/caveman/SKILL.md  … 3. ../skills/caveman/SKILL.md …
// Strip YAML frontmatter → filter intensity table rows + example lines
//   to the active level …
output = 'CAVEMAN MODE ACTIVE — level: ' + modeLabel + '\n\n' + filtered.join('\n');
```

4. 把档位持久化到 `~/.claude/.caveman-sessions/<session_id>.mode`（**per-session**，`.caveman-active` 只是兼容 mirror），并顺手清理过期 session、检测 statusline 未配置时输出一次 nudge。

第 2 个 hook `caveman-mode-tracker.js`（UserPromptSubmit）每轮用户提问前跑一次：识别 `/caveman lite|full|...` 和自然语言触发词，然后输出 `hookSpecificOutput.additionalContext` 做**每轮强化提醒**：

```332:342:d:\repos\CodeWiki-CN\.caveman-tmp\src\hooks\caveman-mode-tracker.js
const context = [notice, reinforce].filter(Boolean).join('\n\n');
if (context) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: { hookEventName: "UserPromptSubmit", additionalContext: context }
  }));
}
```

**这套设计解决的关键痛点**：上下文压缩（compaction）会把规则剪出上下文、模型随之漂回啰嗦风格——所以 SessionStart 对 `compact` 事件也触发、规则全量重注入；UserPromptSubmit 再每轮补一句轻量提醒，双保险。

## 链路 2：Native Pack（CLI / `caveman claude` wrapper）

这是另一套「行为约束 skill」注入系统，与上面「说话风格」技能不同：一个 `native-core.md`（强制核心规则，预算 560 tokens，实测 556）+ 6 个按任务分类激活的 skill（`investigate-first`/`lean-build`/`migration`/`safe-refactor`/`surgical-patch`/`verify-and-stop`）。

`skills/compile.mjs` 是编译闸门：校验 frontmatter 名称必须匹配目录、禁止 `TODO/FIXME/not implemented` 等标记（还特意用 `"TO"+"DO"` 字符串拼接规避源码内自检）、校验 instruction 字节预算、强制冲突技能成对声明且 precedence 不同。产物落到：CLI 的 `.generated.ts`、proxy 的 `native-pack.generated.json`、`skills/generated/<target>/pack.json`。

关键设计是 **同一个 pack 按宿主映射到不同的注入事件**：

```22:29:d:\repos\CodeWiki-CN\.caveman-tmp\skills\compile.mjs
const NATIVE_ACTIVATION = {
  claude:   { core: "SessionStart", task: "UserPromptSubmit" },
  codex:    { core: "developer_instructions+SessionStart", task: "UserPromptSubmit" },
  hermes:   { core: "pre_llm_call", task: "pre_llm_call" },
  gemini:   { core: "BeforeAgent", task: "BeforeAgent" },
  opencode: { core: "experimental.chat.system.transform", task: "chat.message" },
  aider:    { core: "read_only_conventions", task: "native_repository_map_authoritative" },
};
```

这些 skill 不走「每轮全量注入」，而是带 `task_types`/`entry_condition`/`stop_condition`/`precedence` 的**分类激活**（classify 后按任务类型挑选注入），由本地代理（Go，`proxy/internal/nativepack`）在合适时机注入——只注入当前任务需要的规则，省 token。

## 链路 3：通用 skills 分发（`npx skills add` 等）

`skills/<id>/` 每个就是一个标准 skill：`SKILL.md`（YAML frontmatter 的 `description` 写触发场景 + markdown 正文规则）+ 可选 `scripts/`。这是各 skills 兼容 Agent 都能直接认的格式。Claude Code 下 `/caveman`、`/caveman-commit` 还有 `commands/*.toml`（`description` + `prompt` 模板）供命令面板调用。

## 与本仓库可对照的「加载链路」抽象

| 层 | caveman 实现 | 对应的通用机制 |
|---|---|---|
| 规范源 | `skills/<id>/SKILL.md` 只写一份 | 任何 Agent 的 `SKILL.md` |
| 声明 | `registry.json`（delivery/suites/task_types/预算） | 注册表描述投递面 |
| 编译闸门 | `compile.mjs`（校验 + 生成各宿主产物） | build-time validation |
| 宿主映射 | `NATIVE_ACTIVATION`（同 pack → 各 Agent 事件） | 多宿主激活点适配表 |
| 注入机制 | SessionStart stdout = 隐藏上下文 / `additionalContext` / `developer_instructions` / `chat.system.transform`… | 各家「事件 hook」注入 |
| 常驻方式 | core 常驻 + 分类 skill 按任务激活 | core vs on-demand |

## 可复用模式（值得借鉴的点）

1. **单事实源 + 运行时读取注入**：hook 每次启动都重新读 SKILL.md，而不是硬编码拷贝——规则改动即时生效、无两处漂移。
2. **hook 的工程化防御**（最值得抄）：`requireSibling()` 校验兄弟模块的导出形状、缺文件降级而非崩溃；stdin 读取加 2s watchdog、用 `unref()` 防句柄阻塞退出；payload 按首个完整 JSON 对象触发而非等 EOF（Windows 管道 close 延迟坑）；hook 永不非零退出。
3. **per-session 状态而非全局标志**：模式状态按 `session_id` 隔离，多窗口互不干扰。
4. **重新注入兜底**：SessionStart 在 `compact/resume` 也触发，解决"上下文被压缩后规则丢失、行为漂移"。
5. **编译期硬闸门**：registry 与目录一致性、frontmatter name 匹配目录名、prompt 字节预算超限即构建失败。
6. **token 裁剪**：同一 SKILL.md 按激活档位只注入对应示例行，规则本身按字节预算设限。

---

研究用的 clone 在 `d:\repos\CodeWiki-CN\.caveman-tmp\`。要我把它整理成一篇 `repowiki` 对比笔记（如 `comparison`/`query` 类型），还是先清理掉临时目录？另外如果后续要在 CodeWiki 里做「多宿主技能注入」或「hook 防御性加载」，可以基于以上结论进一步设计。
