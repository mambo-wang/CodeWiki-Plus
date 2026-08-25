"""Tests for the task memory layer (task_manager.py).

Covers task CRUD, session binding, per-task memory, context aggregation, and the
end-to-end flow: create task -> capture conversation bound to task -> distill
(notes + task memories) -> retrieve notes filtered by task_id.
"""

import json

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import capture_conversation as capture
from codewiki.mcp.tools import distill_conversation as distill
from codewiki.mcp.tools import knowledge_loop as kl
from codewiki.mcp.tools import task_manager as tm


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _od(repo: str) -> str:
    return f"{repo}/repowiki"


def _store() -> SessionStore:
    return SessionStore()


def _call(fn, **kwargs) -> dict:
    return json.loads(fn(kwargs, _store()))


# --------------------------------------------------------------------------- #
# Task CRUD
# --------------------------------------------------------------------------- #


def test_create_and_list_tasks(tmp_path):
    repo = str(tmp_path)
    r = _call(
        tm.handle_create_task,
        output_dir=_od(repo),
        title="实现登录鉴权",
        description="做一个 OAuth2 登录",
    )
    assert r["ok"] is True
    task_id = r["task"]["id"]
    assert task_id
    assert r["task"]["status"] == "active"

    lst = _call(tm.handle_list_tasks, output_dir=_od(repo))
    assert lst["ok"] is True
    ids = [t["id"] for t in lst["tasks"]]
    assert task_id in ids

    # Status filter: only active tasks, and none completed yet.
    active = _call(tm.handle_list_tasks, output_dir=_od(repo), status="active")
    assert any(t["id"] == task_id for t in active["tasks"])
    done = _call(tm.handle_list_tasks, output_dir=_od(repo), status="completed")
    assert all(t["id"] != task_id for t in done["tasks"])


def test_duplicate_title_rejected(tmp_path):
    repo = str(tmp_path)
    first = _call(tm.handle_create_task, output_dir=_od(repo), title="重构订单模块")
    assert first["ok"] is True

    dup = _call(tm.handle_create_task, output_dir=_od(repo), title="重构订单模块")
    assert "error" in dup
    assert "already exists" in dup["error"]


def test_complete_task(tmp_path):
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="写单元测试")
    task_id = r["task"]["id"]

    c = _call(tm.handle_complete_task, output_dir=_od(repo), task_id=task_id)
    assert c["ok"] is True
    assert c["task"]["status"] == "completed"
    assert c["task"].get("completed_at")

    # Completed tasks disappear from active listing.
    active = _call(tm.handle_list_tasks, output_dir=_od(repo), status="active")
    assert all(t["id"] != task_id for t in active["tasks"])


def test_add_and_get_task_memory(tmp_path):
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="迁移数据库")
    task_id = r["task"]["id"]

    m1 = _call(
        tm.handle_add_task_memory,
        output_dir=_od(repo),
        task_id=task_id,
        content="完成 schema 迁移脚本",
    )
    assert m1["ok"] is True
    m2 = _call(
        tm.handle_add_task_memory, output_dir=_od(repo), task_id=task_id, content="验证数据一致性"
    )
    assert m2["ok"] is True

    got = _call(tm.handle_get_task, output_dir=_od(repo), task_id=task_id)
    assert "完成 schema 迁移脚本" in got["memories"]
    assert "验证数据一致性" in got["memories"]


def test_add_memory_to_missing_task(tmp_path):
    repo = str(tmp_path)
    r = _call(tm.handle_add_task_memory, output_dir=_od(repo), task_id="ghost-task", content="x")
    assert "error" in r
    assert "does not exist" in r["error"]


# --------------------------------------------------------------------------- #
# Session binding
# --------------------------------------------------------------------------- #


def test_set_session_task_binding(tmp_path):
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="修复登录 bug")
    task_id = r["task"]["id"]

    b = _call(
        tm.handle_set_session_task,
        output_dir=_od(repo),
        source_session_id="session-abc",
        task_id=task_id,
    )
    assert b["ok"] is True

    # Binding file exists on disk.
    from pathlib import Path

    bf = Path(repo) / "repowiki" / ".meta" / "task_bindings" / "session-abc.json"
    assert bf.exists()
    assert json.loads(bf.read_text(encoding="utf-8"))["task_id"] == task_id


def test_set_session_task_rejects_missing_task(tmp_path):
    repo = str(tmp_path)
    r = _call(
        tm.handle_set_session_task, output_dir=_od(repo), source_session_id="s1", task_id="nope"
    )
    assert "error" in r


def test_capture_resolves_task_from_session_binding(tmp_path):
    """正向：set_session_task 建绑定后，capture 仅凭 source_session_id 就能盖章 task_id。"""
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="绑定回退任务")
    task_id = r["task"]["id"]

    _call(
        tm.handle_set_session_task,
        output_dir=_od(repo),
        source_session_id="session-bound",
        task_id=task_id,
    )

    # 不传 task_id，只传 source_session_id —— 修复后应从绑定文件反查并盖章。
    cap = _call(
        capture.handle_capture_conversation,
        output_dir=_od(repo),
        source_session_id="session-bound",
        conversation=[
            {"role": "user", "content": "绑定回退任务的对话内容"},
            {"role": "assistant", "content": "收到，开始处理"},
        ],
    )
    assert cap["status"] == "captured"
    assert cap["task_id"] == task_id
    assert cap["task_source"] == "binding"

    # raw frontmatter 也带上了 task_id（top_level_extra 以 JSON 序列化写入）。
    raw_dir = tmp_path / "repowiki" / "raw"
    raw_files = list(raw_dir.glob("conv-*.md"))
    assert len(raw_files) == 1
    text = raw_files[0].read_text(encoding="utf-8")
    assert f'task_id: "{task_id}"' in text


