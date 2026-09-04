---
type: Conversation
title: "conversation 20260904T042422Z"
status: distilled
stale_after: 2026-12-03
generated: { by: codewiki/5.5.1, at: 2026-09-04T04:24:22Z }
captured_at: "2026-09-04T04:24:22Z"
content_hash: "sha256:2bda4f4ae69e8fb736b1ac100e59aa8476cc24a91a4029a3d3e6f20648af4315"
friction_score: 5
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=6"
keep_raw: false
link_to: ""
source_session: "7fbadd84fa88401388e56ffd84e788e0"
task_id: "他山之石"
turn_count: 27
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
user: 在CODEBUDDY中如何使用
assistant: 重绑成功。现在把「他山之石」1 条积压补蒸馏委托给后台 subagent，同时继续查 CodeBuddy 的技能机制。
assistant: 后台蒸馏 worker 已启动。查到了关键线索——CodeBuddy 明确兼容 Claude Code 技能规范。抓官方文档确认细节。
assistant: CodeBuddy 官方文档确认了关键事实：**插件层是有意兼容 Claude Code 的**（`.claude-plugin/`、`marketplace.json`、`${CLAUDE_PLUGIN_ROOT}`、`SessionStart`/`UserPromptSubmit` hooks 全支持），且技能目录是 `.codebuddy/skills/`。先探测一下你本机的环境，再给具体步骤。
assistant: 环境探测结果很关键：**你本机没有 `codebuddy` CLI**（输出为空），但 `~/.codebuddy/skills/` 存在且正是当前会话那些技能（ponytail、archify）的存放地，`~/.codebuddy/plugins/` 也存在（IDE 插件市场缓存）。这说明在 CodeBuddy IDE 里，**技能直接读 `~/.codebuddy/skills/`**。

## 在 CodeBuddy 中如何使用 caveman

### 能生效的部分与不能生效的部分

| caveman 机制 | CodeBuddy 支持 | 说明 |
|---|---|---|
| 纯 `SKILL.md` 技能（`skills/caveman/`） | ✅ 完全支持 | 放 `.codebuddy/skills/`，AI 按 frontmatter `description` 自动触发或 `/caveman` 手动触发 |
| Claude Code Plugin hooks（`SessionStart` → 每会话注入规则） | ⚠️ IDE 层兼容但本机无 CLI 装不了 | 文档确认 CodeBuddy 兼容 `.claude-plugin/`、`SessionStart`/`UserPromptSubmit`、`${CLAUDE_PLUGIN_ROOT}`，但需要 CLI 或插件市场 GUI；且 caveman hook 脚本写死 `~/.claude` 状态目录，有兼容风险 |
| `caveman claude` 本地代理（输入压缩） | ❌ 不适用 | Native Pack 目标表里没有 codebuddy，wrapper 只包 30+ 指定 Agent |
| `/caveman-*` slash 命令（TOML） | ❌ 不一定 | CodeBuddy 的 `commands/` 只认旧版 Markdown 命令，不认新版 `.toml` |

### 推荐做法：把它当普通 Skill 装

caveman 的核心价值其实全在 `SKILL.md` 一份文件里（风格规则 + 档位 + 退出语义），不需要 hook 状态机也能工作——它的 Persistence/Boundaries 段落自己声明了"本会话持续生效直到你说 stop"。

安装步骤：

```powershell
# 1. 建用户级技能目录（已存在可跳过）
New-Item -ItemType Directory -Force "$HOME\.codebuddy\skills\caveman" | Out-Null

# 2. 复制 caveman 技能本体（源码里那份就是唯一事实源）
Copy-Item "d:\repos\CodeWiki-CN\.caveman-tmp\skills\caveman\SKILL.md" `
  "$HOME\.codebuddy\skills\caveman\SKILL.md"

