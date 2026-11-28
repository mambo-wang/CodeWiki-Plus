"""B5：聚类质量 validator 的纯函数与保存链路回归。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.clustering_validator import (
    load_clustering_validation_config,
    measure_scope_file_tokens,
    validate_clustering,
)
from codewiki.mcp.tools.module_tree import handle_save_module_tree
from codewiki.mcp.workspace import SessionWorkspace
from codewiki.src.be.dependency_analyzer.models.core import Node


def _components(*ids: str) -> dict[str, dict[str, str]]:
    return {component_id: {"relative_path": component_id.split("::", 1)[0]} for component_id in ids}


def _config(**overrides) -> dict:
    return {
        "enabled": True,
        "chars_per_token": 4,
        "min_leaf_tokens": 1000,
        "max_leaf_tokens": 32000,
        **overrides,
    }


def _validate(tree, components, counts=None, unmeasured=None, **overrides):
    return validate_clustering(
        tree,
        components,
        counts or {},
        unmeasured_files=unmeasured,
        config=_config(**overrides),
    )


def test_clean_nested_tree_has_no_issues():
    components = _components("src/a.py::A", "src/b.py::B", "src/c.py::C")
    tree = {
        "root": {
            "components": [],
            "children": {
                "alpha": {"components": ["src/a.py::A", "src/b.py::B"]},
                "beta": {"components": ["src/c.py::C"]},
            },
        }
    }

    result = _validate(
        tree,
        components,
        {"src/a.py": 600, "src/b.py": 700, "src/c.py": 1000},
    )

    assert result["mode"] == "observe"
    assert result["status"] == "ok"
    assert result["leaf_count"] == 2
    assert result["module_estimates"][0] == {
        "module_path": ["root"],
        "is_leaf": False,
        "file_count": 3,
        "estimated_tokens": 2300,
        "measured_file_count": 3,
        "unmeasured_file_count": 0,
        "token_estimate_is_partial": False,
    }
    assert result["micro_pages"] == []
    assert result["oversized_leaves"] == []
    assert result["split_files"] == []
    assert result["uncovered_files"] == []
    assert result["unknown_component_ids"] == []


def test_micro_and_oversized_leaves_use_complete_scope_files():
    components = _components("src/small.py::Small", "src/large.py::Large")
    tree = {
        "small": {"components": ["src/small.py::Small"]},
        "large": {"components": ["src/large.py::Large"]},
    }

    result = _validate(
        tree,
        components,
        {"src/small.py": 25, "src/large.py": 33000},
    )

    assert [entry["module_path"] for entry in result["micro_pages"]] == [["small"]]
    assert result["micro_pages"][0]["estimated_tokens"] == 25
    assert result["micro_pages"][0]["token_estimate_is_partial"] is False
    assert [entry["module_path"] for entry in result["oversized_leaves"]] == [["large"]]
    assert result["oversized_leaves"][0]["estimated_tokens"] == 33000


def test_same_file_in_mutually_exclusive_leaves_is_reported_once():
    component_ids = ["src/shared.py::A", "src/shared.py::B", "src/other.py::C"]
    tree = {
        "alpha": {"components": [component_ids[0]]},
        "beta": {"components": [component_ids[1], component_ids[2]]},
    }

    result = _validate(
        tree,
        _components(*component_ids),
        {"src/shared.py": 1500, "src/other.py": 1500},
    )

    assert result["split_files"] == [
        {
            "file": "src/shared.py",
            "leaf_modules": [["alpha"], ["beta"]],
            "component_ids": component_ids[:2],
            "suggestion": "Assign all components from this file to one leaf module, or split the source file first.",
        }
    ]


def test_parent_aggregation_does_not_count_as_a_second_leaf_owner():
    component_ids = ["src/shared.py::A", "src/shared.py::B"]
    tree = {
        "root": {
            "components": [component_ids[1]],
            "children": {"alpha": {"components": [component_ids[0]]}},
        }
    }

    result = _validate(
        tree,
        _components(*component_ids),
        {"src/shared.py": 1500},
    )

    assert result["split_files"] == []
    assert result["uncovered_files"] == []


def test_uncovered_file_and_unknown_component_id_are_explicit():
    tree = {"alpha": {"components": ["src/a.py::A", "src/missing.py::Typo"]}}

    result = _validate(tree, _components("src/a.py::A", "src/b.py::B"), {"src/a.py": 1500})

    assert result["unknown_component_ids"] == ["src/missing.py::Typo"]
    assert result["uncovered_files"] == [
        {
            "file": "src/b.py",
            "component_ids": ["src/b.py::B"],
            "suggestion": "Assign these indexed components to a module, or explicitly exclude the file from documentation scope.",
        }
    ]


def test_unmeasured_file_is_not_silently_counted_as_zero():
    tree = {"alpha": {"components": ["src/gone.py::A"]}}

    result = _validate(
        tree,
        _components("src/gone.py::A"),
        unmeasured={"src/gone.py": "missing"},
    )

    assert result["micro_pages"] == []
    assert result["oversized_leaves"] == []
    assert result["unmeasured_files"] == [
        {
            "file": "src/gone.py",
            "reason": "missing",
            "module_paths": [["alpha"]],
        }
    ]
    assert result["status"] == "issues"


def test_partially_measured_scope_does_not_claim_micro_page():
    tree = {"alpha": {"components": ["src/a.py::A", "src/b.py::B"]}}

    result = _validate(
        tree,
        _components("src/a.py::A", "src/b.py::B"),
        {"src/a.py": 10},
        {"src/b.py": "unreadable"},
    )

    assert result["micro_pages"] == []
    assert result["module_estimates"][0]["estimated_tokens"] == 10
    assert result["module_estimates"][0]["token_estimate_is_partial"] is True
    assert result["module_estimates"][0]["unmeasured_file_count"] == 1
    assert result["unmeasured_files"] == [
        {
            "file": "src/b.py",
            "reason": "unreadable",
            "module_paths": [["alpha"]],
        }
    ]


def test_uncovered_unmeasured_file_keeps_reason_and_empty_owners():
    result = _validate(
        {},
        _components("src/gone.py::A"),
        unmeasured={"src/gone.py": "outside_repo"},
    )

    assert result["uncovered_files"][0]["file"] == "src/gone.py"
    assert result["unmeasured_files"] == [
        {
            "file": "src/gone.py",
            "reason": "outside_repo",
            "module_paths": [],
        }
    ]


def test_empty_leaf_is_micro_but_unknown_only_leaf_is_not():
    result = _validate(
        {"empty": {"components": []}, "unknown": {"components": ["src/x.py::X"]}},
        {},
    )

    assert [entry["module_path"] for entry in result["micro_pages"]] == [["empty"]]
    assert result["unknown_component_ids"] == ["src/x.py::X"]


def test_zero_thresholds_disable_size_diagnostics():
    result = _validate(
        {"tiny": {"components": []}},
        {},
        min_leaf_tokens=0,
        max_leaf_tokens=0,
    )

    assert result["micro_pages"] == []
    assert result["oversized_leaves"] == []


def test_windows_component_id_separators_resolve_uniquely():
    component_id = "src/a.py::A"
    result = _validate(
        {"alpha": {"components": ["src\\a.py::A"]}},
        _components(component_id),
        {"src/a.py": 1500},
    )

    assert result["unknown_component_ids"] == []
    assert result["uncovered_files"] == []
    assert result["status"] == "ok"


def test_invalid_thresholds_are_rejected():
    with pytest.raises(ValueError, match="min_leaf_tokens"):
        _validate({}, {}, min_leaf_tokens=-1)
    with pytest.raises(ValueError, match="min_leaf_tokens"):
        _validate({}, {}, min_leaf_tokens=100, max_leaf_tokens=50)


def test_config_defaults_and_schema_overrides():
    defaults = load_clustering_validation_config(None)
    assert defaults == {
        "enabled": True,
        "chars_per_token": 4,
        "min_leaf_tokens": 1000,
        "max_leaf_tokens": 32000,
    }

    configured = load_clustering_validation_config(
        {
            "conventions": {
                "clustering_validation": {
                    "enabled": False,
                    "chars_per_token": 3,
                    "min_leaf_tokens": 0,
                    "max_leaf_tokens": 9000,
                }
            }
        }
    )
    assert configured == {
        "enabled": False,
        "chars_per_token": 3,
        "min_leaf_tokens": 0,
        "max_leaf_tokens": 9000,
    }


def test_measure_scope_files_reads_full_text_and_marks_unsafe_paths(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.py").write_text("x" * 4001, encoding="utf-8")
    outside = tmp_path.parent / "b5-outside.py"
    outside.write_text("outside", encoding="utf-8")
    components = _components(
        "src/a.py::A",
        "src/missing.py::B",
        "../b5-outside.py::C",
    )

    counts, unmeasured = measure_scope_file_tokens(tmp_path, components, 4)

    assert counts == {"src/a.py": 1001}
    assert unmeasured["src/missing.py"] == "missing"
    assert unmeasured["../b5-outside.py"] == "outside_repo"


def _make_session(store: SessionStore, repo: Path, component_ids: list[str]):
    components = {}
    for component_id in component_ids:
        rel_path, _, name = component_id.partition("::")
        source = repo / rel_path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("x" * 4004, encoding="utf-8")
        components[component_id] = Node(
            id=component_id,
            name=name or component_id,
            component_type="class",
            file_path=rel_path,
            relative_path=rel_path,
        )
    session = store.create(
        repo_path=str(repo),
        output_dir=str(repo / "repowiki"),
        components=cast(Any, components),
        leaf_nodes=list(component_ids),
    )
    session.workspace = SessionWorkspace(repo, session.session_id)
    return session


def test_save_module_tree_returns_observe_diagnostics_without_mutating_tree(tmp_path):
    store = SessionStore()
    ids = ["src/shared.py::A", "src/shared.py::B", "src/uncovered.py::C"]
    session = _make_session(store, tmp_path, ids)
    tree = {
        "alpha": {"components": [ids[0]]},
        "beta": {"components": [ids[1]]},
    }

    result = json.loads(
        handle_save_module_tree(
            {
                "repo_path": str(tmp_path),
                "session_id": session.session_id,
                "module_tree": tree,
            },
            store,
        )
    )

    assert result["status"] == "saved"
    assert result["clustering_validation"]["mode"] == "observe"
    assert result["clustering_validation"]["split_files"][0]["file"] == "src/shared.py"
    assert result["clustering_validation"]["uncovered_files"][0]["file"] == "src/uncovered.py"
    saved = json.loads(Path(result["tree_path"]).read_text(encoding="utf-8"))
    assert saved == tree
    assert session.workspace is not None
    diagnostic_file = session.workspace.root / "clustering_validation.json"
    assert diagnostic_file.is_file()
    assert json.loads(diagnostic_file.read_text(encoding="utf-8"))["mode"] == "observe"


def test_measurement_cache_skips_unchanged_files_and_invalidates_on_change(tmp_path, monkeypatch):
    source = tmp_path / "a.py"
    source.write_text("x" * 4000, encoding="utf-8")
    original_open = Path.open
    reads = 0

    def counted_open(self, *args, **kwargs):
        nonlocal reads
        if self == source:
            reads += 1
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counted_open)
    cache = {}
    components = _components("a.py::A")

    first, first_unmeasured = measure_scope_file_tokens(tmp_path, components, 4, cache=cache)
    second, second_unmeasured = measure_scope_file_tokens(tmp_path, components, 4, cache=cache)
    assert first == second == {"a.py": 1000}
    assert first_unmeasured == second_unmeasured == {}
    assert reads == 1

    source.write_text("x" * 4004, encoding="utf-8")
    reads = 1  # write_text itself used the counted open()
    changed, _ = measure_scope_file_tokens(tmp_path, components, 4, cache=cache)
    assert changed == {"a.py": 1001}
    assert reads == 2


def test_validator_uses_lightweight_items_without_loading_full_nodes():
    class LightweightComponents(dict):
        def __getitem__(self, key):
            raise AssertionError("full component lookup is forbidden")

    components = LightweightComponents(_components("src/a.py::A"))
    result = _validate(
        {"alpha": {"components": ["src/a.py::A"]}},
        components,
        {"src/a.py": 1500},
    )

    assert result["status"] == "ok"
    assert result["uncovered_files"] == []


def test_module_tree_validation_accepts_unique_windows_separator_id():
    from codewiki.mcp.tools.module_tree import _validate_module_tree

    unmatched, leftover = _validate_module_tree(
        {"alpha": {"components": ["src\\a.py::A"]}},
        {"src/a.py::A"},
    )

    assert unmatched == []
    assert leftover == []


def test_module_tree_validation_prefers_exact_id_when_normalized_forms_collide():
    from codewiki.mcp.tools.module_tree import _validate_module_tree

    unmatched, leftover = _validate_module_tree(
        {"alpha": {"components": ["src\\a.py::A"]}},
        {"src/a.py::A", "src\\a.py::A"},
    )

    assert unmatched == []
    assert leftover == ["src/a.py::A"]


def test_save_survives_malformed_clustering_schema(tmp_path):
    store = SessionStore()
    ids = ["src/a.py::A"]
    session = _make_session(store, tmp_path, ids)
    output = Path(session.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "schema.yaml").write_text("- not-a-mapping\n", encoding="utf-8")

    result = json.loads(
        handle_save_module_tree(
            {
                "repo_path": str(tmp_path),
                "session_id": session.session_id,
                "module_tree": {"alpha": {"components": ids}},
            },
            store,
        )
    )

    assert result["status"] == "saved"
    assert result["clustering_validation"]["status"] == "unavailable"
    assert json.loads(Path(result["tree_path"]).read_text(encoding="utf-8")) == {
        "alpha": {"components": ids}
    }
