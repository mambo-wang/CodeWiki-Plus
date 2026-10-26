"""Deterministic change plan (``.meta/change_plan.json``) — ADR-0020 decision 3.

A plan answers one question: *what must change next?* It is derived purely from
the changed files, the previous and current module trees, the page manifest and
the generation baseline commit. Same inputs ⇒ byte-identical plan: no clock, no
LLM, everything sorted. The host agent only names new modules when clustering;
it never decides which pages are stale.

Operators (fixed set):

* ``delete_subtree`` — the module vanished from the tree; its page must go.
* ``add_subtree``    — the module is new; its page does not exist yet.
* ``replan_subtree`` — the module's sources changed (or its page drifted), so
  its page and every ancestor aggregate page must be regenerated.
* ``update_page``    — a page outside the tree (overview, notes, …) needs a
  refresh; the overview is listed whenever a structural op exists.

Execution order is fixed — ``delete → add (parent before child) → replan
(leaf first) → update`` — and every operator carries a deterministic ``op_id``
plus one of ``pending/done/failed/skipped``. Deletions are executed here (no
LLM needed); the other operators are executed by the host agent, and the write
path marks them ``done`` as pages land. ``failed`` means the page was still
missing when the run closed; ``skipped`` means the run closed without touching
an operator that was not strictly required.

The plan is **not** merged with ``page_manifest.json``: the manifest records
what was written, the plan records what to do. Like every other state file here,
reads and writes are fail-open — a broken plan must never block generation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

PLAN_FILENAME = "change_plan.json"
SCHEMA_VERSION = 1

# Operator vocabulary. The tuple order is the execution order.
OP_TYPES = ("delete_subtree", "add_subtree", "replan_subtree", "update_page")
STATUSES = ("pending", "done", "failed", "skipped")
_OP_RANK = {op: i for i, op in enumerate(OP_TYPES)}

# Wiki bookkeeping pages are never "structural" pages of the module tree.
_NON_MODULE_STEMS = frozenset({"index", "log", "overview"})

_LOCK = threading.RLock()


# --------------------------------------------------------------------------- #
# Paths / IO
# --------------------------------------------------------------------------- #


def plan_path(repo_path: str | Path | None, output_dir: str | Path) -> Path:
    """Absolute path of the change plan (same state dir as the job ledger)."""
    from codewiki.mcp.tools import job_state

    return job_state.job_path(repo_path, output_dir).parent / PLAN_FILENAME


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("change plan unreadable: %s", path, exc_info=True)
        return None
    if not isinstance(data, dict) or not isinstance(data.get("ops"), list):
        logger.warning("change plan malformed: %s", path)
        return None
    return data


def load_plan(
    repo_path: str | Path | None, output_dir: str | Path
) -> dict[str, Any] | None:
    """Load the current plan, or ``None`` when absent/corrupt."""
    try:
        return _read(plan_path(repo_path, output_dir))
    except Exception:
        logger.debug("change plan load failed", exc_info=True)
        return None


def _save(path: Path, plan: dict[str, Any]) -> None:
    from codewiki.src.store import atomic_write

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(plan, indent=2, ensure_ascii=False))


def write_plan(
    repo_path: str | Path | None,
    output_dir: str | Path,
    plan: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    """Persist *plan* unless an identical plan for the same job already exists.

    Rebuilding a plan from unchanged inputs must not reset execution progress:
    when the hash and the owning job match, the stored plan (statuses included)
    wins. This is what makes a repeated ``save_module_tree`` in the same attempt
    a no-op instead of a replay from scratch.
    """
    path = plan_path(repo_path, output_dir)
    with _LOCK:
        existing = _read(path)
        if (
            existing is not None
            and existing.get("plan_hash") == plan.get("plan_hash")
            and existing.get("job_id") == plan.get("job_id")
        ):
            return path, existing
        _save(path, plan)
        return path, plan


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #


def base_commit_for(repo_path: str | Path | None, output_dir: str | Path) -> str | None:
    """Generation baseline the plan diffs from (metadata.json ``commit_id``)."""
    meta_file = plan_path(repo_path, output_dir).parent / "metadata.json"
    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    commit = (data.get("generation_info") or {}).get("commit_id")
    return str(commit) if commit else None


def changed_files_since(
    repo_path: str | Path | None, output_dir: str | Path
) -> list[str] | None:
    """Repo-relative files changed since the last generation, or ``None``.

    Reuses the incremental detector's rules (subdirectory scoping, output dir
    and ``.codewiki/`` exclusion, committed + worktree + untracked) so the plan
    sees exactly what ``analyze_repo`` reported. ``None`` means "no baseline /
    not a git repo" — the plan then relies on the tree diff alone.
    """
    if not repo_path:
        return None
    meta_file = plan_path(repo_path, output_dir).parent / "metadata.json"
    metadata: dict[str, Any] = {}
    try:
        loaded = json.loads(meta_file.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            metadata = loaded
    except (OSError, ValueError):
        pass
    try:
        from codewiki.mcp.tools.analysis import _detect_git_from_meta

        info = _detect_git_from_meta(Path(repo_path), metadata, Path(output_dir))
    except Exception:
        logger.debug("change plan git detection failed", exc_info=True)
        return None
    if not isinstance(info, dict):
        return None
    return sorted({str(f).replace("\\", "/") for f in info.get("changed_files") or []})


def detect_drift_pages(output_dir: str | Path, changed_files: Iterable[str]) -> list[str]:
    """Page keys whose baseline drifted (D2 manifest fingerprint), sorted."""
    try:
        from codewiki.mcp.tools.page_manifest import detect_stale_pages

        return sorted(set(detect_stale_pages(Path(output_dir), list(changed_files or []))))
    except Exception:
        logger.debug("change plan stale-page detection failed", exc_info=True)
        return []


# --------------------------------------------------------------------------- #
# Producer (pure)
# --------------------------------------------------------------------------- #


def _component_files(components: Any) -> set[str]:
    files: set[str] = set()
    for comp in components or ():
        text = str(comp)
        if "::" in text:
            rel = text.split("::", 1)[0].replace("\\", "/")
            if rel:
                files.add(rel)
    return files


def _tree_index(tree: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Flatten a module tree into ``{"a/b": {path, name, parent, files}}``.

    Sorted depth-first walk, first hit wins for duplicate leaf names — the
    module name is the page key, so a republished name cannot get two pages.
    """
    index: dict[str, dict[str, Any]] = {}

    def walk(node: Any, path: list[str]) -> None:
        if not isinstance(node, dict):
            return
        for name in sorted(node):
            info = node.get(name)
            if not isinstance(info, dict):
                info = {}
            current = path + [name]
            key = "/".join(current)
            if key not in index:
                index[key] = {
                    "path": current,
                    "name": name,
                    "parent": "/".join(path),
                    "files": _component_files(info.get("components")),
                }
            walk(info.get("children"), current)

    walk(tree, [])
    return index