def test_capture_without_binding_keeps_taskless(tmp_path):
    """负向：无绑定的 source_session_id → task_id 保持空，不误关联。"""
    repo = str(tmp_path)
    cap = _call(
        capture.handle_capture_conversation,
        output_dir=_od(repo),
        source_session_id="session-nobody",
        conversation=[
            {"role": "user", "content": "无任务关联的对话"},
            {"role": "assistant", "content": "回复"},
        ],
    )
    assert cap["status"] == "captured"
    assert cap["task_id"] == ""
    assert cap["task_source"] == ""


def test_capture_deletes_binding_after_successful_write(tmp_path):
    """绑定是一次性消费凭证：捕获成功落盘后绑定文件应被自动删除。"""
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="消费即删任务")
    task_id = r["task"]["id"]

    _call(
        tm.handle_set_session_task,
        output_dir=_od(repo),
        source_session_id="session-once",
        task_id=task_id,
    )
    from pathlib import Path

    bf = Path(repo) / "repowiki" / ".meta" / "task_bindings" / "session-once.json"
    assert bf.exists()

    cap = _call(
        capture.handle_capture_conversation,
        output_dir=_od(repo),
        source_session_id="session-once",
        conversation=[
            {"role": "user", "content": "本次会话的对话"},
            {"role": "assistant", "content": "处理完成"},
        ],
    )
    assert cap["status"] == "captured"
    assert cap["task_id"] == task_id
    assert cap["task_source"] == "binding"
    # 一次性消费：绑定文件已随捕获成功删除。
    assert not bf.exists()

    # 无绑定后再次捕获同一会话 → supersede 应继承原 task_id，归属不丢。
    cap2 = _call(
        capture.handle_capture_conversation,
        output_dir=_od(repo),
        source_session_id="session-once",
        conversation=[
            {"role": "user", "content": "本次会话的对话"},
            {"role": "assistant", "content": "处理完成"},
            {"role": "user", "content": "再补一句"},
            {"role": "assistant", "content": "好的"},
        ],
    )
    assert cap2["status"] == "captured"
    assert cap2["task_id"] == task_id
    assert cap2["task_source"] == "binding-inherited"
    # supersede 后仍只保留一个 raw 文件。
    raw_dir = tmp_path / "repowiki" / "raw"
    assert len(list(raw_dir.glob("conv-*.md"))) == 1
    text = list(raw_dir.glob("conv-*.md"))[0].read_text(encoding="utf-8")
    assert f'task_id: "{task_id}"' in text


def test_explicit_task_id_does_not_consume_binding(tmp_path):
    """显式传 task_id 时不消费绑定：绑定文件保留，供后续无显式 task_id 的捕获使用。"""
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="显式任务")
    task_id = r["task"]["id"]

    _call(
        tm.handle_set_session_task,
        output_dir=_od(repo),
        source_session_id="session-explicit",
        task_id=task_id,
    )
    from pathlib import Path

    bf = Path(repo) / "repowiki" / ".meta" / "task_bindings" / "session-explicit.json"
    assert bf.exists()

    # 显式传 task_id（task_source="argument"）→ 不触发绑定消费。
    cap = _call(
        capture.handle_capture_conversation,
        output_dir=_od(repo),
        source_session_id="session-explicit",
        task_id=task_id,
        conversation=[
            {"role": "user", "content": "显式传任务的对话"},
            {"role": "assistant", "content": "回复"},
        ],
    )
    assert cap["status"] == "captured"
    assert cap["task_source"] == "argument"
    assert bf.exists()


def test_delete_task_cascades_binding(tmp_path):
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="要删除的任务")
    task_id = r["task"]["id"]

    _call(
        tm.handle_set_session_task,
        output_dir=_od(repo),
        source_session_id="session-xyz",
        task_id=task_id,
    )

    d = _call(tm.handle_delete_task, output_dir=_od(repo), task_id=task_id)
    assert d["ok"] is True
    assert d["cleared_bindings"] == 1

    # Task gone from index and disk.
    lst = _call(tm.handle_list_tasks, output_dir=_od(repo))
    assert all(t["id"] != task_id for t in lst["tasks"])

    from pathlib import Path

    bf = Path(repo) / "repowiki" / ".meta" / "task_bindings" / "session-xyz.json"
    assert not bf.exists()


# --------------------------------------------------------------------------- #
# Context aggregation
# --------------------------------------------------------------------------- #


def test_get_task_context_aggregates_related_notes(tmp_path):
    repo = str(tmp_path)
    r = _call(
        tm.handle_create_task, output_dir=_od(repo), title="聚合任务", description="任务描述体"
    )
    task_id = r["task"]["id"]

    _call(tm.handle_add_task_memory, output_dir=_od(repo), task_id=task_id, content="记忆条目")

    # A related note stamped with task_id (via ingest_note).
    nr = _call(
        kl.handle_ingest_note,
        output_dir=_od(repo),
        title="关联经验",
        note_type="lesson",
        content="## 背景\n\n关联内容",
        task_id=task_id,
    )
    assert "error" not in nr

    ctx = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id)
    assert ctx["ok"] is True
    assert ctx["task"]["id"] == task_id
    assert "任务描述体" in ctx["description"]
    assert "记忆条目" in ctx["memories"]
    titles = [n["title"] for n in ctx["related_notes"]]
    assert "关联经验" in titles


