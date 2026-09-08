"""Team-layout Phase 4 git sync: read-only advisory + gated auto-sync.

Two slices:

**First slice (D14)** — :func:`sync_check`: ``git fetch`` (read-only — it
never touches the working tree) at most once per process per repository,
compares HEAD with its upstream, and returns an advisory when the remote
has moved.  Default mode ``advisory``; ``off`` silences it.

**Second slice (D17, design review 2026-09-02)** — :func:`session_ff_only`
and :func:`auto_push`.  The D17 structural gate "the repo holding
``repowiki/`` must be a workspace root" was removed (2026-09-08) for both:
auto_push stages ONLY the knowledge subtree, and session_ff_only relies on
git's own ``--ff-only`` overwrite protection (no clean-tree pre-gate: an
update never touches local edits it would clobber) — so a colocated repo
(``repowiki/`` shares a git repo with business code) syncs too.  Both
operate on the whole branch: the branch, not the path, is the unit of
publication — auto_push's push carries unpushed business commits along,
and a session ff-only pull fast-forwards the entire working tree (a dirty
tree fast-forwards when the update skips its edits, refuses untouched when
they overlap; divergence refuses; no merge, no rebase, no overwrite).

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

import contextlib
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional, Set

logger = logging.getLogger(__name__)

_GIT_TIMEOUT = 15  # seconds — advisory must never stall a tool call

_PUSH_RETRIES = 5  # D10: fetch+rebase retry budget on push races

# once per process per repository (design §6.2 frequency gate)
_checked_repos: Set[str] = set()
_ff_pulled_repos: Set[str] = set()
# Repos whose auto_push is owned by an enclosing batch boundary.  Keyed by
# repo root (not output_dir) so nested items that resolve to the same repo
# are suppressed even when they carry their own output_dir.
_deferred_repos: Set[str] = set()


@contextlib.contextmanager
def defer_push(output_dir: str | Path):
    """Suppress :func:`auto_push` for *output_dir*'s repo inside the block.

    Per-item write tools (ingest_note, write_doc_file) push on their own, so
    a batch driver that loops over them would perform N commit+push round
    trips.  Wrap the loop in this so only the batch's own anchor push fires.
    Exception-safe: the flag is always cleared, even on a failed item.
    """
    root = _find_repo_root(Path(output_dir or "."))
    if root is None:
        yield
        return
    key = str(root)
    _deferred_repos.add(key)
    try:
        yield
    finally:
        _deferred_repos.discard(key)


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


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill *proc* and every child it spawned.

    ``git fetch`` spawns ``git-remote-https`` (plus credential helpers) and
    those grandchildren inherit the captured pipes. Killing only the direct
    child leaves ``communicate()`` waiting on a pipe that never reaches EOF,
    which is why a nominal 15s timeout could hold a call for minutes.
    """
    try:
        import psutil  # project dependency (see pyproject)

        parent = psutil.Process(proc.pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except Exception:
                pass
        try:
            parent.kill()
        except Exception:
            pass
        return
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def run_git_bounded(
    repo_root: Path, args: list, timeout: float = _GIT_TIMEOUT, *, ok_only: bool = True
) -> Optional[subprocess.CompletedProcess]:
    """Run ``git -C <repo_root> <args>`` under a HARD wall-clock bound.

    ``subprocess.run(timeout=...)`` alone is not enough here: when the timeout
    fires Python kills the direct child but keeps waiting for the inherited
    stdout/stderr pipes, which stay open while a grandchild holds them.
    Measured on a stalled fetch: a nominal 15s advisory held the MCP event
    loop for 204s, timing out every unrelated request queued behind it.

    With ``ok_only=True`` (the default) returns a CompletedProcess on success
    (rc == 0) or None on ANY failure (timeout, missing git, non-zero exit) —
    advisory callers never raise and never need to distinguish failures.

    With ``ok_only=False`` returns the full CompletedProcess whenever the
    process RAN (rc 0 or not) — None then means only startup failure or
    timeout.  Use this to separate "network unavailable → degrade silently"
    (None) from "git refused (divergence/conflict) → report per D12"
    (``returncode != 0``).  Never raises either way.
    """
    kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "stdin": subprocess.DEVNULL,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(["git", "-C", str(repo_root), *args], **kwargs)
    except Exception as e:  # no git binary, permission, ...
        logger.debug("git %s failed to start: %s", args[0], e)
        return None
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc)
        try:
            out, err = proc.communicate(timeout=5)
        except Exception:
            out, err = "", ""
        logger.debug("git %s exceeded %ss — process tree killed", args[0], timeout)
        return None
    except Exception as e:
        _kill_process_tree(proc)
        logger.debug("git %s raised: %s", args[0], e)
        return None
    if proc.returncode != 0:
        logger.debug("git %s rc=%s: %s", args[0], proc.returncode, (err or "").strip())
        if ok_only:
            return None
        return subprocess.CompletedProcess(
            args=args, returncode=proc.returncode, stdout=out, stderr=err
        )
    return subprocess.CompletedProcess(args=args, returncode=0, stdout=out, stderr=err)


