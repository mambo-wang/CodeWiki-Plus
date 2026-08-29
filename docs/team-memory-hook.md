# Team-Memory Hook：对话自动采集（IDE 接线说明）

本说明描述如何把「对话 → `repowiki/raw/` 暂存区」的自动采集接到 CodeBuddy IDE，作为 team-memory fusion（对话 → Wiki 经验沉淀）的**采集半环**。

> 边界：hook **只采集不蒸馏**。蒸馏（LLM 重活、异步）由 `distill_conversation` 经后台 subagent/worker 另行执行，不在此层内。

## 组件

- 采集脚本：`codewiki/mcp/_ide_hook.py`（`python -m codewiki.mcp._ide_hook`）—— 只负责 capture，不蒸馏。
- 会话 hook wrapper：`.codebuddy/hooks/capture_session_end.py` —— 由 IDE 直接调用，事件无关（event-agnostic）：读取事件、定位 repo 与 transcript，转发给采集脚本。同一脚本服务三种事件。
- 落盘路径：`repowiki/raw/conv-<timestamp>.md`（带 `content_hash` 幂等去重 + 同会话覆盖式去重，不进 `query_wiki`）
- IDE 配置：`.codebuddy/settings.json`（`hooks.SessionEnd` / `hooks.PreCompact` / `hooks.Stop`）

> 参考 CodeBuddy 官方 Hooks 文档：<https://www.codebuddy.cn/docs/ide/Features/Hooks#sessionend>

## 前置条件

wrapper 通过 `python -m codewiki.mcp._ide_hook` 调起采集脚本，因此要求 hook 所用的 `python` 能导入 `codewiki` 包。满足其一即可：

1. `codewiki` 已通过 pip 安装（如 `pip install codewiki-plus`）；
2. hook 位于 CodeWiki 源码仓库内（`.codebuddy/` 随仓库分发，子进程以仓库为 cwd 运行，本地包直接可导入）；
3. 设置环境变量 `CODEWIKI_HOME` 指向 CodeWiki 源码 checkout 目录（hook 被复制到其他项目使用时，wrapper 会把该目录注入子进程 `PYTHONPATH`）。

三者都不满足时，wrapper 不会静默失败，而是返回一条说明如何修复的 `systemMessage` 并跳过本次采集（不阻塞 IDE）。

## 启用方式（仓库已预置，默认接线）

`.codebuddy/settings.json` 注册了两个事件钩子（接线由 `codewiki install-hooks` 维护；`PreCompact`/`Stop` 早期曾注册，因不带 `transcript_path`、只产生重复空信封而移除）：

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          { "type": "command", "command": "python \"$CODEBUDDY_PROJECT_DIR/.codebuddy/hooks/task_session_start.py\"", "timeout": 15 }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "other",
        "hooks": [
          { "type": "command", "command": "python \"$CODEBUDDY_PROJECT_DIR/.codebuddy/hooks/capture_session_end.py\"", "timeout": 30 }
        ]
      }
    ]
  }
}
```

两个事件的分工：

| 事件 | 触发时机 | matcher | 职责 |
|---|---|---|---|
| `SessionStart` | 新会话开始 | `startup` | 同步返回 `hookSpecificOutput.additionalContext`，注入任务关联引导（脚本 `task_session_start.py`，纯 stdlib，不 import codewiki） |
| `SessionEnd` | 会话终止（切换/删除/清空） | `other`（目前唯一支持的 reason 值） | 唯一可靠携带 `transcript_path` 的事件；采集脚本经 wrapper 转发落盘 |

**命令路径用可移植形式，不写机器相关绝对路径**——`.codebuddy/settings.json` 随仓库共享，绝对路径（如 `d:/repos/CodeWiki-CN/...`）提交后队友克隆到其他目录即失效。各 IDE 的路径形式由 `codewiki install-hooks` 按注册表模板生成：CodeBuddy 用 `$CODEBUDDY_PROJECT_DIR/...`（官方文档称 command 中可用该环境变量），Qoder 用仓库相对路径（官方示例形态），Claude Code 用 `${CLAUDE_PROJECT_DIR}/...` 官方占位符（宿主执行前纯字符串替换，跨平台）。历史沿革：2026-08 曾实测旧版 CodeBuddy 不展开 `$CODEBUDDY_PROJECT_DIR` 而回退绝对路径；现行官方 IDE 文档明确支持环境变量形式，接线后建议开一个新会话验证 hook 触发。

事件触发时，CodeBuddy 通过 **stdin** 向 wrapper 传入事件 JSON（以 SessionEnd 为例）：

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.txt",
  "cwd": "/project/path",
  "hook_event_name": "SessionEnd",
  "reason": "other"
}
```