# --------------------------------------------------------------------------- #
# End-to-end: capture -> distill -> retrieve
# --------------------------------------------------------------------------- #


def test_end_to_end_task_memory_flow(tmp_path):
    repo = str(tmp_path)

    # 1. Create a task.
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="端到端任务")
    task_id = r["task"]["id"]

    # 2. Capture a conversation bound to the task.
    cap = _call(
        capture.handle_capture_conversation,
        output_dir=_od(repo),
        conversation=[
            {"role": "user", "content": "帮我实现端到端任务的登录功能"},
            {"role": "assistant", "content": "已实现登录，采用 JWT 方案"},
        ],
        task_id=task_id,
    )
    assert cap["status"] == "captured"
    assert cap["task_id"] == task_id
    cid = cap["conversation_id"]
    assert cid.startswith("conv-")

    # 3. Distill: produce both a wiki note and a task memory.
    sub = _call(
        distill.handle_distill_conversation,
        output_dir=_od(repo),
        mode="submit",
        distilled={
            cid: {
                "notes": [
                    {
                        "title": "登录采用 JWT 方案",
                        "note_type": "decision",
                        "content": "## 背景\n\n选型\n\n## 决策\n\nJWT",
                        "related_modules": ["auth"],
                        "tags": ["jwt"],
                    }
                ],
                "memories": ["本会话完成登录功能的 JWT 实现"],
            },
        },
    )
    assert sub["status"] == "completed"
    per = sub["distilled"][0]
    assert per["notes_created"] == 1
    assert per["memories_written"] == 1
    assert per["task_id"] == task_id

    # 4. Distilled memories are written DIRECTLY (ADR-0002, no confirm gate):
    #    timestamp-headed entry already in memories.md.
    got = _call(tm.handle_get_task, output_dir=_od(repo), task_id=task_id)
    assert "JWT 实现" in got["memories"]
    assert got["memories_total"] == 1
    assert got["memories"].startswith("### ")

    # 5. The note is stamped with task_id and retrievable via query_wiki.
    #    Draft notes surface with an "[unconfirmed]" prefix, so match on substring.
    q = _call(kl.handle_query_wiki, output_dir=_od(repo), query="JWT", task_id=task_id)
    titles = [res.get("title") for res in q.get("results", [])]
    assert any("登录采用 JWT 方案" in t for t in titles)

    # 6. query_wiki with a different task_id returns no matching note.
    q2 = _call(kl.handle_query_wiki, output_dir=_od(repo), query="JWT", task_id="some-other-task")
    titles2 = [res.get("title") for res in q2.get("results", [])]
    assert not any("登录采用 JWT 方案" in t for t in titles2)


# --------------------------------------------------------------------------- #


def test_delete_task_cascades_task_dir(tmp_path):
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="级联删除")
    task_id = r["task"]["id"]
    _call(tm.handle_add_task_memory, output_dir=_od(repo), task_id=task_id, content="已落盘记忆")

    d = _call(tm.handle_delete_task, output_dir=_od(repo), task_id=task_id)
    assert d["ok"] is True

    from pathlib import Path

    task_dir = Path(repo) / "repowiki" / "tasks" / task_id
    assert not task_dir.exists()


# --------------------------------------------------------------------------- #
# Context injection: pending raw trigger signal + note status
# --------------------------------------------------------------------------- #


def _write_raw_capture(
    tmp_path, name: str, task_id: str, captured_at: str, status: str = "pending"
) -> None:
    from pathlib import Path

    raw_dir = Path(str(tmp_path)) / "repowiki" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / name).write_text(
        "---\n"
        "type: conversation\n"
        f"status: {status}\n"
        f'task_id: "{task_id}"\n'
        f'captured_at: "{captured_at}"\n'
        "---\n\nuser: hi",
        encoding="utf-8",
    )


def test_task_context_pending_raw_count_and_listing(tmp_path):
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="注入任务")
    task_id = r["task"]["id"]

    _write_raw_capture(tmp_path, "conv-a.md", task_id, "2026-08-16T01:00:00Z")
    _write_raw_capture(tmp_path, "conv-b.md", task_id, "2026-08-16T02:00:00Z")
    _write_raw_capture(tmp_path, "conv-c.md", "other-task", "2026-08-16T03:00:00Z")

    ctx = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id)
    assert ctx["pending_raw_count"] == 2
    relpaths = {e["relpath"] for e in ctx["pending_raws"]}
    assert relpaths == {"conv-a.md", "conv-b.md"}
    assert ctx["pending_raws_truncated"] is False
    # captured_at is surfaced for display.
    assert all(e["captured_at"] for e in ctx["pending_raws"])


def test_task_context_distilled_raws_not_counted(tmp_path):
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="注入任务")
    task_id = r["task"]["id"]

    _write_raw_capture(tmp_path, "conv-a.md", task_id, "2026-08-16T01:00:00Z", status="distilled")

    ctx = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id)
    assert ctx["pending_raw_count"] == 0
    assert ctx["pending_raws"] == []


def test_task_context_related_notes_carry_status(tmp_path):
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="注入任务")
    task_id = r["task"]["id"]

    from pathlib import Path

    notes_dir = Path(repo) / "repowiki" / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    (notes_dir / "draft-note.md").write_text(
        f'---\ntitle: "草稿笔记"\ntask_id: "{task_id}"\nstatus: draft\n---\n\nx', encoding="utf-8"
    )
    (notes_dir / "stable-note.md").write_text(
        f'---\ntitle: "稳定笔记"\ntask_id: "{task_id}"\nstatus: stable\n---\n\nx', encoding="utf-8"
    )

    ctx = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id)
    statuses = {n["relpath"]: n["status"] for n in ctx["related_notes"]}
    assert statuses == {"draft-note.md": "draft", "stable-note.md": "stable"}