# 3. 若要配套风格技能（写 commit / review / help），可一并复制：
$names = 'caveman-commit','caveman-review','caveman-help'
foreach ($n in $names) {
  Copy-Item "d:\repos\CodeWiki-CN\.caveman-tmp\skills\$n\SKILL.md" `
    "$HOME\.codebuddy\skills\$n\SKILL.md" -ErrorAction SilentlyContinue
}
```

装完后**新开会话**生效，两个触发方式：
- **自动**：说 "用 caveman 风格回复" / "talk like caveman"（命中 SKILL.md `description` 里的触发词）；
- **手动**：输入 `/caveman`，档位 `/caveman ultra`、`/caveman wenyan-full` 等；
- **退出**：说 "stop caveman" 或 "normal mode"（SKILL.md Boundaries 里写明的退出词，无 hook 也能靠规则执行）。

与 Claude Code 插件版唯一差别：档位切换（lite/full/ultra）没有 hook 帮你持久化状态，靠模型遵循规则实现，长会话压缩后偶尔会漂回啰嗦风格——此时再说一次 `/caveman ultra` 即可。

要不要我直接帮你装？以及装哪一组：
user: <cb_summary>
This session is being continued from a previous conversation that was compacted to stay within the model context window.
Messages after this summary (if any) are the original recent turns. Tool results from before this summary were omitted.
If you need exact code, command output, or file contents from before compaction, re-read those files. Do not treat omitted tool bodies as still in context.

Earlier user requests:
- https://github.com/JuliusBrussee/caveman.git 研究下这个技能是如何生效的
- <question_answer> <questions> <question_item id="q-0"> <question>请选择要关联的任务（本次会话将记录到该任务的上下文中）</question> <answers> 他山之石(研究外部仓库/技能如何生效，符合本次请求) </answers> </question_item> </questions> </question_answer>

Earlier assistant notes (truncated):
- 用户选择了「他山之石」任务。我先建立会话绑定并拉取任务上下文。
- 建立绑定并拉取「他山之石」任务上下文。
- 绑定完成，任务上下文已拉取（`pending_raw_count=0`，无积压需补蒸馏）。现在开始研究 caveman 仓库。
- caveman 是一个「省 token」的 Agent 技能 + 代理项目（输出压缩走 Skill、输入压缩走本地 Proxy）。用户关心「技能如何生效」，需要深入源码看加载链路。我先把仓库 clone 到工作区临时目录进行研究。
- 克隆成功。现在系统探索技能目录结构。
- 技能组织得很规整。让我读关键文件了解加载链路。
- 核心架构已清晰。继续深挖「加载生效」的关键钩子与插件打包结构。

Tools used before this summary: list_dir × 8, read_file × 6, mcp_call_tool × 2, ask_followup_question × 1, mcp_get_tool_description × 1, web_fetch × 1, web_search × 1, execute_command × 1, search_file × 1
</cb_summary>

<teammate-message>
<from>distill-worker-tashan</from>
<summary>Message from distill-worker-tashan</summary>
<content>
「他山之石」任务补蒸馏结果汇报：

【结论】该任务名下唯一的待蒸馏 raw（conv-https-github.com-JuliusBrussee-caveman.git-研究下这个技能是如何生效的，caveman 技能生效机制研究）**已被并发蒸馏完成**——在我 prepare（拉到 1 条 pending）之后、submit 之前，另一 worker/并行进程已处理并归档。我两次 submit 分别返回 noop / 不匹配，未造成重复落盘。

【已存在的蒸馏产出（status=draft，待确认）】：
1. notes/2026-09-04-caveman-技能生效机制skillmd-单事实源经三条加载链路注入各-agent-上下文.md（architecture）— 多宿主分发注入系统总览 + Native Pack 宿主映射/编译闸门 + 三层链路细节
2. notes/2026-09-04-agent-hook-注入的工程化防御与防漂移可复用模式caveman-提炼.md（architecture）— hook 防御性加载清单 + compact/resume 重注入防漂移 + per-session 状态 + token 裁剪

raw 已归档至 conversations/conv-https-github.com-JuliusBrussee-caveman.git-研究下这个技能是如何生效的.md。我原计划提取的 4 条候选笔记与此 2 条高度重叠（内容已被覆盖且更完整），故未重复提交。本 worker 未新建任何 note、未写任何 memory。复查 prepare 确认「他山之石」现已无 pending 积压。

【附带提醒】我一次不带 task_id 的 submit 意外触发了对 raw/ 下 **14 条「未关联任务」pending raw** 的批处理（全部 missing_result，notes_created=0，无落盘副作用）。这 14 条无主积压仍在 raw/（各带 .lck 空锁），如需处理请由主 Agent 统一安排（超出本任务授权范围，我未触碰）。

【待确认草稿建议】向用户展示上述 2 条 draft 笔记，经 confirm_note 确认后转正式知识。
</content>
</teammate-message>
assistant: 后台蒸馏 worker 已完成汇报：无积压、产出 2 条 draft 笔记（与本会话研究一致），另有 14 条无主积压待统一处理。先读这两条草稿以便向你展示确认，同时让 worker 收工。
assistant: 两条草稿笔记内容与本次研究结论一致，内容完整。同时还有一笔未决事项需要你拍板（之前安装弹框没有收到你的选择）：
user: <teammate-message>
<from>distill-worker-tashan</from>
<summary>Message from distill-worker-tashan</summary>
<content>
{"type":"shutdown_response","request_id":"shutdown-1788495331296","approve":true,"reason":"Auto-acknowledged by team-member runtime","from":"distill-worker-tashan","timestamp":"2026-09-04T04:15:31.483Z"}
</content>
</teammate-message>
assistant: 蒸馏 worker 已确认收工。关闭团队，释放资源。
assistant: 团队已收尾：`tashan-distill` 已删除，蒸馏 worker 全部下线。

当前状态：
- **补蒸馏完成**：「他山之石」无 pending 积压，2 条 architecture 草稿笔记待你确认
- **14 条无主积压**：仍在 `raw/`（各带 `.lck` 空锁），需统一安排归属后再处理，本次未触碰
- 弹框已弹出，等你选择草稿去向（确认落盘/暂留/删除）和 caveman 安装范围

收到你的选择后我继续处理。
user: <title>确认与后续</title>

<question>补蒸馏产出了 2 条草稿笔记（caveman 生效机制 + hook 注入可复用模式），要确认落盘吗？</question>
<answers>
确认落盘(将 2 条 architecture 笔记转正式知识（confirm_note）)
</answers>
</question_item>

<question>另外：是否把 caveman 技能装到 ~/.codebuddy/skills/ ？（上轮选择未收到）</question>
<answers>
全量(复制 skills/ 下全部纯规则技能)
</answers>
</question_item>
</questions>
</question_answer>
assistant: 用户选择：确认落盘 2 条笔记 + 全量安装 caveman skills。先查 confirm_note 参数与 clone 目录位置。
assistant: clone 目录不在工作区内，检查同级目录与系统临时目录。
assistant: 执行环境是 PowerShell，改用 PS 语法查找 clone 目录。
