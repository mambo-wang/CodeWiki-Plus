"""Tests for distill_conversation raw-file cleanup behaviour.

When a conversation yields no reusable knowledge (no_knowledge), its raw file
in repowiki/raw/ must be cleaned up so the transient staging area doesn't
accumulate noise. Only keep_raw (explicit opt-in) preserves the raw file.
"""
import json
from pathlib import Path

import pytest

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import distill_conversation as distill
from codewiki.src.config import RAW_DIR


def _write_raw(repo: str, cid: str, body: str = "user: hi\nassistant: hello",
               keep_raw: bool = False) -> str:
    from pathlib import Path
    raw_dir = Path(repo) / "repowiki" / RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    p = raw_dir / f"conv-{cid}.md"
    extra = "keep_raw: true\n" if keep_raw else ""
    p.write_text(
        "---\n"
        "type: conversation\n"
        f"conversation_id: \"{cid}\"\n"
        "status: pending\n"
        "origin: conversation\n"
        + extra +
        "---\n\n" + body,
        encoding="utf-8",
    )
    return str(p)


def _submit(repo: str, distilled: dict):
    store = SessionStore()
    out = distill.handle_distill_conversation({
        "output_dir": f"{repo}/repowiki",
        "mode": "submit",
        "distilled": distilled,
    }, store)
    data = json.loads(out)
    # submit aggregates per-conversation results under data["distilled"], keyed
    # by the full filename stem (e.g. "conv-<id>").
    by_cid = {r["conversation_id"]: r for r in data.get("distilled", [])}
    return data, by_cid


def _cid(cid: str) -> str:
    return f"conv-{cid}"


def test_no_knowledge_raw_is_cleaned_up(tmp_path):
    repo = str(tmp_path)
    cid = "no-knowledge-001"
    raw_path = _write_raw(repo, cid)

    _data, by_cid = _submit(repo, {cid: {"notes": []}})

    r = by_cid[_cid(cid)]
    assert r["status"] == "no_knowledge"
    # raw file should be gone
    import os
    assert not os.path.exists(raw_path)
    assert r["deleted_raw"] is True


def test_keep_raw_preserves_no_knowledge_file(tmp_path):
    """L0 archive semantics: keep_raw retains even no-knowledge conversations
    — archived to conversations/ instead of lingering in raw/ (staging queue)."""
    repo = str(tmp_path)
    cid = "keep-raw-001"
    raw_path = _write_raw(repo, cid, keep_raw=True)

    _data, by_cid = _submit(repo, {cid: {"notes": []}})

    r = by_cid[_cid(cid)]
    assert r["status"] == "no_knowledge"
    import os
    assert not os.path.exists(raw_path)  # left the raw/ staging queue...
    assert r["deleted_raw"] is False
    # ...but was preserved via the L0 archive
    archived = Path(repo) / "repowiki" / "conversations" / Path(raw_path).name
    assert archived.exists()
    assert r["archived_raw"] == f"conversations/{Path(raw_path).name}"


def test_produced_knowledge_archives_raw(tmp_path):
    """L0 archive semantics (changed from delete): conversations that produced
    knowledge are archived to conversations/ for provenance."""
    repo = str(tmp_path)
    cid = "produced-001"
    raw_path = _write_raw(repo, cid)

    _data, by_cid = _submit(repo, {cid: {"notes": [{
        "title": "sample note",
        "note_type": "pitfall",
        "content": "## background\n\nsomething reusable",
        "related_modules": ["x"],
        "tags": ["t"],
    }]}})

    r = by_cid[_cid(cid)]
    assert r["status"] == "completed"
    import os
    assert not os.path.exists(raw_path)  # left raw/ staging queue
    assert r["deleted_raw"] is False
    assert r["archived_raw"] == f"conversations/{Path(raw_path).name}"
    archived = Path(repo) / "repowiki" / r["archived_raw"]
    assert archived.exists()
    assert "status: distilled" in archived.read_text(encoding="utf-8")
    assert r["notes_created"] == 1


# --------------------------------------------------------------------------- #
# sessionStart catch-up: task_id scoping
# --------------------------------------------------------------------------- #

