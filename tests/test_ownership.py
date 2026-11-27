"""B2：变更未归属组件的确定性 ownership closure。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import git
import pytest

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.analysis import handle_analyze_repo
from codewiki.mcp.tools.ownership import close_ownership, resolve_owner


def _component(
    component_id: str,
    path: str,
    *,
    name: str | None = None,
    depends_on: set[str] | None = None,
):
    return SimpleNamespace(
        id=component_id,
        name=name or component_id.split("::", 1)[-1],
        relative_path=path,
        depends_on=depends_on or set(),
    )


def test_same_file_rule_wins_and_resolves_enclosing_class_owner() -> None:
    tree = {
        "Core": {"components": ["src/api.py::Tracker"]},
        "Other": {"components": ["src/api.py::Other"]},
    }
    components = {
        "src/api.py::Tracker": _component("src/api.py::Tracker", "src/api.py"),
        "src/api.py::Tracker.method": _component("src/api.py::Tracker.method", "src/api.py"),
        "src/api.py::Other": _component("src/api.py::Other", "src/api.py"),
        "src/api.py::helper": _component("src/api.py::helper", "src/api.py"),
        "src/elsewhere.py::fresh": _component("src/elsewhere.py::fresh", "src/elsewhere.py"),
    }

    result = close_ownership(
        tree,
        components,
        changed_component_ids={"src/api.py::helper"},
    )

    candidate = result["effective_owner_candidates"]["src/api.py::helper"]
    assert candidate == {
        "component_id": "src/api.py::helper",
        "relative_path": "src/api.py",
        "deleted": False,
        "resolved": True,
        "rule": "1:same_file",
        "candidates": [{"module_path": ["Core"], "votes": 2, "total": 3}],
    }
    assert "src/elsewhere.py::fresh" not in result["effective_owner_candidates"]


def test_same_directory_rule_uses_strict_majority() -> None:
    tree = {
        "Core": {"components": ["src/core.py::a", "src/core.py::b"]},
        "Other": {"components": ["src/other.py::c"]},
    }
    components = {
        "src/core.py::a": _component("src/core.py::a", "src/core.py"),
        "src/core.py::b": _component("src/core.py::b", "src/core.py"),
        "src/other.py::c": _component("src/other.py::c", "src/other.py"),
        "src/new.py::fresh": _component("src/new.py::fresh", "src/new.py"),
    }

    result = close_ownership(
        tree,
        components,
        changed_component_ids={"src/new.py::fresh"},
    )

    candidate = result["effective_owner_candidates"]["src/new.py::fresh"]
    assert candidate["rule"] == "2:same_dir"
    assert candidate["candidates"] == [{"module_path": ["Core"], "votes": 2, "total": 3}]


def test_neighbor_rule_counts_direct_and_reverse_dependencies() -> None:
    tree = {
        "Core": {"components": ["dep/a.py::a", "dep/b.py::b"]},
        "Other": {"components": ["dep/c.py::c"]},
    }
    components = {
        "dep/a.py::a": _component("dep/a.py::a", "dep/a.py"),
        "dep/b.py::b": _component("dep/b.py::b", "dep/b.py"),
        "dep/c.py::c": _component("dep/c.py::c", "dep/c.py", depends_on={"new/new.py::fresh"}),
        "new/new.py::fresh": _component(
            "new/new.py::fresh",
            "new/new.py",
            depends_on={"dep/a.py::a", "dep/b.py::b"},
        ),
    }

    result = close_ownership(
        tree,
        components,
        changed_component_ids={"new/new.py::fresh"},
    )

    candidate = result["effective_owner_candidates"]["new/new.py::fresh"]
    assert candidate["rule"] == "3:neighbor_majority"
    assert candidate["candidates"] == [{"module_path": ["Core"], "votes": 2, "total": 3}]


def test_ties_keep_all_leaders_but_unique_plurality_is_not_a_majority() -> None:
    tied_tree = {
        "Core": {"components": ["src/a.py::a"]},
        "Other": {"components": ["src/b.py::b"]},
    }
    components = {
        "src/a.py::a": _component("src/a.py::a", "src/a.py"),
        "src/b.py::b": _component("src/b.py::b", "src/b.py"),
        "src/new.py::fresh": _component("src/new.py::fresh", "src/new.py"),
    }
    tied = close_ownership(
        tied_tree,
        components,
        changed_component_ids={"src/new.py::fresh"},
    )["effective_owner_candidates"]["src/new.py::fresh"]
    assert tied["resolved"] is False
    assert tied["candidates"] == [
        {"module_path": ["Core"], "votes": 1, "total": 2},
        {"module_path": ["Other"], "votes": 1, "total": 2},
    ]

    plural_tree = {
        "Core": {"components": ["src/a.py::a", "src/b.py::b"]},
        "Other": {"components": ["src/c.py::c"]},
        "Third": {"components": ["src/d.py::d"]},
    }
    components.update(
        {
            "src/b.py::b": _component("src/b.py::b", "src/b.py"),
            "src/c.py::c": _component("src/c.py::c", "src/c.py"),
            "src/d.py::d": _component("src/d.py::d", "src/d.py"),
        }
    )
    plural = close_ownership(
        plural_tree,
        components,
        changed_component_ids={"src/new.py::fresh"},
    )["effective_owner_candidates"]["src/new.py::fresh"]
    assert plural["resolved"] is False
    assert plural["rule"] == "2:same_dir"
    assert plural["candidates"] == []


def test_deleted_components_use_old_graph_and_unresolved_deletions_are_explicit() -> None:
    tree = {"Core": {"components": ["src/core.py::tracked"]}}
    previous = {
        "src/core.py::tracked": _component("src/core.py::tracked", "src/core.py"),
        "src/api.py::gone": _component("src/api.py::gone", "src/api.py"),
        "isolated/gone.py::orphan": _component("isolated/gone.py::orphan", "isolated/gone.py"),
    }
    current = {"src/core.py::tracked": previous["src/core.py::tracked"]}

    result = close_ownership(
        tree,
        current,
        previous_components=previous,
        deleted_component_ids={"src/api.py::gone", "isolated/gone.py::orphan"},
    )

    adopted = result["effective_owner_candidates"]["src/api.py::gone"]
    assert adopted["deleted"] is True
    assert adopted["rule"] == "2:same_dir"
    assert adopted["candidates"] == [{"module_path": ["Core"], "votes": 1, "total": 1}]
    assert result["unresolved_deletions"] == [
        {
            "component_id": "isolated/gone.py::orphan",
            "relative_path": "isolated/gone.py",
            "reason": "no_owner_evidence",
        }
    ]


def test_closure_is_deterministic_and_does_not_mutate_inputs() -> None:
    tree = {
        "Root": {
            "children": {
                "Core": {"components": ["src/a.py::a"]},
                "Other": {"components": ["src/b.py::b"]},
            }
        }
    }
    components = {
        "src/a.py::a": _component("src/a.py::a", "src/a.py"),
        "src/b.py::b": _component("src/b.py::b", "src/b.py"),
        "src/new.py::z": _component("src/new.py::z", "src/new.py"),
        "src/new.py::a": _component("src/new.py::a", "src/new.py"),
    }
    before = copy.deepcopy((tree, components))

    first = close_ownership(
        tree,
        components,
        changed_component_ids={"src/new.py::z", "src/new.py::a"},
    )
    second = close_ownership(
        tree,
        components,
        changed_component_ids={"src/new.py::a", "src/new.py::z"},
    )

    assert first == second
    assert list(first["effective_owner_candidates"]) == ["src/new.py::a", "src/new.py::z"]
    assert (tree, components) == before
    assert resolve_owner({"src/a.py::Root.Child": ("Root", "Child")}, "src/a.py::Root.Child.m") == (
        "Root",
        "Child",
    )


@pytest.mark.parametrize("incremental", [True, False])
def test_analyze_repo_returns_ownership_candidates_without_editing_tree(
    tmp_path: Path, monkeypatch, incremental: bool
) -> None:
    repo = git.Repo.init(tmp_path)
    repo.git.config("user.name", "test")
    repo.git.config("user.email", "test@example.com")
    (tmp_path / ".gitignore").write_text("repowiki/\n.codewiki/\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/core.py").write_text("def tracked():\n    return 1\n", encoding="utf-8")
    (tmp_path / "src/api.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (tmp_path / "isolated").mkdir()
    (tmp_path / "isolated/gone.py").write_text("def orphan():\n    return 1\n", encoding="utf-8")
    repo.index.add([".gitignore", "src/core.py", "src/api.py", "isolated/gone.py"])
    repo.index.commit("initial")

    store = SessionStore()
    first = json.loads(
        handle_analyze_repo({"repo_path": str(tmp_path), "incremental": False}, store)
    )
    assert "error" not in first, first

    output_dir = tmp_path / "repowiki"
    tree_path = output_dir / ".meta/module_tree.json"
    tree_path.parent.mkdir(parents=True, exist_ok=True)
    tree = {"Core": {"components": ["src/core.py::tracked"]}}
    tree_path.write_text(json.dumps(tree, indent=2), encoding="utf-8")
    tree_before = tree_path.read_bytes()
    if not incremental:
        metadata_path = tree_path.parent / "metadata.json"
        metadata_path.write_text(
            json.dumps({"generation_info": {"commit_id": repo.head.commit.hexsha}}),
            encoding="utf-8",
        )

    (tmp_path / "src/api.py").write_text(
        "def helper():\n    return 2\n\n\ndef added():\n    return 3\n",
        encoding="utf-8",
    )
    (tmp_path / "isolated/gone.py").unlink()
    response = json.loads(
        handle_analyze_repo({"repo_path": str(tmp_path), "incremental": incremental}, store)
    )
    assert "error" not in response, response

    changes = response["changes"]
    assert changes["ownership_tree_status"] == "loaded"
    assert changes["effective_owner_candidates"]["src/api.py::helper"]["rule"] == "2:same_dir"
    assert changes["effective_owner_candidates"]["src/api.py::added"]["candidates"] == [
        {"module_path": ["Core"], "votes": 1, "total": 1}
    ]
    assert changes["unresolved_deletions"] == [
        {
            "component_id": "isolated/gone.py::orphan",
            "relative_path": "isolated/gone.py",
            "reason": "no_owner_evidence",
        }
    ]
    assert tree_path.read_bytes() == tree_before
    written = json.loads(
        (Path(response["workspace_dir"]) / "changes.json").read_text(encoding="utf-8")
    )
    assert written["effective_owner_candidates"] == changes["effective_owner_candidates"]
    assert written["unresolved_deletions"] == changes["unresolved_deletions"]

    from codewiki.mcp.cache import AnalysisCache

    monkeypatch.setattr(
        AnalysisCache,
        "detect_changes",
        lambda self: {"no_changes": True, "changed_files": []},
    )
    no_change = json.loads(handle_analyze_repo({"repo_path": str(tmp_path)}, store))
    assert no_change["changes"]["effective_owner_candidates"] == {}
    assert no_change["changes"]["unresolved_deletions"] == []
    assert no_change["changes"]["ownership_tree_status"] == "loaded"


def test_missing_or_corrupt_tree_keeps_untracked_components_visible(tmp_path: Path, caplog) -> None:
    from codewiki.mcp.tools.analysis import _enrich_ownership

    output_dir = tmp_path / "repowiki"
    components = {"src/new.py::fresh": _component("src/new.py::fresh", "src/new.py")}
    changes = {"changed_files": ["src/new.py"]}

    missing = _enrich_ownership(
        changes,
        tmp_path,
        output_dir,
        components=components,
        changed_components=components,
    )
    assert missing["effective_owner_candidates"]["src/new.py::fresh"]["resolved"] is False
    assert missing["effective_owner_candidates"]["src/new.py::fresh"]["candidates"] == []
    assert missing["ownership_tree_status"] == "missing"

    tree_path = output_dir / ".meta/module_tree.json"
    tree_path.parent.mkdir(parents=True, exist_ok=True)
    tree_path.write_text("{broken", encoding="utf-8")
    corrupt = _enrich_ownership(
        {"changed_files": ["src/new.py"]},
        tmp_path,
        output_dir,
        components=components,
        changed_components=components,
    )
    assert corrupt["effective_owner_candidates"]["src/new.py::fresh"]["resolved"] is False
    assert corrupt["ownership_tree_status"] == "invalid"
    assert corrupt["ownership_warning"]
    assert "module tree load failed" in caplog.text
    assert tree_path.read_text(encoding="utf-8") == "{broken"

    tree_path.write_text(json.dumps({"Core": {"components": "not-a-list"}}), encoding="utf-8")
    malformed = _enrich_ownership(
        {"changed_files": ["src/new.py"]},
        tmp_path,
        output_dir,
        components=components,
        changed_components=components,
    )
    assert malformed["ownership_tree_status"] == "invalid"
    assert "components must be a list" in malformed["ownership_warning"]