# --------------------------------------------------------------------------- #
# P0: entry structuring (timestamp headings) + bounded memories reads
# (see docs/任务记忆存储与加载扩展性设计方案.md; ADR-0001)
# --------------------------------------------------------------------------- #


def test_add_task_memory_stamps_timestamp_heading(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEWIKI_USER", "alice")
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="打头任务")
    task_id = r["task"]["id"]

    _call(tm.handle_add_task_memory, output_dir=_od(repo), task_id=task_id, content="第一条记忆")
    _call(tm.handle_add_task_memory, output_dir=_od(repo), task_id=task_id, content="第二条记忆")

    from pathlib import Path

    # Per-user split storage: writes land in memories/<user_id>.md (multi-user
    # split design §4.2), NOT the legacy single file.
    text = (Path(repo) / "repowiki" / "tasks" / task_id / "memories" / "alice.md").read_text(
        encoding="utf-8"
    )
    headings = [ln for ln in text.splitlines() if ln.startswith("### ")]
    assert len(headings) == 2
    import re as _re

    assert all(_re.match(r"^### \d{4}-\d{2}-\d{2} \d{2}:\d{2}$", h) for h in headings)
    assert "第一条记忆" in text and "第二条记忆" in text


def test_append_direct_stamps_heading_and_tolerates_ghost(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.setenv("CODEWIKI_USER", "alice")
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="直写打头")
    task_id = r["task"]["id"]

    # Direct write (ADR-0002): timestamp-headed entries land immediately.
    written = tm.append_task_memories_direct(Path(_od(repo)), task_id, ["蒸馏出的任务进度", ""])
    assert written == 1
    text = (Path(repo) / "repowiki" / "tasks" / task_id / "memories" / "alice.md").read_text(
        encoding="utf-8"
    )
    assert text.startswith("### ")
    assert "蒸馏出的任务进度" in text

    # Ghost task_id tolerated: no write, no crash.
    assert tm.append_task_memories_direct(Path(_od(repo)), "ghost-task", ["x"]) == 0


def test_split_memories_three_formats():
    # Headed form: heading + multi-paragraph body stays one entry.
    headed = "### 2026-08-24 10:00\n\npara one\n\npara two\n\n### 2026-08-24 11:00\n\nsecond"
    assert len(tm._split_memories(headed)) == 2
    # Legacy form: blank-line separated paragraphs.
    legacy = "旧条目一\n\n旧条目二\n\n旧条目三"
    assert len(tm._split_memories(legacy)) == 3
    # Mixed (lazy-migration intermediate state): legacy block before first heading.
    mixed = "无头旧条目甲\n\n无头旧条目乙\n\n### 2026-08-24 10:00\n\n新条目"
    entries = tm._split_memories(mixed)
    assert len(entries) == 3
    assert entries[-1].startswith("### ")
    assert tm._split_memories("") == []


def test_get_task_context_bounded_memories(tmp_path):
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="截断任务")
    task_id = r["task"]["id"]

    for i in range(5):
        _call(tm.handle_add_task_memory, output_dir=_od(repo), task_id=task_id, content=f"记忆{i}")

    # Default (20) keeps everything.
    ctx = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id)
    assert ctx["memories_total"] == 5
    assert ctx["memories_truncated"] is False
    assert ctx["compaction_due"] is False
    assert "记忆4" in ctx["memories"]

    # max_memories=2 keeps only the most recent two entries.
    ctx2 = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id, max_memories=2)
    assert ctx2["memories_total"] == 5
    assert ctx2["memories_truncated"] is True
    assert "记忆4" in ctx2["memories"] and "记忆3" in ctx2["memories"]
    assert "记忆0" not in ctx2["memories"] and "记忆2" not in ctx2["memories"]

    # Invalid max_memories means no limit.
    ctx3 = _call(
        tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id, max_memories="bogus"
    )
    assert ctx3["memories_truncated"] is False


def test_get_task_bounded_memories_default_five(tmp_path):
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="详情截断")
    task_id = r["task"]["id"]

    for i in range(7):
        _call(tm.handle_add_task_memory, output_dir=_od(repo), task_id=task_id, content=f"记忆{i}")

    t = _call(tm.handle_get_task, output_dir=_od(repo), task_id=task_id)
    assert t["memories_total"] == 7
    assert t["memories_truncated"] is True
    assert "记忆6" in t["memories"] and "记忆2" in t["memories"]
    assert "记忆0" not in t["memories"]

    # Explicit larger value pages back through older entries.
    t2 = _call(tm.handle_get_task, output_dir=_od(repo), task_id=task_id, max_memories=50)
    assert t2["memories_truncated"] is False and t2["memories_total"] == 7


def test_legacy_memories_file_counts_by_paragraph(tmp_path):
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="存量回退")
    task_id = r["task"]["id"]

    from pathlib import Path

    mem = Path(repo) / "repowiki" / "tasks" / task_id / "memories.md"
    mem.parent.mkdir(parents=True, exist_ok=True)
    mem.write_text("旧一\n\n旧二\n\n旧三\n\n旧四", encoding="utf-8")

    ctx = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id, max_memories=2)
    assert ctx["memories_total"] == 4
    assert ctx["memories_truncated"] is True
    assert "旧四" in ctx["memories"] and "旧一" not in ctx["memories"]


