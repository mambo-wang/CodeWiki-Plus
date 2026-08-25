"""Tests for the low_adoption lint check (P1 B-line).

Covers docs/知识飞轮增强设计方案-P1三项.md §3 acceptance criteria:
  - hot (hit >= 5) + zero adoption + recently hit -> warning with counts
  - adopted >= 1 -> not flagged
  - hit < min_hits -> not flagged
  - last_hit older than recent_days -> not flagged (stale_notes territory)
  - cold-start guard: no adoption_events table / zero adoptions bundle-wide
    -> the whole check silently skips
  - schema.yaml conventions.usage_ranking.low_adoption config override works
  - registry lint_wiki checks enum stays in sync (MCP validation pitfall)
  - draft notes are out of scope
  - full dispatch (checks=['all']) surfaces low_adoption in the output
"""
from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.wiki_lint import _check_low_adoption, handle_lint_wiki


# --------------------------------------------------------------------------- #
# Helpers (fixture style follows tests/test_freshness.py)
# --------------------------------------------------------------------------- #
def _mk_wiki(tmp_path, low_adoption=None) -> Path:
    od = tmp_path / "repowiki"
    od.mkdir(parents=True, exist_ok=True)
    (od / "notes").mkdir(exist_ok=True)
    conv: dict = {}
    if low_adoption is not None:
        conv["usage_ranking"] = {"low_adoption": low_adoption}
    (od / "schema.yaml").write_text(
        yaml.safe_dump({"conventions": conv}), encoding="utf-8"
    )
    return od


def _write_note(od: Path, name: str, *, status="stable", title="T",
                ntype="pitfall") -> Path:
    fm = {"type": ntype, "title": title, "status": status}
    p = od / "notes" / name
    p.write_text(
        "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
        + "---\n\nbody\n",
        encoding="utf-8",
    )
    return p


