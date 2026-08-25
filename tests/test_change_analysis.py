"""Tests for analyze_changes — git-diff driven blast-radius analysis.

Covers:
* unified diff parsing (pure text, no git required)
* changed-function location precision (line span matching)
* end-to-end worktree / commit-range / untracked flows against a real
  temp git repository + analyze_repo pipeline
* test suggestion heuristics
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import git
import pytest

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.analysis import handle_analyze_repo
from codewiki.mcp.tools.change_analysis import (
    _test_candidates_for,
    locate_changed_components,
    parse_unified_diff,
    suggest_tests,
)
from codewiki.mcp.tools.impact import handle_analyze_impact

# ------------------------------------------------------------------
# Unit tests: parse_unified_diff
# ------------------------------------------------------------------

DIFF_WITH_CONTEXT = """diff --git a/b.py b/b.py
index 1111111..2222222 100644
--- a/b.py
+++ b/b.py
@@ -1,6 +1,7 @@
 def func_b():
-    x = 1
+    x = 2
     y = 3
+    return x
 def func_c():
     pass
"""

DIFF_ZERO_CONTEXT = """diff --git a/c.py b/c.py
index 1111111..2222222 100644
--- a/c.py
+++ b/c.py
@@ -2,1 +2,1 @@
-    old_line
+    new_line
"""

DIFF_NEW_FILE = """diff --git a/new_mod.py b/new_mod.py
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/new_mod.py
@@ -0,0 +1,3 @@
+def fresh():
+    pass
+
"""

DIFF_DELETED_FILE = """diff --git a/gone.py b/gone.py
deleted file mode 100644
index 1111111..0000000
--- a/gone.py
+++ /dev/null
@@ -1,3 +0,0 @@
-def gone():
-    pass
-
"""


def test_parse_unified_diff_with_context() -> None:
    changes = parse_unified_diff(DIFF_WITH_CONTEXT)
    assert len(changes) == 1
    fc = changes[0]
    assert fc.path == "b.py"
    # new-file line numbers: hunk starts at new line 1
    # "- x = 1" (old line 2) -> anchor = new line 1
    # "+ x = 2" -> added line 2
    # "  y = 3" -> context
    # "+ return x" -> added line 4
    assert fc.added_lines == [2, 4]
    assert fc.deleted_anchors == [1]


def test_parse_unified_diff_zero_context() -> None:
    changes = parse_unified_diff(DIFF_ZERO_CONTEXT)
    assert len(changes) == 1
    fc = changes[0]
    assert fc.path == "c.py"
    assert fc.added_lines == [2]
    assert fc.deleted_anchors == [1]


def test_parse_unified_diff_new_file() -> None:
    changes = parse_unified_diff(DIFF_NEW_FILE)
    assert len(changes) == 1
    fc = changes[0]
    assert fc.path == "new_mod.py"
    assert fc.added_lines == [1, 2, 3]
    assert fc.deleted_anchors == []


def test_parse_unified_diff_deleted_file() -> None:
    changes = parse_unified_diff(DIFF_DELETED_FILE)
    assert len(changes) == 1
    fc = changes[0]
    assert fc.path == "gone.py"
    assert fc.added_lines == []
    # hunk @@ -1,3 +0,0 @@: deletions anchored at new line 1
    assert fc.deleted_anchors == [1, 1, 1]


# ------------------------------------------------------------------
# Unit tests: changed-component location (line span matching)
# ------------------------------------------------------------------

class _FakeMeta:
    def __init__(self, rel: str, start: int, end: int):
        self.relative_path = rel
        self.start_line = start
        self.end_line = end


def _fake_components() -> Dict[str, Any]:
    return {
        "b.py::func_b": _FakeMeta("b.py", 1, 5),
        "b.py::func_c": _FakeMeta("b.py", 7, 9),
        "a.py::func_a": _FakeMeta("a.py", 1, 3),
    }


def test_locate_changed_components_exact_function() -> None:
    from codewiki.mcp.tools.change_analysis import FileChange

    changes = [
        FileChange(path="b.py", added_lines=[3], deleted_anchors=[]),  # inside func_b
    ]
    located = locate_changed_components(_fake_components(), changes)
    assert located["changed_component_ids"] == {"b.py::func_b"}
    assert located["file_level_changes"] == []
    assert located["deleted_unlocated"] == []


def test_locate_changed_components_deleted_anchor_falls_outside() -> None:
    from codewiki.mcp.tools.change_analysis import FileChange

    # anchor at line 6 is between func_b (1-5) and func_c (7-9)
    changes = [FileChange(path="b.py", added_lines=[], deleted_anchors=[6])]
    located = locate_changed_components(_fake_components(), changes)
    assert located["changed_component_ids"] == set()
    assert located["deleted_unlocated"] == [{"file": "b.py", "anchor_line": 6}]


def test_locate_changed_components_untracked() -> None:
    from codewiki.mcp.tools.change_analysis import FileChange

    changes = [FileChange(path="new_mod.py", added_lines=[1, 2], is_untracked=True)]
    located = locate_changed_components(_fake_components(), changes)
    assert located["changed_component_ids"] == set()
    assert located["untracked_files"] == ["new_mod.py"]


# ------------------------------------------------------------------
# Unit tests: test suggestion heuristics
# ------------------------------------------------------------------

def test_test_candidates_for() -> None:
    cands = _test_candidates_for("src/auth/login.py")
    assert "src/auth/test_login.py" in cands
    assert "src/auth/login_test.py" in cands
    assert "tests/auth/test_login.py" in cands
    cands_go = _test_candidates_for("service/order.go")
    assert "service/order_test.go" in cands_go


def test_suggest_tests_filesystem(tmp_path) -> None:
    (tmp_path / "service").mkdir()
    (tmp_path / "service" / "order.py").write_text("def order(): pass\n", encoding="utf-8")
    (tmp_path / "service" / "test_order.py").write_text("def test_order(): pass\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_order.py").write_text("def test_order(): pass\n", encoding="utf-8")

    comps = {"service/order.py::order": _FakeMeta("service/order.py", 1, 1)}
    suggested = suggest_tests(comps, {"service/order.py::order"}, repo_path=str(tmp_path))
    files = {s["file"] for s in suggested}
    assert "service/test_order.py" in files
    assert "tests/test_order.py" in files


# ------------------------------------------------------------------
# Integration tests: real temp git repo + analyze_repo pipeline
# ------------------------------------------------------------------

PY_A = '''"""module a"""
def func_a():
    return 1
'''

PY_B = '''"""module b"""
import a

def func_b():
    return a.func_a()

def func_other():
    return 42
'''

PY_C = '''"""module c"""
import b

def func_c():
    return b.func_b()
'''

PY_C_TEST = '''"""tests for c"""
import c

def test_func_c():
    assert c.func_c() == 1
'''


@pytest.fixture()
def analyzed_repo(tmp_path):
    """A temp git repo with a.py/b.py/c.py analyzed into a CodeWiki session."""
    (tmp_path / "a.py").write_text(PY_A, encoding="utf-8")
    (tmp_path / "b.py").write_text(PY_B, encoding="utf-8")
    (tmp_path / "c.py").write_text(PY_C, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_c.py").write_text(PY_C_TEST, encoding="utf-8")

    repo = git.Repo.init(str(tmp_path))
    repo.git.config("user.name", "test")
    repo.git.config("user.email", "test@example.com")
    # NOTE: index.add(".") is broken on GitPython 3.1.50 Windows — it walks
    # into .git/ and stages paths like "./a.py" (prefix), which makes git
    # treat real files as untracked. Add explicit paths instead.
    repo.index.add(["a.py", "b.py", "c.py", "tests/test_c.py"])
    repo.index.commit("initial")

    store = SessionStore()
    resp = json.loads(
        handle_analyze_repo(
            {"repo_path": str(tmp_path), "output_dir": str(tmp_path / "repowiki"), "incremental": False},
            store,
        )
    )
    assert "error" not in resp, resp
    return tmp_path, store


def _run_changes(repo_path, store, **overrides) -> Dict[str, Any]:
    from codewiki.mcp.tools.change_analysis import handle_analyze_changes

    args = {"repo_path": str(repo_path), **overrides}
    raw = handle_analyze_changes(args, store)
    parsed = json.loads(raw)
    assert "error" not in parsed, parsed
    return parsed


def _read_workspace_file(resp: Dict[str, Any]) -> Dict[str, Any]:
    with open(resp["file"], encoding="utf-8") as fh:
        return json.load(fh)


def test_analyze_changes_worktree_precision(analyzed_repo) -> None:
    """Modifying one line inside func_b locates func_b only (not func_other),
    and blast radius reaches func_c (its transitive caller)."""
    tmp_path, store = analyzed_repo
    # Bump func_b's inner line — func_other stays untouched.
    (tmp_path / "b.py").write_text(
        PY_B.replace("return a.func_a()", "return a.func_a() + 1"), encoding="utf-8"
    )

    resp = _run_changes(tmp_path, store, worktree=True)
    full = _read_workspace_file(resp)

    changed = [c["name"] for c in full["changed_components"]]
    assert changed == ["func_b"], changed  # func_other must NOT be flagged

    affected = [c["name"] for c in full["affected_components"]]
    assert "func_c" in affected, affected  # func_c calls func_b
    assert "func_b" in affected  # start node included at depth 0

    tests = [t["file"] for t in full["suggested_tests"]]
    assert "tests/test_c.py" in tests, tests


def test_analyze_changes_commit_range(analyzed_repo) -> None:
    """Committed change: since='HEAD~1' sees the same blast radius."""
    tmp_path, store = analyzed_repo
    (tmp_path / "b.py").write_text(
        PY_B.replace("return a.func_a()", "return a.func_a() + 1"), encoding="utf-8"
    )
    repo = git.Repo(str(tmp_path))
    repo.index.add("b.py")
    repo.index.commit("modify func_b")

    resp = _run_changes(tmp_path, store, since="HEAD~1")
    full = _read_workspace_file(resp)

    changed = [c["name"] for c in full["changed_components"]]
    assert changed == ["func_b"], changed
    affected = [c["name"] for c in full["affected_components"]]
    assert "func_c" in affected


def test_analyze_changes_untracked_hint(analyzed_repo) -> None:
    """An untracked file is reported as a hint, never guessed as a component.

    The response is inline (no workspace file): start_ids is empty, so the
    handler returns the compact branch without write_result().
    """
    tmp_path, store = analyzed_repo
    (tmp_path / "new_mod.py").write_text("def fresh():\n    pass\n", encoding="utf-8")

    resp = _run_changes(tmp_path, store, worktree=True)
    assert resp["changed_components"] == []
    assert resp["untracked_files"] == ["new_mod.py"]
    assert any("new_mod.py" in fl["file"] for fl in resp["file_level_changes"])


def test_analyze_changes_no_changes(analyzed_repo) -> None:
    """Clean worktree + no since → informative empty result, not an error."""
    tmp_path, store = analyzed_repo
    from codewiki.mcp.tools.change_analysis import handle_analyze_changes

    raw = handle_analyze_changes({"repo_path": str(tmp_path), "worktree": True}, store)
    parsed = json.loads(raw)
    assert parsed["summary"]["total_affected"] == 0
    assert "No source-code changes" in parsed["summary"]["hint"]


def test_analyze_impact_still_works_after_changes(analyzed_repo) -> None:
    """analyze_changes must not disturb the session for analyze_impact."""
    tmp_path, store = analyzed_repo
    (tmp_path / "b.py").write_text(
        PY_B.replace("return a.func_a()", "return a.func_a() + 1"), encoding="utf-8"
    )
    _run_changes(tmp_path, store, worktree=True)

    raw = handle_analyze_impact(
        {"repo_path": str(tmp_path), "component_ids": ["b.py::func_b"], "direction": "depended_by"},
        store,
    )
    parsed = json.loads(raw)
    assert "error" not in parsed