def _run_git(repo_root: Path, args: list) -> Optional[str]:
    """stdout of a bounded git call, or None on any failure."""
    res = run_git_bounded(repo_root, args)
    return res.stdout if res is not None else None


def _run_git_result(repo_root: Path, args: list) -> Optional[subprocess.CompletedProcess]:
    """Full result of a bounded git call for callers that branch on the exit
    code (D12: "git refused" must be reported, not swallowed).

    Returns a CompletedProcess whenever the process ran (rc 0 or not);
    None means the process could not run or timed out (network → silent).
    """
    return run_git_bounded(repo_root, args, ok_only=False)


def _resolve_auto_push(output_dir: Path) -> bool:
    """conventions.git_sync.auto_push — default False (decision C)."""
    try:
        from codewiki.mcp.tools.page_router import load_schema

        schema = load_schema(str(output_dir))
        git_sync = (schema.get("conventions") or {}).get("git_sync") or {}
        return bool(git_sync.get("auto_push", False))
    except Exception:
        return False


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

    Runs once per process per repo when mode == session_ff_only.  The D17
    "workspace-root repo" gate was removed (2026-09-08, same call as
    auto_push).  No clean-tree pre-gate: ``--ff-only`` never merges or
    rebases, and git itself refuses when an incoming update would touch
    local uncommitted/untracked work — so a dirty tree whose edits don't
    collide fast-forwards fine, while an update that WOULD overwrite local
    state is refused by git with the tree left untouched.  Note the whole
    branch fast-forwards, not just the knowledge paths (branch =
    publication unit).
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir() or _resolve_mode(output_dir) != "session_ff_only":
        return None
    repo_root = _find_repo_root(output_dir)
    if repo_root is None:
        return None
    key = str(repo_root)
    if key in _ff_pulled_repos:
        return None
    _ff_pulled_repos.add(key)

    # No clean-tree pre-gate (2026-09-08): "worktree dirty" does not imply
    # conflict — git's own overwrite protection decides.  An update that
    # skips the dirty files fast-forwards cleanly; one that would clobber
    # them (tracked edits or untracked collisions) is refused untouched.
    proc = _run_git_result(repo_root, ["pull", "--ff-only", "--quiet"])
    if proc is None:
        return None
    if proc.returncode == 0:
        return "git_sync: 已同步远端知识（ff-only）。"
    # rc != 0: divergence, or the incoming update overlaps local work — git
    # refuses both and leaves the working tree as-is.  Distinguish so the
    # report tells the operator whether they must stash/commit first.
    err = (proc.stderr or "") + " " + (proc.stdout or "")
    if any(h in err for h in ("would be overwritten", "untracked working tree files", "将被合并操作覆盖")):
        return (
            "git_sync: ff-only 拉取被拒——远端更新与本地未提交改动重叠，"
            "git 未改动任何文件。请先提交/暂存本地改动后手动同步，"
            "本次会话不再自动拉取。"
        )
    return (
        "git_sync: ff-only 拉取失败（远端与本地分叉或网络问题），本次会话不再自动拉取，请人工同步。"
    )


