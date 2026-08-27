"""Tests for P1 distillation quality enhancements (team-memory fusion 阶段二).

Covers docs/团队记忆融合-L2场景聚合与L3-Doctrine设计方案.md §4.1/§4.2:

1. priority gate      — notes with priority < 70 are deterministically dropped;
                        priority >= 90 maps to severity=high, 70-89 to medium.
2. scene label        — distilled 'scene' lands in the note's metadata block.
3. two-stage dedup    — strong duplicates keep legacy suppress semantics;
                        weak conflicts are held (conflicts_pending, raw kept)
                        until the agent re-submits with a dedup_action:
                        store / skip / update / merge.
"""

import json
from pathlib import Path

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import distill_conversation as distill
from codewiki.src.config import RAW_DIR


# --------------------------------------------------------------------------- #
# Helpers (same conventions as test_distill_cleanup.py)
# --------------------------------------------------------------------------- #
def _write_raw(repo: str, cid: str, body: str = "user: hi\nassistant: hello") -> str:
    raw_dir = Path(repo) / "repowiki" / RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    p = raw_dir / f"conv-{cid}.md"
    p.write_text(
        "---\n"
        "type: conversation\n"
        f'conversation_id: "{cid}"\n'
        "status: pending\n"
        "origin: conversation\n"
        "---\n\n" + body,
        encoding="utf-8",
    )
    return str(p)


def _write_note(
    repo: str, filename: str, title: str, note_type: str = "pitfall", body: str = "existing body"
) -> str:
    """Create a pre-existing note with unquoted frontmatter title (dedup target)."""
    notes_dir = Path(repo) / "repowiki" / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    p = notes_dir / filename
    p.write_text(
        f"---\ntype: {note_type}\ntitle: {title}\nstatus: stable\n---\n\n" + body + "\n",
        encoding="utf-8",
    )
    return f"notes/{filename}"


def _submit(repo: str, distilled: dict):
    store = SessionStore()
    out = distill.handle_distill_conversation(
        {
            "output_dir": f"{repo}/repowiki",
            "mode": "submit",
            "distilled": distilled,
        },
        store,
    )
    data = json.loads(out)
    by_cid = {r["conversation_id"]: r for r in data.get("distilled", [])}
    return data, by_cid


def _notes_of_type(repo: str, note_type: str):
    notes_dir = Path(repo) / "repowiki" / "notes"
    if not notes_dir.is_dir():
        return []
    out = []
    for p in notes_dir.glob("*.md"):
        text = p.read_text(encoding="utf-8")
        if f"type: {note_type}" in text.split("---", 2)[1]:
            out.append(p)
    return out


# --------------------------------------------------------------------------- #
# 0. unit: priority parsing
# --------------------------------------------------------------------------- #
def test_parse_priority_clamps_and_rejects_invalid():
    assert distill._parse_priority(None) is None
    assert distill._parse_priority(True) is None  # bool is not a priority
    assert distill._parse_priority("abc") is None
    assert distill._parse_priority(75) == 75
    assert distill._parse_priority("82") == 82
    assert distill._parse_priority(150) == 100
    assert distill._parse_priority(-5) == 0


def test_prompt_contains_p1_disciplines_and_fields():
    p = distill._DISTILL_SYSTEM
    assert "EXTRACTION DISCIPLINES" in p
    assert "Accurate attribution" in p
    assert '"priority": 85' in p
    assert '"scene":' in p


# --------------------------------------------------------------------------- #
# 1. priority gate
# --------------------------------------------------------------------------- #
def test_low_priority_note_is_dropped(tmp_path):
    repo = str(tmp_path)
    cid = "prio-low"
    _write_raw(repo, cid)
    _data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "Trivial formatting tweak",
                        "note_type": "general",
                        "priority": 50,
                        "content": "low value content",
                    }
                ]
            }
        },
    )
    res = by_cid[f"conv-{cid}"]
    assert res["status"] == "no_knowledge" or res["status"] == "completed"
    entry = res["notes"][0]
    assert entry["status"] == "low_priority"
    assert entry["priority"] == 50
    # nothing landed in notes/
    assert list((Path(repo) / "repowiki" / "notes").glob("*.md")) == []


