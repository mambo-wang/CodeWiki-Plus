"""MCP tool: analyze_changes — git-diff driven blast-radius analysis.

Answers "what does my change affect?" after editing code.  Two input modes:

* ``since``  — committed range ``git diff <since>..HEAD`` (e.g. ``HEAD~1``)
* ``worktree`` — uncommitted changes (staged + unstaged + untracked)

The diff is parsed at *line level* (``--unified=0`` hunks), then changed
lines are matched against component line spans (``start_line``..``end_line``)
so the blast radius starts from the exact functions whose lines changed —
not whole files.  Transitive impact (``depended_by``) then answers which
callers are affected, and a naming-convention heuristic suggests regression
test files.

Known limitations (deliberately punted):
* Deleted lines exist in the OLD file version; they are anchored to the
  nearest NEW-file line and may miss when a whole function was deleted
  (its component no longer exists in the graph).  Such lines are reported
  as ``deleted_unlocated`` instead of silently dropped.
* Untracked files are not in the graph yet; they are reported as a hint to
  re-run ``analyze_repo`` rather than guessed.
"""

from __future__ import annotations

import json
import logging
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.workspace_result import write_result
from codewiki.src.be.dependency_analyzer.topo_sort import (
    build_graph_from_components,
    transitive_impact,
)

logger = logging.getLogger(__name__)

# Source extensions the analyzers cover (mirrors cache.py _SRC_EXTS).
_SRC_EXTS = {
    ".py",
    ".pyx",
    ".java",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cc",
    ".hh",
    ".cs",
    ".kt",
    ".kts",
    ".go",
    ".php",
}

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_DIFF_FILE_RE = re.compile(r"^diff --git a/(.*?) b/(.*)$")
_NEW_FILE_RE = re.compile(r"^\+\+\+ b/(.*)$")


# ------------------------------------------------------------------
# Diff parsing (pure text, no git required — unit-testable)
# ------------------------------------------------------------------


@dataclass
class FileChange:
    """Line-level changes for a single file.

    ``added_lines`` are line numbers in the NEW file version.
    ``deleted_anchors`` are NEW-file line numbers near each deleted line
    (the anchor is the last line before the deletion point; ``1`` when the
    deletion starts at the top of the file).
    """

    path: str
    added_lines: List[int] = field(default_factory=list)
    deleted_anchors: List[int] = field(default_factory=list)
    is_untracked: bool = False


def _norm(p: str) -> str:
    """Normalize a repo-relative path to forward slashes without "./" prefixes.

    ``git diff`` (and GitPython on Windows) can emit paths like ``./b.py`` or
    ``a/./b.py``; normpath collapses those so they match component
    ``relative_path`` values. Empty input stays empty (normpath("") is ".").
    """
    p = p.replace("\\", "/")
    return posixpath.normpath(p) if p else ""


def parse_unified_diff(diff_text: str) -> List[FileChange]:
    """Parse a unified diff (``git diff --unified=0`` or with context).

    Returns one :class:`FileChange` per changed file, with line numbers
    resolved relative to the file versions:
      - ``+`` lines → new-file line numbers (``added_lines``)
      - ``-`` lines → anchored new-file position (``deleted_anchors``)
    """
    changes: Dict[str, FileChange] = {}
    current: Optional[FileChange] = None
    old_line = new_line = 0

    for raw in diff_text.splitlines():
        line = raw.rstrip("\r")
        if line.startswith("diff --git "):
            m = _DIFF_FILE_RE.match(line)
            if not m:
                current = None
                continue
            path = _norm(m.group(2))
            current = changes.setdefault(path, FileChange(path=path))
            old_line = new_line = 0
            continue
        if line.startswith("@@ "):
            m = _HUNK_RE.match(line)
            if not m or current is None:
                continue
            old_line = int(m.group(1))
            new_line = int(m.group(3))
            continue
        if current is None:
            continue
        # Metadata lines ("+++ b/x", "--- a/x", "index ...", "new file mode",
        # "Binary files differ", "\\ No newline at end of file") are not hunks.
        if line.startswith(
            (
                "+++ ",
                "--- ",
                "index ",
                "new file mode",
                "deleted file mode",
                "similarity index",
                "rename from",
                "rename to",
                "Binary files",
                "\\ No newline",
            )
        ):
            continue
        if line.startswith("+"):
            current.added_lines.append(new_line)
            new_line += 1
        elif line.startswith("-"):
            # Anchor: last NEW-file line before the deletion point.
            anchor = max(1, new_line - 1)
            current.deleted_anchors.append(anchor)
            old_line += 1
        elif line.startswith(" "):
            old_line += 1
            new_line += 1
        # "\\ No newline at end of file" and other metadata lines are ignored.

    return list(changes.values())