def test_compaction_due_signal(tmp_path):
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="压缩信号")
    task_id = r["task"]["id"]

    from pathlib import Path

    mem = Path(repo) / "repowiki" / "tasks" / task_id / "memories.md"
    mem.parent.mkdir(parents=True, exist_ok=True)

    # Below thresholds: 40 entries exactly, small payload.
    mem.write_text("\n\n".join(f"条目{i}" for i in range(40)), encoding="utf-8")
    ctx = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id, max_memories=1)
    assert ctx["compaction_due"] is False

    # Count threshold: 41 entries.
    mem.write_text("\n\n".join(f"条目{i}" for i in range(41)), encoding="utf-8")
    ctx2 = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id, max_memories=1)
    assert ctx2["compaction_due"] is True

    # Byte threshold: 21 entries (beyond keep window) with oversized total payload.
    mem.write_text("\n\n".join(f"条目{i} " + "x" * 1200 for i in range(21)), encoding="utf-8")
    ctx3 = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id)
    assert ctx3["compaction_due"] is True

    # Oversized payload but entries within the keep window: compaction cannot
    # help (nothing to compress), so the signal stays off.
    mem.write_text("### 2026-08-24 10:00\n\n" + "x" * (24 * 1024 + 1), encoding="utf-8")
    ctx4 = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id)
    assert ctx4["compaction_due"] is False


# --------------------------------------------------------------------------- #
# P1: memory compaction (compact_task_memories, two-phase prepare/submit)
# (see docs/任务记忆存储与加载扩展性设计方案.md §5.2; ADR-0001)
# --------------------------------------------------------------------------- #


def _make_task_with_entries(tmp_path, title, n_entries, legacy=False):
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title=title)
    task_id = r["task"]["id"]
    if legacy:
        from pathlib import Path

        mem = Path(repo) / "repowiki" / "tasks" / task_id / "memories.md"
        mem.parent.mkdir(parents=True, exist_ok=True)
        mem.write_text("\n\n".join(f"旧条目{i}" for i in range(n_entries)), encoding="utf-8")
    else:
        for i in range(n_entries):
            _call(
                tm.handle_add_task_memory, output_dir=_od(repo), task_id=task_id, content=f"记忆{i}"
            )
    return repo, task_id


def test_compact_prepare_returns_entries_and_instruction(tmp_path):
    repo, task_id = _make_task_with_entries(tmp_path, "压缩准备", 41)

    p = _call(tm.handle_compact_task_memories, output_dir=_od(repo), task_id=task_id)
    assert p["ok"] is True and p["compaction_needed"] is True
    assert len(p["entries_to_compress"]) == 21  # 41 - keep 20
    assert all("记忆" in e for e in p["entries_to_compress"])
    assert p["existing_summary"] == ""
    assert p["summary_max_chars"] == tm._COMPACTION_SUMMARY_MAX_CHARS
    assert "submit" in p["instruction"]


def test_compact_prepare_noop_below_thresholds(tmp_path):
    repo, task_id = _make_task_with_entries(tmp_path, "压缩空转", 15)

    p = _call(tm.handle_compact_task_memories, output_dir=_od(repo), task_id=task_id)
    assert p["ok"] is True and p["compaction_needed"] is False
    assert "entries_to_compress" not in p


def test_compact_prepare_noop_when_within_keep_window(tmp_path):
    # 10 entries, oversized payload -> byte threshold hit but only 10 entries
    # (<= keep 20): compaction cannot help, must be a no-op.
    from pathlib import Path

    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="窗口内空转")
    task_id = r["task"]["id"]
    mem = Path(repo) / "repowiki" / "tasks" / task_id / "memories.md"
    mem.parent.mkdir(parents=True, exist_ok=True)
    mem.write_text("\n\n".join("x" * 3000 for _ in range(10)), encoding="utf-8")

    ctx = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id, max_memories=1)
    assert ctx["compaction_due"] is False
    p = _call(tm.handle_compact_task_memories, output_dir=_od(repo), task_id=task_id)
    assert p["compaction_needed"] is False


def test_compact_submit_rewrites_and_archives(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEWIKI_USER", "alice")
    repo, task_id = _make_task_with_entries(tmp_path, "压缩落盘", 45)

    p = _call(tm.handle_compact_task_memories, output_dir=_od(repo), task_id=task_id)
    assert len(p["entries_to_compress"]) == 25

    s = _call(
        tm.handle_compact_task_memories,
        output_dir=_od(repo),
        task_id=task_id,
        mode="submit",
        summary="早期记忆摘要：完成了 A、B，遗留 C 待办。",
    )
    assert s["ok"] is True and s["compressed"] == 25 and s["kept"] == 20
    assert s["archives"] == ["memories-archive/alice.md"]
    assert s["legacy_converged"] is False

    from pathlib import Path

    # File-domain compaction: the caller's own per-user file is rewritten.
    text = (
        Path(repo) / "repowiki" / "tasks" / task_id / "memories" / "alice.md"
    ).read_text(encoding="utf-8")
    assert text.startswith(tm._SUMMARY_HEADING)
    assert "早期记忆摘要" in text
    assert "memories-archive/alice.md，截至" in text and "共 25 条" in text
    # Keep window: entries 25..44 remain full-text.
    assert "记忆44" in text and "记忆25" in text
    assert "记忆24" not in text and "记忆0" not in text

    archive = (
        Path(repo) / "repowiki" / "tasks" / task_id / "memories-archive" / "alice.md"
    ).read_text(encoding="utf-8")
    # All 25 compressed originals preserved verbatim.
    for i in (0, 12, 24):
        assert f"记忆{i}" in archive

    # Bounded read after compaction: summary always kept + recent entries only.
    ctx = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id, max_memories=3)
    assert ctx["memories_total"] == 20
    assert ctx["memories_truncated"] is True
    assert tm._SUMMARY_HEADING in ctx["memories"]
    assert "记忆44" in ctx["memories"] and "记忆21" not in ctx["memories"]


