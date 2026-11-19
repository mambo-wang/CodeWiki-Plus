"""Tests for the provenance_backstop lint check (他山之石: TAM ontology borrow).

Covers the shared classifier's issue forms (missing / deprecated-without-
absorption / no-reason deprecated / unconfirmed draft note / soft-deleted),
absorption keyword discrimination (Chinese + English reject_reason), empty-
string filtering, unparseable-frontmatter skip, the notes/ basename fallback,
and the bidirectional scan (scenario source_notes forward + note backlinks
backward).  skill_lint delegation lives in test_skill_pages.py.

Fixture style follows test_consolidation_p2 / test_skill_pages: tmp_path
minimal repowiki → direct handle_lint_wiki calls.  conftest autouse pins zh.
"""

import json
from pathlib import Path

import yaml

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.wiki_lint import handle_lint_wiki


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _mk_repo(tmp_path: Path) -> tuple[str, Path]:
    repo = tmp_path / "repo"
    od = repo / "repowiki"
    (od / "notes").mkdir(parents=True)
    (od / "wiki" / "scenarios").mkdir(parents=True)
    return str(repo), od


def _write_note(
    od: Path,
    name: str,
    status: str = "stable",
    reason: str | None = None,
    body: str = "## 背景\nbody",
    meta: dict | None = None,
) -> str:
    fm: dict = {"type": "pitfall", "title": name, "status": status, "metadata": meta or {}}
    if reason is not None:
        fm["reject_reason"] = reason
    p = od / "notes" / f"{name}.md"
    p.write_text(
        "---\n" + yaml.safe_dump(fm, allow_unicode=True) + "---\n\n" + body + "\n",
        encoding="utf-8",
    )
    return f"notes/{name}.md"


def _write_scenario(od: Path, name: str, source_notes: list, body: str = "## 工作场景\nx") -> str:
    fm = {
        "type": "Scenario",
        "title": name,
        "status": "stable",
        "metadata": {"source_notes": source_notes},
    }
    p = od / "wiki" / "scenarios" / f"{name}.md"
    p.write_text(
        "---\n" + yaml.safe_dump(fm, allow_unicode=True) + "---\n\n" + body + "\n",
        encoding="utf-8",
    )
    return f"wiki/scenarios/{name}.md"


def _lint(repo: str, checks: list[str] | None = None) -> dict:
    store = SessionStore()
    return json.loads(
        handle_lint_wiki({"repo_path": repo, "checks": checks or ["provenance_backstop"]}, store)
    )


def _prov(repo: str) -> list[dict]:
    return [i for i in _lint(repo)["issues"] if i["check"] == "provenance_backstop"]


# --------------------------------------------------------------------------- #
# 1. forward scan: scenario source_notes
# --------------------------------------------------------------------------- #
def test_clean_provenance_passes_and_check_registered(tmp_path):
    repo, od = _mk_repo(tmp_path)
    ref = _write_note(od, "live-note")
    _write_scenario(od, "clean-scene", [ref])
    assert _prov(repo) == []
    assert "provenance_backstop" in _lint(repo, ["all"])["checks_run"]


def test_missing_target_warns(tmp_path):
    repo, od = _mk_repo(tmp_path)
    scen = _write_scenario(od, "broken-scene", ["notes/ghost.md"])
    issues = _prov(repo)
    assert len(issues) == 1
    assert issues[0]["severity"] == "warning"
    assert issues[0]["file"] == scen
    assert "溯源目标缺失" in issues[0]["message"]
    assert "notes/ghost.md" in issues[0]["message"]


def test_absorbed_retirement_does_not_flag(tmp_path):
    """deprecated + absorption keywords (zh/en) = normal lifecycle, not stale."""
    repo, od = _mk_repo(tmp_path)
    zh = _write_note(od, "absorbed-zh", status="deprecated", reason="聚合进场景：Redis 运维方法")
    en = _write_note(od, "absorbed-en", status="deprecated", reason="consolidated into Redis scene")
    _write_scenario(od, "absorb-scene", [zh, en])
    assert _prov(repo) == []


def test_deprecated_without_absorption_warns_with_reason(tmp_path):
    repo, od = _mk_repo(tmp_path)
    ref = _write_note(od, "invalidated", status="deprecated", reason="已被新方案取代")
    _write_scenario(od, "cite-invalidated", [ref])
    issues = _prov(repo)
    assert len(issues) == 1
    assert "未被吸收" in issues[0]["message"]
    assert "已被新方案取代" in issues[0]["message"]


