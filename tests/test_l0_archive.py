"""Tests for the L0 archive (team-memory fusion, 链接优先、零索引 design).

Semantics under test (设计方案 §9):
- conversations that produced knowledge are archived to repowiki/conversations/
  after successful distillation (raw/ stays the pending staging queue);
- note source_ref links are repointed raw/ -> conversations/, including the
  multi-round conflict-submit case;
- drop_raw (submit argument or raw frontmatter) is the explicit delete path;
- archived conversations are NOT indexed (link-only discovery);
- query_wiki note results expose source_ref for on-demand tracing.
"""

import json
from pathlib import Path

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import distill_conversation as distill
from codewiki.src.config import RAW_DIR


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _write_raw(
    repo: str, cid: str, body: str = "user: hi\nassistant: hello", extra_fm: str = ""
) -> str:
    raw_dir = Path(repo) / "repowiki" / RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    p = raw_dir / f"conv-{cid}.md"
    p.write_text(
        "---\n"
        "type: conversation\n"
        f'conversation_id: "{cid}"\n'
        "status: pending\n"
        "origin: conversation\n" + extra_fm + "---\n\n" + body,
        encoding="utf-8",
    )
    return str(p)


def _submit(repo: str, distilled: dict, **extra_args):
    store = SessionStore()
    out = distill.handle_distill_conversation(
        {
            "output_dir": f"{repo}/repowiki",
            "mode": "submit",
            "distilled": distilled,
            **extra_args,
        },
        store,
    )
    data = json.loads(out)
    by_cid = {r["conversation_id"]: r for r in data.get("distilled", [])}
    return data, by_cid


def _note_source_ref(repo: str, note_file: str) -> str:
    """Read metadata.source_ref from a note file (yaml-parsed)."""
    import yaml

    text = (Path(repo) / "repowiki" / "notes" / note_file).read_text(encoding="utf-8")
    end = text.find("---", 3)
    fm = yaml.safe_load(text[3:end])
    return fm.get("metadata", {}).get("source_ref", "")


def _notes(repo: str):
    return sorted(p.name for p in (Path(repo) / "repowiki" / "notes").glob("*.md"))


# --------------------------------------------------------------------------- #
# 1. drop_raw — explicit privacy delete
# --------------------------------------------------------------------------- #
def test_drop_raw_argument_deletes(tmp_path):
    repo = str(tmp_path)
    cid = "privacy-arg"
    raw_path = _write_raw(repo, cid)
    _data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "privacy note",
                        "note_type": "general",
                        "content": "x",
                    }
                ]
            }
        },
        drop_raw=True,
    )
    r = by_cid[f"conv-{cid}"]
    assert r["deleted_raw"] is True
    assert r["archived_raw"] is None
    assert not Path(raw_path).exists()
    assert not (Path(repo) / "repowiki" / "conversations" / Path(raw_path).name).exists()


def test_drop_raw_frontmatter_deletes(tmp_path):
    repo = str(tmp_path)
    cid = "privacy-fm"
    raw_path = _write_raw(repo, cid, extra_fm="drop_raw: true\n")
    _data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "privacy fm note",
                        "note_type": "general",
                        "content": "x",
                    }
                ]
            }
        },
    )
    r = by_cid[f"conv-{cid}"]
    assert r["deleted_raw"] is True
    assert r["archived_raw"] is None
    assert not Path(raw_path).exists()


# --------------------------------------------------------------------------- #
# 2. source_ref repointing
# --------------------------------------------------------------------------- #
def test_source_ref_repointed_to_archive(tmp_path):
    repo = str(tmp_path)
    cid = "repoint-001"
    _write_raw(repo, cid)
    _data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "traceable note",
                        "note_type": "decision",
                        "content": "## Background\ntrace me",
                    }
                ]
            }
        },
    )
    r = by_cid[f"conv-{cid}"]
    assert r["archived_raw"] == f"conversations/conv-{cid}.md"
    note_file = _notes(repo)[0]
    ref = _note_source_ref(repo, note_file)
    assert ref == f"conversations/conv-{cid}.md", ref


