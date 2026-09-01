"""Tests for D2 page-level baseline manifest (per-page drift detection).

Covers:
  - manifest read/write lifecycle (atomic, corruption-tolerant)
  - evidence source_fingerprint aggregation (deterministic, order-independent)
  - component/file collection for module pages
  - stale-page detection via changed files AND fingerprint drift
  - doc_writer write-path integration (``_record_page_manifest``)
"""

from __future__ import annotations

from pathlib import Path

from codewiki.mcp.session import SessionState
from codewiki.mcp.tools.doc_writer import _record_page_manifest
from codewiki.mcp.tools.page_manifest import (
    collect_page_files,
    compute_source_fingerprint,
    detect_stale_pages,
    load_manifest,
    page_key_for,
    upsert_page_manifest,
)
from codewiki.src.be.dependency_analyzer.models.core import Node

_CALC = "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n"


def _node() -> Node:
    return Node(
        id="src/calc.py::add",
        name="add",
        component_type="function",
        file_path="src/calc.py",
        relative_path="src/calc.py",
        start_line=1,
        end_line=2,
    )


def _session(repo: Path, od: Path) -> SessionState:
    return SessionState(
        session_id="s",
        repo_path=str(repo),
        output_dir=str(od),
        components={"src/calc.py::add": _node()},
        leaf_nodes=[],
        module_tree={"Calc": {"components": ["src/calc.py::add"]}},
    )


def _page(od: Path, rel: str, content: str) -> Path:
    p = od / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# Fingerprint aggregation
# --------------------------------------------------------------------------- #
def test_compute_source_fingerprint_no_evidence():
    assert compute_source_fingerprint("---\ntype: Module\n---\nbody\n") is None
    assert compute_source_fingerprint("no frontmatter\n") is None


def test_compute_source_fingerprint_deterministic_and_order_independent():
    a = '---\nsources:\n- id: a\n  content_hash: "sha256:1"\n- id: b\n  content_hash: "sha256:2"\n---\nbody\n'
    b = '---\nsources:\n- id: b\n  content_hash: "sha256:2"\n- id: a\n  content_hash: "sha256:1"\n---\nbody\n'
    fp = compute_source_fingerprint(a)
    assert fp and fp.startswith("sha256:")
    assert compute_source_fingerprint(b) == fp
    # single-entry sources dict form
    assert (
        compute_source_fingerprint(
            '---\nsources:\n  id: a\n  content_hash: "sha256:1"\n---\nbody\n'
        )
        != fp
    )


# --------------------------------------------------------------------------- #
# Component / file collection
# --------------------------------------------------------------------------- #
def test_collect_page_files_module_vs_non_module(tmp_path):
    repo = tmp_path / "repo"
    od = repo / "repowiki"
    session = _session(repo, od)

    files, components = collect_page_files(session, "Calc.md", "module")
    assert files == ["src/calc.py"]
    assert components == ["src/calc.py::add"]

    # Shared-pool pages carry no component attribution.
    assert collect_page_files(session, "SomeNote.md", "note") == ([], [])
    assert collect_page_files(None, "Calc.md", "module") == ([], [])


def test_collect_page_files_entity_attribution(tmp_path):
    repo = tmp_path / "repo"
    od = repo / "repowiki"
    session = SessionState(
        session_id="s",
        repo_path=str(repo),
        output_dir=str(od),
        components={
            "src/user.py::UserService": Node(
                id="src/user.py::UserService",
                name="UserService",
                component_type="class",
                file_path="src/user.py",
                relative_path="src/user.py",
                start_line=10,
                end_line=40,
            ),
            "src/user.py::login": Node(
                id="src/user.py::login",
                name="login",
                component_type="function",
                file_path="src/user.py",
                relative_path="src/user.py",
                start_line=1,
                end_line=5,
            ),
        },
        leaf_nodes=[],
        module_tree={},
    )

    # Entity page matches the class-like component, not the function.
    files, comps = collect_page_files(session, "UserService.md", "entity")
    assert files == ["src/user.py"]
    assert comps == ["src/user.py::UserService"]

    # Non-matching name -> no attribution (shared-pool fallback behaviour).
    assert collect_page_files(session, "Missing.md", "entity") == ([], [])


