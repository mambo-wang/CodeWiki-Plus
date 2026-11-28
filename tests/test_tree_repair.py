"""B3：模块树确定性修复，默认观察、显式应用。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import git
import pytest

from codewiki.mcp.cache import LazyComponentStore
from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.analysis import handle_analyze_repo
from codewiki.mcp.tools.module_tree import handle_save_module_tree
from codewiki.mcp.tools.tree_repair import repair_module_tree


def _component(
    component_id: str,
    path: str,
    *,
    depends_on: set[str] | None = None,
    start_line: int = 1,
    end_line: int = 2,
    component_type: str = "function",
):
    return SimpleNamespace(
        id=component_id,
        name=component_id.split("::", 1)[-1],
        relative_path=path,
        depends_on=depends_on or set(),
        start_line=start_line,
        end_line=end_line,
        component_type=component_type,
    )


def _changes(*, added: list[str] | None = None, deleted: list[str] | None = None, renamed=None):
    return {
        "added": sorted(added or []),
        "deleted": sorted(deleted or []),
        "renamed": sorted(renamed or [], key=lambda item: (item["from"], item["to"])),
    }


def test_rename_delete_prune_and_add_run_in_order_without_mutating_inputs() -> None:
    tree = {
        "Root": {
            "components": [],
            "children": {
                "Core": {"components": ["src/api.py::old", "src/gone.py::gone"]},
                "EmptyParent": {"children": {"EmptyLeaf": {"components": []}}},
            },
        }
    }
    current = {
        "src/api.py::new": _component("src/api.py::new", "src/api.py"),
        "src/new.py::fresh": _component("src/new.py::fresh", "src/new.py"),
    }
    changes = _changes(
        added=["src/new.py::fresh"],
        deleted=["src/gone.py::gone"],
        renamed=[{"from": "src/api.py::old", "to": "src/api.py::new"}],
    )
    before = copy.deepcopy((tree, current, changes))

    observed = repair_module_tree(
        tree,
        current,
        component_changes=changes,
        tracked_component_ids=set(current),
    )
    applied = repair_module_tree(
        tree,
        current,
        component_changes=changes,
        tracked_component_ids=set(current),
        apply=True,
    )

    assert observed["mode"] == "observe"
    assert "repaired_tree" not in observed
    assert [op["action"] for op in observed["operations"]] == [
        "rename",
        "delete",
        "prune",
        "prune",
        "add",
    ]
    assert applied["repaired_tree"] == {
        "Root": {
            "components": [],
            "children": {"Core": {"components": ["src/api.py::new", "src/new.py::fresh"]}},
        }
    }
    assert applied["deleted_nodes"] == [
        ["Root", "EmptyParent", "EmptyLeaf"],
        ["Root", "EmptyParent"],
    ]
    assert (tree, current, changes) == before


def test_same_file_strict_majority_precedes_same_directory() -> None:
    tree = {
        "Core": {"components": ["src/api.py::a", "src/api.py::b"]},
        "Other": {"components": ["src/api.py::c", "src/other.py::d"]},
    }
    current = {
        "src/api.py::a": _component("src/api.py::a", "src/api.py"),
        "src/api.py::b": _component("src/api.py::b", "src/api.py"),
        "src/api.py::c": _component("src/api.py::c", "src/api.py"),
        "src/other.py::d": _component("src/other.py::d", "src/other.py"),
        "src/api.py::fresh": _component("src/api.py::fresh", "src/api.py"),
    }
    result = repair_module_tree(
        tree,
        current,
        component_changes=_changes(added=["src/api.py::fresh"]),
        tracked_component_ids=set(current),
        apply=True,
    )

    operation = result["operations"][0]
    assert operation["action"] == "add"
    assert operation["rule"] == "1:same_file"
    assert operation["module_path"] == ["Core"]
    assert operation["candidates"] == [{"module_path": ["Core"], "votes": 2, "total": 3}]
    assert result["repaired_tree"]["Core"]["components"][-1] == "src/api.py::fresh"


def test_same_directory_requires_one_leaf_and_keeps_ambiguous_candidates() -> None:
    components = {
        "src/a.py::a": _component("src/a.py::a", "src/a.py"),
        "src/b.py::b": _component("src/b.py::b", "src/b.py"),
        "src/new.py::fresh": _component("src/new.py::fresh", "src/new.py"),
    }
    single = repair_module_tree(
        {"Core": {"components": ["src/a.py::a", "src/b.py::b"]}},
        components,
        component_changes=_changes(added=["src/new.py::fresh"]),
        tracked_component_ids=set(components),
        apply=True,
    )
    assert single["operations"][0]["rule"] == "2:same_dir"
    assert single["operations"][0]["module_path"] == ["Core"]

    ambiguous = repair_module_tree(
        {
            "Core": {"components": ["src/a.py::a"]},
            "Other": {"components": ["src/b.py::b"]},
        },
        components,
        component_changes=_changes(added=["src/new.py::fresh"]),
        tracked_component_ids=set(components),
    )
    operation = ambiguous["operations"][0]
    assert operation["status"] == "orphan"
    assert operation["module_path"] is None
    assert operation["candidates"] == [
        {"module_path": ["Core"], "votes": 1},
        {"module_path": ["Other"], "votes": 1},
    ]
    assert ambiguous["unplaced_component_ids"] == ["src/new.py::fresh"]


def test_neighbor_rule_counts_reverse_dependencies_and_untracked_is_explicit() -> None:
    tree = {
        "Core": {"components": ["dep/a.py::a", "dep/b.py::b"]},
        "Other": {"components": ["dep/c.py::c"]},
    }
    current = {
        "dep/a.py::a": _component("dep/a.py::a", "dep/a.py"),
        "dep/b.py::b": _component("dep/b.py::b", "dep/b.py"),
        "dep/c.py::c": _component("dep/c.py::c", "dep/c.py", depends_on={"new/fresh.py::fresh"}),
        "new/fresh.py::fresh": _component(
            "new/fresh.py::fresh",
            "new/fresh.py",
            depends_on={"dep/a.py::a", "dep/b.py::b"},
        ),
        "new/untracked.py::helper": _component("new/untracked.py::helper", "new/untracked.py"),
    }
    result = repair_module_tree(
        tree,
        current,
        component_changes=_changes(added=["new/fresh.py::fresh", "new/untracked.py::helper"]),
        tracked_component_ids=set(current) - {"new/untracked.py::helper"},
        apply=True,
    )

    routed, untracked = result["operations"]
    assert routed["rule"] == "3:neighbor_majority"
    assert routed["module_path"] == ["Core"]
    assert routed["candidates"] == [{"module_path": ["Core"], "votes": 2, "total": 3}]
    assert untracked["status"] == "untracked"
    assert untracked["module_path"] is None
    assert result["unplaced_component_ids"] == ["new/untracked.py::helper"]


def test_rename_collision_is_not_silently_applied() -> None:
    tree = {"Core": {"components": ["src/a.py::old", "src/a.py::taken"]}}
    current = {"src/a.py::taken": _component("src/a.py::taken", "src/a.py")}
    result = repair_module_tree(
        tree,
        current,
        component_changes=_changes(renamed=[{"from": "src/a.py::old", "to": "src/a.py::taken"}]),
        tracked_component_ids=set(current),
        apply=True,
    )

    assert result["operations"][0]["status"] == "conflict"
    assert result["repaired_tree"] == tree
    assert result["warnings"]


def test_growth_threshold_warns_without_reclustering() -> None:
    tree = {"Core": {"components": ["src/a.py::a"]}}
    current = {
        "src/a.py::a": _component("src/a.py::a", "src/a.py"),
        "src/new.py::b": _component("src/new.py::b", "src/new.py"),
        "src/new.py::c": _component("src/new.py::c", "src/new.py"),
    }
    result = repair_module_tree(
        tree,
        current,
        component_changes=_changes(added=["src/new.py::b", "src/new.py::c"]),
        tracked_component_ids=set(current),
        apply=True,
        growth_threshold=0.33,
    )

    assert result["growth"] == {"Core": 0.6667}
    assert result["growth_flagged"] == [["Core"]]
    assert result["warnings"]
    assert len(result["repaired_tree"]["Core"]["components"]) == 3


def test_invalid_tree_shape_raises_instead_of_dropping_components() -> None:
    with pytest.raises(ValueError, match="components must be a list"):
        repair_module_tree(
            {"Core": {"components": "src/a.py::a"}},
            {"src/a.py::a": _component("src/a.py::a", "src/a.py")},
            component_changes=_changes(),
            tracked_component_ids={"src/a.py::a"},
        )


@pytest.mark.parametrize("incremental", [True, False])
def test_analyze_repo_observe_plan_does_not_edit_tree(
    tmp_path: Path, monkeypatch, incremental: bool
) -> None:
    repo = git.Repo.init(tmp_path)
    repo.git.config("user.name", "test")
    repo.git.config("user.email", "test@example.com")
    (tmp_path / ".gitignore").write_text("repowiki/\n.codewiki/\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/core.py").write_text("def old():\n    return 1\n", encoding="utf-8")
    repo.index.add([".gitignore", "src/core.py"])
    repo.index.commit("initial")

    store = SessionStore()
    first = json.loads(
        handle_analyze_repo({"repo_path": str(tmp_path), "incremental": False}, store)
    )
    assert "error" not in first, first
    tree_path = tmp_path / "repowiki/.meta/module_tree.json"
    tree_path.parent.mkdir(parents=True, exist_ok=True)
    tree_path.write_text(
        json.dumps({"Core": {"components": ["src/core.py::old"]}}, indent=2),
        encoding="utf-8",
    )
    before = tree_path.read_bytes()
    if not incremental:
        (tree_path.parent / "metadata.json").write_text(
            json.dumps({"generation_info": {"commit_id": repo.head.commit.hexsha}}),
            encoding="utf-8",
        )

    (tmp_path / "src/core.py").write_text("def new():\n    return 2\n", encoding="utf-8")
    response = json.loads(
        handle_analyze_repo({"repo_path": str(tmp_path), "incremental": incremental}, store)
    )
    assert "error" not in response, response
    repair = response["changes"]["tree_repair"]
    assert response["changes"]["tree_repair_status"] == "loaded"
    assert repair["mode"] == "observe"
    assert repair["operations"] == [
        {
            "action": "rename",
            "component_id": "src/core.py::old",
            "new_component_id": "src/core.py::new",
            "module_paths": [["Core"]],
            "status": "planned",
        }
    ]
    assert tree_path.read_bytes() == before

    from codewiki.mcp.cache import AnalysisCache

    monkeypatch.setattr(
        AnalysisCache,
        "detect_changes",
        lambda self: {"no_changes": True, "changed_files": []},
    )
    no_change = json.loads(handle_analyze_repo({"repo_path": str(tmp_path)}, store))
    assert no_change["changes"]["tree_repair"]["operations"] == []
    assert no_change["changes"]["tree_repair"]["summary"]["unplaced"] == 0
    assert tree_path.read_bytes() == before


def test_save_module_tree_defaults_to_observe_and_apply_is_explicit(tmp_path: Path) -> None:
    store = SessionStore()
    ids = ["src/a.py::old", "src/a.py::tracked"]
    components = {cid: _component(cid, "src/a.py") for cid in ids}
    session = store.create(
        repo_path=str(tmp_path),
        output_dir=str(tmp_path / "repowiki"),
        components=cast(LazyComponentStore, components),
        leaf_nodes=ids,
    )
    session.component_changes = _changes(renamed=[{"from": "src/a.py::old", "to": "src/a.py::new"}])
    current = dict(components)
    current["src/a.py::new"] = _component("src/a.py::new", "src/a.py")
    del current["src/a.py::old"]
    session.components = cast(LazyComponentStore, current)
    tree = {"Core": {"components": ["src/a.py::old", "src/a.py::tracked"]}}

    observed = json.loads(
        handle_save_module_tree(
            {"repo_path": str(tmp_path), "session_id": session.session_id, "module_tree": tree},
            store,
        )
    )
    tree_path = tmp_path / "repowiki/.meta/module_tree.json"
    assert json.loads(tree_path.read_text(encoding="utf-8")) == tree
    assert observed["tree_repair"]["mode"] == "observe"

    applied = json.loads(
        handle_save_module_tree(
            {
                "repo_path": str(tmp_path),
                "session_id": session.session_id,
                "module_tree": tree,
                "repair_mode": "apply",
            },
            store,
        )
    )
    assert applied["tree_repair"]["mode"] == "apply"
    assert json.loads(tree_path.read_text(encoding="utf-8"))["Core"]["components"] == [
        "src/a.py::new",
        "src/a.py::tracked",
    ]


def test_already_assigned_add_is_not_duplicated() -> None:
    tree = {"Core": {"components": ["src/a.py::fresh"]}}
    current = {"src/a.py::fresh": _component("src/a.py::fresh", "src/a.py")}
    result = repair_module_tree(
        tree,
        current,
        component_changes=_changes(added=["src/a.py::fresh"]),
        tracked_component_ids=set(current),
        apply=True,
    )
    assert result["operations"][0]["status"] == "already_assigned"
    assert result["repaired_tree"] == tree
    assert result["unplaced_component_ids"] == []


def test_rename_alone_does_not_count_as_leaf_growth() -> None:
    tree = {"Core": {"components": ["src/a.py::old"]}}
    current = {"src/a.py::new": _component("src/a.py::new", "src/a.py")}
    result = repair_module_tree(
        tree,
        current,
        component_changes=_changes(renamed=[{"from": "src/a.py::old", "to": "src/a.py::new"}]),
        tracked_component_ids=set(current),
        apply=True,
    )
    assert result["growth"] == {}
    assert result["growth_flagged"] == []


def test_tree_repair_wrapper_reports_invalid_tree_without_blocking(tmp_path: Path) -> None:
    from codewiki.mcp.tools.analysis import _enrich_tree_repair

    tree_path = tmp_path / "repowiki/.meta/module_tree.json"
    tree_path.parent.mkdir(parents=True)
    tree_path.write_text(json.dumps({"Core": {"components": "not-a-list"}}), encoding="utf-8")
    before = tree_path.read_bytes()
    changes = {"no_changes": False}
    result = _enrich_tree_repair(
        changes,
        tmp_path,
        tmp_path / "repowiki",
        components={},
        component_changes=_changes(),
        tracked_component_ids=[],
    )
    assert result["tree_repair_status"] == "invalid"
    assert "components must be a list" in result["tree_repair_warning"]
    assert result["tree_repair"]["mode"] == "observe"
    assert tree_path.read_bytes() == before


def test_same_file_tie_falls_back_to_unique_directory_leaf() -> None:
    tree = {
        "Core": {"components": ["src/a.py::a", "src/b.py::b"]},
        "Other": {
            "components": ["src/a.py::c"],
            "children": {"Nested": {"components": ["lib/x.py::x"]}},
        },
    }
    components = {
        "src/a.py::a": _component("src/a.py::a", "src/a.py"),
        "src/a.py::c": _component("src/a.py::c", "src/a.py"),
        "src/b.py::b": _component("src/b.py::b", "src/b.py"),
        "lib/x.py::x": _component("lib/x.py::x", "lib/x.py"),
        "src/new.py::fresh": _component("src/new.py::fresh", "src/new.py"),
    }
    result = repair_module_tree(
        tree,
        components,
        component_changes=_changes(added=["src/new.py::fresh"]),
        tracked_component_ids=set(components),
        apply=True,
    )

    operation = result["operations"][0]
    assert operation["rule"] == "2:same_dir"
    assert operation["module_path"] == ["Core"]
    assert result["repaired_tree"]["Core"]["components"][-1] == "src/new.py::fresh"


def test_neighbor_rule_counts_non_leaf_owners() -> None:
    tree = {
        "Parent": {
            "components": ["dep/a.py::a", "dep/b.py::b"],
            "children": {"Nested": {"components": ["lib/x.py::x"]}},
        }
    }
    components = {
        "dep/a.py::a": _component("dep/a.py::a", "dep/a.py"),
        "dep/b.py::b": _component("dep/b.py::b", "dep/b.py"),
        "lib/x.py::x": _component("lib/x.py::x", "lib/x.py"),
        "new/fresh.py::fresh": _component(
            "new/fresh.py::fresh",
            "new/fresh.py",
            depends_on={"dep/a.py::a", "dep/b.py::b"},
        ),
    }
    result = repair_module_tree(
        tree,
        components,
        component_changes=_changes(added=["new/fresh.py::fresh"]),
        tracked_component_ids=set(components),
        apply=True,
    )

    operation = result["operations"][0]
    assert operation["rule"] == "3:neighbor_majority"
    assert operation["module_path"] == ["Parent"]
    assert result["repaired_tree"]["Parent"]["components"][-1] == "new/fresh.py::fresh"


def test_rename_with_missing_source_falls_back_to_add() -> None:
    tree = {"Core": {"components": ["src/a.py::tracked"]}}
    components = {
        "src/a.py::tracked": _component("src/a.py::tracked", "src/a.py"),
        "src/a.py::new": _component("src/a.py::new", "src/a.py"),
    }
    result = repair_module_tree(
        tree,
        components,
        component_changes=_changes(renamed=[{"from": "src/a.py::old", "to": "src/a.py::new"}]),
        tracked_component_ids=set(components),
        apply=True,
    )

    assert [operation["status"] for operation in result["operations"]] == [
        "not_assigned",
        "planned",
    ]
    assert result["operations"][1]["action"] == "add"
    assert result["unplaced_component_ids"] == []
    assert result["repaired_tree"]["Core"]["components"] == [
        "src/a.py::tracked",
        "src/a.py::new",
    ]


def test_duplicate_component_ownership_is_rejected() -> None:
    tree = {
        "Core": {"components": ["src/a.py::same"]},
        "Other": {"components": ["src/a.py::same"]},
    }
    with pytest.raises(ValueError, match="multiple module owners"):
        repair_module_tree(
            tree,
            {"src/a.py::same": _component("src/a.py::same", "src/a.py")},
            component_changes=_changes(),
            tracked_component_ids={"src/a.py::same"},
        )


def test_location_evidence_shares_path_normalization() -> None:
    tree = {
        "Core": {"components": ["./src\\api.py::a", "src/api.py::b"]},
        "Other": {"components": ["src/api.py::c"]},
    }
    components = {
        "./src\\api.py::a": _component("./src\\api.py::a", "./src\\api.py"),
        "src/api.py::b": _component("src/api.py::b", "src/api.py"),
        "src/api.py::c": _component("src/api.py::c", "src/api.py"),
        "src/api.py::fresh": _component("src/api.py::fresh", "src/api.py"),
    }
    result = repair_module_tree(
        tree,
        components,
        component_changes=_changes(added=["src/api.py::fresh"]),
        tracked_component_ids=set(components),
        apply=True,
    )

    operation = result["operations"][0]
    assert operation["rule"] == "1:same_file"
    assert operation["module_path"] == ["Core"]


def test_save_apply_uses_latest_analysis_generation(tmp_path: Path) -> None:
    store = SessionStore()
    first = store.create(
        repo_path=str(tmp_path),
        output_dir=str(tmp_path / "repowiki"),
        components=cast(
            LazyComponentStore, {"src/a.py::old": _component("src/a.py::old", "src/a.py")}
        ),
        leaf_nodes=["src/a.py::old"],
    )
    first.component_changes = _changes(renamed=[{"from": "src/a.py::old", "to": "src/a.py::stale"}])
    second = store.create(
        repo_path=str(tmp_path),
        output_dir=str(tmp_path / "repowiki"),
        components=cast(
            LazyComponentStore, {"src/a.py::new": _component("src/a.py::new", "src/a.py")}
        ),
        leaf_nodes=["src/a.py::new"],
    )
    second.component_changes = _changes(renamed=[{"from": "src/a.py::old", "to": "src/a.py::new"}])

    assert store.find_active(str(tmp_path)) is second
    assert store.find_or_restore(str(tmp_path)) is second
    result = json.loads(
        handle_save_module_tree(
            {
                "repo_path": str(tmp_path),
                "module_tree": {"Core": {"components": ["src/a.py::old"]}},
                "repair_mode": "apply",
            },
            store,
        )
    )
    assert result["tree_repair"]["operations"][0]["new_component_id"] == "src/a.py::new"
    written = json.loads((tmp_path / "repowiki/.meta/module_tree.json").read_text(encoding="utf-8"))
    assert written["Core"]["components"] == ["src/a.py::new"]


def test_restored_session_cannot_apply_without_component_diff(tmp_path: Path, monkeypatch) -> None:
    store = SessionStore()
    cache = SimpleNamespace(
        is_fresh=lambda: True,
        get_all_metas=lambda: {"src/a.py::a": _component("src/a.py::a", "src/a.py")},
        get_leaf_nodes=lambda: ["src/a.py::a"],
    )
    monkeypatch.setattr(store, "get_cache", lambda repo_path: cache)
    restored = store.find_or_restore(str(tmp_path))
    assert restored is not None
    assert restored.component_changes is None

    result = json.loads(
        handle_save_module_tree(
            {
                "repo_path": str(tmp_path),
                "session_id": restored.session_id,
                "module_tree": {"Core": {"components": ["src/a.py::old"]}},
                "repair_mode": "apply",
            },
            store,
        )
    )
    assert "requires a fresh analyze_repo session" in result["error"]
    assert not (tmp_path / "repowiki/.meta/module_tree.json").exists()


def test_apply_without_analysis_session_is_rejected(tmp_path: Path) -> None:
    result = json.loads(
        handle_save_module_tree(
            {
                "repo_path": str(tmp_path),
                "module_tree": {"Core": {"components": []}},
                "repair_mode": "apply",
            },
            SessionStore(),
        )
    )
    assert "requires an active analyze_repo session" in result["error"]
    assert not (tmp_path / "repowiki/.meta/module_tree.json").exists()
