"""确定性的文档反向引用索引。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import git

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import reference_index as ri
from codewiki.mcp.tools.analysis import handle_analyze_repo


def _component(
    component_id: str,
    name: str,
    path: str,
    start: int = 1,
    end: int = 2,
    component_type: str = "function",
):
    return SimpleNamespace(
        id=component_id,
        name=name,
        relative_path=path,
        start_line=start,
        end_line=end,
        component_type=component_type,
    )


def _write(output_dir: Path, rel: str, content: str) -> None:
    target = output_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def test_extracts_page_links_component_ids_and_unique_code_symbols(tmp_path: Path) -> None:
    output_dir = tmp_path / "repowiki"
    _write(output_dir, "overview.md", "# Overview\n")
    _write(output_dir, "wiki/modules/B.md", "# B\n")
    _write(
        output_dir,
        "wiki/modules/A.md",
        """# A
[Overview](../../overview.md)
[[B]](../modules/B.md)
[[B]]
Component `a.py::Alpha` is documented here.
```python
Alpha()
run()
[fake](missing.md)
```
Inline `Beta` is also a symbol reference.
""",
    )
    _write(output_dir, "notes/note.md", "Alpha and run are prose words, not code references.\n")

    _, index = ri.rebuild_index(
        tmp_path,
        output_dir,
        {
            "a.py::Alpha": _component("a.py::Alpha", "Alpha", "a.py"),
            "b.py::Beta": _component("b.py::Beta", "Beta", "b.py"),
            "a.py::run": _component("a.py::run", "run", "a.py", 4, 5),
            "b.py::run": _component("b.py::run", "run", "b.py", 4, 5),
            "a.py::python": _component("a.py::python", "python", "a.py", 8, 9),
        },
    )

    refs = index["pages"]["wiki/modules/A.md"]
    assert refs == [
        "component:a.py::Alpha",
        "component:b.py::Beta",
        "page:overview.md",
        "page:wiki/modules/B.md",
    ]
    assert index["pages"]["notes/note.md"] == []
    assert index["references"]["component:a.py::Alpha"] == ["wiki/modules/A.md"]
    assert "component:a.py::run" not in index["references"]
    assert "component:b.py::run" not in index["references"]
    assert "component:a.py::python" not in index["references"]
    assert "page:missing.md" not in index["references"]


def test_index_is_deterministic_and_rebuilds_after_deletion_or_corruption(tmp_path: Path) -> None:
    output_dir = tmp_path / "repowiki"
    _write(output_dir, "wiki/modules/A.md", "`a.py::Alpha`\n")
    components = {"a.py::Alpha": _component("a.py::Alpha", "Alpha", "a.py")}

    path, first = ri.rebuild_index(tmp_path, output_dir, components)
    original = path.read_bytes()
    assert first == ri.rebuild_index(tmp_path, output_dir, components)[1]
    assert path.read_bytes() == original

    path.unlink()
    _, rebuilt = ri.rebuild_index(tmp_path, output_dir, components)
    assert rebuilt == first
    assert path.read_bytes() == original

    path.write_text("{broken", encoding="utf-8")
    _, repaired = ri.rebuild_index(tmp_path, output_dir, components)
    assert repaired == first
    assert path.read_bytes() == original


def test_persistent_symbol_baseline_survives_index_deletion(tmp_path: Path) -> None:
    output_dir = tmp_path / "repowiki"
    _write(output_dir, "wiki/modules/A.md", "```python\nOldClass()\n```\n")
    old = {"a.py::OldClass": _component("a.py::OldClass", "OldClass", "a.py")}

    path, first = ri.rebuild_index(tmp_path, output_dir, old)
    baseline = first["symbols"]
    path.unlink()
    _, rebuilt = ri.rebuild_index(
        tmp_path,
        output_dir,
        {},
        historical_symbols=baseline,
    )

    assert rebuilt["symbols"]["OldClass"] == "a.py::OldClass"
    assert ri.referencing_pages(rebuilt, component_ids=["a.py::OldClass"]) == {
        "components": {"a.py::OldClass": ["wiki/modules/A.md"]},
        "pages": {},
    }


def test_rebuild_index_never_auto_stages(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "repowiki"
    _write(output_dir, "wiki/modules/A.md", "`a.py::Alpha`\n")
    staged: list[Path] = []
    monkeypatch.setattr("codewiki.src.git_sync.auto_stage", lambda path: staged.append(path))

    ri.rebuild_index(
        tmp_path,
        output_dir,
        {"a.py::Alpha": _component("a.py::Alpha", "Alpha", "a.py")},
    )

    assert staged == []


def test_index_is_registered_as_rebuildable() -> None:
    from codewiki.src.config import TEAM_LAYOUT_REBUILDABLE_FILES

    assert ".meta/reference_index.json" in TEAM_LAYOUT_REBUILDABLE_FILES
    template = (
        Path(__file__).resolve().parents[1]
        / "codewiki"
        / "templates"
        / "workspace"
        / "gitignore.tpl"
    )
    assert "repowiki/.meta/reference_index.json" in template.read_text(encoding="utf-8")


def test_component_change_classification_pairs_only_unambiguous_same_span_renames() -> None:
    previous = {
        "a.py::old_name": _component("a.py::old_name", "old_name", "a.py", 1, 2),
        "a.py::deleted": _component("a.py::deleted", "deleted", "a.py", 4, 5),
    }
    current = {
        "a.py::new_name": _component("a.py::new_name", "new_name", "a.py", 1, 2),
    }

    assert ri.classify_component_changes(previous, current) == {
        "added": [],
        "deleted": ["a.py::deleted"],
        "renamed": [{"from": "a.py::old_name", "to": "a.py::new_name"}],
    }


def test_analyze_repo_prepare_returns_referencing_pages_without_editing_docs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = git.Repo.init(tmp_path)
    repo.git.config("user.name", "test")
    repo.git.config("user.email", "test@example.com")
    source = tmp_path / "a.py"
    source.write_text(
        "def old_name():\n    return 1\n\n\ndef deleted():\n    return 2\n", encoding="utf-8"
    )
    repo.index.add(["a.py"])
    repo.index.commit("initial")

    store = SessionStore()
    first = json.loads(
        handle_analyze_repo({"repo_path": str(tmp_path), "incremental": False}, store)
    )
    assert "error" not in first, first

    output_dir = tmp_path / "repowiki"
    page = output_dir / "wiki" / "modules" / "A.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    content = """# A