def _stem(page_key: str) -> str:
    name = str(page_key).replace("\\", "/").rsplit("/", 1)[-1]
    return name[:-3] if name.lower().endswith(".md") else name


def _page_key_for(pages: dict[str, Any], name: str) -> str | None:
    """Manifest key whose stem is *name* (case-insensitive), if any."""
    target = name.casefold()
    for page_key in sorted(pages):
        if _stem(page_key).casefold() == target:
            return page_key
    return None


def _manifest_files(pages: dict[str, Any], name: str) -> set[str]:
    page_key = _page_key_for(pages, name)
    entry = pages.get(page_key) if page_key else None
    files = entry.get("files") if isinstance(entry, dict) else None
    if not isinstance(files, list):
        return set()
    return {str(f).replace("\\", "/") for f in files}


def _new_op(op: str, *, page: str, path: list[str] | None = None, **extra: Any) -> dict:
    path = list(path or [])
    ident = "/".join(path) or page
    return {
        "op_id": f"{op}:{ident}",
        "op": op,
        "page": page,
        "path": path,
        **extra,
        "status": "pending",
    }


def _delete_ops(prev: dict[str, dict], new: dict[str, dict], pages: dict) -> list[dict]:
    ops = []
    for key in sorted(prev):
        if key in new:
            continue
        rec = prev[key]
        page_key = _page_key_for(pages, rec["name"])
        if page_key is None:
            continue  # never written → nothing to delete
        ops.append(
            _new_op(
                "delete_subtree",
                page=rec["name"],
                path=rec["path"],
                page_key=page_key,
                reason="module_removed",
            )
        )
    return ops


