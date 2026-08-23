---
type: Conversation
title: "conversation 20260823T063004Z"
status: distilled
stale_after: 2026-11-21
generated: { by: codewiki/5.3.0, at: 2026-08-23T06:30:04Z }
captured_at: "2026-08-23T06:30:04Z"
content_hash: "sha256:a20cfd93d4d75cb16b80f921bf97667eab6e698147633483030d5cb7e1b0874b"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=3"
keep_raw: false
link_to: ""
source_session: "d897d478298e4268a713ca4a49637194"
task_id: "产品维护"
turn_count: 9
---

# Conversation Transcript

user: 现在codewiki-plus开启hook机制，支持那些智能体，目前我只知道支持codebuddy @prompts.py:1312-1318
user: <question>本会话是否关联一个进行中的任务？</question>
<answers>
产品维护(关联到「产品维护」任务（task_id=产品维护），该任务有 1 条未蒸馏对话积压)
</answers>
</question_item>
</questions>
</question_answer>
assistant: 任务已绑定（产品维护），`pending_raw_count` 为 0，无需补蒸馏。现在来回答你的问题——先查一下 hook 机制的实际实现，确认支持哪些智能体。
assistant: 查完了，结论很清晰：**目前正式支持并验证接线的只有 CodeBuddy**，但采集脚本在底层做了一些对 Claude Code 的兼容设计。分两层看：

## 1. 正式支持：仅 CodeBuddy

IDE 接线层完全是 CodeBuddy 特有的，没有其他 agent 的接线：

| 组件 | 位置 | 说明 |
|---|---|---|
| Hook 注册 | `.codebuddy/settings.json` | CodeBuddy 专用的 `hooks.SessionStart/SessionEnd` 注册格式，且命令是写死的绝对路径 `d:/repos/CodeWiki-CN/...` |
| Wrapper 脚本 | `.codebuddy/hooks/task_session_start.py`、`capture_session_end.py` | 拷贝到 CodeBuddy 专用目录 `.codebuddy/hooks/`，stdout 按 CodeBuddy 期望的 `{continue, systemMessage}` 形状输出 |
| MCP prompt | `prompts.py` 的 `team-memory-hook` | 只操作 `.codebuddy/settings.json`，只注册 `SessionStart`/`SessionEnd` 两个 CodeBuddy 事件 |
| 官方文档 | `docs/team-memory-hook.md` | 引用的也是 CodeBuddy 官方 Hooks 文档（`codebuddy.cn/docs/ide/Features/Hooks`） |

`task_session_start.py` 源码里写得很明确：
```
This is the **source** copy of the hook, shipped inside the codewiki
package. ... CodeBuddy runs the *copied* file, not this one.
```

## 2. 对 Claude Code：采集脚本层有显式兼容设计（未接线、未验证）

虽然没提供 `.claude/settings.json` 接线，但两处源码明确留了兼容口子：

- `_ide_hook.py` 注释：`CodeBuddy/Claude-Code compatible hook events (e.g. SessionEnd)`，载荷解析是事件无关的（`transcript_path`/`transcript` + 内联 turns 多 key 兜底）
- `task_session_start.py` 的仓库路径解析优先级：`CODEBUDDY_PROJECT_DIR`（CodeBuddy 专用）→ `CLAUDE_PROJECT_DIR`（compat）→ 事件 `cwd`

也就是说**采集侧**只要 agent 的 hook 事件能注入 `transcript_path` 或内联对话 turns，就能被 `_ide_hook.py` 消费；缺的只是 `SessionStart`/`SessionEnd` 的 `.claude/settings.json` 注册文件。

## 3. 其他 agent（Cursor / Windsurf / Gemini CLI 等）

没有任何代码或文档提及，属于「理论上可用、实际未适配」。

---

如果你想把 Claude Code 也接上，最省事的方式是仿照 `.codebuddy/settings.json` 生成一个 `.claude/settings.json`，把 `SessionEnd`/`SessionStart` 事件注册到同一批 wrapper 脚本即可。需要我帮你补上这份 Claude Code 接线吗？
user: 要不把hooks暂时仅支持codebuddy加到readme
assistant: 任务已绑定，继续当前文档修改任务。先看 README 里 hook 相关章节的结构。
assistant: README 是双语结构。先精读中英两处「团队记忆融合」章节，确定插入点。
assistant: 两处「关键约束」各加一条支持范围说明。
assistant: 已加到 README 中英两处「团队记忆融合 → 关键约束」：

**中文版（`README.md` 383-387 行）：**
```383:387:README.md
- 自动采集 Hook 只落 raw，永不自动蒸馏；蒸馏须显式调用 `distill_conversation`。
- `repowiki/raw/` 是暂存区，不进 `query_wiki` 检索；蒸馏完成后由工具自动清理（除非 `keep_raw`）。
- 触发形态为 **both**：手动命令（主）+ IDE Hook（可选）。
- 自动采集/任务引导 Hook 目前**仅接线支持 CodeBuddy**（`.codebuddy/settings.json`）；采集脚本对事件载荷做了通用化处理，但其他 IDE（如 Claude Code）的接线尚未提供。
```

**英文版（`README.md` 996-1000 行）** 对应加了一句 `wired for **CodeBuddy only** ... no off-the-shelf wiring is provided for other IDEs (e.g. Claude Code) yet.`

措辞用了「**仅接线支持**」而不是「仅支持」——因为底层采集脚本（`_ide_hook.py`）其实已经做了 CodeBuddy/Claude-Code 兼容的事件载荷解析，只是缺少其他 IDE 的注册文件，这样描述更准确，避免误导。
