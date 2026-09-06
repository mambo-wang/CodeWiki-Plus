"""Tests for B6 — evidence-drift signal feeding incremental decisions.

Covers:
  - ``collect_evidence_drift`` (shared collection point in tools/evidence.py):
    fresh / stale / missing / unresolvable matrix, legacy-page skip
  - ``_enrich_stale_evidence`` post-step: changed-code path enrichment with
    page-level aggregation + review-guiding hint; ``no_changes`` silence
  - ``_check_stale_evidence`` lint regression: thin wrapper keeps behavior
  - coexistence semantics: ``stale_pages`` (D2) and ``stale_evidence_pages``
    (B6) report the same page independently, no dedup
"""

from __future__ import annotations

from pathlib import Path

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.analysis import _enrich_stale_evidence
from codewiki.mcp.tools.evidence import collect_evidence_drift, handle_stamp_evidence
from codewiki.mcp.tools.wiki_lint import _check_stale_evidence

_CALC = "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n"


def _mk_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "calc.py").write_text(_CALC, encoding="utf-8")
    od = repo / "repowiki"
    (od / "wiki" / "modules").mkdir(parents=True)
    return repo, od


def _write_page(od: Path, name: str = "Calc.md") -> Path:
    p = od / "wiki" / "modules" / name
    p.write_text(
        "---\ntype: Architecture\ntitle: Calc\nstatus: stable\n---\n\nbody\n",
        encoding="utf-8",
    )
    return p


def _stamp(od: Path, repo: Path, page: str, resource: str) -> None:
    handle_stamp_evidence(
        {
            "page": page,
            "evidence": [{"resource": resource}],
            "output_dir": str(od),
            "repo_path": str(repo),
        },
        SessionStore(),
    )