def test_compact_submit_legacy_entries_get_synthetic_heading(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEWIKI_USER", "alice")
    repo, task_id = _make_task_with_entries(tmp_path, "压缩存量", 45, legacy=True)

    s = _call(
        tm.handle_compact_task_memories,
        output_dir=_od(repo),
        task_id=task_id,
        mode="submit",
        summary="存量压缩摘要。",
    )
    assert s["ok"] is True and s["compressed"] == 25
    assert s["archives"] == ["memories-archive/legacy.md"]
    assert s["legacy_converged"] is True  # legacy file converged into alice's

    from pathlib import Path

    archive = (
        Path(repo) / "repowiki" / "tasks" / task_id / "memories-archive" / "legacy.md"
    ).read_text(encoding="utf-8")
    assert archive.count("### 历史条目（存量格式，无时间戳）") == 25
    assert "旧条目0" in archive and "旧条目24" in archive

    # Legacy converges into the caller's own file: kept entries land there,
    # and the legacy single file is REMOVED (attribution now explicit).
    text = (
        Path(repo) / "repowiki" / "tasks" / task_id / "memories" / "alice.md"
    ).read_text(encoding="utf-8")
    assert "旧条目44" in text and "旧条目25" in text
    assert not (Path(repo) / "repowiki" / "tasks" / task_id / "memories.md").exists()


def test_compact_second_round_appends_archive_and_carries_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEWIKI_USER", "alice")
    repo, task_id = _make_task_with_entries(tmp_path, "二轮压缩", 45)

    _call(
        tm.handle_compact_task_memories,
        output_dir=_od(repo),
        task_id=task_id,
        mode="submit",
        summary="第一轮摘要。",
    )
    # 20 kept; add 25 more headed entries -> 45 again.
    for i in range(100, 125):
        _call(
            tm.handle_add_task_memory, output_dir=_od(repo), task_id=task_id, content=f"新记忆{i}"
        )

    p2 = _call(tm.handle_compact_task_memories, output_dir=_od(repo), task_id=task_id)
    assert p2["compaction_needed"] is True
    assert "第一轮摘要" in p2["existing_summary"]  # caller folds it into the new summary
    assert len(p2["entries_to_compress"]) == 25

    s2 = _call(
        tm.handle_compact_task_memories,
        output_dir=_od(repo),
        task_id=task_id,
        mode="submit",
        summary="第二轮摘要（含第一轮内容）。",
    )
    assert s2["ok"] is True and s2["compressed"] == 25

    from pathlib import Path

    archive = (
        Path(repo) / "repowiki" / "tasks" / task_id / "memories-archive" / "alice.md"
    ).read_text(encoding="utf-8")
    # Archive is append-only: round-1 originals (记忆0..24) AND round-2 (记忆25..44) present.
    assert "记忆0" in archive and "记忆44" in archive
    # Old summary replaced by the new one in the caller's own file.
    text = (
        Path(repo) / "repowiki" / "tasks" / task_id / "memories" / "alice.md"
    ).read_text(encoding="utf-8")
    assert "第二轮摘要" in text and "第一轮摘要" not in text
    assert "新记忆124" in text  # latest entries kept


def test_compact_submit_validations(tmp_path):
    repo, task_id = _make_task_with_entries(tmp_path, "压缩校验", 41)

    # Missing summary.
    r = _call(tm.handle_compact_task_memories, output_dir=_od(repo), task_id=task_id, mode="submit")
    assert "summary is required" in r["error"]
    # Oversized summary.
    r2 = _call(
        tm.handle_compact_task_memories,
        output_dir=_od(repo),
        task_id=task_id,
        mode="submit",
        summary="x" * 2049,
    )
    assert "exceeds" in r2["error"]
    # Invalid mode.
    r3 = _call(tm.handle_compact_task_memories, output_dir=_od(repo), task_id=task_id, mode="bogus")
    assert "mode must be" in r3["error"]
    # Unknown task.
    r4 = _call(tm.handle_compact_task_memories, output_dir=_od(repo), task_id="ghost-task")
    assert "does not exist" in r4["error"]


def test_compact_idempotent_after_compaction(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEWIKI_USER", "alice")
    repo, task_id = _make_task_with_entries(tmp_path, "压缩幂等", 41)

    _call(
        tm.handle_compact_task_memories,
        output_dir=_od(repo),
        task_id=task_id,
        mode="submit",
        summary="一次摘要。",
    )
    # After compaction: 20 kept entries -> below keep window + thresholds -> no-op.
    again = _call(tm.handle_compact_task_memories, output_dir=_od(repo), task_id=task_id)
    assert again["compaction_needed"] is False

    from pathlib import Path

    archive = (
        Path(repo) / "repowiki" / "tasks" / task_id / "memories-archive" / "alice.md"
    ).read_text(encoding="utf-8")
    # No duplicate archiving from the no-op round.
    assert archive.count("### ") == 21  # 21 compressed entries, archived once


# --------------------------------------------------------------------------- #
# Multi-user split: layered hot/warm loading + file-domain compaction
# (see docs/任务记忆多人协作分片设计方案.md §4.2-4.4, §6)
# --------------------------------------------------------------------------- #


def _write_user_mem(repo, task_id, owner, content):
    """Write a per-user memory file directly (simulates another teammate)."""
    from pathlib import Path

    p = Path(repo) / "repowiki" / "tasks" / task_id / "memories" / f"{owner}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_layered_loading_own_full_others_summary_plus_two(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEWIKI_USER", "alice")
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="分层加载")
    task_id = r["task"]["id"]

    for i in range(3):
        _call(tm.handle_add_task_memory, output_dir=_od(repo), task_id=task_id, content=f"我的记忆{i}")

    bob_text = (
        f"{tm._SUMMARY_HEADING}\n\nbob 的早期工作摘要。\n\n> 指针行。\n\n"
        "### 2026-08-20 09:00\n\nbob 条目一（较旧）\n\n"
        "### 2026-08-21 10:00\n\nbob 条目二\n\n"
        "### 2026-08-22 11:00\n\nbob 最新条目三"
    )
    _write_user_mem(repo, task_id, "bob", bob_text)

    ctx = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id)
    # Hot layer: all 3 of alice's entries.
    assert "我的记忆0" in ctx["memories"] and "我的记忆2" in ctx["memories"]
    # Warm layer: bob's summary + only the 2 most recent entries (Q9/Q11).
    assert tm._WARM_SECTION_HEADING in ctx["memories"]
    assert "bob 的早期工作摘要" in ctx["memories"]
    assert "bob 最新条目三" in ctx["memories"] and "bob 条目二" in ctx["memories"]
    assert "bob 条目一（较旧）" not in ctx["memories"]
    # totals count all files; truncation refers to the hot layer only.
    assert ctx["memories_total"] == 6
    assert ctx["memories_truncated"] is False


