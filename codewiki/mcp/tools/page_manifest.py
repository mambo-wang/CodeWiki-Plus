"""Page-level baseline manifest (D2) — per-page drift detection for the wiki.

Borrowed from langchain-ai/openwiki's ``.page-manifest.json`` (per-page
baseline diff).  CodeWiki keeps only the *baseline fingerprint* — the page
body itself lives in git, so there is no rollback snapshot side-car.

Each wiki page gets an entry recording the git head, the set of source files
its component claims reference, and a deterministic ``source_fingerprint``
aggregated from the page's evidence ``sources`` content hashes (shared with
D1's hash primitives).  :func:`detect_stale_pages` then flags pages whose
referenced files changed OR whose evidence fingerprint drifted — this is the
only mechanism that gives *shared-pool* pages (entities/concepts/notes) a
change-driven expiry signal instead of the time window alone.

Manifest location is ``<output_dir>/.meta/page_manifest.json`` for every
layout (single-repo / colocated / centralized).  Unlike ``metadata.json``
(a whole-repo single file that gets overwritten by whichever repo analyzed
last), the manifest is keyed per page, so a centralized workspace's shared
``repowiki/.meta/`` holds one entry per page without clobbering.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from codewiki.src.config import actor_id, meta_join

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "page_manifest.json"
SCHEMA_VERSION = 1
_HASH_PREFIX = "sha256:"


# --------------------------------------------------------------------------- #
# Path / IO
# --------------------------------------------------------------------------- #


def manifest_path(output_dir: Path) -> Path:
    """Path to the page manifest under ``<output_dir>/.meta/``."""
    return Path(meta_join(str(output_dir), MANIFEST_FILENAME))


def load_manifest(output_dir: Path) -> Dict[str, Any]:
    """Read the manifest, tolerating absence / corruption.

    Always returns a well-formed ``{"schema_version": 1, "pages": {}}``
    envelope so callers never branch on file existence.
    """
    empty: Dict[str, Any] = {"schema_version": SCHEMA_VERSION, "pages": {}}
    path = manifest_path(output_dir)
    if not path.is_file():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("page_manifest.json corrupt; treating as empty", exc_info=True)
        return empty
    if not isinstance(data, dict):
        return empty
    data.setdefault("schema_version", SCHEMA_VERSION)
    pages = data.get("pages")
    if not isinstance(pages, dict):
        data["pages"] = {}
    return data


def save_manifest(output_dir: Path, manifest: Dict[str, Any]) -> None:
    """Atomically persist the manifest (temp file + ``os.replace``)."""
    path = manifest_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest.setdefault("schema_version", SCHEMA_VERSION)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def page_key_for(output_dir: Path, doc_path: Path) -> str:
    """Canonical page key: posix path relative to output_dir (e.g. ``wiki/modules/X.md``)."""
    return doc_path.resolve().relative_to(output_dir.resolve()).as_posix()


def upsert_page(manifest: Dict[str, Any], page_key: str, entry: Dict[str, Any]) -> None:
    """Insert or replace a page entry (idempotent by page key)."""
    manifest.setdefault("pages", {})[page_key] = entry


def remove_page(manifest: Dict[str, Any], page_key: str) -> None:
    """Drop a page entry (no-op when absent)."""
    manifest.setdefault("pages", {}).pop(page_key, None)


# --------------------------------------------------------------------------- #
# Evidence fingerprint (shares D1 hash primitives)
# --------------------------------------------------------------------------- #


def compute_source_fingerprint(content: str) -> Optional[str]:
    """Deterministic fingerprint of a page's evidence ``sources``.

    Aggregates the ``content_hash`` of every ``sources`` entry (the D1
    evidence) into a single ``sha256:...``.  Returns ``None`` when the page
    carries no evidence — such pages are not subject to fingerprint-drift
    detection (only file-level detection applies).
    """
    if not content.startswith("---"):
        return None
    end = content.find("---", 3)
    if end < 0:
        return None
    try:
        import yaml

        data = yaml.safe_load(content[3:end]) or {}
    except Exception:  # noqa: BLE001 - malformed FM is other checks' concern
        return None
    if not isinstance(data, dict):
        return None
    sources = data.get("sources")
    if isinstance(sources, dict):
        sources = [sources]
    if not isinstance(sources, list):
        return None
    hashes = []
    for entry in sources:
        if isinstance(entry, dict) and isinstance(entry.get("content_hash"), str):
            hashes.append(entry["content_hash"])
    if not hashes:
        return None
    joined = "\n".join(sorted(set(hashes)))
    return _HASH_PREFIX + hashlib.sha256(joined.encode("utf-8")).hexdigest()


def compute_source_fingerprint_for_file(path: Path) -> Optional[str]:
    """Fingerprint of the page's evidence, reading the file from disk."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return compute_source_fingerprint(content)


# --------------------------------------------------------------------------- #
# Component / file collection (write path)
# --------------------------------------------------------------------------- #