# ------------------------------------------------------------------
# Git diff acquisition
# ------------------------------------------------------------------


def _git_diff_since(repo: Any, since: str) -> str:
    """Committed range diff ``since..HEAD`` as unified text."""
    try:
        return str(repo.git.diff(f"{since}..HEAD", unified=0) or "")
    except Exception as exc:  # GitCommandError / BadName etc.
        raise ValueError(f"Invalid 'since' range {since!r}: {exc}")


def _git_diff_worktree(repo: Any) -> Tuple[str, List[str]]:
    """Uncommitted diff (staged + unstaged) plus untracked file paths.

    Untracked files come from ``git ls-files --others --exclude-standard``
    (NUL-separated) — ``Repo.untracked_files`` is unreliable on Windows
    (GitPython 3.1.50 can list already-tracked files).
    """
    staged = str(repo.git.diff(cached=True, unified=0) or "")
    unstaged = str(repo.git.diff(unified=0) or "")
    raw = repo.git.ls_files("--others", "--exclude-standard", z=True)
    untracked = [p for p in raw.split("\x00") if p] if raw else []
    return staged + "\n" + unstaged, untracked


def _repo_subdir(repo_path: Path, git_root: Path) -> str:
    """Repo-relative subdir prefix ('' when repo_path == git root).

    ``Path.relative_to`` on identical paths yields ``Path('.')`` whose
    ``as_posix()`` is ``'.'`` — normalize that back to ``''`` so callers can
    treat empty as "no subdir filter".
    """
    try:
        rel = repo_path.resolve().relative_to(git_root.resolve())
    except ValueError:
        return ""
    return "" if rel == Path(".") else rel.as_posix()