def test_get_task_warm_layer_summaries_only(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEWIKI_USER", "alice")
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="详情分层")
    task_id = r["task"]["id"]

    _call(tm.handle_add_task_memory, output_dir=_od(repo), task_id=task_id, content="我的记忆")
    _write_user_mem(
        repo,
        task_id,
        "bob",
        f"{tm._SUMMARY_HEADING}\n\nbob 摘要。\n\n### 2026-08-22 11:00\n\nbob 条目",
    )

    t = _call(tm.handle_get_task, output_dir=_od(repo), task_id=task_id)
    assert "我的记忆" in t["memories"]
    assert "bob 摘要" in t["memories"]
    # Summary view: other users' entries are NOT injected (Q9), no hints either.
    assert "bob 条目" not in t["memories"]
    assert "- @bob" not in t["memories"]


def test_warm_layer_budget_degrades_to_hints(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEWIKI_USER", "alice")
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="预算降级")
    task_id = r["task"]["id"]

    _call(tm.handle_add_task_memory, output_dir=_od(repo), task_id=task_id, content="我的记忆")
    big = "y" * (tm._WARM_ENTRY_BUDGET + 10)
    older = "### 2026-08-20 09:00\n\n" + big + "\n\n### 2026-08-22 11:00\n\nbob 最新内容"
    _write_user_mem(repo, task_id, "bob", older)

    ctx = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id)
    # Newest warm entry stays full; the oversized older one degrades to a
    # one-line hint (Q12): clue kept, bulk dropped, pointer to the live file.
    assert "bob 最新内容" in ctx["memories"]
    assert big not in ctx["memories"]
    assert "- @bob 08-20：" in ctx["memories"]
    assert "→ memories/bob.md" in ctx["memories"]


def test_legacy_file_is_hot_layer_single_user_zero_regression(tmp_path, monkeypatch):
    # Q10: legacy memories.md is HOT — a single-user legacy task renders exactly
    # as the pre-split reader did (byte-identical), no warm section appears.
    from pathlib import Path

    monkeypatch.setenv("CODEWIKI_USER", "alice")
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="存量零回归")
    task_id = r["task"]["id"]

    raw = "\n\n".join(f"### 2026-08-2{i} 10:00\n\n旧记忆{i}" for i in range(1, 4))
    mem = Path(repo) / "repowiki" / "tasks" / task_id / "memories.md"
    mem.parent.mkdir(parents=True, exist_ok=True)
    mem.write_text(raw, encoding="utf-8")

    ctx = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id)
    assert ctx["memories"] == raw
    assert tm._WARM_SECTION_HEADING not in ctx["memories"]


def test_hot_merge_own_and_legacy_chronological(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEWIKI_USER", "alice")
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="热层合并")
    task_id = r["task"]["id"]

    # Alice's own file holds the NEWEST entry; legacy holds an older one —
    # union-merged output must be chronological regardless of file order.
    _call(tm.handle_add_task_memory, output_dir=_od(repo), task_id=task_id, content="新记忆")
    from pathlib import Path

    mem = Path(repo) / "repowiki" / "tasks" / task_id / "memories.md"
    mem.write_text("### 2026-08-01 08:00\n\n旧记忆", encoding="utf-8")

    ctx = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id)
    assert ctx["memories"].index("旧记忆") < ctx["memories"].index("新记忆")
    assert ctx["memories_total"] == 2