def test_source_ref_repointed_across_conflict_rounds(tmp_path):
    """Round 1: one note ingested, one held as weak conflict. Round 2: the
    conflict resolves. Both notes' source_ref must end at conversations/."""
    repo = str(tmp_path)
    cid = "repoint-conflict"
    # Pre-existing note creating a weak title-similarity band for one draft
    store = SessionStore()
    from codewiki.mcp.tools.knowledge_loop import handle_ingest_note, handle_confirm_note

    r0 = json.loads(
        handle_ingest_note(
            {
                "output_dir": f"{repo}/repowiki",
                "title": "alpha beta gamma delta epsilon",
                "note_type": "pitfall",
                "content": "existing",
                "status": "draft",
            },
            store,
        )
    )
    handle_confirm_note(
        {
            "output_dir": f"{repo}/repowiki",
            "note_file": Path(r0["note_path"]).name,
        },
        store,
    )

    _write_raw(repo, cid)
    notes_json = {
        "notes": [
            {
                "title": "alpha beta gamma zeta eta",
                "note_type": "lesson",
                "content": "weak duplicate candidate",
            },
            {
                "title": "completely unrelated knowledge",
                "note_type": "decision",
                "content": "fresh knowledge",
            },
        ]
    }
    # Round 1
    _data, by_cid = _submit(repo, {cid: notes_json})
    r1 = by_cid[f"conv-{cid}"]
    assert r1["status"] == "conflicts_pending"
    assert (Path(repo) / "repowiki" / RAW_DIR / f"conv-{cid}.md").exists()  # raw kept

    # Round 2: resolve the conflict with store
    resolve_json = {
        "notes": [
            {
                "title": "alpha beta gamma zeta eta",
                "note_type": "lesson",
                "content": "weak duplicate candidate",
                "dedup_action": "store",
            },
        ]
    }
    _data, by_cid = _submit(repo, {cid: resolve_json})
    r2 = by_cid[f"conv-{cid}"]
    assert r2["status"] == "completed"
    assert r2["archived_raw"] == f"conversations/conv-{cid}.md"

    # Both distilled notes (round-1 fresh + round-2 stored) repointed
    refs = {_note_source_ref(repo, n) for n in _notes(repo) if n != Path(r0["note_path"]).name}
    assert refs == {f"conversations/conv-{cid}.md"}, refs


# --------------------------------------------------------------------------- #
# 3. zero-index: archives never enter search; links are the discovery path
# --------------------------------------------------------------------------- #
def test_archived_conversations_not_searchable(tmp_path):
    repo = str(tmp_path)
    cid = "noindex-001"
    marker = "独特标记词鲲鹏协议"
    _write_raw(repo, cid, body=f"user: 讨论{marker}\nassistant: 好的")
    _data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "noindex note",
                        "note_type": "general",
                        "content": f"## Background\n提到{marker}",
                    }
                ]
            }
        },
    )
    assert by_cid[f"conv-{cid}"]["archived_raw"]

    from codewiki.mcp.tools.wiki_search import build_full_index, search

    od = Path(repo) / "repowiki"
    build_full_index(od)
    hits = search(od, marker, max_results=10, score_threshold=0.0)
    files = {h["file"] for h in hits}
    # the note is found, the archived conversation is NOT
    assert any(f.startswith("notes/") for f in files)
    assert not any(f.startswith("conversations/") for f in files), files


def test_query_wiki_surfaces_source_ref(tmp_path):
    repo = str(tmp_path)
    cid = "surface-ref"
    _write_raw(repo, cid, body="user: 讨论缓存击穿\nassistant: 结论")
    _data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "缓存击穿防护决策",
                        "note_type": "decision",
                        "content": "## Background\n缓存击穿需要互斥锁",
                    }
                ]
            }
        },
    )
    assert by_cid[f"conv-{cid}"]["archived_raw"]

    from codewiki.mcp.tools.knowledge_loop import handle_query_wiki

    store = SessionStore()
    resp = json.loads(
        handle_query_wiki(
            {
                "output_dir": f"{repo}/repowiki",
                "query": "缓存击穿",
            },
            store,
        )
    )
    note_hits = [r for r in resp.get("results", []) if r.get("file", "").startswith("notes/")]
    assert note_hits, resp
    assert note_hits[0].get("source_ref") == f"conversations/conv-{cid}.md"


def test_conflict_pending_keeps_raw_unarchived(tmp_path):
    repo = str(tmp_path)
    cid = "pending-noarchive"
    store = SessionStore()
    from codewiki.mcp.tools.knowledge_loop import handle_ingest_note

    handle_ingest_note(
        {
            "output_dir": f"{repo}/repowiki",
            "title": "alpha beta gamma delta epsilon",
            "note_type": "pitfall",
            "content": "existing",
            "status": "draft",
        },
        store,
    )
    _write_raw(repo, cid)
    _data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "alpha beta gamma zeta eta",
                        "note_type": "lesson",
                        "content": "conflict",
                    },
                ]
            }
        },
    )
    r = by_cid[f"conv-{cid}"]
    assert r["status"] == "conflicts_pending"
    assert r["archived_raw"] is None
    assert (Path(repo) / "repowiki" / RAW_DIR / f"conv-{cid}.md").exists()