def collect_git_changes(
    repo_path: str,
    *,
    since: Optional[str] = None,
    worktree: bool = True,
) -> Dict[str, Any]:
    """Collect line-level changes from git for *repo_path*.

    Returns ``{"changes": List[FileChange], "untracked": List[FileChange],
    "git_root": str, "source": "worktree"|"commit:<since>"}``.
    Raises ``ValueError`` when git is unavailable or no commits exist.
    """
    import git

    repo = git.Repo(str(repo_path), search_parent_directories=True)
    git_root = Path(repo.working_dir).resolve()
    sub = _repo_subdir(Path(repo_path), git_root)

    def _keep(p: str) -> Optional[str]:
        """Filter paths outside repo_path's subtree; return repo-relative posix path."""
        p = _norm(p)
        if sub and not (p == sub or p.startswith(sub + "/")):
            return None
        return p[len(sub) + 1 :] if sub else p

    def _ext(path: str) -> bool:
        return Path(path).suffix.lower() in _SRC_EXTS

    if since:
        diff_text = _git_diff_since(repo, since)
        changes = [c for c in parse_unified_diff(diff_text) if _ext(c.path)]
        return {
            "changes": changes,
            "untracked": [],
            "git_root": str(git_root),
            "source": f"commit:{since}",
        }

    diff_text, untracked_paths = _git_diff_worktree(repo)
    changes = [c for c in parse_unified_diff(diff_text) if _ext(c.path)]

    untracked: List[FileChange] = []
    for up in untracked_paths:
        kept = _keep(up)
        if not kept or not _ext(kept):
            continue
        full = git_root / up
        try:
            n_lines = len(full.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
        untracked.append(
            FileChange(path=kept, added_lines=list(range(1, n_lines + 1)), is_untracked=True)
        )

    return {
        "changes": changes + untracked,
        "untracked": [c.path for c in untracked],
        "git_root": str(git_root),
        "source": "worktree",
    }


# ------------------------------------------------------------------
# Changed-function location (line numbers → component spans)
# ------------------------------------------------------------------


def _file_components(components: Any) -> Dict[str, List[Tuple[str, int, int]]]:
    """Build relative_path → [(comp_id, start_line, end_line)] index."""
    index: Dict[str, List[Tuple[str, int, int]]] = {}
    for cid, meta in components.items():
        rel = _norm(getattr(meta, "relative_path", "") or "")
        if not rel:
            continue
        index.setdefault(rel, []).append(
            (cid, int(getattr(meta, "start_line", 0) or 0), int(getattr(meta, "end_line", 0) or 0))
        )
    return index


def _locate_components_for_lines(
    file_comps: List[Tuple[str, int, int]],
    lines: List[int],
) -> Set[str]:
    """Return component IDs whose [start, end] span contains any line."""
    hit: Set[str] = set()
    for ln in lines:
        for cid, start, end in file_comps:
            if start <= ln <= end:
                hit.add(cid)
    return hit


def locate_changed_components(
    components: Any,
    changes: List[FileChange],
) -> Dict[str, Any]:
    """Map line-level changes to graph components (function-level precision).

    Returns::

        {
          "changed_component_ids": Set[str],
          "file_level_changes": [{"file": ..., "reason": ...}],   # no line hit
          "deleted_unlocated": [{"file": ..., "old_line": ..., "anchor": ...}],
          "untracked_files": [path, ...],                          # not in graph
        }
    """
    index = _file_components(components)
    changed: Set[str] = set()
    file_level: List[Dict[str, str]] = []
    deleted_unlocated: List[Dict[str, Any]] = []
    untracked_files: List[str] = []

    for fc in changes:
        if fc.is_untracked:
            untracked_files.append(fc.path)
            file_level.append(
                {
                    "file": fc.path,
                    "reason": "untracked file not in analysis graph — re-run analyze_repo",
                }
            )
            continue

        file_comps = index.get(fc.path, [])
        if not file_comps:
            continue  # file changed but not analyzed (excluded pattern etc.)

        added_hit = _locate_components_for_lines(file_comps, fc.added_lines)
        deleted_hit = _locate_components_for_lines(file_comps, fc.deleted_anchors)
        changed.update(added_hit)
        changed.update(deleted_hit)

        # Deleted lines anchored outside any component (e.g. whole function
        # removed, or deleted at module level) — report, do not drop silently.
        anchored_outside = [
            ln
            for ln in fc.deleted_anchors
            if not any(start <= ln <= end for _, start, end in file_comps)
        ]
        for ln in anchored_outside:
            deleted_unlocated.append({"file": fc.path, "anchor_line": ln})

        if not added_hit and not deleted_hit:
            file_level.append(
                {"file": fc.path, "reason": "changed lines not inside any analyzed component"}
            )

    return {
        "changed_component_ids": changed,
        "file_level_changes": file_level,
        "deleted_unlocated": deleted_unlocated,
        "untracked_files": untracked_files,
    }


# ------------------------------------------------------------------
# Test suggestion (naming-convention heuristic)
# ------------------------------------------------------------------

_TEST_DIR_RE = re.compile(r"(^|/)(tests?|spec|__tests__)(/|$)", re.IGNORECASE)
_EXT_RE = re.compile(r"\.[A-Za-z0-9]+$")

_TEST_STEM_MARKERS = ("test_", "Test", "Tests", "_test", "_spec", ".test", ".spec")


def _is_test_path(rel: str) -> bool:
    p = _norm(rel)
    if _TEST_DIR_RE.search(p):
        return True
    name = p.rsplit("/", 1)[-1]
    return any(
        name.startswith(m) or name.endswith(m)
        for m in ("test_", "Test", "Tests", "_test", "_spec", ".test", ".spec")
    )


def _strip_ext(name: str) -> str:
    return _EXT_RE.sub("", name)


def _test_candidates_for(source: str) -> List[str]:
    """Possible test file relpaths for a source file (heuristic)."""
    src = _norm(source)
    parts = src.split("/")
    name = parts[-1]
    stem = _strip_ext(name)
    dirpath = "/".join(parts[:-1])
    cands: List[str] = []
    for fmt in (
        "test_{stem}.py",
        "test_{stem}.go",
        "{stem}Test.java",
        "{stem}Tests.java",
        "{stem}_test.py",
        "{stem}_test.go",
        "{stem}.test.js",
        "{stem}.test.ts",
        "{stem}.spec.js",
        "{stem}.spec.ts",
    ):
        fname = fmt.format(stem=stem)
        cands.append(f"{dirpath}/{fname}" if dirpath else fname)
        # tests/ mirror of the source's parent dir (src/foo/bar.py → tests/foo/test_bar.py)
        parent = parts[-2] if len(parts) >= 2 else ""
        if parent:
            cands.append(f"tests/{parent}/{fname}")
        # flat tests/ mirror (tests/test_bar.py)
        cands.append(f"tests/{fname}")
        cands.append(f"test/{fname}")
    return cands


def suggest_tests(
    components: Any,
    affected_ids: Set[str],
    repo_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Suggest regression-test files covering the affected surface.

    Test files are excluded from the analysis graph by design, so this uses
    naming-convention candidates checked against the *filesystem*: for each
    affected source file, look for same-dir ``test_<base>`` / ``<base>_test`` /
    ``<base>Test`` / ``<base>.test`` / ``<base>.spec`` or a ``tests/`` mirror.
    Graph components that happen to be test files are appended as bonus hits.
    """
    affected_files: Set[str] = set()
    for cid in affected_ids:
        meta = components.get(cid)
        if meta is not None:
            rel = _norm(getattr(meta, "relative_path", "") or "")
            if rel:
                affected_files.add(rel)

    candidates: Set[str] = set()
    for f in affected_files:
        candidates.update(_test_candidates_for(f))

    results: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    repo_root = Path(repo_path).resolve() if repo_path else None
    for cand in sorted(candidates):
        if repo_root is not None and (repo_root / cand).is_file():
            results.append({"file": cand, "exists": True})
            seen.add(cand)

    # Bonus: test components already present in the graph (e.g. user analyzed
    # tests explicitly via include_patterns).
    for cid, meta in components.items():
        rel = _norm(getattr(meta, "relative_path", "") or "")
        if not rel or not _is_test_path(rel) or rel not in candidates:
            continue
        if rel in seen:
            continue
        seen.add(rel)
        results.append(
            {
                "file": rel,
                "component_id": cid,
                "component_name": getattr(meta, "name", cid),
                "exists": True,
            }
        )
    return results


# ------------------------------------------------------------------
# Main handler
# ------------------------------------------------------------------


def handle_analyze_changes(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Analyze blast radius of a git change (commit range or working tree).

    Parameters (via *arguments*)
    ----------------------------
    repo_path : str
        Repository path. Auto-restores the session from the SQLite
        cache if a previous analysis exists.
    since : str, optional
        Committed range ``git diff <since>..HEAD`` (e.g. ``HEAD~1``).
        Mutually exclusive with *worktree* (takes precedence).
    worktree : bool
        Analyze uncommitted changes: staged + unstaged + untracked
        (default True).
    direction : str
        ``"depended_by"`` (default, who calls the changed functions,
        transitively) | ``"depends_on"`` | ``"both"``.
    max_depth : int
        Maximum BFS depth (default 10).
    """
    from codewiki.mcp.tools.workspace_result import resolve_session

    session = resolve_session(arguments, store)
    if session is None:
        return json.dumps(
            {
                "error": "Session not found. Provide a valid repo_path pointing to a previously analyzed repository."
            }
        )

    components = session.components
    repo_path = session.repo_path
    since = arguments.get("since")
    worktree = bool(arguments.get("worktree", True))
    direction = arguments.get("direction", "depended_by")
    max_depth = min(int(arguments.get("max_depth", 10)), 50)

    if not since and not worktree:
        return json.dumps(
            {"error": "Provide 'since' (commit range) or set worktree=true (uncommitted changes)."}
        )

    try:
        git_info = collect_git_changes(repo_path, since=since or None, worktree=worktree)
    except ValueError as exc:
        return json.dumps({"error": f"Git analysis failed: {exc}"})
    except Exception as exc:
        logger.warning("Git collection failed for %s: %s", repo_path, exc)
        return json.dumps({"error": f"Git analysis failed: {exc}"})

    changes: List[FileChange] = git_info["changes"]
    if not changes:
        return json.dumps(
            {
                "query": {"repo_path": repo_path, "since": since, "worktree": worktree},
                "summary": {
                    "total_affected": 0,
                    "changed_components": 0,
                    "changed_files": 0,
                    "source": git_info["source"],
                    "hint": "No source-code changes found for the requested range.",
                },
                "changed_components": [],
                "affected_components": [],
                "suggested_tests": [],
            },
            indent=2,
            ensure_ascii=False,
        )

    located = locate_changed_components(components, changes)
    start_ids: Set[str] = located["changed_component_ids"]

    if not start_ids:
        return json.dumps(
            {
                "query": {"repo_path": repo_path, "since": since, "worktree": worktree},
                "summary": {
                    "total_affected": 0,
                    "changed_components": 0,
                    "changed_files": len(changes),
                    "source": git_info["source"],
                    "hint": "Changed lines fall outside analyzed components "
                    "(untracked files or removed functions). Re-run analyze_repo for new files.",
                },
                "changed_files": [c.path for c in changes],
                "changed_components": [],
                "affected_components": [],
                "suggested_tests": [],
                "file_level_changes": located["file_level_changes"],
                "deleted_unlocated": located["deleted_unlocated"],
                "untracked_files": located["untracked_files"],
            },
            indent=2,
            ensure_ascii=False,
        )

    # --- Transitive impact --------------------------------------------
    graph = build_graph_from_components(components)
    result = transitive_impact(
        graph, start_ids, max_depth=max_depth, direction=direction, track_paths=False
    )
    affected: Dict[str, int] = result["affected"]

    # --- Enrich -------------------------------------------------------
    meta_map: Dict[str, Any] = dict(components.items())
    changed_list: List[Dict[str, Any]] = []
    for cid in sorted(start_ids):
        meta = meta_map.get(cid)
        changed_list.append(
            {
                "component_id": cid,
                "name": getattr(meta, "name", cid) if meta else cid,
                "file_path": _norm(getattr(meta, "relative_path", "") or "") if meta else "",
                "component_type": getattr(meta, "component_type", "unknown") if meta else "unknown",
            }
        )

    affected_list: List[Dict[str, Any]] = []
    for cid, depth in sorted(affected.items(), key=lambda x: (x[1], x[0])):
        meta = meta_map.get(cid)
        if meta is None:
            continue
        affected_list.append(
            {
                "component_id": cid,
                "name": getattr(meta, "name", cid),
                "file_path": _norm(getattr(meta, "relative_path", "") or ""),
                "component_type": getattr(meta, "component_type", "unknown"),
                "depth": depth,
            }
        )

    suggested = suggest_tests(components, set(affected.keys()), repo_path=repo_path)

    # --- Assemble -----------------------------------------------------
    full_result: Dict[str, Any] = {
        "query": {
            "repo_path": repo_path,
            "since": since,
            "worktree": worktree,
            "direction": direction,
            "max_depth": max_depth,
            "source": git_info["source"],
        },
        "summary": {
            "changed_files": len(changes),
            "changed_components": len(changed_list),
            "total_affected": len(affected_list),
            "suggested_tests": len(suggested),
            "max_depth": max(affected.values()) if affected else 0,
        },
        "changed_components": changed_list,
        "affected_components": affected_list,
        "suggested_tests": suggested,
    }
    if located["file_level_changes"]:
        full_result["file_level_changes"] = located["file_level_changes"]
    if located["deleted_unlocated"]:
        full_result["deleted_unlocated"] = located["deleted_unlocated"]
    if located["untracked_files"]:
        full_result["untracked_files"] = located["untracked_files"]

    response = write_result(
        session,
        "change_analysis.json",
        full_result,
        summary={
            "changed_files": len(changes),
            "changed_components": len(changed_list),
            "total_affected": len(affected_list),
            "suggested_tests": len(suggested),
            "source": git_info["source"],
            "hint": "Read the file for full change-impact data including per-component details.",
        },
    )

    return json.dumps(response, indent=2, ensure_ascii=False)