def auto_push(output_dir: str | Path, tool_name: str) -> Optional[str]:
    """Commit + push the knowledge tree after a write (second slice).

    Gated on auto_push enabled (decision C).  Stages ONLY ``<repowiki>/``
    paths, commits with the repo's own git identity (decision B — message
    prefixed ``codewiki:``), pushes with fetch+rebase retry (D10, <=5) on
    races.  On exhaustion the local commit is KEPT and the caller is told
    the next successful push carries it (D12).  Never force-pushes, never
    resets.

    The D17 "repowiki's repo must be a workspace root" gate was removed
    (2026-09-08): staging is already confined to the knowledge subtree, so a
    colocated repo — where ``repowiki/`` shares a git repo with business
    code — syncs too.  Note that ``git push`` publishes the whole branch, so
    unpushed business commits ride along with a knowledge sync; that is
    accepted — the branch, not the path, is the unit of publication.
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir() or not _resolve_auto_push(output_dir):
        return None
    repo_root = _find_repo_root(output_dir)
    if repo_root is None:
        return None
    if str(repo_root) in _deferred_repos:
        return None  # an enclosing batch boundary owns this push

    try:
        rel = output_dir.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None

    # 0) PRE-EXISTING staged content guard (real-repo acceptance finding
    # 2026-09-02): ``git commit`` commits the WHOLE index.  If the user
    # already staged their own changes, auto_push must ABORT — silently
    # committing them is a boundary violation.  We never unstage their work.
    pre_staged = _run_git(repo_root, ["diff", "--cached", "--name-only"])
    if pre_staged and pre_staged.strip():
        return (
            "git_sync(auto_push): 暂存区已有非工具改动（可能是用户手动 git add 的内容），"
            "为避免误提交已跳过自动推送；请先提交或暂存（stash）你的改动。"
        )

    # 1) stage only the knowledge tree
    if _run_git(repo_root, ["add", "-A", "--", rel]) is None:
        return None
    staged = _run_git(repo_root, ["diff", "--cached", "--name-only"])
    if not staged or not staged.strip():
        return None  # nothing new — skip silently

    # 1b) sidecar lock files must never be committed even when a repo's
    # .gitignore predates the team layout (real-repo finding: harness repos
    # without the Phase 1 ignore list had *.lck staged).  Unstage ours —
    # unstaging is safe: the files stay on disk, just not in the commit.
    if any(name.endswith(".lck") for name in staged.splitlines()):
        _run_git(repo_root, ["reset", "-q", "--", "*.lck"])
        restaged = _run_git(repo_root, ["diff", "--cached", "--name-only"])
        if not restaged or not restaged.strip():
            return None

    # 2) commit with the repo's own identity (decision B)
    from datetime import date

    msg = f"codewiki: auto-sync knowledge ({tool_name}, {date.today().isoformat()})"
    if _run_git(repo_root, ["commit", "-q", "-m", msg]) is None:
        return "git_sync(auto_push): 提交失败，改动保留在工作区。"

    # 3) No content guard: the branch is the user's unit of publication, so
    # unpushed business commits riding along with a knowledge sync is
    # accepted.  Only the mechanical case is handled — with no upstream,
    # pushing cannot succeed at all.
    upstream = _run_git(
        repo_root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]
    )
    if not upstream or not upstream.strip():
        # No upstream — pushing cannot succeed.  Swallow it here instead of
        # burning the whole D10 retry budget on a guaranteed failure; the
        # local commit is kept and rides along once a branch is published.
        return "git_sync(auto_push): 知识变更已提交到本地（当前分支未配置 upstream，跳过推送）。"

    # 4) push with fetch+rebase retry (D10)
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


def auto_push_into_result(result_json: str, output_dir, tool_name: str) -> str:
    """Run :func:`auto_push` and merge its report into a JSON tool response.

    Single wiring point for write tools whose handler builds a ``result``
    dict (or an already-serialized JSON string): call this on the way out so
    the "did it sync?" line lands in the same place everywhere.

    Never raises and never changes the payload on failure — *result_json* is
    returned verbatim when auto_push is off, gated, deferred, or errors.
    """
    try:
        _push = auto_push(output_dir, tool_name)
        if _push:
            data = json.loads(result_json)
            if isinstance(data, dict):
                data["git_sync"] = _push
                return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception as e:  # never let sync break a write
        logger.debug("auto_push_into_result skipped: %s", e)
    return result_json
