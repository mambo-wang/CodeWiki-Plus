"""Team-layout Phase 4 git sync: read-only advisory + gated auto-sync.

Two slices:

**First slice (D14)** — :func:`sync_check`: ``git fetch`` (read-only — it
never touches the working tree) at most once per process per repository,
compares HEAD with its upstream, and returns an advisory when the remote
has moved.  Default mode ``advisory``; ``off`` silences it.

**Second slice (D17, design review 2026-09-02)** — :func:`session_ff_only`
and :func:`auto_push`, gated on the STRUCTURAL rule "the repowiki's repo
must not contain business code": the repo holding ``repowiki/`` must BE a
workspace root (``repowiki/.meta/workspace.json`` — centralized OR
colocated; both keep business sub-repos as separate ignored clones, so the
root tree is pure knowledge).  Single repos and business repos never carry
the workspace config, so they never qualify.  Stray untracked business
files in a root are still protected by session_ff_only's clean-tree gate.

Design-review decisions (2026-09-02):
  - A: auto_push anchors = close_session / batch_ingest /
    capture_conversation / distill submit (natural batch boundaries).
  - B: commits use the repo's existing git identity, message prefixed
    ``codewiki:`` (never touch the user's git config).
  - C: session_ff_only / auto_push default OFF; a harness maintainer
    enables them in schema.yaml (config travels with the repo).

Failure contract (D12, "data intact, arrives later"): any failure — no git,
offline, credentials, timeout, push race — degrades to "report and keep
the local state"; auto_push keeps its local commit so the next successful
push piggy-backs it.  Nothing is ever force-pushed or reset.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional, Set

logger = logging.getLogger(__name__)

_GIT_TIMEOUT = 15  # seconds — advisory must never stall a tool call

_PUSH_RETRIES = 5  # D10: fetch+rebase retry budget on push races

# once per process per repository (design §6.2 frequency gate)
_checked_repos: Set[str] = set()
_ff_pulled_repos: Set[str] = set()


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


def _run_git_result(repo_root: Path, args: list) -> Optional[subprocess.CompletedProcess]:
    """Like _run_git but returns the full result (callers need stderr/rc)."""
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT,
        )
    except Exception as e:
        logger.debug("git %s raised: %s", args[0], e)
        return None


def _resolve_auto_push(output_dir: Path) -> bool:
    """conventions.git_sync.auto_push — default False (decision C)."""
    try:
        from codewiki.mcp.tools.page_router import load_schema

        schema = load_schema(str(output_dir))
        git_sync = (schema.get("conventions") or {}).get("git_sync") or {}
        return bool(git_sync.get("auto_push", False))
    except Exception:
        return False


def _is_workspace_root_repo(output_dir: Path, repo_root: Path) -> bool:
    """D17 gate: the repo holding repowiki/ IS a workspace root."""
    try:
        od = output_dir.resolve()
        if od.parent != repo_root.resolve():
            return False
    except OSError:
        return False
    return (od / ".meta" / "workspace.json").is_file()


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


def session_ff_only(output_dir: str | Path) -> Optional[str]:
    """Session-start fast-forward pull (second slice, decision C: explicit).

    Runs once per process per repo, only when mode == session_ff_only AND
    the D17 gate passes (repowiki's repo IS a workspace root).  Pulls with
    ``--ff-only`` on a CLEAN tree only; divergence/dirty tree skips with a
    report line.  Never merges, never rebases, never raises.
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir() or _resolve_mode(output_dir) != "session_ff_only":
        return None
    repo_root = _find_repo_root(output_dir)
    if repo_root is None or not _is_workspace_root_repo(output_dir, repo_root):
        return None
    key = str(repo_root)
    if key in _ff_pulled_repos:
        return None
    _ff_pulled_repos.add(key)

    # clean-tree precondition (stray untracked files block the pull)
    status = _run_git(repo_root, ["status", "--porcelain"])
    if status is None:
        return None
    if status.strip():
        return "git_sync: 工作树不干净，跳过会话拉取（session_ff_only 仅在干净树上执行）。"

    proc = _run_git_result(repo_root, ["pull", "--ff-only", "--quiet"])
    if proc is None:
        return None
    if proc.returncode == 0:
        return "git_sync: 已同步远端知识（ff-only）。"
    return (
        "git_sync: ff-only 拉取失败（远端与本地分叉或网络问题），本次会话不再自动拉取，请人工同步。"
    )


def auto_push(output_dir: str | Path, tool_name: str) -> Optional[str]:
    """Commit + push repowiki/ after a batch write (second slice).

    Gated on auto_push enabled (decision C) AND the D17 gate.  Stages ONLY
    ``<repowiki>/`` paths, commits with the repo's own git identity
    (decision B — message prefixed ``codewiki:``), pushes with fetch+rebase
    retry (D10, ≤5) on races.  On exhaustion the local commit is KEPT and
    the caller is told the next successful push carries it (D12).  Never
    force-pushes, never resets.
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir() or not _resolve_auto_push(output_dir):
        return None
    repo_root = _find_repo_root(output_dir)
    if repo_root is None or not _is_workspace_root_repo(output_dir, repo_root):
        return None

    try:
        rel = output_dir.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None

    # 1) stage only the knowledge tree
    if _run_git(repo_root, ["add", "-A", "--", rel]) is None:
        return None
    staged = _run_git(repo_root, ["diff", "--cached", "--name-only"])
    if not staged or not staged.strip():
        return None  # nothing new — skip silently

    # 2) commit with the repo's own identity (decision B)
    from datetime import date

    msg = f"codewiki: auto-sync knowledge ({tool_name}, {date.today().isoformat()})"
    if _run_git(repo_root, ["commit", "-q", "-m", msg]) is None:
        return "git_sync(auto_push): 提交失败，改动保留在工作区。"

    # 3) push with fetch+rebase retry (D10)
    for attempt in range(1, _PUSH_RETRIES + 1):
        proc = _run_git_result(repo_root, ["push", "--quiet"])
        if proc is not None and proc.returncode == 0:
            return f"git_sync(auto_push): 已推送知识变更（{tool_name}，第 {attempt} 次尝试）。"
        # push race → fetch + rebase, abort on conflict, retry
        _run_git(repo_root, ["fetch", "--quiet"])
        rebase = _run_git_result(repo_root, ["rebase", "@{upstream}"])
        if rebase is None or rebase.returncode != 0:
            _run_git(repo_root, ["rebase", "--abort"])

    return (
        f"git_sync(auto_push): 推送重试 {_PUSH_RETRIES} 次未成功，本地提交已保留，"
        "下次成功推送时自动搭载；请人工检查远端状态。"
    )