def test_user_id_change_old_file_becomes_warm_layer(tmp_path, monkeypatch):
    # Q13: a renamed user keeps their old file visible as a warm (other) file —
    # information is not sunk; deep history stays reachable via the summary.
    monkeypatch.setenv("CODEWIKI_USER", "alice")
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="身份变更")
    task_id = r["task"]["id"]

    _call(tm.handle_add_task_memory, output_dir=_od(repo), task_id=task_id, content="alice 时的记忆")
    _write_user_mem(
        repo,
        task_id,
        "alice",
        "### 2026-08-20 09:00\n\nalice 旧条目",
    )

    monkeypatch.setenv("CODEWIKI_USER", "carol")
    ctx = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id)
    # alice's file is now warm: her entries enter as the 2 most recent, carol
    # has no own file so the hot layer is empty.
    assert "alice 旧条目" in ctx["memories"]
    assert tm._WARM_SECTION_HEADING in ctx["memories"]


def test_compaction_never_touches_other_users_files(tmp_path, monkeypatch):
    # Q6 invariant: the compactor may only rewrite its own file (+ legacy).
    monkeypatch.setenv("CODEWIKI_USER", "alice")
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="压缩不动他人")
    task_id = r["task"]["id"]

    for i in range(41):
        _call(tm.handle_add_task_memory, output_dir=_od(repo), task_id=task_id, content=f"记忆{i}")

    bob_file = _write_user_mem(repo, task_id, "bob", "### 2026-08-20 09:00\n\nbob 条目一")
    bob_before = bob_file.read_text(encoding="utf-8")

    p = _call(tm.handle_compact_task_memories, output_dir=_od(repo), task_id=task_id)
    # Other users' entries never enter the compaction unit.
    assert all("bob" not in e for e in p["entries_to_compress"])

    _call(
        tm.handle_compact_task_memories,
        output_dir=_od(repo),
        task_id=task_id,
        mode="submit",
        summary="摘要。",
    )
    assert bob_file.read_text(encoding="utf-8") == bob_before
    # bob's file is untouched AND stays out of alice's hot layer post-merge.
    ctx = _call(tm.handle_get_task_context, output_dir=_od(repo), task_id=task_id)
    assert ctx["memories_total"] == 21  # 20 kept + bob's 1


# --------------------------------------------------------------------------- #
# P1: .index.json as a rebuildable cache (multi-user split design §4.5)
# --------------------------------------------------------------------------- #


def test_index_rebuilt_when_teammate_task_merged_in(tmp_path):
    # Git merge dropped the index entry but kept the task directory: the next
    # read re-discovers the task from tasks/<id>/task.md and rewrites the index.
    from pathlib import Path

    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="索引丢失")
    task_id = r["task"]["id"]

    index = Path(repo) / "repowiki" / "tasks" / ".index.json"
    index.unlink()  # simulate the merge losing the index entirely

    lst = _call(tm.handle_list_tasks, output_dir=_od(repo))
    ids = [t["id"] for t in lst["tasks"]]
    assert task_id in ids
    # Index file rewritten with the rebuilt entry (title/status recovered).
    data = json.loads(index.read_text(encoding="utf-8"))
    assert any(t["id"] == task_id and t["title"] == "索引丢失" for t in data["tasks"])


def test_index_rebuilt_on_corrupt_json(tmp_path):
    from pathlib import Path

    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="索引损坏")
    task_id = r["task"]["id"]

    index = Path(repo) / "repowiki" / "tasks" / ".index.json"
    index.write_text("{not valid json", encoding="utf-8")

    got = _call(tm.handle_get_task, output_dir=_od(repo), task_id=task_id)
    assert got["ok"] is True  # corrupt index did not sink the task
    data = json.loads(index.read_text(encoding="utf-8"))
    assert any(t["id"] == task_id for t in data["tasks"])


def test_index_drops_entries_whose_dir_is_gone(tmp_path):
    # Teammate deleted their task and the merge kept OUR index copy: the
    # stale entry is dropped on the next read (directory = source of truth).
    import shutil
    from pathlib import Path

    repo = str(tmp_path)
    r1 = _call(tm.handle_create_task, output_dir=_od(repo), title="保留任务")
    r2 = _call(tm.handle_create_task, output_dir=_od(repo), title="他人删除")
    keep_id, gone_id = r1["task"]["id"], r2["task"]["id"]

    shutil.rmtree(Path(repo) / "repowiki" / "tasks" / gone_id)

    lst = _call(tm.handle_list_tasks, output_dir=_od(repo))
    ids = [t["id"] for t in lst["tasks"]]
    assert keep_id in ids and gone_id not in ids
    data = json.loads((Path(repo) / "repowiki" / "tasks" / ".index.json").read_text(encoding="utf-8"))
    assert gone_id not in [t["id"] for t in data["tasks"]]


def test_index_rebuild_idempotent_and_status_preserved(tmp_path):
    from pathlib import Path

    repo = str(tmp_path)
    r = _call(tm.handle_create_task, output_dir=_od(repo), title="重建幂等")
    task_id = r["task"]["id"]
    _call(tm.handle_complete_task, output_dir=_od(repo), task_id=task_id)

    lst1 = _call(tm.handle_list_tasks, output_dir=_od(repo))
    lst2 = _call(tm.handle_list_tasks, output_dir=_od(repo))
    assert lst1["tasks"] == lst2["tasks"]  # steady state: no rebuild churn
    entry = [t for t in lst1["tasks"] if t["id"] == task_id][0]
    assert entry["status"] == "completed"  # completed_at carried through rebuild paths

    # Force a rebuild (delete index) — status recovered from task.md frontmatter.
    (Path(repo) / "repowiki" / "tasks" / ".index.json").unlink()
    lst3 = _call(tm.handle_list_tasks, output_dir=_od(repo))
    entry3 = [t for t in lst3["tasks"] if t["id"] == task_id][0]
    assert entry3["status"] == "completed"
    assert entry3.get("completed_at")
