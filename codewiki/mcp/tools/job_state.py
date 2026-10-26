"""Generation job ledger (``.meta/job.json``) — ADR-0020.

A *job* is one wiki generation/update attempt: phase, attempt count, baseline
commit, page counters and degradation records. It stores **state and pointers
only** — the module tree, page manifest and metadata.json remain the owners of
their own content, so the ledger never becomes a fourth source of truth.

The MCP tool path owns the ledger: only it creates and closes a job. The
legacy pipeline (``src/be/documentation_generator.py``) may *annotate* an
existing job — page writes and ``degraded`` records — but never creates one,
so a plain ``codewiki generate`` run still leaves no ledger behind
(ADR-0020 decision 1).

Everything here is fail-open: a corrupt or unwritable ledger must never break
generation. Readers return ``None`` and log; writers swallow and log.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

JOB_FILENAME = "job.json"
SCHEMA_VERSION = 1

# Phase vocabulary. ``analyzing`` → ``analyzed`` → ``planned`` → ``generating``
# → ``done``; ``degraded`` closes an attempt that lost non-fatal work but may be
# resumed; ``failed`` is terminal and fatal.
PHASES = (
    "analyzing",
    "analyzed",
    "planned",
    "generating",
    "finalizing",
    "done",
    "degraded",
    "failed",
)

# Phases that reject further writes. ``degraded`` is deliberately NOT terminal:
# a later run may resume it and fill the pages it reported as missing
# (ADR-0020 decision 2 — the tier is ``partial``, not a rebuild).
TERMINAL_PHASES = frozenset({"done", "failed"})

# Resume tiers (ADR-0020 decision 2). ``as_leaf`` is recorded via
# ``record_degraded`` when a parent module cannot be aggregated; it is not a
# decision made up front.
RESUME_MODES = ("persisted", "partial", "as_leaf", "rebuild")

# One writer process per repo is assumed (MCP server). The lock keeps
# concurrent handlers in this process from interleaving read-modify-write.
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _meta_dir(repo_path: str | Path | None, output_dir: str | Path) -> Path:
    """Resolve the analysis-state dir, falling back to ``<output_dir>/.meta``."""
    if repo_path:
        try:
            from codewiki.mcp.cache import analysis_meta_dir

            return Path(analysis_meta_dir(Path(repo_path), Path(output_dir)))
        except Exception:  # pragma: no cover - layout must never break the ledger
            logger.debug("analysis_meta_dir failed; falling back to .meta", exc_info=True)
    return Path(output_dir) / ".meta"


def job_path(repo_path: str | Path | None, output_dir: str | Path) -> Path:
    """Absolute path of the job ledger for this repo/output pair."""
    return _meta_dir(repo_path, output_dir) / JOB_FILENAME


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("job ledger unreadable: %s", path, exc_info=True)
        return None
    if not isinstance(data, dict) or not data.get("job_id"):
        logger.warning("job ledger malformed (missing job_id): %s", path)
        return None
    return data


def _write(path: Path, job: dict[str, Any]) -> None:
    from codewiki.src.store import atomic_write

    job["updated_at"] = _now()
    atomic_write(path, json.dumps(job, indent=2, ensure_ascii=False))


def load_job(repo_path: str | Path | None, output_dir: str | Path) -> dict[str, Any] | None:
    """Load the current job, or ``None`` when absent/corrupt."""
    try:
        return _read(job_path(repo_path, output_dir))
    except Exception:
        logger.debug("job ledger load failed", exc_info=True)
        return None


def _page_keys(job: dict[str, Any]) -> tuple[list[str], list[str]]:
    pages = job.get("pages") or {}
    planned = [str(k) for k in pages.get("planned_keys") or []]
    written = [str(k) for k in pages.get("written_keys") or []]
    return planned, written


def missing_pages(job: dict[str, Any] | None) -> list[str]:
    """Planned module pages not yet written, sorted. Empty when nothing planned."""
    if not job:
        return []
    planned, written = _page_keys(job)
    written_set = set(written)
    return sorted(k for k in planned if k not in written_set)


def decide_resume(job: dict[str, Any] | None, base_commit: str | None) -> str:
    """Pick the resume tier for a new attempt (ADR-0020 decision 2).

    ``rebuild`` — no job, terminal job, or the repository moved off the job's
    baseline commit. ``partial`` — unfinished job with planned pages still
    missing. ``persisted`` — unfinished job with nothing missing.
    """
    if not job:
        return "rebuild"
    if job.get("phase") in TERMINAL_PHASES:
        return "rebuild"
    old = job.get("base_commit")
    if base_commit and old and str(base_commit) != str(old):
        return "rebuild"
    return "partial" if missing_pages(job) else "persisted"


def _artifact_pointers(repo_path: str | Path | None, output_dir: str | Path) -> dict[str, str]:
    """Pointers to the files the job coordinates — never their content."""
    meta = _meta_dir(repo_path, output_dir)

    def _rel(target: Path) -> str:
        try:
            return target.relative_to(Path(output_dir)).as_posix()
        except ValueError:
            return target.as_posix()

    return {
        "meta_dir": _rel(meta),
        "module_tree": _rel(meta / "module_tree.json"),
        "page_manifest": _rel(meta / "page_manifest.json"),
        "change_plan": _rel(meta / "change_plan.json"),
        "metadata": _rel(meta / "metadata.json"),
    }


def _new_job(
    *,
    repo_path: str | Path | None,
    output_dir: str | Path,
    base_commit: str | None,
    surface: str,
    resume: str,
) -> dict[str, Any]:
    now = _now()
    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": uuid.uuid4().hex,
        "surface": surface,
        "repo_path": str(repo_path) if repo_path else None,
        "output_dir": str(output_dir),
        "phase": "analyzing",
        "attempt": 1,
        "resume": resume,
        "base_commit": base_commit,
        "started_at": now,
        "updated_at": now,
        "finished_at": None,
        "pages": {
            "planned": 0,
            "written": 0,
            "other_written": 0,
            "planned_keys": [],
            "written_keys": [],
            "missing": [],
        },
        "artifacts": _artifact_pointers(repo_path, output_dir),
        "degraded": [],
    }


def start_job(
    repo_path: str | Path | None,
    output_dir: str | Path,
    *,
    base_commit: str | None = None,
    surface: str = "mcp",
) -> dict[str, Any] | None:
    """Start or resume a job at the beginning of ``analyze_repo``."""
    try:
        path = job_path(repo_path, output_dir)
        with _LOCK:
            existing = _read(path)
            resume = decide_resume(existing, base_commit)
            if existing is not None and resume != "rebuild":
                job = existing
                job["attempt"] = int(job.get("attempt") or 1) + 1
                job["phase"] = "analyzing"
                job["resume"] = resume
                job["finished_at"] = None
                if base_commit:
                    job["base_commit"] = base_commit
            else:
                job = _new_job(
                    repo_path=repo_path,
                    output_dir=output_dir,
                    base_commit=base_commit,
                    surface=surface,
                    resume=resume,
                )
            _write(path, job)
            return job
    except Exception:
        logger.warning("job ledger start failed (non-fatal)", exc_info=True)
        return None


def _mutate(
    repo_path: str | Path | None,
    output_dir: str | Path,
    fn,
) -> dict[str, Any] | None:
    """Load → mutate → write under the process lock. No-op without a job."""
    try:
        path = job_path(repo_path, output_dir)
        with _LOCK:
            job = _read(path)
            if job is None:
                return None
            changed = fn(job)
            if changed is False:
                return job
            _write(path, job)
            return job
    except Exception:
        logger.warning("job ledger update failed (non-fatal)", exc_info=True)
        return None


def set_phase(
    repo_path: str | Path | None,
    output_dir: str | Path,
    phase: str,
) -> dict[str, Any] | None:
    """Move the job to *phase* (unknown values are ignored, not written)."""
    if phase not in PHASES:
        logger.warning("ignoring unknown job phase: %s", phase)
        return load_job(repo_path, output_dir)

    def _apply(job: dict[str, Any]) -> bool:
        if job.get("phase") in TERMINAL_PHASES and job.get("phase") != phase:
            return False
        job["phase"] = phase
        if phase in TERMINAL_PHASES:
            job["finished_at"] = _now()
        return True

    return _mutate(repo_path, output_dir, _apply)


def record_planned(
    repo_path: str | Path | None,
    output_dir: str | Path,
    page_keys: Iterable[str],
) -> dict[str, Any] | None:
    """Record the planned module pages produced by ``save_module_tree``."""
    keys = sorted({str(k) for k in page_keys if str(k).strip()})
    if not keys:
        return load_job(repo_path, output_dir)

    def _apply(job: dict[str, Any]) -> bool:
        pages = job.setdefault("pages", {})
        pages["planned_keys"] = keys
        pages["planned"] = len(keys)
        written = set(pages.get("written_keys") or [])
        pages["missing"] = sorted(k for k in keys if k not in written)
        if job.get("phase") not in TERMINAL_PHASES:
            job["phase"] = "planned"
        return True

    return _mutate(repo_path, output_dir, _apply)


def mark_page_written(
    repo_path: str | Path | None,
    output_dir: str | Path,
    filename: str,
    page_type: str = "module",
) -> dict[str, Any] | None:
    """Record one page write. Module pages advance the planned/written counters."""
    key = Path(str(filename)).stem
    if not key:
        return load_job(repo_path, output_dir)

    def _apply(job: dict[str, Any]) -> bool:
        # A done job is a historical record; later edits do not reopen it.
        # ``degraded`` stays writable: a resume fills the pages it lost.
        if job.get("phase") in TERMINAL_PHASES:
            return False
        pages = job.setdefault("pages", {})
        planned = set(pages.get("planned_keys") or [])
        # Bookkeeping keys off the planned set, not page_type alone: the
        # overview page is planned but written with its own page_type.
        if page_type == "module" or key in planned:
            written = list(pages.get("written_keys") or [])
            if key not in written:
                written.append(key)
                pages["written_keys"] = sorted(written)
            pages["written"] = len(pages["written_keys"])
            planned = pages.get("planned_keys") or []
            pages["missing"] = sorted(k for k in planned if k not in set(pages["written_keys"]))
        else:
            pages["other_written"] = int(pages.get("other_written") or 0) + 1
        if job.get("phase") not in ("finalizing",):
            job["phase"] = "generating"
        return True

    return _mutate(repo_path, output_dir, _apply)


def record_degraded(
    repo_path: str | Path | None,
    output_dir: str | Path,
    *,
    stage: str,
    code: str,
    detail: str = "",
) -> dict[str, Any] | None:
    """Append a non-fatal loss record (atlas ``stage.degraded`` equivalent)."""
    entry = {
        "stage": str(stage),
        "code": str(code),
        "detail": str(detail),
        "at": _now(),
    }

    def _apply(job: dict[str, Any]) -> bool:
        job.setdefault("degraded", []).append(entry)
        return True

    return _mutate(repo_path, output_dir, _apply)


def finish_job(
    repo_path: str | Path | None,
    output_dir: str | Path,
    *,
    incomplete_ops: int = 0,
) -> dict[str, Any] | None:
    """Close the job: ``done`` when nothing is missing, else ``degraded``.

    *incomplete_ops* is the number of change-plan operators this attempt left
    ``failed``/``skipped`` (ADR-0020 #3). It is attempt-scoped on purpose: the
    plan file keeps the per-operator history, so a later attempt that clears
    the plan closes ``done`` instead of inheriting a permanent downgrade.
    """

    def _apply(job: dict[str, Any]) -> bool:
        # ``failed`` is final. ``done``/``degraded`` may be closed again: a
        # resumed degraded job calls this once more after refilling pages.
        if job.get("phase") == "failed":
            return False
        missing = missing_pages(job)
        pages = job.setdefault("pages", {})
        pages["missing"] = missing
        job["phase"] = "degraded" if (missing or incomplete_ops > 0) else "done"
        job["finished_at"] = _now()
        return True

    return _mutate(repo_path, output_dir, _apply)


def job_summary(job: dict[str, Any] | None) -> dict[str, Any] | None:
    """Compact, response-safe view of the ledger.

    ``missing_pages`` is the actionable subset the host agent needs to run a
    ``partial`` resume; the full planned/written key lists stay on disk.
    """
    if not job:
        return None
    pages = job.get("pages") or {}
    missing = missing_pages(job)
    return {
        "job_id": job.get("job_id"),
        "phase": job.get("phase"),
        "attempt": job.get("attempt"),
        "resume": job.get("resume"),
        "base_commit": job.get("base_commit"),
        "pages": {
            "planned": int(pages.get("planned") or 0),
            "written": int(pages.get("written") or 0),
            "other_written": int(pages.get("other_written") or 0),
            "missing": len(missing),
        },
        "missing_pages": missing,
        "degraded_count": len(job.get("degraded") or []),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
    }
