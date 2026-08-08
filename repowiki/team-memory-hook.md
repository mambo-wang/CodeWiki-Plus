# Team-Memory Hook：对话自动采集（IDE 接线说明）

本说明描述如何把「对话 → `repowiki/raw/` 暂存区」的自动采集接到 CodeBuddy IDE，作为 team-memory fusion（对话 → Wiki 经验沉淀）的**采集半环**。

> 边界：hook **只采集不蒸馏**。蒸馏（LLM 重活、异步）由 `distill_conversation` 经后台 subagent/worker 另行执行，不在此层内。

## 组件

- 采集脚本：`codewiki/mcp/_ide_hook.py`（`python -m codewiki.mcp._ide_hook`）—— 只负责 capture，不蒸馏。
- SessionEnd wrapper：`.codebuddy/hooks/capture_session_end.py` —— 由 IDE 直接调用，读取 SessionEnd 事件、定位 repo 与 transcript，转发给采集脚本。
- 落盘路径：`repowiki/raw/conv-<timestamp>.md`（带 `content_hash` 幂等去重，不进 `query_wiki`）
- IDE 配置：`.codebuddy/settings.json`（`hooks.SessionEnd`）

> 参考 CodeBuddy 官方 Hooks 文档：<https://www.codebuddy.cn/docs/ide/Features/Hooks#sessionend>

## 启用方式（仓库已预置，默认接线）

`.codebuddy/settings.json` 已注册 `SessionEnd`（`matcher: "other"`）钩子，指向稳定绝对路径的 wrapper：

```json
{
  "hooks": {
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

会话结束（对话终止）时，CodeBuddy 通过 **stdin** 向 wrapper 传入事件 JSON：

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.txt",
  "cwd": "/project/path",
  "hook_event_name": "SessionEnd",
  "reason": "other"
}
```

wrapper 据此解析 `repo_path`（`cwd` → `$CODEBUDDY_PROJECT_DIR` 回退）与对话来源 `transcript_path`，调用采集脚本完成落盘。无需额外环境变量——此路径已用 `--enable` 强制开启。

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
- SessionEnd 事件：若事件 JSON 含 `transcript_path`/`transcript`，脚本自动读取并抽取 turns（支持 JSON 数组、`{messages:[]}` 包装、逐行 JSONL）。

## 重要约束

- **SessionEnd 事件不直接内联对话 turns**，但通过 `transcript_path` 字段提供对话记录文件路径（官方文档确认）。wrapper 自动读取并抽取 turns（支持 JSON 数组、`{messages:[]}` / `{conversation:[]}` / `{turns:[]}` 包装、逐行 JSONL）。若 `transcript_path` 缺失或不可读，脚本以退出码 0 安全返回，不误采集。
- **默认关闭**：未设置环境变量且未传 `--enable` 时，脚本打印 `disabled` 并以退出码 0 返回，不写任何文件。
- **失败不崩溃 IDE**：捕获/导入异常仅打印到 stderr，不中断 IDE。
- `--repo-path`（或 JSON 里的 `repo_path`）必填，用于解析 `repowiki/raw/`；缺失则退出码 2。

## 生命周期

- 自动采集落下的 raw 与手动 `capture_conversation` 同属暂存区，遵循同一清理策略：蒸馏完成后由 `distill_conversation` 删除；默认 7 天保留上限自动清理。
- raw 暂存区不进 `query_wiki` 检索，不膨胀、不影响查询性能。

## 手动验证

```powershell
# 方式 A：直接调用采集脚本（文件方式）
'[{"role":"user","content":"如何初始化 wiki"},{"role":"assistant","content":"调用 init_wiki 即可"}]' | Out-File -Encoding utf8 d:/tmp/conv.json
python -m codewiki.mcp._ide_hook --enable --repo-path "d:/repos/CodeWiki-CN" --conversation d:/tmp/conv.json

# 方式 B：模拟 CodeBuddy SessionEnd 事件（经 wrapper，验证完整链路）
'{"session_id":"sess-1","transcript_path":"d:/tmp/conv.json","cwd":"d:/repos/CodeWiki-CN","hook_event_name":"SessionEnd","reason":"other"}' | python "d:/repos/CodeWiki-CN/.codebuddy/hooks/capture_session_end.py"
# 期望 stdout: {"continue": true, "systemMessage": "...\"status\": \"captured\"..."}
```

验证后清理：`repowiki/raw/conv-*.md` 为测试残留，可删除。