def test_priority_maps_to_severity(tmp_path):
    repo = str(tmp_path)
    cid = "prio-high"
    _write_raw(repo, cid)
    _data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "Never delete production data without backup",
                        "note_type": "pitfall",
                        "priority": 95,
                        "content": "## Root cause\ndata loss risk",
                    },
                    {
                        "title": "Prefer incremental index rebuild",
                        "note_type": "decision",
                        "priority": 75,
                        "content": "## Decision\nincremental rebuild",
                    },
                ]
            }
        },
    )
    res = by_cid[f"conv-{cid}"]
    assert res["status"] == "completed"
    highs = _notes_of_type(repo, "pitfall")
    meds = _notes_of_type(repo, "decision")
    assert len(highs) == 1 and "severity: high" in highs[0].read_text(encoding="utf-8")
    assert len(meds) == 1 and "severity: medium" in meds[0].read_text(encoding="utf-8")


def test_note_without_priority_ingests_without_severity(tmp_path):
    repo = str(tmp_path)
    cid = "prio-none"
    _write_raw(repo, cid)
    _data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "Legacy note has no priority field",
                        "note_type": "general",
                        "content": "backward compatible",
                    }
                ]
            }
        },
    )
    res = by_cid[f"conv-{cid}"]
    assert res["notes"][0]["status"] in ("ingested", "draft", "already_exists")
    notes = list((Path(repo) / "repowiki" / "notes").glob("*.md"))
    assert len(notes) == 1
    assert "severity:" not in notes[0].read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 2. scene label
# --------------------------------------------------------------------------- #
def test_scene_written_to_metadata(tmp_path):
    repo = str(tmp_path)
    cid = "scene-001"
    _write_raw(repo, cid)
    _data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "BM25 threshold tuning for short notes",
                        "note_type": "decision",
                        "priority": 80,
                        "scene": "围绕检索质量调优",
                        "content": "## Decision\nlower threshold",
                    }
                ]
            }
        },
    )
    res = by_cid[f"conv-{cid}"]
    assert res["status"] == "completed"
    notes = list((Path(repo) / "repowiki" / "notes").glob("*.md"))
    assert len(notes) == 1
    text = notes[0].read_text(encoding="utf-8")
    assert "scene:" in text and "围绕检索质量调优" in text


# --------------------------------------------------------------------------- #
# 3. two-stage dedup: strong duplicate keeps legacy semantics
# --------------------------------------------------------------------------- #
def test_strong_duplicate_still_suppressed(tmp_path):
    repo = str(tmp_path)
    cid = "strong-dup"
    _write_raw(repo, cid)
    # identical title + same type => Jaccard 1.0, strong duplicate
    _write_note(
        repo, "2026-01-01-redis-pool.md", "Redis connection pool timeout", note_type="pitfall"
    )
    _data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "Redis connection pool timeout",
                        "note_type": "pitfall",
                        "priority": 85,
                        "content": "dup content",
                    }
                ]
            }
        },
    )
    res = by_cid[f"conv-{cid}"]
    entry = res["notes"][0]
    assert entry["status"] == "suppressed"
    assert entry.get("duplicate_of", "").replace("\\", "/").startswith("notes/")
    # raw cleaned up (no pending conflicts)
    assert not (Path(repo) / "repowiki" / RAW_DIR / f"conv-{cid}.md").exists()


# --------------------------------------------------------------------------- #
# 4. weak conflict: held for agent adjudication, raw retained
# --------------------------------------------------------------------------- #
def _weak_conflict_setup(repo: str, cid: str):
    """Existing note shares 3/7 title tokens (sim≈0.43, weak band, diff type)."""
    _write_raw(repo, cid)
    return _write_note(
        repo, "2026-01-01-alpha.md", "alpha beta gamma delta epsilon", note_type="pitfall"
    )


def test_weak_conflict_holds_and_retains_raw(tmp_path):
    repo = str(tmp_path)
    cid = "weak-conflict"
    _weak_conflict_setup(repo, cid)
    data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "alpha beta gamma zeta eta",  # 3/7 ≈ 0.43, different type
                        "note_type": "lesson",
                        "priority": 85,
                        "content": "new knowledge, maybe overlapping",
                    }
                ]
            }
        },
    )
    res = by_cid[f"conv-{cid}"]
    assert res["status"] == "conflicts_pending"
    entry = res["notes"][0]
    assert entry["status"] == "conflict"
    assert entry["candidates"], "candidates must be reported for adjudication"
    assert data.get("conflicts_pending") == 1
    assert "conflict_next" in res
    # note NOT ingested, raw RETAINED (second submit must stay possible)
    assert _notes_of_type(repo, "lesson") == []
    raw = Path(repo) / "repowiki" / RAW_DIR / f"conv-{cid}.md"
    assert raw.exists()
    assert "status: distilled" not in raw.read_text(encoding="utf-8")