def _add_ops(prev: dict[str, dict], new: dict[str, dict]) -> list[dict]:
    ops = []
    for key in sorted(new, key=lambda k: (len(new[k]["path"]), k)):
        if key in prev:
            continue
        rec = new[key]
        ops.append(
            _new_op(
                "add_subtree",
                page=rec["name"],
                path=rec["path"],
                parent=rec["parent"] or None,
                reason="new_module",
            )
        )
    return ops


def _parent_keys(rec: dict[str, Any]) -> list[str]:
    path = rec["path"]
    return ["/".join(path[:i]) for i in range(len(path) - 1, 0, -1)]


def _replan_ops(
    prev: dict[str, dict],
    new: dict[str, dict],
    pages: dict,
    changed: set[str],
    stale: set[str],
) -> list[dict]:
    direct: dict[str, dict[str, Any]] = {}
    for key in sorted(new):
        if key not in prev:
            continue  # covered by add_subtree; only its ancestors are cascaded
        rec = new[key]
        files = rec["files"] | _manifest_files(pages, rec["name"])
        hit = sorted(files & changed)
        if hit:
            direct[key] = {"reason": "changed_files", "changed_files": hit}
            continue
        if rec["files"] != prev[key]["files"]:
            direct[key] = {"reason": "components_changed", "changed_files": []}
            continue
        page_key = _page_key_for(pages, rec["name"])
        if page_key and page_key in stale:
            direct[key] = {"reason": "stale_page", "changed_files": []}

    targets: dict[str, dict[str, Any]] = dict(direct)
    # A new module is fully covered by its add_subtree op, so it never gets a
    # replan of its own. Its ancestors still do: an aggregate page describes
    # its child set, so adding or removing a child invalidates the parent.
    structural = [k for k in sorted(new) if k not in prev]
    structural += [k for k in sorted(prev) if k not in new]
    for key in structural:
        rec = new.get(key) or prev[key]
        for parent in _parent_keys(rec):
            if parent in new and parent in prev:
                targets.setdefault(parent, {"reason": "cascade", "changed_files": []})
    for key in direct:
        for parent in _parent_keys(new[key]):
            if parent in new and parent in prev:
                targets.setdefault(parent, {"reason": "cascade", "changed_files": []})

    ops = []
    for key in sorted(targets, key=lambda k: (-len(new[k]["path"]), k)):
        info = targets[key]
        ops.append(
            _new_op(
                "replan_subtree",
                page=new[key]["name"],
                path=new[key]["path"],
                page_key=_page_key_for(pages, new[key]["name"]),
                reason=info["reason"],
                changed_files=info["changed_files"],
            )
        )
    return ops


def _update_ops(
    new: dict[str, dict], pages: dict, changed: set[str], stale: set[str]
) -> list[dict]:
    module_stems = {rec["name"].casefold() for rec in new.values()}
    ops = []
    for page_key in sorted(pages):
        stem = _stem(page_key)
        if stem.casefold() in module_stems or stem.casefold() in _NON_MODULE_STEMS:
            continue
        entry = pages.get(page_key)
        files = entry.get("files") if isinstance(entry, dict) else None
        files = {str(f).replace("\\", "/") for f in files} if isinstance(files, list) else set()
        if files & changed:
            reason = "changed_files"
        elif page_key in stale:
            reason = "stale_page"
        else:
            continue
        ops.append(
            _new_op("update_page", page=stem, page_key=page_key, reason=reason)
        )
    return ops


def _overview_op(pages: dict) -> dict:
    return _new_op(
        "update_page",
        page="overview",
        page_key=_page_key_for(pages, "overview"),
        reason="overview_stale",
    )


def _sort_key(op: dict) -> tuple:
    rank = _OP_RANK.get(str(op.get("op")), len(OP_TYPES))
    path = op.get("path") or []
    if op.get("op") == "add_subtree":
        return (rank, len(path), "/".join(path))
    if op.get("op") == "replan_subtree":
        return (rank, -len(path), "/".join(path))
    return (rank, str(op.get("page_key") or op.get("page") or ""))