# --------------------------------------------------------------------------- #
# collect_evidence_drift matrix
# --------------------------------------------------------------------------- #
def test_drift_matrix_fresh_stale_missing_unresolvable(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_page(od, "Fresh.md")
    _write_page(od, "Drift.md")
    _write_page(od, "Gone.md")
    _write_page(od, "Broken.md")
    (repo / "src" / "fresh.py").write_text(_CALC, encoding="utf-8")
    _stamp(od, repo, "wiki/modules/Fresh.md", "repo://src/fresh.py#L1-L2")
    _stamp(od, repo, "wiki/modules/Drift.md", "repo://src/calc.py#L1-L2")
    (repo / "src" / "gone.py").write_text("x = 1\n", encoding="utf-8")
    _stamp(od, repo, "wiki/modules/Gone.md", "repo://src/gone.py")
    _stamp(od, repo, "wiki/modules/Broken.md", "repo://src/calc.py#L1-L2")

    # fresh baseline
    assert collect_evidence_drift(od) == []

    # drift: source line region content changes
    (repo / "src" / "calc.py").write_text(
        "def add(a, b):\n    return a * b\n\ndef sub(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    # gone: referenced file removed
    (repo / "src" / "gone.py").unlink()
    # broken: rewrite one entry's resource to a malformed URI (keep hash)
    broken = od / "wiki" / "modules" / "Broken.md"
    text = broken.read_text(encoding="utf-8").replace(
        "resource: repo://src/calc.py#L1-L2", "resource: repo:/\\/\\/bad"
    )
    broken.write_text(text, encoding="utf-8")

    drift = {r["file"]: r for r in collect_evidence_drift(od)}
    assert set(drift) == {"wiki/modules/Drift.md", "wiki/modules/Gone.md", "wiki/modules/Broken.md"}
    assert drift["wiki/modules/Drift.md"]["status"] == "stale"
    assert drift["wiki/modules/Gone.md"]["status"] == "missing"
    assert drift["wiki/modules/Broken.md"]["status"] == "unresolvable"
    assert drift["wiki/modules/Drift.md"]["resource"] == "repo://src/calc.py#L1-L2"


def test_drift_skips_legacy_pages_without_content_hash(tmp_path):
    repo, od = _mk_repo(tmp_path)
    # Legacy page: sources WITHOUT content_hash must never trigger drift
    # (D1 progressive-enable semantics).
    p = od / "wiki" / "modules" / "Legacy.md"
    p.write_text(
        "---\ntype: Architecture\ntitle: Legacy\nsources:\n  - resource: repo://src/calc.py\n---\n\nbody\n",
        encoding="utf-8",
    )
    (repo / "src" / "calc.py").write_text("changed entirely\n", encoding="utf-8")
    assert collect_evidence_drift(od) == []


def test_drift_skips_scratch_and_raw_dirs(tmp_path):
    repo, od = _mk_repo(tmp_path)
    raw = od / "raw"
    raw.mkdir()
    (raw / "conv.md").write_text("---\ntitle: x\n---\n", encoding="utf-8")
    assert collect_evidence_drift(od) == []


# --------------------------------------------------------------------------- #
# _enrich_stale_evidence post-step
# --------------------------------------------------------------------------- #
def test_enrich_changed_path_aggregates_and_guides_review(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_page(od, "Calc.md")
    _stamp(od, repo, "wiki/modules/Calc.md", "repo://src/calc.py#L1-L2")
    (repo / "src" / "calc.py").write_text(
        "def add(a, b):\n    return a * b\n\ndef sub(a, b):\n    return a - b\n",
        encoding="utf-8",
    )

    changes = {"no_changes": False, "changed_files": ["src/calc.py"], "hint": "Only 1 module(s) need updating."}
    result = _enrich_stale_evidence(changes, od)

    assert result["stale_evidence_pages"] == {"wiki/modules/Calc.md": {"stale": 1}}
    assert "review" in result["hint"]
    assert "stamp_evidence" in result["hint"]  # guides re-stamp, not rewrite
    assert "lint_wiki(checks=['stale_evidence'])" in result["hint"]


def test_enrich_noop_when_evidence_fresh(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_page(od, "Calc.md")
    _stamp(od, repo, "wiki/modules/Calc.md", "repo://src/calc.py#L1-L2")

    changes = {"no_changes": False, "changed_files": ["README.md"]}
    result = _enrich_stale_evidence(changes, od)
    assert "stale_evidence_pages" not in result
    assert "hint" not in result  # unchanged hint


def test_enrich_silent_on_no_changes_path(tmp_path):
    """ADR-0005: the no_changes short-circuit stays silent by design."""
    repo, od = _mk_repo(tmp_path)
    _write_page(od, "Calc.md")
    _stamp(od, repo, "wiki/modules/Calc.md", "repo://src/calc.py#L1-L2")
    (repo / "src" / "calc.py").write_text("totally different\n", encoding="utf-8")

    changes = {"no_changes": True, "changed_files": []}
    result = _enrich_stale_evidence(changes, od)
    assert "stale_evidence_pages" not in result
    assert "hint" not in result


def test_enrich_handles_none_changes_info(tmp_path):
    repo, od = _mk_repo(tmp_path)
    assert _enrich_stale_evidence(None, od) is None


def test_enrich_coexists_with_stale_pages_no_dedup(tmp_path):
    """Same page may appear in both D2 stale_pages and B6 stale_evidence_pages."""
    repo, od = _mk_repo(tmp_path)
    _write_page(od, "Calc.md")
    _stamp(od, repo, "wiki/modules/Calc.md", "repo://src/calc.py#L1-L2")
    (repo / "src" / "calc.py").write_text(
        "def add(a, b):\n    return a * b\n\ndef sub(a, b):\n    return a - b\n",
        encoding="utf-8",
    )

    changes = {
        "no_changes": False,
        "changed_files": ["src/calc.py"],
        "stale_pages": ["wiki/modules/Calc.md"],  # D2 already flagged it
        "hint": "",
    }
    result = _enrich_stale_evidence(changes, od)
    # Both signals present, independently reported
    assert result["stale_pages"] == ["wiki/modules/Calc.md"]
    assert result["stale_evidence_pages"] == {"wiki/modules/Calc.md": {"stale": 1}}


# --------------------------------------------------------------------------- #
# lint thin-wrapper regression
# --------------------------------------------------------------------------- #
def test_lint_wrapper_keeps_issue_shape(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_page(od, "Calc.md")
    _stamp(od, repo, "wiki/modules/Calc.md", "repo://src/calc.py#L1-L2")

    assert _check_stale_evidence(od) == []

    (repo / "src" / "calc.py").write_text(
        "def add(a, b):\n    return a * b\n\ndef sub(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    issues = _check_stale_evidence(od)
    assert len(issues) == 1
    assert issues[0]["check"] == "stale_evidence"
    assert issues[0]["severity"] == "warning"
    assert "drifted" in issues[0]["message"]
    assert issues[0]["file"] == "wiki/modules/Calc.md"
    assert "stamp_evidence" in issues[0]["suggestion"]


# --------------------------------------------------------------------------- #
# colocated smoke (multi-root resolution)
# --------------------------------------------------------------------------- #
def test_colocated_workspace_resolves_via_fallback_root(tmp_path):
    """Colocated layout: code at output_dir.parent — evidence_roots fallback path."""
    repo, od = _mk_repo(tmp_path)
    _write_page(od, "Calc.md")
    _stamp(od, repo, "wiki/modules/Calc.md", "repo://src/calc.py#L1-L2")
    (repo / "src" / "calc.py").write_text("changed\n", encoding="utf-8")

    drift = collect_evidence_drift(od)
    assert len(drift) == 1
    assert drift[0]["status"] == "stale"