```python
old_name()
deleted()
```
"""
    page.write_text(content, encoding="utf-8")
    repo.index.add([page.relative_to(tmp_path).as_posix()])
    repo.index.commit("document components")

    source.write_text("def new_name():\n    return 1\n", encoding="utf-8")
    response = json.loads(handle_analyze_repo({"repo_path": str(tmp_path)}, store))
    assert "error" not in response, response

    changes = response["changes"]
    assert changes["component_changes"] == {
        "added": [],
        "deleted": ["a.py::deleted"],
        "renamed": [{"from": "a.py::old_name", "to": "a.py::new_name"}],
    }
    assert changes["referencing_pages"]["components"] == {
        "a.py::deleted": ["wiki/modules/A.md"],
        "a.py::old_name": ["wiki/modules/A.md"],
    }
    assert changes["reference_index_file"].endswith("repowiki/.meta/reference_index.json")
    assert ri.reference_index_path(tmp_path, output_dir).is_file()
    assert page.read_text(encoding="utf-8") == content

    index_path = ri.reference_index_path(tmp_path, output_dir)
    index_path.unlink()
    rebuilt_response = json.loads(handle_analyze_repo({"repo_path": str(tmp_path)}, store))
    assert "error" not in rebuilt_response, rebuilt_response
    assert index_path.is_file()
    rebuilt_index = json.loads(index_path.read_text(encoding="utf-8"))
    assert rebuilt_index["references"]["component:a.py::deleted"] == ["wiki/modules/A.md"]
    assert rebuilt_index["references"]["component:a.py::old_name"] == ["wiki/modules/A.md"]

    index_path.unlink()
    monkeypatch.setattr(
        "codewiki.mcp.cache.AnalysisCache.detect_changes",
        lambda self: {"changed_files": [], "method": "git", "no_changes": True},
    )
    no_change_response = json.loads(handle_analyze_repo({"repo_path": str(tmp_path)}, store))
    assert "error" not in no_change_response, no_change_response
    assert no_change_response["hint"].startswith("No changes detected")
    assert no_change_response["changes"]["component_changes"] == {
        "added": [],
        "deleted": [],
        "renamed": [],
    }
    assert index_path.is_file()
