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

wrapper 通过 `<python> -m codewiki.mcp._ide_hook` 调起采集脚本（`install-hooks` 生成的解释器名按本机平台解析：Windows 为 `python`，mac/Linux 一般为 `python3`），因此要求该解释器能导入 `codewiki` 包。满足其一即可：

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
          { "type": "command", "command": "python \".codebuddy/hooks/task_session_start.py\"", "timeout": 15 }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "other",
        "hooks": [
          { "type": "command", "command": "python \".codebuddy/hooks/capture_session_end.py\"", "timeout": 30 }
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

**命令路径用项目相对形式（如 `python ".codebuddy/hooks/capture_session_end.py"`），不写机器相关绝对路径**——`.<ide>/settings.json` 随仓库共享，绝对路径（如 `d:/repos/CodeWiki-CN/...`）提交后队友克隆到其他目录即失效。相对路径可行的前提是宿主以项目根为工作目录执行 hook 命令（已实测）；各宿主的 `$*_PROJECT_DIR` 环境变量展开曾尝试（CodeBuddy `$CODEBUDDY_PROJECT_DIR`、Qoder `$QODER_PROJECT_DIR`、Claude Code `$CLAUDE_PROJECT_DIR`、Gemini CLI `$GEMINI_PROJECT_DIR`），实测不可靠故弃用。重跑 `codewiki install-hooks` 会把旧格式条目（绝对路径/环境变量占位符）原地迁移为相对形式，不产生重复注册。接线后建议开一个新会话验证 hook 触发。**解释器名是安装机平台的快照**（Windows `python`，mac/Linux `python3`）：`install-hooks` 每次按本机重新解析并原地迁移旧条目，所以换机器或刚克隆后，`install-hooks` 是每机一次的固定动作——跳过它，hook 会以 exit 127（command not found）静默失败：任务关联弹框不出现、对话不采集，只在宿主日志里留一行。宿主 hook「没反应」时先看退出码再看接线档位：127 是命令本身起不来（解释器/路径），不是宿主不支持该事件。

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

- **对话 turns 来源**：优先读 `transcript_path` 指向的文件（支持 JSON 数组、`{messages:[]}` / `{conversation:[]}` / `{turns:[]}` 包装、逐行 JSONL）；若 IDE 直接把对话**内联**在事件 JSON 里（`conversation` / `messages` / `turns` / `transcript_turns` / `chat` 任一非空数组），则直接采用内联 turns，无需 transcript 文件。若两者都缺失/不可读，脚本**不写任何文件**：只向 stderr 打印一条诊断（`<事件名> event has no conversation turns and no usable transcript_path`）并以退出码 0 返回。**事件信封落盘路径已移除**——把事件本身合成为一行伪对话写进 raw/ 的兜底做法，产物既无正文也无 task_id/session 归属，只会堆积成永不蒸馏的 raw 积压，且因复用 `source_session_id` 存在覆盖真实 transcript 的风险（决策见 `notes/2026-09-16-移除事件信封落盘无-transcript-的-hook-生命周期事件一律-no-op仅-stderr-诊断.md`）。要确认 IDE 真实注入的 payload 形状，看下面的诊断留痕。
- **诊断留痕**：每次触发都会把 IDE 传入的原始 stdin 原样写入 `repowiki/raw/.hook-debug/event-<ts>.json`（不进 `query_wiki`），用于确认 CodeBuddy 实际注入的字段。定位"为何没抓到对话"时先查这里。
- **默认关闭**：未设置环境变量且未传 `--enable` 时，脚本打印 `disabled` 并以退出码 0 返回，不写任何文件。
- **失败不崩溃 IDE**：捕获/导入异常仅打印到 stderr，不中断 IDE。
- `--repo-path`（或 JSON 里的 `repo_path`）必填，用于解析 `repowiki/raw/`；缺失则退出码 2。

## 同会话覆盖式去重（supersede）

Stop 每轮都会触发，PreCompact 也可能在会话中途触发，同一会话因此会被反复采集，且 transcript 逐轮增长。`capture_conversation` 对此做两层去重：

1. **内容哈希去重**：transcript 完全相同（如 Stop 后无新轮次又触发一次）→ 返回 `duplicate`，不写文件。
2. **会话级覆盖**：事件里的 `session_id` 作为 `source_session_id` 传入并写入 raw 文件的 `source_session` 字段；同一会话再次采集且旧文件仍为 `status: pending` 时，直接覆盖该文件（新 transcript 是旧的超集），不新建递增副本。已蒸馏（`distilled`）或 `keep_raw: true` 的文件不受影响。

效果：无论三个事件在一个会话里触发多少次，`raw/` 中该会话始终只保留**最新一份完整 transcript**；蒸馏成本与只接 SessionEnd 时相同，但获得了轮次级的崩溃保险。

## 档位 × 采集开关（v3 接线选择）

接线有两个轴（设计依据 `docs/接线档位选择设计方案.md` §3.1，ADR-0014）：

- **档位 `wiring`（读 / 生命周期侧）**：`hook`（拷脚本 + 写 settings.json/hooks.json + 注入引导段）/ `prompt`（只写注入文件，不建配置目录、不拷脚本、不写 settings）/ `auto`（按 `codewiki/hooks.yaml` 注册表判定，**默认 = 今日行为**）。
- **采集开关 `capture`**：`on`（默认，SessionEnd/TRAE Stop 采集注册写入）/ `off`（移除采集注册，主动沉淀成为唯一记忆写入通道，采集→蒸馏链路停摆）。

**主动沉淀固定启用**（ADR-0014）：不再是轴、不再有开关——`--active-settle` 参数已删除（传入即硬报错），CODEWIKI-ACTIVE-SETTLE 协议块恒渲染，任务记忆唯一通道是 `add_task_memory` 直写，蒸馏固定只产经验笔记。

| 档位 | capture | 产物 | 适用 |
|---|---|---|---|
| `hook` | `on`（默认） | 脚本 + settings 注册 + 注入引导段 + 协议块 | 采集完整宿主（CodeBuddy/Qoder/Claude Code）默认，现状批处理 + 主动沉淀 |
| `hook` | `off` | 同上，但无 SessionEnd（TRAE 为 Stop）采集注册 | 主动沉淀效果好、不再需要采集→蒸馏链路 |
| `prompt` | `on` | 仅注入文件（引导段 + 协议块） | 无 shell hook 宿主（QwenWork）默认，或团队共享仓库不留脚本/settings |

可用 CLI 控制：

```powershell
codewiki install-hooks --ide trae                    # 档位自动判定：TRAE → hook 档
codewiki install-hooks --ide qwenwork                # 档位自动判定：QwenWork → prompt 档
codewiki install-hooks --capture off                 # 停采集，主动沉淀是唯一通道
```

档位由 `codewiki/hooks.yaml` 注册表自动判定——支持 SessionStart 的宿主走 hook 档，不支持的（QwenWork）走 prompt 档，无手动覆盖（`--mode` 已移除，传入即硬报错）。

### 决策树（设计方案 §3.12）

```
--status 看支持性与当前采集状态
├─ 采集完整宿主（codebuddy/claude, verified=true）
│    ├─ 满足现状批处理 ─────────► 直接接线（默认，零回归）
│    └─ 主动沉淀效果好、想停采集─► --capture off（主动沉淀固定启用）
├─ 采集断供宿主（trae 企业版 / qwenwork）
│    ─ 默认即对：档位由注册表自动判定（trae → hook 档，qwenwork → prompt 档），
│       主动沉淀兜底 ────────────────────────────────────────► 直接装，默认已对
```

### `--status`：先看后选（只读，不改任何文件）

```
| agent     | family | registry | wiring | capture  | wired-on-disk                        | capability gap                     |
|-----------|--------|----------|--------|----------|--------------------------------------|------------------------------------|
| codebuddy | claude | 已验证   | hook   | on(默认) | not wired                            | -                                  |
| trae      | trae   | 已验证   | hook   | on(默认) | not wired                            | no SessionEnd -> 主动沉淀兜底       |
| qwenwork  | prompt | 已验证   | prompt | on(默认) | not wired                            | no auto-capture; agent-mediated    |
```

（表样示意；`wired-on-disk` 反映该仓库实际接线状态——hook 宿主显示 `hooks+settings`/`hooks(仅SS)+settings(capture off)`/`hooks(仅SS)+AGENTS`，prompt 宿主显示 `AGENTS.md only`；`capture` 来源标注 `(默认)` 或 CLI 覆盖的 `(CLI)`。）

### 主动沉淀（固定启用，ADR-0014）

接线即向注入文件（默认 `AGENTS.md`）写入 `CODEWIKI-ACTIVE-SETTLE` 协议块：

- **停顿点四判据即写即沉淀**（任务里程碑达成 / 关键技术决策落定 / 用户话题明显转向 / 收尾轮强制兜底）：任务记忆走 `add_task_memory` 直写（无闸门，ADR-0002），通用经验走 `ingest_note(status="draft")`（**确认闸门保留**，两区制 ADR-0004）——当轮落盘，下一轮 `get_task_context` 即取。
- **收尾轮沉淀自查（必做）**：收尾轮检查本会话是否有未沉淀的进展/决策，漏了补写（不再采集全文）。蒸馏固定只产经验笔记、不产任务记忆（通道互斥，ADR-0014）——漏沉淀的会话失去蒸馏捞回兜底，漏报率由观察期数据验证，不达标可重开 capture。**禁止手写 `raw/*.md` 文件。**

### 注入文件：AGENTS.md 自动加载的核验状态（开放问题 1）

hook 宿主的 SessionStart 注入与注入文件无关；**prompt 档**依赖宿主自动加载注入文件（默认 `AGENTS.md`）。`claude-code` / `cursor` 是否自动加载 `AGENTS.md` **尚未真机核验**（设计方案 §7 开放问题 1、§3.11）：核验前不臆断——prompt 档默认按 `AGENTS.md` 注入，请用户自行确认该宿主确实会自动加载，否则用 `--inject-file <path>` 覆盖指向宿主实际读取的记忆文件（如 claude 家族惯用 `CLAUDE.md`）；核验后再回填注册表 `inject_file`。

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
#   wrapper 是 fire-and-forget：只回报「后台采集已启动」，不回报采集结果。
#   是否真的落盘，要等 1-2 秒后看 repowiki/raw/ 里有没有该会话的 conv-*.md。
#   cwd 别写反斜杠路径（d:\repos 里的 \r、\C 是非法 JSON 转义，事件会被整体丢弃）。
'{"session_id":"sess-1","transcript_path":"d:/tmp/conv.json","cwd":"d:/repos/CodeWiki-CN","hook_event_name":"SessionEnd","reason":"other"}' | python "d:/repos/CodeWiki-CN/.codebuddy/hooks/capture_session_end.py"
# 期望 stdout: {"continue": true, "systemMessage": "team-memory capture started in background"}
# stdin 事件缺失或 JSON 非法时: systemMessage 为 "team-memory capture skipped: <原因>"，raw/ 不变

# 方式 C：验证「无正文事件不落盘」（PreCompact/Stop 已不再注册，此处仅作防回归用例）
'{"session_id":"sess-2","cwd":"d:/repos/CodeWiki-CN","hook_event_name":"Stop","stop_hook_active":false}' | python "d:/repos/CodeWiki-CN/.codebuddy/hooks/capture_session_end.py"
# 期望: stdout 仍返回 continue=true（不阻塞 IDE），raw/ 不新增文件

# 方式 D：验证同会话覆盖去重——同一 session_id 用更长的 transcript 再采集一次
'[{"role":"user","content":"如何初始化 wiki"},{"role":"assistant","content":"调用 init_wiki 即可"},{"role":"user","content":"追问：如何查询"}]' | Out-File -Encoding utf8 d:/tmp/conv2.json
'{"session_id":"sess-1","transcript_path":"d:/tmp/conv2.json","cwd":"d:/repos/CodeWiki-CN","hook_event_name":"SessionEnd","reason":"other"}' | python "d:/repos/CodeWiki-CN/.codebuddy/hooks/capture_session_end.py"
# 期望: raw/ 中 sess-1 仍只有一个 conv-*.md，内容为 3 turns（看文件系统，wrapper 不再回报 superseded）
```

验证后清理：`repowiki/raw/conv-*.md` 为测试残留，可删除。