# --------------------------------------------------------------------------- #
# Manifest lifecycle
# --------------------------------------------------------------------------- #
def test_manifest_roundtrip_and_corruption_tolerance(tmp_path):
    od = tmp_path / "repowiki"
    page = _page(od, "wiki/modules/Calc.md", "---\ntype: Module\n---\nbody\n")

    assert load_manifest(od) == {"schema_version": 1, "pages": {}}

    entry = upsert_page_manifest(od, page, filename="Calc.md", page_type="module", repo_name="repo")
    assert entry is not None
    assert entry["repo"] == "repo"
    assert entry["git_head"] is None  # no git in this fixture
    assert entry["source_fingerprint"] is None  # no evidence
    assert entry["producer"].startswith("codewiki/")
    assert "written_at" in entry

    manifest = load_manifest(od)
    assert page_key_for(od, page) == "wiki/modules/Calc.md"
    assert manifest["pages"]["wiki/modules/Calc.md"]["repo"] == "repo"

    # Corruption -> tolerated as empty.
    (od / ".meta" / "page_manifest.json").write_text("{not json", encoding="utf-8")
    assert load_manifest(od) == {"schema_version": 1, "pages": {}}


# --------------------------------------------------------------------------- #
# Stale-page detection
# --------------------------------------------------------------------------- #
def test_detect_stale_pages_empty(tmp_path):
    od = tmp_path / "repowiki"
    assert detect_stale_pages(od, ["a.py"]) == []


def test_detect_stale_pages_via_file_change(tmp_path):
    repo = tmp_path / "repo"
    od = repo / "repowiki"
    page = _page(od, "wiki/modules/Calc.md", "---\ntype: Module\n---\nbody\n")
    session = _session(repo, od)

    upsert_page_manifest(
        od, page, session=session, filename="Calc.md", page_type="module", repo_path=str(repo)
    )

    assert detect_stale_pages(od, []) == []
    assert detect_stale_pages(od, ["unrelated.py"]) == []
    assert detect_stale_pages(od, ["src/calc.py"]) == ["wiki/modules/Calc.md"]


def test_detect_stale_pages_via_fingerprint_drift(tmp_path):
    od = tmp_path / "repowiki"
    page = _page(
        od,
        "wiki/modules/Note.md",
        '---\nsources:\n- id: a\n  content_hash: "sha256:1"\n---\nbody\n',
    )
    upsert_page_manifest(od, page, filename="Note.md", page_type="note")

    # No drift -> not stale.
    assert detect_stale_pages(od, []) == []

    # External edit to the page's evidence -> fingerprint drift.
    page.write_text(
        '---\nsources:\n- id: a\n  content_hash: "sha256:2"\n---\nbody\n', encoding="utf-8"
    )
    assert detect_stale_pages(od, []) == ["wiki/modules/Note.md"]

    # Evidence removed entirely -> still flagged as drifted.
    page.write_text("---\ntype: Module\n---\nbody\n", encoding="utf-8")
    assert detect_stale_pages(od, []) == ["wiki/modules/Note.md"]


# --------------------------------------------------------------------------- #
# doc_writer write-path integration
# --------------------------------------------------------------------------- #
def test_record_page_manifest_integration(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "calc.py").write_text(_CALC, encoding="utf-8")
    od = repo / "repowiki"
    page = _page(od, "wiki/modules/Calc.md", "---\ntype: Module\n---\nbody\n")
    session = _session(repo, od)

    _record_page_manifest(od, page, session, "Calc.md", "module", str(repo))

    entry = load_manifest(od)["pages"]["wiki/modules/Calc.md"]
    assert entry["files"] == ["src/calc.py"]
    assert entry["components"] == ["src/calc.py::add"]
    assert entry["repo"] == "repo"

    # Referenced file changed -> flagged stale.
    assert detect_stale_pages(od, ["src/calc.py"]) == ["wiki/modules/Calc.md"]
