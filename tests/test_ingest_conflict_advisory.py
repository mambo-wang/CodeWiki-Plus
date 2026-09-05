"""ingest_note conflict advisory (write-path dedup awareness).

Background this guards: ``ingest_note`` only de-duplicates by
``<date>-<slug>.md`` path, so a corrected conclusion ingested days later
under a different title silently coexists with the refuted note — and the
older note, richer in keywords, can out-rank the correction in BM25. The
advisory makes the collision visible at write time; retiring or merging the
old note stays the caller's decision (no silent overwrite/merge).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codewiki.mcp.tools.knowledge_loop import handle_ingest_note


class _StubStore:
    def find_or_restore(self, repo_path):
        return None

    def get(self, session_id):
        return None


def _write_note(notes_dir: Path, filename: str, title: str, status: str = "stable") -> Path:
    notes_dir.mkdir(parents=True, exist_ok=True)
    p = notes_dir / filename
    p.write_text(
        f"---\ntype: pitfall\ntitle: {json.dumps(title, ensure_ascii=False)}\n"
        f"tags: [\"x\"]\nmetadata:\n  date: 2026-08-27\n  related_modules: [\"cache\"]\n"
        f"status: {status}\n---\n\n写入后必须删除 key，否则读到旧值。\n",
        encoding="utf-8",
    )
    return p


def _ingest(output_dir: Path, title: str, **extra):
    args = {
        "output_dir": str(output_dir),
        "title": title,
        "content": "写入后删除 key，读多写少场景走 TTL。",
        "note_type": "general",
    }
    args.update(extra)
    return json.loads(handle_ingest_note(args, _StubStore()))


@pytest.fixture()
def wiki(tmp_path):
    od = tmp_path / "repowiki"
    (od / "notes").mkdir(parents=True)
    (od / ".meta").mkdir(parents=True)
    return od


def _posix_files(cands):
    return [Path(c["file"]).as_posix() for c in (cands or [])]


def test_similar_note_is_reported_with_retire_hint(wiki):
    _write_note(wiki / "notes", "2026-08-27-a.md", "缓存失效策略：写入后删除 key")

    res = _ingest(wiki, "缓存失效策略：写入后删除 cache key")

    assert res["status"] == "ingested"
    assert "notes/2026-08-27-a.md" in _posix_files(res.get("similar_notes", []))
    assert "deprecated" in res["hint"]


def test_unrelated_note_stays_silent(wiki):
    _write_note(wiki / "notes", "2026-08-27-a.md", "构建产物目录应在 .gitignore 中排除")

    res = _ingest(wiki, "缓存失效策略：写入后删除 cache key")

    assert res["status"] == "ingested"
    assert "similar_notes" not in res
    assert "deprecated" not in res["hint"]


def test_detect_conflicts_false_skips_the_scan(wiki):
    _write_note(wiki / "notes", "2026-08-27-a.md", "缓存失效策略：写入后删除 key")

    res = _ingest(wiki, "缓存失效策略：写入后删除 cache key", detect_conflicts=False)

    assert res["status"] == "ingested"
    assert "similar_notes" not in res


def test_retired_notes_are_not_conflict_candidates(wiki):
    _write_note(
        wiki / "notes",
        "2026-08-27-a.md",
        "缓存失效策略：写入后删除 key",
        status="deprecated",
    )

    res = _ingest(wiki, "缓存失效策略：写入后删除 cache key")

    assert "similar_notes" not in res


def test_advisory_failure_never_blocks_the_write(wiki, monkeypatch):
    from codewiki.mcp.tools import distill_conversation as distill

    def _boom(*args, **kwargs):
        raise RuntimeError("index exploded")

    monkeypatch.setattr(distill, "_find_conflict_candidates", _boom)
    _write_note(wiki / "notes", "2026-08-27-a.md", "缓存失效策略：写入后删除 key")

    res = _ingest(wiki, "缓存失效策略：写入后删除 cache key")

    assert res["status"] == "ingested"
    assert Path(res["note_path"]).is_file()


# --------------------------------------------------------------------------- #
# Regression: the distillation pipeline still sees the WEAK band only — the
# strong band remains _find_existing_note's job (store/skip/update/merge).
# --------------------------------------------------------------------------- #
def test_distill_weak_band_still_excludes_strong(wiki):
    from codewiki.mcp.tools.distill_conversation import _find_conflict_candidates

    _write_note(wiki / "notes", "2026-08-27-a.md", "缓存失效策略：写入后删除 key")

    # Default (weak band): the strong title-sim signal must NOT surface a
    # candidate flagged strong — a BM25 recall hit may still appear, which is
    # fine for the distillation pipeline (it is only reached after
    # _find_existing_note confirmed there is no strong duplicate).
    weak = _find_conflict_candidates("缓存失效策略：写入后删除 cache key", "body", "general", wiki)
    assert all(c.get("strong") is not True for c in weak)
    assert all(c.get("signal") != "title_sim" for c in weak)

    # include_strong=True: the strong band is surfaced as an advisory.
    strong = _find_conflict_candidates(
        "缓存失效策略：写入后删除 cache key",
        "body",
        "general",
        wiki,
        include_strong=True,
    )
    assert "notes/2026-08-27-a.md" in _posix_files(strong)
    assert any(c.get("strong") is True for c in strong)