def test_deprecated_no_reason_is_suspicious(tmp_path):
    repo, od = _mk_repo(tmp_path)
    ref = _write_note(od, "no-reason", status="deprecated")
    _write_scenario(od, "cite-no-reason", [ref])
    issues = _prov(repo)
    assert len(issues) == 1
    assert "未记录 reject_reason" in issues[0]["message"]


def test_draft_note_warns(tmp_path):
    repo, od = _mk_repo(tmp_path)
    ref = _write_note(od, "unconfirmed", status="draft")
    _write_scenario(od, "cite-draft", [ref])
    issues = _prov(repo)
    assert len(issues) == 1
    assert "draft" in issues[0]["message"]


def test_soft_deleted_source_warns(tmp_path):
    repo, od = _mk_repo(tmp_path)
    ref = _write_note(od, "deleted-note", body="[DELETED]")
    _write_scenario(od, "cite-deleted", [ref])
    issues = _prov(repo)
    assert len(issues) == 1
    assert "软删除" in issues[0]["message"]


def test_empty_refs_are_filtered(tmp_path):
    repo, od = _mk_repo(tmp_path)
    ref = _write_note(od, "ok-note")
    _write_scenario(od, "empty-refs", ["", "   ", ref])
    assert _prov(repo) == []


def test_unparseable_frontmatter_is_skipped(tmp_path):
    """okf_conformance §11 owns the parse error — no double report here."""
    repo, od = _mk_repo(tmp_path)
    bad = od / "wiki" / "scenarios" / "corrupt.md"
    bad.write_text("---\nfoo: [unclosed\n---\nbody\n", encoding="utf-8")
    broken_target = od / "notes" / "broken-fm.md"
    broken_target.write_text("---\nfoo: [unclosed\n---\nbody\n", encoding="utf-8")
    _write_scenario(od, "cite-broken", ["notes/broken-fm.md"])
    assert _prov(repo) == []


def test_basename_fallback_resolves(tmp_path):
    """Hand-written provenance often omits the notes/ directory."""
    repo, od = _mk_repo(tmp_path)
    _write_note(od, "bare-note")
    _write_scenario(od, "bare-ref", ["bare-note.md"])
    assert _prov(repo) == []


def test_draft_skill_target_is_normal_zone(tmp_path):
    """draft is the NORMAL state for skills — only draft NOTES are suspicious."""
    repo, od = _mk_repo(tmp_path)
    sk = od / "skills" / "draft-skill"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text(
        "---\nname: draft-skill\ntype: Skill\nstatus: draft\n---\nbody\n", encoding="utf-8"
    )
    _write_scenario(od, "cite-skill", ["skills/draft-skill/SKILL.md"])
    assert _prov(repo) == []


def test_soft_deleted_scenario_is_skipped(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_scenario(od, "pending-delete", ["notes/ghost.md"], body="[DELETED]")
    assert _prov(repo) == []


# --------------------------------------------------------------------------- #
# 2. backward scan: note backlinks (consolidated_into / compiled_into / promoted_to)
# --------------------------------------------------------------------------- #
def test_backlink_missing_warns_for_all_three_keys(tmp_path):
    repo, od = _mk_repo(tmp_path)
    rel = _write_note(
        od,
        "backlinked",
        meta={
            "consolidated_into": ["wiki/scenarios/ghost.md"],
            "compiled_into": ["skills/ghost/SKILL.md"],
            "promoted_to": ["wiki/queries/ghost.md"],
        },
    )
    issues = _prov(repo)
    assert len(issues) == 3
    assert all(i["file"] == rel and i["severity"] == "warning" for i in issues)
    keys = {
        k
        for i in issues
        for k in ("consolidated_into", "compiled_into", "promoted_to")
        if k in i["message"]
    }
    assert keys == {"consolidated_into", "compiled_into", "promoted_to"}
    assert all("回链目标缺失" in i["message"] for i in issues)


def test_backlink_existing_and_empty_pass(tmp_path):
    repo, od = _mk_repo(tmp_path)
    scen = _write_scenario(od, "real-scene", [])
    _write_note(od, "linked", meta={"consolidated_into": [scen], "compiled_into": ""})
    assert _prov(repo) == []
