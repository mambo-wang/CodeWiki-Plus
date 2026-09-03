"""Team-layout helpers: keep rebuildable derived files out of git.

Team-layout Phase 1 (docs/团队化文件冲突治理与同步策略设计方案.md §5.1):
git stores *content* only; every index/derived/runtime file listed in
``TEAM_LAYOUT_REBUILDABLE_FILES`` has a local rebuild path and must not be
committed — committing them only creates merge conflicts (timestamp churn,
whole-file rewrites, JSON array appends).

This module is the shared core used by three call sites:

* ``lint_wiki`` check ``team_layout_gitignore`` — reports still-tracked files;
* ``init_wiki`` — appends the ignore entries to the repo-root .gitignore;
* the ``codewiki migrate-team-layout`` CLI — untracks (``git rm --cached``)
  the files and updates .gitignore for existing repositories.

All git access goes through subprocess (list-arg form, no shell) with a
short timeout; every failure degrades to "nothing found / nothing done"
rather than raising — these are advisory hygiene operations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from codewiki.src.config import TEAM_LAYOUT_REBUILDABLE_FILES

logger = logging.getLogger(__name__)

# Marker block written into .gitignore so the append is idempotent and the
# entries are explainable in place (same style as the existing T2/T3 blocks).
_GITIGNORE_MARKER_BEGIN = "# Team-layout Phase 1: 可重建派生物不入库（D1，详见 docs/团队化文件冲突治理与同步策略设计方案.md）"

_GIT_TIMEOUT = 15  # seconds — local git ops, never worth blocking on


def find_repo_root(start: Path) -> Optional[Path]:
    """Walk up from *start* to the enclosing git repository root, or None.

    Like ``git rev-parse --show-toplevel`` but filesystem-only (no subprocess,
    no timeout, works in bare checkouts of subtrees).
    """
    cur = start.resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def _run_git(repo_root: Path, args: List[str]) -> Optional[str]:
    """Run a git subcommand in *repo_root*; return stdout or None on failure.

    Delegates to :func:`codewiki.src.git_sync.run_git_bounded` so ``timeout``
    is a hard wall-clock bound — ``subprocess.run(timeout=...)`` alone keeps
    waiting on pipes held by git's grandchildren (see that helper).
    """
    try:
        from codewiki.src.git_sync import run_git_bounded

        res = run_git_bounded(repo_root, args, timeout=_GIT_TIMEOUT)
        return res.stdout if res is not None else None
    except Exception as e:  # import failure, missing git, ...
        logger.debug("git %s unavailable: %s", args[0], e)
        return None


def list_tracked_rebuildables(repo_root: Path, output_dir: Path) -> List[str]:
    """Return repo-root-relative paths of tracked rebuildable files.

    A directory entry in TEAM_LAYOUT_REBUILDABLE_FILES (trailing ``/``)
    matches every tracked file under it.  Returns [] when git is
    unavailable or the repo has none tracked (the healthy state).
    """
    out = _run_git(repo_root, ["ls-files"])
    if out is None:
        return []
    tracked = [line.strip() for line in out.splitlines() if line.strip()]
    try:
        rel_output = output_dir.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return []  # output_dir outside the repo — nothing we manage
    hit: List[str] = []
    for entry in TEAM_LAYOUT_REBUILDABLE_FILES:
        full = f"{rel_output}/{entry}" if rel_output != "." else entry
        if full.endswith("/"):
            prefix = full
            hit.extend(t for t in tracked if t.startswith(prefix))
        else:
            if full in tracked:
                hit.append(full)
    return sorted(set(hit))


def gitignore_entries(repo_root: Path, output_dir: Path) -> List[str]:
    """Repo-root-relative .gitignore lines for the rebuildable set."""
    try:
        rel_output = output_dir.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return []
    prefix = f"{rel_output}/" if rel_output != "." else ""
    return [f"{prefix}{entry}" for entry in TEAM_LAYOUT_REBUILDABLE_FILES]


def ensure_gitignore_entries(repo_root: Path, output_dir: Path) -> Tuple[bool, List[str]]:
    """Append missing team-layout entries to the repo-root .gitignore.

    Idempotent: only lines not already present are added, wrapped in a
    marked block on first write.  Returns (changed, added_lines).  Never
    raises — failures are logged and reported as no-op.
    """
    entries = gitignore_entries(repo_root, output_dir)
    if not entries:
        return False, []
    gitignore = repo_root / ".gitignore"
    try:
        current = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    except OSError as e:
        logger.warning("Cannot read %s: %s", gitignore, e)
        return False, []
    missing = [e for e in entries if e not in current.splitlines()]
    if not missing:
        return False, []
    block_parts: List[str] = []
    if _GITIGNORE_MARKER_BEGIN not in current:
        if current and not current.endswith("\n"):
            block_parts.append("")
        block_parts.append(_GITIGNORE_MARKER_BEGIN)
    block_parts.extend(missing)
    try:
        with open(gitignore, "a", encoding="utf-8") as f:
            f.write("\n".join(block_parts) + "\n")
    except OSError as e:
        logger.warning("Cannot append to %s: %s", gitignore, e)
        return False, []
    return True, missing


def untrack_files(repo_root: Path, repo_relative_paths: List[str]) -> Tuple[bool, List[str]]:
    """``git rm --cached`` the given paths (files stay on disk).

    The index removal is staged but not committed — the caller/user reviews
    and commits.  Returns (ok, staged_paths); on git failure nothing is
    staged and the failure is logged.
    """
    if not repo_relative_paths:
        return True, []
    # batch: one rm invocation, list-args (no shell), paths from git ls-files
    # output only — never user input — so no injection surface.
    out = _run_git(repo_root, ["rm", "--cached", "--", *repo_relative_paths])
    if out is None:
        return False, []
    return True, repo_relative_paths