def _find_module_components(module_tree: Dict[str, Any], target: str) -> List[str]:
    """Locate a module's component ids in the module tree by module name."""
    for name, info in module_tree.items():
        if name.lower().replace(" ", "_") == target.lower().replace(" ", "_"):
            return list(info.get("components", []) or [])
        children = info.get("children", {})
        if isinstance(children, dict):
            found = _find_module_components(children, target)
            if found:
                return found
    return []


_ENTITY_COMPONENT_TYPES = frozenset(
    {"class", "interface", "struct", "enum", "record", "annotation"}
)


def _component_relative_path(node: Any, comp_id: str) -> str:
    """Relative path of a component node, falling back to the comp-id prefix."""
    rel = (getattr(node, "relative_path", "") or "").replace("\\", "/")
    if not rel and "::" in comp_id:
        rel = comp_id.split("::", 1)[0].replace("\\", "/")
    return rel


def collect_page_files(session: Any, filename: str, page_type: str) -> Tuple[List[str], List[str]]:
    """Resolve a page's source files and component ids.

    Returns ``(files, components)``.  ``module`` pages are attributed through
    the module tree; ``entity`` pages (class/interface/...) are matched to
    components by name.  Other shared-pool pages (concept/note/source/...)
    carry no component attribution and rely on fingerprint drift instead.
    """
    if session is None:
        return [], []
    name = filename.replace(".md", "")

    if page_type == "module":
        module_tree = session.module_tree or {}
        comp_ids = _find_module_components(module_tree, name) if module_tree else []
        files: List[str] = []
        for comp_id in comp_ids:
            node = session.components.get(comp_id) if session.components else None
            if node is None:
                continue
            rel = _component_relative_path(node, comp_id)
            if rel and rel not in files:
                files.append(rel)
        return files, list(comp_ids)

    if page_type == "entity":
        components = getattr(session, "components", None)
        if not components:
            return [], []
        try:
            items = components.items()
        except AttributeError:
            return [], []
        files, comp_ids = [], []
        for comp_id, node in items:
            if getattr(node, "name", "") != name:
                continue
            if (getattr(node, "component_type", "") or "") not in _ENTITY_COMPONENT_TYPES:
                continue
            rel = _component_relative_path(node, comp_id)
            if rel and rel not in files:
                files.append(rel)
            comp_ids.append(comp_id)
        return files, comp_ids

    return [], []


def current_git_head(repo_path: Optional[str]) -> Optional[str]:
    """HEAD sha of the repo, or None when git is unavailable."""
    if not repo_path:
        return None
    try:
        import git

        return git.Repo(repo_path).head.commit.hexsha
    except Exception:
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# High-level write entry (called by write/edit_doc_file)
# --------------------------------------------------------------------------- #


def upsert_page_manifest(
    output_dir: Path,
    doc_path: Path,
    *,
    session: Any = None,
    filename: str = "",
    page_type: str = "module",
    repo_name: Optional[str] = None,
    repo_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Record (or refresh) a page's baseline entry after a successful write.

    Missing component attribution or missing evidence simply yields empty
    ``files`` / ``None`` fingerprint — the page is still tracked via
    ``git_head``, and later gains change sensitivity once evidence exists.
    Returns the recorded entry (for debugging), or None on failure.
    """
    try:
        page_key = page_key_for(output_dir, doc_path)
    except ValueError:
        return None

    files, components = collect_page_files(session, filename, page_type)
    fingerprint = compute_source_fingerprint_for_file(doc_path)

    entry: Dict[str, Any] = {
        "git_head": current_git_head(repo_path),
        "components": components,
        "files": files,
        "source_fingerprint": fingerprint,
        "repo": repo_name,
        "producer": actor_id(),
        "written_at": _now_iso(),
    }

    try:
        manifest = load_manifest(output_dir)
        upsert_page(manifest, page_key, entry)
        save_manifest(output_dir, manifest)
    except Exception:  # noqa: BLE001 - manifest is a best-effort side effect
        logger.warning("page_manifest upsert failed (non-fatal)", exc_info=True)
        return None
    return entry


# --------------------------------------------------------------------------- #
# High-level read entry (called by _detect_doc_changes)
# --------------------------------------------------------------------------- #


def detect_stale_pages(output_dir: Path, changed_files: List[str]) -> List[str]:
    """Return page keys whose baseline is stale relative to *changed_files*.

    A page is stale when (a) any of its referenced source files changed, or
    (b) its evidence ``source_fingerprint`` drifted from what was recorded
    (e.g. its ``sources`` were edited externally, or evidence went stale
    without a re-write).  Missing pages are skipped (deletion is a separate
    lifecycle concern).
    """
    output_dir = Path(output_dir)
    manifest = load_manifest(output_dir)
    pages = manifest.get("pages", {})
    if not pages:
        return []

    changed = set(changed_files)
    stale: List[str] = []
    for page_key, entry in pages.items():
        if not isinstance(entry, dict):
            continue
        files = entry.get("files")
        if isinstance(files, list) and changed.intersection(files):
            stale.append(page_key)
            continue
        recorded = entry.get("source_fingerprint")
        if isinstance(recorded, str):
            page_path = output_dir / page_key
            if not page_path.is_file():
                continue
            current = compute_source_fingerprint_for_file(page_path)
            if current != recorded:
                stale.append(page_key)
    return stale
