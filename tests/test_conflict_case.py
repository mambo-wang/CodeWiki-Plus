"""Conflict case tools (ADR-0007, 冲突一等对象).

Coverage:
- flag_conflict: case creation, frontmatter shape, duplicate open-pair gate,
  input validation (2 distinct existing claimants, description required);
- adjudicate_conflict: keep_a/keep_b deprecate the loser via the reject_note
  primitive, coexist/reject touch neither claimant, resolved cases reject
  re-adjudication, resolution lands in the case frontmatter;
- load_open_conflicts + query_wiki annotation (main path and by_file);
- lint open_conflicts check: overdue window + dangling claimant.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from codewiki.mcp.tools.conflict_case import (
    handle_adjudicate_conflict,
    handle_flag_conflict,
    load_open_conflicts,
)
from codewiki.mcp.tools.note_query import handle_query_wiki
from codewiki.mcp.tools.wiki_lint import _check_open_conflicts
from codewiki.src.frontmatter import parse_frontmatter


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
        f'tags: ["x"]\nmetadata:\n  date: 2026-09-12\n  related_modules: ["conflict_case"]\n'
        f"status: {status}\n---\n\n正文：锁语义测试。\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture()
def wiki(tmp_path):
    od = tmp_path / "repowiki"
    (od / "notes").mkdir(parents=True)
    (od / ".meta").mkdir(parents=True)
    return od


@pytest.fixture()
def pair(wiki):
    a = _write_note(wiki / "notes", "2026-09-12-alpha.md", "锁不可重入导致死锁")
    b = _write_note(wiki / "notes", "2026-09-12-beta.md", "锁可重入不阻塞")
    return a, b


def _flag(wiki, a, b, description="两条笔记对锁的可重入性结论矛盾", **extra):
    args = {
        "repo_path": str(wiki.parent),
        "claimants": [a, b],
        "description": description,
    }
    args.update(extra)
    return json.loads(handle_flag_conflict(args, _StubStore()))


def _adjudicate(wiki, conflict_file, action, **extra):
    args = {
        "repo_path": str(wiki.parent),
        "conflict_file": conflict_file,
        "action": action,
    }
    args.update(extra)
    return json.loads(handle_adjudicate_conflict(args, _StubStore()))


def _fm_of(wiki, relpath):
    fm, body = parse_frontmatter((wiki / relpath).read_text(encoding="utf-8"))
    return fm, body


def test_flag_creates_open_case(wiki, pair):
    a, b = pair
    res = _flag(wiki, "notes/2026-09-12-alpha.md", "notes/2026-09-12-beta.md")
    assert res["status"] == "created"
    assert res["conflict_file"].startswith("conflicts/")
    assert (wiki / res["conflict_file"]).is_file()

    fm, body = _fm_of(wiki, res["conflict_file"])
    assert fm["type"] == "conflict"
    assert fm["status"] == "open"
    assert fm["claimants"] == [
        "notes/2026-09-12-alpha.md",
        "notes/2026-09-12-beta.md",
    ]
    assert fm["group_key"]
    assert "锁" in fm["title"]
    # case body links both claimants relatively (resolvable from conflicts/)
    assert "../notes/2026-09-12-alpha.md" in body


def test_flag_normalizes_bare_names_to_notes(wiki, pair):
    res = _flag(wiki, "2026-09-12-alpha.md", "notes/2026-09-12-beta.md")
    fm, _ = _fm_of(wiki, res["conflict_file"])
    assert fm["claimants"][0] == "notes/2026-09-12-alpha.md"


def test_flag_rejects_bad_input(wiki, pair):
    a, b = pair
    assert "error" in _flag(wiki, "notes/missing.md", "notes/2026-09-12-beta.md")
    assert "error" in _flag(wiki, a, a)  # same claimant twice
    assert "error" in _flag(
        wiki, "notes/2026-09-12-alpha.md", "notes/2026-09-12-beta.md", description="  "
    )
    assert "error" in _flag(wiki, "notes/2026-09-12-alpha.md", ["not", "two", "strings"])


def test_flag_duplicate_open_pair_returns_existing(wiki, pair):
    first = _flag(wiki, "notes/2026-09-12-alpha.md", "notes/2026-09-12-beta.md")
    # reversed order is still the same pair
    second = _flag(wiki, "notes/2026-09-12-beta.md", "notes/2026-09-12-alpha.md")
    assert second["status"] == "exists"
    assert second["conflict_file"] == first["conflict_file"]


def test_adjudicate_keep_a_deprecates_loser(wiki, pair):
    res = _flag(wiki, "notes/2026-09-12-alpha.md", "notes/2026-09-12-beta.md")
    out = _adjudicate(wiki, res["conflict_file"], "keep_a", reason="alpha 有源码证据")
    assert out["status"] == "resolved"
    assert out["deprecated"] == ["notes/2026-09-12-beta.md"]

    fm, body = _fm_of(wiki, res["conflict_file"])
    assert fm["status"] == "resolved"
    assert fm["resolution"] == "keep_a"
    assert fm["reason"] == "alpha 有源码证据"
    assert fm["resolved_by"]
    assert fm["resolved_at"]
    # regression lock: the closing fence must stay followed by a newline —
    # otherwise the lenient regex can swallow the body into the frontmatter
    # and still "pass" by accident (found during implementation).
    assert body.startswith("# ")
    assert "裁决记录" in body
    # the human-readable header must not still claim "open" (review finding)
    assert "open（未裁决）" not in body
    assert "resolved（已裁决）" in body

    loser_fm, _ = _fm_of(wiki, "notes/2026-09-12-beta.md")
    assert loser_fm["status"] == "deprecated"
    assert "keep_a" in str(loser_fm.get("reject_reason", ""))
    winner_fm, _ = _fm_of(wiki, "notes/2026-09-12-alpha.md")
    assert winner_fm["status"] == "stable"


def test_adjudicate_keep_b_mirror(wiki, pair):
    res = _flag(wiki, "notes/2026-09-12-alpha.md", "notes/2026-09-12-beta.md")
    out = _adjudicate(wiki, res["conflict_file"], "keep_b")
    assert out["deprecated"] == ["notes/2026-09-12-alpha.md"]
    fm, _ = _fm_of(wiki, "notes/2026-09-12-alpha.md")
    assert fm["status"] == "deprecated"


def test_adjudicate_coexist_and_reject_touch_neither(wiki, pair):
    for action in ("coexist", "reject"):
        res = _flag(wiki, "notes/2026-09-12-alpha.md", "notes/2026-09-12-beta.md")
        out = _adjudicate(wiki, res["conflict_file"], action)
        assert out["deprecated"] == []
        for name in ("2026-09-12-alpha.md", "2026-09-12-beta.md"):
            fm, _ = _fm_of(wiki, f"notes/{name}")
            assert fm["status"] == "stable"


def test_adjudicate_rejects_resolved_case(wiki, pair):
    res = _flag(wiki, "notes/2026-09-12-alpha.md", "notes/2026-09-12-beta.md")
    _adjudicate(wiki, res["conflict_file"], "coexist")
    out = _adjudicate(wiki, res["conflict_file"], "keep_a")
    assert "error" in out


def test_adjudicate_validates_action_and_file(wiki, pair):
    res = _flag(wiki, "notes/2026-09-12-alpha.md", "notes/2026-09-12-beta.md")
    assert "error" in _adjudicate(wiki, res["conflict_file"], "nuke")
    assert "error" in _adjudicate(wiki, "conflicts/missing.md", "keep_a")


def test_load_open_conflicts_and_query_annotation(wiki, pair):
    a, b = pair
    res = _flag(wiki, "notes/2026-09-12-alpha.md", "notes/2026-09-12-beta.md")

    mapping = load_open_conflicts(wiki)
    assert mapping["notes/2026-09-12-alpha.md"]["file"] == res["conflict_file"]
    assert mapping["notes/2026-09-12-beta.md"]["file"] == res["conflict_file"]

    # query_wiki main path: results hitting a claimant carry the marker.
    args = {
        "repo_path": str(wiki.parent),
        "query": "锁 语义",
        "max_results": 10,
    }
    payload = json.loads(handle_query_wiki(args, _StubStore()))
    claimant_results = [r for r in payload["results"] if "open_conflict" in r]
    assert claimant_results, "claimant results must carry the open_conflict marker"
    for r in claimant_results:
        assert r["open_conflict"] == res["conflict_file"]
    assert "OPEN" in payload["context_package"]

    # after adjudication the marker disappears
    _adjudicate(wiki, res["conflict_file"], "coexist")
    payload2 = json.loads(handle_query_wiki(args, _StubStore()))
    assert not any("open_conflict" in r for r in payload2["results"])


def test_query_wiki_by_file_annotation(wiki, pair):
    a, b = pair
    res = _flag(wiki, "notes/2026-09-12-alpha.md", "notes/2026-09-12-beta.md")
    args = {
        "repo_path": str(wiki.parent),
        "by_file": "codewiki/mcp/tools/conflict_case.py",
        "query": "锁",
    }
    payload = json.loads(handle_query_wiki(args, _StubStore()))
    timeline = (
        payload["file_knowledge"]["timeline"]
        if "timeline" in payload.get("file_knowledge", {})
        else payload.get("timeline", [])
    )
    # alpha matches by related_modules — it MUST be in the timeline and,
    # as a claimant of an open case, carry the marker (hard assertion, not
    # a conditional: review flagged the original as potentially vacuous).
    alpha_entries = [e for e in timeline if e.get("file") == "notes/2026-09-12-alpha.md"]
    assert alpha_entries, "by_file timeline must return the matching note"
    assert alpha_entries[0].get("open_conflict") == res["conflict_file"]


def test_lint_open_conflicts_checks(wiki, pair):
    res = _flag(wiki, "notes/2026-09-12-alpha.md", "notes/2026-09-12-beta.md")
    case_rel = res["conflict_file"]

    # fresh case: no issues
    assert _check_open_conflicts(wiki) == []

    # backdate the case beyond the 14-day window
    fm, body = _fm_of(wiki, case_rel)
    fm["created"] = (date.today() - timedelta(days=20)).isoformat()
    import yaml

    (wiki / case_rel).write_text(
        f"---\n{yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)}---\n{body}",
        encoding="utf-8",
    )
    issues = _check_open_conflicts(wiki)
    assert any(i["check"] == "open_conflicts" and "days" in i["message"] for i in issues)

    # dangling claimant
    (wiki / "notes/2026-09-12-beta.md").unlink()
    issues = _check_open_conflicts(wiki)
    assert any("Claimant not found" in i["message"] for i in issues)

    # resolved cases never produce issues
    _adjudicate(wiki, case_rel, "reject")
    assert _check_open_conflicts(wiki) == []


def test_lint_generic_checks_skip_conflicts_dir(wiki, pair):
    from codewiki.mcp.tools.wiki_lint import (
        _check_broken_links,
        _check_no_outlinks,
        _check_stale_refs,
    )

    _flag(wiki, "notes/2026-09-12-alpha.md", "notes/2026-09-12-beta.md")
    # case has outgoing links and lives outside wiki/ — without the exclusion
    # it would surface in no_outlinks (info) / broken_links scans
    assert not any(i["file"].startswith("conflicts/") for i in _check_no_outlinks(wiki))
    assert not any(i["file"].startswith("conflicts/") for i in _check_broken_links(wiki))
    assert not any(i["file"].startswith("conflicts/") for i in _check_stale_refs(wiki, None))