def _write_raw_tasked(repo: str, cid: str, task_id: str) -> str:
    """Write a pending raw capture bound to a task (frontmatter carries task_id)."""
    from pathlib import Path
    raw_dir = Path(repo) / "repowiki" / RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    p = raw_dir / f"conv-{cid}.md"
    p.write_text(
        "---\n"
        "type: conversation\n"
        f"conversation_id: \"{cid}\"\n"
        "status: pending\n"
        "origin: conversation\n"
        f"task_id: \"{task_id}\"\n"
        "captured_at: \"2026-08-16T00:00:00Z\"\n"
        "---\n\nuser: hi\nassistant: hello",
        encoding="utf-8",
    )
    return str(p)


def _write_raw_index(repo: str, entries: list) -> None:
    """Write raw/.index.json in the shape capture_conversation maintains."""
    from pathlib import Path
    raw_dir = Path(repo) / "repowiki" / RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / ".index.json").write_text(
        json.dumps({"files": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _prepare(repo: str, task_id: str | None) -> dict:
    store = SessionStore()
    args = {"output_dir": f"{repo}/repowiki", "mode": "prepare"}
    if task_id is not None:
        args["task_id"] = task_id
    return json.loads(distill.handle_distill_conversation(args, store))


class TestDistillTaskIdFilter:
    def test_prepare_scopes_to_task_via_index(self, tmp_path):
        repo = str(tmp_path)
        _write_raw_tasked(repo, "a", "task-one")
        _write_raw_tasked(repo, "b", "task-two")
        _write_raw_tasked(repo, "c", "")  # unbound capture
        _write_raw_index(repo, [
            {"relpath": "conv-a.md", "content_hash": "h1", "source_session": "s1",
             "status": "pending", "task_id": "task-one"},
            {"relpath": "conv-b.md", "content_hash": "h2", "source_session": "s2",
             "status": "pending", "task_id": "task-two"},
            {"relpath": "conv-c.md", "content_hash": "h3", "source_session": "s3",
             "status": "pending", "task_id": ""},
        ])

        data = _prepare(repo, "task-one")
        assert data["status"] == "prepared"
        assert [c["conversation_id"] for c in data["captures"]] == ["conv-a"]

    def test_prepare_no_match_is_noop(self, tmp_path):
        repo = str(tmp_path)
        _write_raw_tasked(repo, "a", "task-one")
        _write_raw_index(repo, [
            {"relpath": "conv-a.md", "content_hash": "h1", "source_session": "s1",
             "status": "pending", "task_id": "task-one"},
        ])

        data = _prepare(repo, "some-other-task")
        assert data["status"] == "noop"
        assert data["task_id"] == "some-other-task"

    def test_filter_falls_back_to_frontmatter_without_index(self, tmp_path):
        repo = str(tmp_path)
        _write_raw_tasked(repo, "a", "task-one")
        _write_raw_tasked(repo, "b", "task-two")
        # No .index.json — membership must come from frontmatter.

        data = _prepare(repo, "task-two")
        assert data["status"] == "prepared"
        assert [c["conversation_id"] for c in data["captures"]] == ["conv-b"]

    def test_submit_ignores_other_tasks_extractions(self, tmp_path):
        repo = str(tmp_path)
        _write_raw_tasked(repo, "a", "task-one")
        _write_raw_tasked(repo, "b", "task-two")
        _write_raw_index(repo, [
            {"relpath": "conv-a.md", "content_hash": "h1", "source_session": "s1",
             "status": "pending", "task_id": "task-one"},
            {"relpath": "conv-b.md", "content_hash": "h2", "source_session": "s2",
             "status": "pending", "task_id": "task-two"},
        ])

        store = SessionStore()
        out = distill.handle_distill_conversation({
            "output_dir": f"{repo}/repowiki",
            "mode": "submit",
            "task_id": "task-one",
            # Extraction for conv-b (another task) must be ignored; conv-a has
            # no extraction yet, so nothing should be processed.
            "distilled": {"conv-b": {"notes": []}},
        }, store)
        data = json.loads(out)
        # conv-a is in scope but has no extraction yet → missing_result (raw
        # untouched); conv-b (another task) must not be processed at all.
        assert [r["conversation_id"] for r in data["distilled"]] == ["conv-a"]
        assert data["distilled"][0]["status"] == "missing_result"
        import os
        assert os.path.exists(f"{repo}/repowiki/{RAW_DIR}/conv-b.md")
        assert "status: pending" in Path(f"{repo}/repowiki/{RAW_DIR}/conv-b.md").read_text(encoding="utf-8")
