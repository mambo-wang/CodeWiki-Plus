"""Tests for P0 evidence anchoring (repo:// content-hash code evidence).

Covers:
  - pure helpers: resource parse, region/file hashing, entry verification
  - stamp_evidence: idempotent sources merge onto a page's frontmatter
  - stale_evidence lint: drifted code -> warning, disappeared file -> warning
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from codewiki.mcp.session import SessionState, SessionStore
from codewiki.mcp.tools.doc_writer import _inject_evidence
from codewiki.mcp.tools.evidence import append_evidence_block, handle_stamp_evidence
from codewiki.mcp.tools.wiki_lint import _check_stale_evidence, handle_lint_wiki
from codewiki.src.be.dependency_analyzer.models.core import Node
from codewiki.src.evidence import (
    compute_file_hash,
    compute_region_hash,
    make_entry,
    parse_resource,
    resource_for,
    verify_entry,
)

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


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def test_parse_resource_with_and_without_range():
    assert parse_resource("repo://src/calc.py#L1-L2") == ("src/calc.py", 1, 2)
    assert parse_resource("repo://src/calc.py") == ("src/calc.py", 0, 0)
    assert parse_resource("repo://a/b.py#L10") == ("a/b.py", 10, 10)
    assert parse_resource("not-a-uri") is None
    assert parse_resource("https://x/y") is None


def test_region_and_file_hash(tmp_path):
    p = tmp_path / "calc.py"
    p.write_text(_CALC, encoding="utf-8")
    region = compute_region_hash(p, 1, 2)
    assert region.startswith("sha256:")
    assert region == compute_region_hash(p, 1, 2)
    assert compute_file_hash(p).startswith("sha256:")
    assert compute_file_hash(p) != region


def test_resource_for_and_make_entry():
    assert resource_for("src/calc.py", 1, 2) == "repo://src/calc.py#L1-L2"
    entry = make_entry("src/calc.py", 1, 2, "sha256:abc")
    assert entry == {
        "id": "repo://src/calc.py#L1-L2",
        "resource": "repo://src/calc.py#L1-L2",
        "content_hash": "sha256:abc",
    }
    # Whole-file evidence: no #L range.
    file_entry = make_entry("src/calc.py", 0, 0, "sha256:def")
    assert file_entry["resource"] == "repo://src/calc.py"


def test_verify_entry_status(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "calc.py").write_text(_CALC, encoding="utf-8")

    entry = make_entry("src/calc.py", 1, 2, compute_region_hash(repo / "src" / "calc.py", 1, 2))
    assert verify_entry(entry, repo) == "ok"

    (repo / "src" / "calc.py").write_text(
        "def add(a, b):\n    return a + b + 1\n", encoding="utf-8"
    )
    assert verify_entry(entry, repo) == "stale"

    (repo / "src" / "calc.py").unlink()
    assert verify_entry(entry, repo) == "missing"

    assert (
        verify_entry({"resource": "repo://x#L1-L2", "content_hash": "sha256:z"}, repo) == "missing"
    )
    assert verify_entry({"resource": "nope", "content_hash": "sha256:z"}, repo) == "unresolvable"


# --------------------------------------------------------------------------- #
# stamp_evidence integration
# --------------------------------------------------------------------------- #
def test_stamp_evidence_idempotent(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_page(od)
    store = SessionStore()

    args = {
        "page": "wiki/modules/Calc.md",
        "evidence": [{"resource": "repo://src/calc.py#L1-L2"}],
        "output_dir": str(od),
        "repo_path": str(repo),
    }
    res = json.loads(handle_stamp_evidence(args, store))
    assert res["stamped"]["new"] == 1

    # Idempotent: same hash, no new entry, no update.
    res2 = json.loads(handle_stamp_evidence(args, store))
    assert res2["stamped"]["new"] == 0
    assert res2["stamped"]["updated"] == 0

    # Only one sources entry survives.
    import yaml

    text = (od / "wiki" / "modules" / "Calc.md").read_text(encoding="utf-8")
    fm = yaml.safe_load(text[3 : text.find("---", 3)])
    sources = fm["sources"]
    assert len(sources) == 1
    assert sources[0]["resource"] == "repo://src/calc.py#L1-L2"
    assert sources[0]["content_hash"].startswith("sha256:")


def test_stamp_whole_file_evidence(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_page(od)
    store = SessionStore()
    args = {
        "page": "wiki/modules/Calc.md",
        "evidence": [{"resource": "repo://src/calc.py"}],
        "output_dir": str(od),
        "repo_path": str(repo),
    }
    res = json.loads(handle_stamp_evidence(args, store))
    assert res["stamped"]["new"] == 1

    import yaml

    text = (od / "wiki" / "modules" / "Calc.md").read_text(encoding="utf-8")
    fm = yaml.safe_load(text[3 : text.find("---", 3)])
    assert fm["sources"][0]["resource"] == "repo://src/calc.py"
    assert _check_stale_evidence(od) == []

    (repo / "src" / "calc.py").write_text("changed\n", encoding="utf-8")
    issues = _check_stale_evidence(od)
    assert len(issues) == 1 and "drifted" in issues[0]["message"]


def test_stamp_evidence_rejects_bad_resource(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_page(od)
    store = SessionStore()
    args = {
        "page": "wiki/modules/Calc.md",
        "evidence": [{"resource": "repo://src/missing.py#L1-L2"}],
        "output_dir": str(od),
        "repo_path": str(repo),
    }
    res = json.loads(handle_stamp_evidence(args, store))
    assert "error" in res
    assert res["skipped"][0]["reason"].startswith("file not found")


# --------------------------------------------------------------------------- #
# stale_evidence lint
# --------------------------------------------------------------------------- #
def test_stale_evidence_detects_drift_and_missing(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_page(od)
    store = SessionStore()
    args = {
        "page": "wiki/modules/Calc.md",
        "evidence": [{"resource": "repo://src/calc.py#L1-L2"}],
        "output_dir": str(od),
        "repo_path": str(repo),
    }
    handle_stamp_evidence(args, store)

    assert _check_stale_evidence(od) == []  # fresh

    (repo / "src" / "calc.py").write_text(
        "def add(a, b):\n    return a + b + 1\n", encoding="utf-8"
    )
    issues = _check_stale_evidence(od)
    assert len(issues) == 1
    assert issues[0]["check"] == "stale_evidence"
    assert "drifted" in issues[0]["message"]

    (repo / "src" / "calc.py").unlink()
    issues = _check_stale_evidence(od)
    assert len(issues) == 1
    assert "disappeared" in issues[0]["message"]


def test_lint_wiki_dispatches_stale_evidence(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_page(od)
    store = SessionStore()
    args = {
        "page": "wiki/modules/Calc.md",
        "evidence": [{"resource": "repo://src/calc.py#L1-L2"}],
        "output_dir": str(od),
        "repo_path": str(repo),
    }
    handle_stamp_evidence(args, store)
    (repo / "src" / "calc.py").write_text("changed\n", encoding="utf-8")

    res = json.loads(handle_lint_wiki({"output_dir": str(od), "checks": ["stale_evidence"]}, store))
    assert res["checks_run"] == ["stale_evidence"]
    assert res["total_issues"] == 1
    assert res["issues"][0]["check"] == "stale_evidence"
    assert "drifted" in res["issues"][0]["message"]


# --------------------------------------------------------------------------- #
# Option B: auto-stamp evidence during write_doc_file
# --------------------------------------------------------------------------- #
def _session_for_evidence(tmp_path: Path, *, auto_evidence: bool) -> SessionState:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "calc.py").write_text(_CALC, encoding="utf-8")
    od = repo / "repowiki"
    (od / "wiki" / "modules").mkdir(parents=True)
    (od / "schema.yaml").write_text(
        yaml.safe_dump({"conventions": {"auto_evidence": auto_evidence}}),
        encoding="utf-8",
    )
    node = Node(
        id="src/calc.py::add",
        name="add",
        component_type="function",
        file_path="src/calc.py",
        relative_path="src/calc.py",
        start_line=1,
        end_line=2,
    )
    session = SessionState(
        session_id="s",
        repo_path=str(repo),
        output_dir=str(od),
        components={"src/calc.py::add": node},
        leaf_nodes=[],
        module_tree={"Calc": {"components": ["src/calc.py::add"]}},
    )
    return session, repo, od


def test_append_evidence_block():
    content = "---\ntype: Module\ntitle: Calc\nstatus: stable\n---\n\nbody\n"
    out = append_evidence_block(
        content,
        [
            {
                "id": "repo://src/calc.py#L1-L2",
                "resource": "repo://src/calc.py#L1-L2",
                "content_hash": "sha256:abc",
            }
        ],
    )
    assert "sources:" in out
    assert 'content_hash: "sha256:abc"' in out or "sha256:abc" in out
    assert out.rstrip().endswith("body")  # body preserved

    # Already declares sources -> unchanged.
    with_sources = "---\ntype: Module\nsources:\n- id: x\n---\nbody\n"
    assert (
        append_evidence_block(with_sources, [{"id": "y", "resource": "y", "content_hash": "z"}])
        == with_sources
    )
    # No frontmatter -> unchanged.
    assert (
        append_evidence_block("no fm\n", [{"id": "y", "resource": "y", "content_hash": "z"}])
        == "no fm\n"
    )


def test_inject_evidence_auto_stamp(tmp_path):
    session, repo, od = _session_for_evidence(tmp_path, auto_evidence=True)
    page = od / "wiki" / "modules" / "Calc.md"
    page.write_text(
        "---\ntype: Module\ntitle: Calc\nstatus: stable\n---\n\nbody\n", encoding="utf-8"
    )

    result = _inject_evidence(session, "Calc.md", page)
    assert result is not None
    assert result["evidence_stamped"] == 1

    fm = yaml.safe_load(page.read_text(encoding="utf-8").split("---", 2)[1])
    assert fm["sources"][0]["resource"] == "repo://src/calc.py#L1-L2"
    assert fm["sources"][0]["content_hash"].startswith("sha256:")
    assert _check_stale_evidence(od) == []

    (repo / "src" / "calc.py").write_text(
        "def add(a, b):\n    return a + b + 1\n", encoding="utf-8"
    )
    issues = _check_stale_evidence(od)
    assert len(issues) == 1 and "drifted" in issues[0]["message"]


def test_inject_evidence_opt_in(tmp_path):
    session, repo, od = _session_for_evidence(tmp_path, auto_evidence=False)
    page = od / "wiki" / "modules" / "Calc.md"
    page.write_text(
        "---\ntype: Module\ntitle: Calc\nstatus: stable\n---\n\nbody\n", encoding="utf-8"
    )
    assert _inject_evidence(session, "Calc.md", page) is None
    assert "sources:" not in page.read_text(encoding="utf-8")