wrapper 据此解析 `repo_path`（优先 `CODEBUDDY_PROJECT_DIR` / `CLAUDE_PROJECT_DIR` 环境变量，其次事件 JSON 的 `cwd` 字段，最后从脚本自身位置推导）与对话来源 `transcript_path`，调用采集脚本完成落盘。脚本本体不依赖工作目录，可移植性只取决于 settings.json 里那行命令能否定位到脚本。

### 备选：手动调用采集脚本（不走 IDE 钩子）

```powershell
# 环境变量方式
$env:CODEWIKI_TEAM_MEMORY_HOOK = "1"
python -m codewiki.mcp._ide_hook --repo-path "d:/repos/CodeWiki-CN"

# 或单次 --enable 强制开启
python -m codewiki.mcp._ide_hook --enable --repo-path "d:/repos/CodeWiki-CN"
```

## 喂入对话内容

- `--conversation <json文件>`：文件为 turns 列表 `[{"role","content"}]` 或 `{"conversation":[...]}`。文件用 UTF-8（PowerShell `Out-File` 默认带 BOM，脚本已用 `utf-8-sig` 兼容）。
- stdin 管道：直接传 JSON 列表或对象（实际接线中由 IDE 注入）。
- IDE hook 事件（SessionEnd / PreCompact / Stop）：若事件 JSON 含 `transcript_path`/`transcript`，脚本自动读取并抽取 turns（支持 JSON 数组、`{messages:[]}` 包装、逐行 JSONL）。

## 重要约束

- **对话 turns 来源**：优先读 `transcript_path` 指向的文件（支持 JSON 数组、`{messages:[]}` / `{conversation:[]}` / `{turns:[]}` 包装、逐行 JSONL）；若 IDE 直接把对话**内联**在事件 JSON 里（`conversation` / `messages` / `turns` / `transcript_turns` / `chat` 任一非空数组），则直接采用内联 turns，无需 transcript 文件。若两者都缺失/不可读，脚本不再静默跳过，而是把**事件信封本身**作为最小记录落盘（frontmatter 完整 + 一条 system 说明），以便确认 hook 确实触发、并能在 `repowiki/raw/.hook-debug/` 看到 IDE 真实注入的 payload 形状。
- **诊断留痕**：每次触发都会把 IDE 传入的原始 stdin 原样写入 `repowiki/raw/.hook-debug/event-<ts>.json`（不进 `query_wiki`），用于确认 CodeBuddy 实际注入的字段。定位"为何没抓到对话"时先查这里。
- **默认关闭**：未设置环境变量且未传 `--enable` 时，脚本打印 `disabled` 并以退出码 0 返回，不写任何文件。
- **失败不崩溃 IDE**：捕获/导入异常仅打印到 stderr，不中断 IDE。
- `--repo-path`（或 JSON 里的 `repo_path`）必填，用于解析 `repowiki/raw/`；缺失则退出码 2。

## 同会话覆盖式去重（supersede）

Stop 每轮都会触发，PreCompact 也可能在会话中途触发，同一会话因此会被反复采集，且 transcript 逐轮增长。`capture_conversation` 对此做两层去重：

1. **内容哈希去重**：transcript 完全相同（如 Stop 后无新轮次又触发一次）→ 返回 `duplicate`，不写文件。
2. **会话级覆盖**：事件里的 `session_id` 作为 `source_session_id` 传入并写入 raw 文件的 `source_session` 字段；同一会话再次采集且旧文件仍为 `status: pending` 时，直接覆盖该文件（新 transcript 是旧的超集），不新建递增副本。已蒸馏（`distilled`）或 `keep_raw: true` 的文件不受影响。

效果：无论三个事件在一个会话里触发多少次，`raw/` 中该会话始终只保留**最新一份完整 transcript**；蒸馏成本与只接 SessionEnd 时相同，但获得了轮次级的崩溃保险。

## 触发蒸馏（何时提取经验）

采集与蒸馏完全解耦：hook **只落 raw**，蒸馏永远不会自动发生，必须显式调用 `distill_conversation`。它是无状态工具，自身不持有 LLM，按调用方形态分三种模式：