def test_conflict_resolved_with_store(tmp_path):
    repo = str(tmp_path)
    cid = "resolve-store"
    _weak_conflict_setup(repo, cid)
    _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "alpha beta gamma zeta eta",
                        "note_type": "lesson",
                        "content": "genuinely new",
                    }
                ]
            }
        },
    )
    # second pass: agent adjudicates 'store'
    data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "alpha beta gamma zeta eta",
                        "note_type": "lesson",
                        "content": "genuinely new",
                        "dedup_action": "store",
                    }
                ]
            }
        },
    )
    res = by_cid[f"conv-{cid}"]
    assert res["status"] == "completed"
    assert len(_notes_of_type(repo, "lesson")) == 1
    # everything resolved → raw cleaned up
    assert not (Path(repo) / "repowiki" / RAW_DIR / f"conv-{cid}.md").exists()


def test_conflict_resolved_with_skip(tmp_path):
    repo = str(tmp_path)
    cid = "resolve-skip"
    _weak_conflict_setup(repo, cid)
    _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "alpha beta gamma zeta eta",
                        "note_type": "lesson",
                        "content": "maybe dup",
                    }
                ]
            }
        },
    )
    _data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "alpha beta gamma zeta eta",
                        "note_type": "lesson",
                        "content": "maybe dup",
                        "dedup_action": "skip",
                    }
                ]
            }
        },
    )
    res = by_cid[f"conv-{cid}"]
    assert res["notes"][0]["status"] == "skipped"
    assert _notes_of_type(repo, "lesson") == []
    assert not (Path(repo) / "repowiki" / RAW_DIR / f"conv-{cid}.md").exists()


def test_conflict_resolved_with_update_replaces_body(tmp_path):
    repo = str(tmp_path)
    cid = "resolve-update"
    target = _weak_conflict_setup(repo, cid)
    _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "alpha beta gamma zeta eta",
                        "note_type": "lesson",
                        "content": "maybe dup",
                    }
                ]
            }
        },
    )
    _data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "alpha beta gamma zeta eta",
                        "note_type": "lesson",
                        "content": "NEW SUPERSEDING BODY",
                        "dedup_action": "update",
                        "target": target,
                    }
                ]
            }
        },
    )
    res = by_cid[f"conv-{cid}"]
    assert res["notes"][0]["status"] == "updated"
    text = (Path(repo) / "repowiki" / target).read_text(encoding="utf-8")
    assert "NEW SUPERSEDING BODY" in text
    assert "existing body" not in text
    # frontmatter (type) preserved
    assert "type: pitfall" in text
    # provenance accumulated
    assert "source_conversations" in text
    # no extra note created
    assert _notes_of_type(repo, "lesson") == []


def test_conflict_resolved_with_merge_appends_section(tmp_path):
    repo = str(tmp_path)
    cid = "resolve-merge"
    target = _weak_conflict_setup(repo, cid)
    _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "alpha beta gamma zeta eta",
                        "note_type": "lesson",
                        "content": "complementary knowledge",
                    }
                ]
            }
        },
    )
    _data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "alpha beta gamma zeta eta",
                        "note_type": "lesson",
                        "content": "complementary knowledge",
                        "dedup_action": "merge",
                        "target": target,
                    }
                ]
            }
        },
    )
    res = by_cid[f"conv-{cid}"]
    assert res["notes"][0]["status"] == "merged"
    text = (Path(repo) / "repowiki" / target).read_text(encoding="utf-8")
    # original body kept, new section appended
    assert "existing body" in text
    assert "## alpha beta gamma zeta eta" in text
    assert "complementary knowledge" in text
    assert _notes_of_type(repo, "lesson") == []


def test_update_without_target_reports_error(tmp_path):
    repo = str(tmp_path)
    cid = "resolve-no-target"
    _weak_conflict_setup(repo, cid)
    _data, by_cid = _submit(
        repo,
        {
            cid: {
                "notes": [
                    {
                        "title": "alpha beta gamma zeta eta",
                        "note_type": "lesson",
                        "content": "x",
                        "dedup_action": "update",
                    }
                ]
            }
        },
    )
    res = by_cid[f"conv-{cid}"]
    assert res["notes"][0]["status"] == "target_required"
