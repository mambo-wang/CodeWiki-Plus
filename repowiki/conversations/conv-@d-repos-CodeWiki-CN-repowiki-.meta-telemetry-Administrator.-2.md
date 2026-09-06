---
type: Conversation
title: "conversation 20260827T094322Z"
status: distilled
stale_after: 2026-11-25
generated: { by: codewiki/5.4.4, at: 2026-08-27T09:43:22Z }
captured_at: "2026-08-27T09:43:22Z"
content_hash: "sha256:2921fb3b50dfe27379df958f70c2a524a5bb1abff3c513f8b716149430af0d9f"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=2"
keep_raw: false
link_to: ""
source_session: "f033542961a148cdb8cdf18a39e1e0fe"
task_id: "产品维护"
turn_count: 3
---

# Conversation Transcript

user: @d:\repos\CodeWiki-CN\repowiki\.meta\telemetry\Administrator.jsonl.tmp.19748  这个文件是如何产生的，什么时候回删除
user: <question>本次会话要关联哪个任务？</question>
<answers>
产品维护(task_id=产品维护)
</answers>
</question_item>
</questions>
</question_answer>
assistant: 任务关联已建立（`产品维护`），补蒸馏已委托后台 subagent 执行，不阻塞本回答。

## 结论

这个 `Administrator.jsonl.tmp.19748` 是 **telemetry 事件写入过程中的一个孤儿临时文件**，由崩溃安全写入逻辑残留，**没有任何自动清理机制，会一直留着直到你手动删除**。

## 产生方式

`codewiki/mcp/tools/telemetry.py` 的 `_atomic_write_lines()` 每次写 `Administrator.jsonl`（记录 `hit` 检索命中事件）时，采用「临时文件 + `os.replace` 原子替换」的写法：

```112:124:codewiki/mcp/tools/telemetry.py
def _atomic_write_lines(path: Path, lines: List[str]) -> None:
    """Write jsonl lines via temp file + os.replace (crash-safe)."""
    tmp = path.parent / (path.name + f".tmp.{os.getpid()}")
    try:
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise
```

- 临时文件命名 = 正式文件名 + `.tmp.<进程PID>`，这里的 `19748` 就是当时写入进程的 PID。
- 正常流程：写临时文件 → `os.replace(tmp, path)` 原子替换 → 临时文件消失，只剩正式文件。

## 什么时候会删除

| 场景 | 结果 |
|------|------|
| 正常写成功 | `os.replace` 后临时文件被替换掉，自动消失 |
| 抛 `OSError` 且进程存活 | `except OSError` 分支里 `tmp.unlink()` 清理掉 |
| **进程在写临时文件与 replace 之间被强杀/崩溃/断电** | **残留成孤儿文件**（你现在看到的这个） |
| 抛非 `OSError` 异常（如 `KeyboardInterrupt`、`MemoryError`） | **残留**（`except` 只捕 `OSError`） |

关键点：**代码里没有任何启动流程或定时任务去扫描删除 `*.tmp.*` 残留文件**。所以一旦进程在 `write_text` 之后、`os.replace` 之前被 kill 掉，这个临时文件就成了永久残留（除非下次有人手动删）。

## 影响与处理建议

- **不影响功能**：`aggregate_usage` 用 `glob("*.jsonl")` 扫描，而 `Administrator.jsonl.tmp.19748` 不以 `.jsonl` 结尾，不会被聚合读入。
- 它只是 git 里的一条 untracked 残留，直接手动删除即可，无副作用。需要的话我可以帮你删掉。