- **Mode C（推荐，IDE Agent 场景）**：宿主 Agent 自己就是 LLM。先 `distill_conversation(mode="prepare")` 取回所有 pending transcript + 蒸馏 system prompt；Agent 用自己的模型逐条提取，产出 `{"notes": [...]}` JSON；再 `distill_conversation(mode="submit", distilled={conversation_id: <JSON>})`，工具执行确定性的一半（解析、去重、`ingest_note` 落 draft、清理 raw、重建索引）。纯 MCP JSON 即可走通，无需注入回调或配置模型环境变量。
- **Mode A（subagent 直调）**：注入 `llm` async 回调，内联蒸馏（回调无法经 MCP JSON 传递）。
- **Mode B（后台 worker）**：`run_in_background=true`，从 `MAIN_MODEL`/`LLM_BASE_URL`/`LLM_API_KEY` 环境变量构建 LLM，进度写 `repowiki/distill-jobs.json`。

配套 MCP prompt 模板（经 `prompts/list` / `prompts/get` 获取，与 generate-wiki 等同级）：

- `team-memory-hook`：启用/关闭采集 hook 的操作指引（支持 `action = enable|disable` 参数）。
- `distill-conversations`：蒸馏工作流指引（prepare → 提取 → submit → 与用户评审 confirm/reject）。

蒸馏产出的 note 以 `status=draft` 落盘，需 `confirm_note` 确认后才成为正式知识；确认后 raw 即被删除（除非 `keep_raw: true`）。

## 生命周期

- 自动采集落下的 raw 与手动 `capture_conversation` 同属暂存区，遵循同一清理策略：蒸馏完成后由 `distill_conversation` 删除。**未蒸馏的 raw 会一直保留**（没有自动过期机制），请定期蒸馏或手动清理。
- raw 暂存区不进 `query_wiki` 检索，不膨胀、不影响查询性能。
- `repowiki/raw/` 已加入 `.gitignore`：暂存文件不会被误提交。
- 采集**不写** `wiki/log.md`：raw 是蒸馏后即删的暂存文件，逐会话记日志会留下指向已删文件的永久条目；日志在蒸馏产出 note 时由 `ingest_note` 记录。

## 手动验证

```powershell
# 方式 A：直接调用采集脚本（文件方式）
'[{"role":"user","content":"如何初始化 wiki"},{"role":"assistant","content":"调用 init_wiki 即可"}]' | Out-File -Encoding utf8 d:/tmp/conv.json
python -m codewiki.mcp._ide_hook --enable --repo-path "d:/repos/CodeWiki-CN" --conversation d:/tmp/conv.json

# 方式 B：模拟 CodeBuddy SessionEnd 事件（经 wrapper，验证完整链路）
'{"session_id":"sess-1","transcript_path":"d:/tmp/conv.json","cwd":"d:/repos/CodeWiki-CN","hook_event_name":"SessionEnd","reason":"other"}' | python "d:/repos/CodeWiki-CN/.codebuddy/hooks/capture_session_end.py"
# 期望 stdout: {"continue": true, "systemMessage": "...\"status\": \"captured\"..."}

# 方式 C：模拟 PreCompact / Stop 事件（仅 hook_event_name 与附加字段不同）
'{"session_id":"sess-1","transcript_path":"d:/tmp/conv.json","cwd":"d:/repos/CodeWiki-CN","hook_event_name":"PreCompact","trigger":"auto"}' | python "d:/repos/CodeWiki-CN/.codebuddy/hooks/capture_session_end.py"
'{"session_id":"sess-1","transcript_path":"d:/tmp/conv.json","cwd":"d:/repos/CodeWiki-CN","hook_event_name":"Stop","stop_hook_active":false}' | python "d:/repos/CodeWiki-CN/.codebuddy/hooks/capture_session_end.py"

# 方式 D：验证同会话覆盖去重——同一 session_id 用更长的 transcript 再采集一次
'[{"role":"user","content":"如何初始化 wiki"},{"role":"assistant","content":"调用 init_wiki 即可"},{"role":"user","content":"追问：如何查询"}]' | Out-File -Encoding utf8 d:/tmp/conv2.json
'{"session_id":"sess-1","transcript_path":"d:/tmp/conv2.json","cwd":"d:/repos/CodeWiki-CN","hook_event_name":"Stop","stop_hook_active":false}' | python "d:/repos/CodeWiki-CN/.codebuddy/hooks/capture_session_end.py"
# 期望: "superseded": true，且 raw/ 中 sess-1 仍只有一个 conv-*.md 文件（内容为 3 turns）
```

验证后清理：`repowiki/raw/conv-*.md` 为测试残留，可删除。
