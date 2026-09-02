"""Team-layout Phase 4 (first slice): read-only remote-sync advisory.

Implements D14 (Rev. 3): ``sync_check`` runs ``git fetch`` (read-only — it
never touches the working tree) at most once per process per repository,
compares HEAD with its upstream, and returns an advisory message when the
remote has moved.  The advisory is attached to tool results so the drift
information reaches the conversation (the Agent relays it); it never
blocks, never raises, never pulls.

Design anchors (docs/团队化文件冲突治理与同步策略设计方案.md §6):
  - mode: off | advisory | session_ff_only   (conventions.git_sync.mode)
  - D14: advisory is the DEFAULT — zero risk (read-only, silent degrade,
    once per process) yet it protects every real team member from writing
    on a stale baseline.
  - D11: for repos that mix business code (single-repo / colocated
    business repos) the tool performs NO git mutations at all — knowledge
    rides along with the user's own pulls ("搭便车").  sync_check's fetch
    is compatible with that contract precisely because it is read-only.
  - session_ff_only / auto_push belong to the SECOND slice and are gated
    per D17 ("repowiki's repo must not contain business code").

Failure contract (D12, "data intact, arrives later"): any failure — no git,
offline, credentials, timeout — degrades to "no advisory for this process"
and is never retried, never raised.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional, Set

logger = logging.getLogger(__name__)

_GIT_TIMEOUT = 15  # seconds — advisory must never stall a tool call

# once per process per repository (design §6.2 frequency gate)
_checked_repos: Set[str] = set()


def _resolve_mode(output_dir: Path) -> str:
    """conventions.git_sync.mode — default 'advisory' (D14)."""
    try:
        from codewiki.mcp.tools.page_router import load_schema

        schema = load_schema(str(output_dir))
        git_sync = (schema.get("conventions") or {}).get("git_sync") or {}
        mode = str(git_sync.get("mode") or "advisory").strip()
        return mode if mode in ("off", "advisory", "session_ff_only") else "advisory"
    except Exception:
        return "advisory"


def _run_git(repo_root: Path, args: list) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT,
        )
        if proc.returncode == 0:
            return proc.stdout
    except Exception as e:  # timeout / no git / offline — silent degrade
        logger.debug("git %s failed (advisory only): %s", args[0], e)
    return None


def _find_repo_root(start: Path) -> Optional[Path]:
    cur = start.resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def sync_check(output_dir: str | Path, *, force: bool = False) -> Optional[str]:
    """Read-only remote-drift advisory; None when there is nothing to say.

    Runs at most once per process per repository (pass force=True to
    re-check, e.g. a user-invoked status command).  Never raises; failures
    degrade to None for the rest of the process (no retry loop — an offline
    machine must not pay a 15s timeout on every call).
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        return None
    if _resolve_mode(output_dir) == "off":
        return None

    repo_root = _find_repo_root(output_dir)
    if repo_root is None:
        return None  # not a git repo — knowledge never leaves this machine
    key = str(repo_root)
    if not force and key in _checked_repos:
        return None
    _checked_repos.add(key)  # claim the slot BEFORE running — failures count too

    # 1) read-only fetch (never touches the working tree)
    if _run_git(repo_root, ["fetch", "--quiet"]) is None:
        return None  # offline / credentials / timeout → silent for this process

    # 2) HEAD vs upstream
    upstream = _run_git(
        repo_root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]
    )
    if not upstream or not upstream.strip():
        return None  # no upstream configured (local-only repo) — nothing to compare
    ahead = _run_git(repo_root, ["rev-list", "--count", "@{upstream}..HEAD"])
    behind = _run_git(repo_root, ["rev-list", "--count", "HEAD..@{upstream}"])
    try:
        n_ahead, n_behind = int((ahead or "0").strip()), int((behind or "0").strip())
    except ValueError:
        return None

    if n_ahead and n_behind:
        return (
            f"git_sync: 本地与远端已分叉（领先 {n_ahead} / 落后 {n_behind} 提交）——"
            "当前写入基于过期基线，建议先同步远端知识再继续。"
        )
    if n_behind:
        return (
            f"git_sync: 远端已前进 {n_behind} 个提交——当前写入基于过期基线，"
            "建议先同步（git pull）再写入知识文件。"
        )
    return None