def _append_events(od: Path, events: list) -> None:
    """Append events to the tester's stream (helpers must not clobber
    each other's writes — write_telemetry rewrites the whole file)."""
    from tests.telemetry_seed import write_telemetry
    from codewiki.mcp.tools import telemetry as _tel
    existing = []
    p = Path(od) / ".meta" / _tel.TELEMETRY_DIRNAME / "tester.jsonl"
    if p.exists():
        import json as _json
        existing = [
            _json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
    write_telemetry(od, "tester", existing + events)


def _touch(od: Path, rel_path: str, hit_count: int, last_hit: str) -> None:
    """Seed a hit event (T2: telemetry jsonl replaces the stats table)."""
    _append_events(od, [
        {"t": "hit", "doc": rel_path, "at": last_hit, "n": hit_count},
    ])


def _adopt(od: Path, doc_path: str, count: int = 1) -> None:
    """Record *count* adoption events (distinct capture keys; T2 jsonl)."""
    _append_events(od, [
        {"t": "adopted", "doc": doc_path,
         "at": datetime.now().isoformat(timespec="seconds"),
         "key": f"tester/sess-{i}"}
        for i in range(count)
    ])


def _adopted(issues) -> list:
    return [i for i in issues if i["check"] == "low_adoption"]


TODAY = datetime.now()
RECENT = (TODAY - timedelta(days=5)).strftime("%Y-%m-%d")
OLD = (TODAY - timedelta(days=90)).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# 1. Core judgment
# --------------------------------------------------------------------------- #
def test_hot_zero_adoption_warns(tmp_path):
    od = _mk_wiki(tmp_path)
    _write_note(od, "hot.md", title="Port Conflict Fix")
    _touch(od, "notes/hot.md", hit_count=7, last_hit=RECENT)
    # A global adoption elsewhere proves the adoption signal is in use
    # (cold-start guard must not fire) without adopting hot.md itself.
    _adopt(od, "notes/other.md")

    issues = _check_low_adoption(od)
    assert len(issues) == 1
    issue = issues[0]
    assert issue["check"] == "low_adoption"
    assert issue["severity"] == "warning"
    assert issue["file"] == "notes/hot.md"
    # message must carry title, hit count and adopted count
    assert "Port Conflict Fix" in issue["message"]
    assert "7 times" in issue["message"]
    assert "adopted 0" in issue["message"]
    # suggestion must point at a more actionable rewrite (distill/edit flow)
    assert "distill_conversation" in issue["suggestion"]
    assert "edit_doc_file" in issue["suggestion"]


def test_adopted_note_not_flagged(tmp_path):
    od = _mk_wiki(tmp_path)
    _write_note(od, "used.md")
    _touch(od, "notes/used.md", hit_count=7, last_hit=RECENT)
    _adopt(od, "notes/used.md", count=1)
    assert _adopted(_check_low_adoption(od)) == []


def test_below_min_hits_not_flagged(tmp_path):
    od = _mk_wiki(tmp_path)
    _write_note(od, "warm.md")
    _touch(od, "notes/warm.md", hit_count=4, last_hit=RECENT)  # < 5
    _adopt(od, "notes/other.md")
    assert _adopted(_check_low_adoption(od)) == []


def test_stale_last_hit_not_flagged(tmp_path):
    # "was hot, now dead" belongs to stale_notes — not low_adoption
    od = _mk_wiki(tmp_path)
    _write_note(od, "dead.md")
    _touch(od, "notes/dead.md", hit_count=20, last_hit=OLD)  # 90 days ago
    _adopt(od, "notes/other.md")
    assert _adopted(_check_low_adoption(od)) == []


# --------------------------------------------------------------------------- #
# 2. Cold-start guard
# --------------------------------------------------------------------------- #
def test_no_adoption_table_skips(tmp_path):
    od = _mk_wiki(tmp_path)
    _write_note(od, "hot.md")
    _touch(od, "notes/hot.md", hit_count=20, last_hit=RECENT)
    # hits exist but no adoption events anywhere (T2: no adopted lines)
    assert _check_low_adoption(od) == []


def test_empty_adoption_table_skips(tmp_path):
    od = _mk_wiki(tmp_path)
    _write_note(od, "hot.md")
    _touch(od, "notes/hot.md", hit_count=20, last_hit=RECENT)
    # an empty telemetry file exists (bundle-wide zero adoption)
    from tests.telemetry_seed import write_telemetry
    write_telemetry(od, "tester", [])
    assert _check_low_adoption(od) == []


# --------------------------------------------------------------------------- #
# 3. Config precedence (schema.yaml conventions.usage_ranking.low_adoption)
# --------------------------------------------------------------------------- #
def test_schema_config_min_hits_override(tmp_path):
    od = _mk_wiki(tmp_path, low_adoption={"min_hits": 2})
    _write_note(od, "hot.md")
    _touch(od, "notes/hot.md", hit_count=3, last_hit=RECENT)  # < default 5
    _adopt(od, "notes/other.md")
    issues = _adopted(_check_low_adoption(od))
    assert len(issues) == 1
    assert issues[0]["file"] == "notes/hot.md"


# --------------------------------------------------------------------------- #
# 4. Scope: only stable/confirmed notes
# --------------------------------------------------------------------------- #
def test_draft_note_out_of_scope(tmp_path):
    od = _mk_wiki(tmp_path)
    _write_note(od, "draft.md", status="draft")
    _write_note(od, "legacy.md", status="confirmed")  # legacy vocabulary counts
    _touch(od, "notes/draft.md", hit_count=20, last_hit=RECENT)
    _touch(od, "notes/legacy.md", hit_count=20, last_hit=RECENT)
    _adopt(od, "notes/other.md")
    files = [i["file"] for i in _adopted(_check_low_adoption(od))]
    assert files == ["notes/legacy.md"]


# --------------------------------------------------------------------------- #
# 5. Registry sync + dispatch integration
# --------------------------------------------------------------------------- #
def test_registry_enum_contains_low_adoption():
    from codewiki.mcp.registry import REGISTRY

    tool = REGISTRY["lint_wiki"]
    schema = tool.schema.inputSchema  # ToolDef exposes .schema.inputSchema
    enum = schema["properties"]["checks"]["items"]["enum"]
    assert "low_adoption" in enum

    # handler_path must resolve (importlib) to a callable handler
    module_path, _, func_name = tool.handler_path.partition(":")
    module = importlib.import_module(module_path)
    handler = getattr(module, func_name)
    assert callable(handler)


def test_dispatch_all_surfaces_low_adoption(tmp_path):
    od = _mk_wiki(tmp_path)
    _write_note(od, "hot.md", title="Hot Note")
    _touch(od, "notes/hot.md", hit_count=6, last_hit=RECENT)
    _adopt(od, "notes/other.md")

    store = SessionStore()
    resp = json.loads(handle_lint_wiki(
        {"output_dir": str(od), "checks": ["all"]}, store))
    issues = _adopted(resp.get("issues", []))
    assert len(issues) == 1
    assert issues[0]["severity"] == "warning"
    assert issues[0]["file"] == "notes/hot.md"
    assert "Hot Note" in issues[0]["message"]