def _dedupe(ops: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out = []
    for op in ops:
        key = (
            str(op.get("op")),
            "/".join(op.get("path") or []) or str(op.get("page_key") or op.get("page") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(op)
    return out


def _counts(ops: list[dict]) -> dict[str, Any]:
    per_type = Counter(str(op.get("op")) for op in ops)
    return {
        "total": len(ops),
        **{op: per_type.get(op, 0) for op in OP_TYPES},
    }


def compute_plan_hash(plan: dict[str, Any]) -> str:
    """Stable hash of the plan's *content* (statuses and clock excluded)."""
    core = {
        "schema_version": plan.get("schema_version"),
        "surface": plan.get("surface"),
        "base_commit": plan.get("base_commit"),
        "basis": plan.get("basis"),
        "ops": [
            {
                key: op.get(key)
                for key in ("op_id", "op", "page", "path", "page_key", "reason", "changed_files")
            }
            for op in plan.get("ops") or []
        ],
    }
    blob = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_plan(
    *,
    previous_tree: dict[str, Any] | None,
    module_tree: dict[str, Any] | None,
    page_manifest: dict[str, Any] | None = None,
    changed_files: Iterable[str] | None = None,
    stale_pages: Iterable[str] | None = None,
    base_commit: str | None = None,
    surface: str = "mcp",
    job_id: str | None = None,
) -> dict[str, Any]:
    """Produce the plan for one tree transition. Pure and deterministic."""
    changed = sorted(
        {str(f).replace("\\", "/").strip() for f in changed_files or () if str(f).strip()}
    )
    stale = sorted({str(p).replace("\\", "/") for p in stale_pages or () if str(p).strip()})
    pages = (page_manifest or {}).get("pages") or {}
    if not isinstance(pages, dict):
        pages = {}

    prev_index = _tree_index(previous_tree or {})
    new_index = _tree_index(module_tree or {})

    ops: list[dict] = []
    if prev_index:
        ops.extend(_delete_ops(prev_index, new_index, pages))
        ops.extend(_add_ops(prev_index, new_index))
        ops.extend(_replan_ops(prev_index, new_index, pages, set(changed), set(stale)))
        ops.extend(_update_ops(new_index, pages, set(changed), set(stale)))
        ops = _dedupe(ops)
        if ops and not any(op.get("page") == "overview" for op in ops):
            ops.append(_overview_op(pages))
        ops.sort(key=_sort_key)

    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "surface": surface,
        "job_id": job_id,
        "base_commit": base_commit,
        "basis": {
            "tree": "diff" if prev_index else "no_previous_tree",
            "changed_files": len(changed),
            "stale_pages": len(stale),
            "page_manifest_pages": len(pages),
        },
        "summary": _counts(ops),
        "ops": ops,
    }
    plan["plan_hash"] = compute_plan_hash(plan)
    return plan


# --------------------------------------------------------------------------- #
# Executor state
# --------------------------------------------------------------------------- #


def plan_summary(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    """Compact, response-safe view of the plan.

    ``pending_pages`` is the set of pages the run still owes: any operator that
    is not ``done`` — ``failed`` (page still missing at close) and ``skipped``
    (closed without touching it) come back on the next attempt, which is what
    makes a resume a replay. Deletions are excluded: the executor owns them.
    """
    if not plan:
        return None
    ops = plan.get("ops") or []
    status = Counter(str(op.get("status") or "pending") for op in ops)
    view = {
        "plan_hash": plan.get("plan_hash"),
        "base_commit": plan.get("base_commit"),
        **_counts(ops),
        "pending": status.get("pending", 0),
        "done": status.get("done", 0),
        "failed": status.get("failed", 0),
        "skipped": status.get("skipped", 0),
        "pending_pages": sorted(
            {
                str(op.get("page"))
                for op in ops
                if str(op.get("status") or "pending") != "done"
                and op.get("op") != "delete_subtree"
            }
        ),
    }
    return view


def _resolve_page_path(output_dir: str | Path, op: dict[str, Any]) -> Path | None:
    od = Path(output_dir)
    page_key = op.get("page_key")
    if page_key:
        return od / str(page_key)
    name = str(op.get("page") or "")
    if not name:
        return None
    try:
        from codewiki.mcp.tools.page_router import resolve_doc_path

        candidate = resolve_doc_path(name + ".md", "module", od)
    except Exception:
        candidate = od / f"{name}.md"
    legacy = od / f"{name}.md"
    if not candidate.is_file() and legacy.is_file():
        return legacy
    return candidate


def _drop_manifest_pages(output_dir: str | Path, page_keys: list[str]) -> None:
    if not page_keys:
        return
    try:
        from codewiki.mcp.tools.page_manifest import load_manifest, remove_page, save_manifest

        manifest = load_manifest(Path(output_dir))
        stale = [k for k in page_keys if k in (manifest.get("pages") or {})]
        if not stale:
            return
        for key in stale:
            remove_page(manifest, key)
        save_manifest(Path(output_dir), manifest)
    except Exception:
        logger.warning("page_manifest delete cleanup failed (non-fatal)", exc_info=True)


def execute_deletions(
    repo_path: str | Path | None, output_dir: str | Path
) -> list[str]:
    """Apply every unsettled ``delete_subtree`` op and mark it done.

    Deletion is deterministic, so the plan executes it itself instead of asking
    the host agent to remove files. ``failed`` deletes are retried: an earlier
    attempt may have been killed between the file removal and the ledger write.
    Returns the deleted page keys.
    """
    path = plan_path(repo_path, output_dir)
    deleted: list[str] = []
    with _LOCK:
        plan = _read(path)
        if plan is None:
            return []
        touched = False
        for op in plan.get("ops") or []:
            if op.get("op") != "delete_subtree":
                continue
            if str(op.get("status") or "pending") == "done":
                continue
            touched = True
            target = _resolve_page_path(output_dir, op)
            status = "done"
            if target is not None:
                try:
                    rel = target.resolve().relative_to(Path(output_dir).resolve())
                except (OSError, ValueError):
                    logger.warning("change plan delete target escapes wiki: %s", target)
                    status = "failed"
                else:
                    try:
                        if target.is_file():
                            target.unlink()
                            deleted.append(rel.as_posix())
                    except OSError:
                        logger.warning("change plan delete failed: %s", target, exc_info=True)
                        status = "failed"
            op["status"] = status
        if touched:
            _save(path, plan)
    _drop_manifest_pages(output_dir, sorted(deleted))
    return sorted(deleted)


def mark_op_done(
    repo_path: str | Path | None, output_dir: str | Path, page: str
) -> dict[str, Any] | None:
    """Mark the operators for *page* as done (called from the write path).

    Any unsettled operator counts — on replay an operator may be ``failed`` or
    ``skipped`` from the previous attempt, and writing the page settles it.
    """
    key = Path(str(page)).stem
    if not key:
        return None
    path = plan_path(repo_path, output_dir)
    with _LOCK:
        plan = _read(path)
        if plan is None:
            return None
        changed = False
        for op in plan.get("ops") or []:
            if str(op.get("status") or "pending") == "done":
                continue
            target = str(op.get("page") or "")
            if target == key or target.casefold() == key.casefold():
                op["status"] = "done"
                changed = True
        if not changed:
            return None
        _save(path, plan)
        return plan_summary(plan)


def finalize_plan(
    repo_path: str | Path | None,
    output_dir: str | Path,
    missing_pages: Iterable[str] = (),
) -> dict[str, Any] | None:
    """Settle leftovers when the run closes.

    A pending operator whose page is still missing becomes ``failed`` (the run
    owed that page); everything else becomes ``skipped`` (closed without
    touching it). Replay is by status: ``done`` operators are never redone.
    """
    path = plan_path(repo_path, output_dir)
    missing = {str(p).casefold() for p in missing_pages or () if str(p).strip()}
    with _LOCK:
        plan = _read(path)
        if plan is None:
            return None
        changed = False
        for op in plan.get("ops") or []:
            if str(op.get("status") or "pending") != "pending":
                continue
            page = str(op.get("page") or "").casefold()
            op["status"] = "failed" if page in missing else "skipped"
            changed = True
        if changed:
            _save(path, plan)
        return plan_summary(plan)
