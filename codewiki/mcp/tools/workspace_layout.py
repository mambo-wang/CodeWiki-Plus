"""Workspace layout resolution (centralized vs colocated knowledge layouts).

Single routing seam for the centralized-wiki-layout feature (see
``.scratch/centralized-wiki-layout/spec.md``): every tool that routes
knowledge by ``output_dir`` consults :func:`resolve_workspace` instead of
walking directories on its own.

Guardrails:

1. **Discovery signal is ``<dir>/repowiki/.meta/workspace.json`` only.**
   The bootstrap registration tables are *not* discovery signals — a
   directory without a layout config is a v5.5.0 workspace or a plain
   directory and keeps status-quo behaviour.
2. **A hit still requires membership.**  The repo's directory name (the
   first path component under the workspace root) must appear in the
   bootstrap registration table; unregistered directories (e.g. a stray
   clone inside a workspace tree) are never routed centrally.
3. **Tri-state fallback.**  No workspace found / not a member /
   ``colocated`` layout all mean "keep the status-quo path
   (``repo_path/repowiki``)".
4. **Results are cached** per resolved path for the process lifetime
   (:func:`clear_cache` for tests).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

LAYOUT_COLOCATED = "colocated"
LAYOUT_CENTRALIZED = "centralized"
VALID_LAYOUTS = (LAYOUT_COLOCATED, LAYOUT_CENTRALIZED)

#: Location of the machine-readable layout config, relative to the root.
CONFIG_RELPARTS = ("repowiki", ".meta", "workspace.json")

#: Knowledge-base directory name at the workspace root (discovery anchor).
REPOWIKI_DIRNAME = CONFIG_RELPARTS[0]

_cache: dict[str, "WorkspaceResolution"] = {}


@dataclass(frozen=True)
class WorkspaceResolution:
    """Outcome of resolving a directory against workspace layout rules."""

    root: Path | None
    layout: str
    member: bool

    @property
    def centralized(self) -> bool:
        """True when centralized routing must be applied for this path."""
        return self.root is not None and self.member and self.layout == LAYOUT_CENTRALIZED


def clear_cache() -> None:
    """Drop all cached resolutions (tests and config changes)."""
    _cache.clear()


def find_workspace_root(start: Path) -> Path | None:
    """Walk upward from *start* looking for a workspace layout config.

    Only ``repowiki/.meta/workspace.json`` counts as a signal; stops at the
    filesystem root.  Returns the workspace root directory or None.
    """
    current = start.resolve()
    while True:
        if current.joinpath(*CONFIG_RELPARTS).is_file():
            return current
        if current.parent == current:
            return None
        current = current.parent


def read_layout_value(config_path: Path) -> str | None:
    """Return the stored ``wiki_layout`` value, or None.

    None covers every degraded case: file missing, unreadable, not a JSON
    object, or an unknown value.  Callers decide what None means for them
    (lenient fallback during resolution; conflict detection during init).
    """
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    layout = data.get("wiki_layout")
    return layout if layout in VALID_LAYOUTS else None


def read_layout(workspace_root: Path) -> str:
    """Read ``wiki_layout`` from the workspace config (lenient)."""
    config_path = workspace_root.joinpath(*CONFIG_RELPARTS)
    layout = read_layout_value(config_path)
    if layout is None and config_path.is_file():
        logger.warning(
            "unreadable or invalid workspace config %s; assuming %s",
            config_path,
            LAYOUT_COLOCATED,
        )
    return layout or LAYOUT_COLOCATED


def resolve_workspace(repo_path: Union[str, Path]) -> WorkspaceResolution:
    """Resolve *repo_path* against the workspace layout rules.

    See the module docstring for the guardrails.  Callers should branch on
    :attr:`WorkspaceResolution.centralized`: everything else (single repos,
    unregistered directories, colocated workspaces) keeps the status-quo
    ``repo_path/repowiki`` behaviour.
    """
    start = Path(repo_path).resolve()
    key = str(start)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    root = find_workspace_root(start)
    if root is None:
        resolution = WorkspaceResolution(root=None, layout=LAYOUT_COLOCATED, member=False)
    else:
        # Lazy import: workspace_bootstrap imports this module at top level
        # (layout constants), so the reverse edge must not exist at load time.
        from codewiki.mcp.tools.workspace_bootstrap import read_registration_table_names

        layout = read_layout(root)
        rel = start.relative_to(root)
        first = rel.parts[0] if rel.parts else None
        member = first is not None and first in read_registration_table_names(root)
        resolution = WorkspaceResolution(root=root, layout=layout, member=member)

    _cache[key] = resolution
    return resolution


# ---------------------------------------------------------------------------
# Write routing (ticket 04): where knowledge lands under each layout
# ---------------------------------------------------------------------------


def default_output_dir(repo_path: Union[str, Path]) -> Path:
    """Knowledge-base directory for *repo_path* under the active layout.

    Centralized member → the workspace repowiki (single knowledge base).
    Everything else → status quo ``repo_path/repowiki``.
    """
    rp = Path(repo_path).resolve()
    resolution = resolve_workspace(rp)
    if resolution.centralized:
        return resolution.root / REPOWIKI_DIRNAME
    return rp / REPOWIKI_DIRNAME


def is_centralized_corpus(output_dir: Union[str, Path]) -> bool:
    """True when *output_dir* lies within a centralized workspace's corpus.

    Accepts the corpus root itself (``<root>/repowiki``) or any directory
    inside it (e.g. an explicit partition target).  Used to gate layout-only
    semantics (e.g. the ``repo=`` query filter), which must stay inert
    outside centralized workspaces.
    """
    try:
        od = Path(output_dir).resolve()
    except OSError:
        return False
    root = find_workspace_root(od)
    if root is None:
        return False
    if read_layout(root) != LAYOUT_CENTRALIZED:
        return False
    corpus = (root / REPOWIKI_DIRNAME).resolve()
    return od == corpus or corpus in od.parents


def routing_for_write(
    output_dir: Union[str, Path], repo_path: Union[str, Path, None]
) -> str | None:
    """Partition repo name for a write, or None for status-quo routing.

    Returns the registered directory name of *repo_path* only when ALL hold:
    *repo_path* is a centralized-workspace member, and *output_dir* IS that
    workspace's repowiki (explicit custom targets keep status-quo behaviour).
    Callers use the result to route ``module`` pages into
    ``wiki/modules/<name>/`` and to stamp shared-pool provenance.
    """
    if not repo_path:
        return None
    resolution = resolve_workspace(repo_path)
    if not resolution.centralized:
        return None
    expected = (resolution.root / REPOWIKI_DIRNAME).resolve()
    try:
        if Path(output_dir).resolve() != expected:
            return None
    except OSError:
        return None
    rel = Path(repo_path).resolve().relative_to(resolution.root)
    return rel.parts[0] if rel.parts else None


# ---------------------------------------------------------------------------
# Shared-pool provenance (``repo:`` / ``repos:`` frontmatter)
# ---------------------------------------------------------------------------

_REPO_LINE_RE = re.compile(r"^\s*repo:\s*(?P<val>.+?)\s*$", re.MULTILINE)
_REPOS_LINE_RE = re.compile(r"^\s*repos:\s*(?P<val>.+?)\s*$", re.MULTILINE)


def _frontmatter_block(text: str) -> str:
    """Return the leading YAML frontmatter block (without fences), or ''."""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[4:end] if end != -1 else ""


def _parse_prov_value(raw: str) -> list[str]:
    """Parse a frontmatter scalar or JSON list into repo names."""
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        data = raw.strip("'\"")
    if isinstance(data, list):
        return [str(item) for item in data if str(item).strip()]
    return [str(data)] if str(data).strip() else []


def read_provenance(text: str | None) -> set[str]:
    """Repo names recorded in a page's frontmatter (top-level or metadata)."""
    names: set[str] = set()
    if not text:
        return names
    for m in _REPOS_LINE_RE.finditer(_frontmatter_block(text)):
        names.update(_parse_prov_value(m.group("val")))
    for m in _REPO_LINE_RE.finditer(_frontmatter_block(text)):
        names.update(_parse_prov_value(m.group("val")))
    return names


def parse_scope_arg(value) -> Union[str, list, None]:
    """Normalise the manual-write ``scope`` argument (ticket 06).

    Returns one of three shapes:
    * ``None`` — omitted/empty: automatic stamping with the writing repo;
    * ``"global"`` — product-line knowledge, no provenance;
    * ``list[str]`` — exactly these source repos (single name included).

    Accepts a list, a single repo name, or a comma-separated string.
    Raises ``ValueError`` on values that carry no meaning.
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        names = [str(n).strip() for n in value if str(n).strip()]
        if not names:
            raise ValueError("scope list must not be empty")
        return names
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in ("global", "product", "product-line", "全局"):
        return "global"
    names = [p.strip() for p in text.split(",") if p.strip()]
    if not names:
        raise ValueError(f"invalid scope value: {value!r}")
    return names


def merge_provenance(
    new_content: str,
    old_content: str | None,
    repo_name: str | None = None,
    explicit_scope: Union[str, list, None] = None,
) -> str:
    """Return *new_content* with the desired provenance lines.

    Default (automatic writes): provenance = union(old, new, *repo_name*) —
    later writes overwrite the body, but sources only grow (design doc §9 /
    D9).

    Explicit scope (manual re-scoping, ticket 06) replaces the decision:
    * ``explicit_scope="global"`` → strip provenance entirely (product-line
      knowledge applicable to every repo);
    * ``explicit_scope=["a", "b"]`` → exactly these sources.

    Existing ``repo:``/``repos:`` lines are always replaced by one canonical
    line — ``repo: "<n>"`` for a single source, ``repos: [...]`` for several,
    none for global.

    PLACEMENT: provenance is producer-private under OKF v0.2 (§4/§5), so the
    canonical line is written as a child of the frontmatter's ``metadata:``
    node — the same place ``ingest_note`` stamps it — creating that node when
    absent. Writing it at the top level trips the ``okf_conformance`` lint
    check ("Non-OKF top-level frontmatter key(s): repo").
    """
    if explicit_scope == "global":
        ordered: list[str] = []
    elif isinstance(explicit_scope, (list, tuple)):
        ordered = sorted({str(n) for n in explicit_scope if str(n).strip()})
    else:
        union = read_provenance(old_content) | read_provenance(new_content)
        if repo_name:
            union |= {repo_name}
        ordered = sorted(n for n in union if n)

    canonical = ""
    if len(ordered) == 1:
        canonical = f"repo: {json.dumps(ordered[0], ensure_ascii=False)}"
    elif len(ordered) > 1:
        canonical = f"repos: {json.dumps(ordered, ensure_ascii=False)}"

    lines = new_content.split("\n")

    # Pre-scan the frontmatter for a top-level `metadata:` node.
    metadata_idx: int | None = None
    close_idx: int | None = None
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                close_idx = i
                break
        end = close_idx if close_idx is not None else len(lines)
        for i in range(1, end):
            if lines[i].rstrip() == "metadata:":
                metadata_idx = i
                break

    out: list[str] = []
    fence_count = 0
    inserted = False
    for idx, line in enumerate(lines):
        if line.strip() == "---":
            fence_count += 1
            out.append(line)
            # No `metadata:` node in this frontmatter — create one right after
            # the opening fence so provenance never lands at the top level.
            if fence_count == 1 and canonical and metadata_idx is None and not inserted:
                out.append("metadata:")
                out.append("  " + canonical)
                inserted = True
            continue
        in_fm = fence_count == 1
        if in_fm and (_REPO_LINE_RE.match(line) or _REPOS_LINE_RE.match(line)):
            continue  # replaced by the canonical line (or stripped)
        if in_fm and canonical and not inserted and idx == metadata_idx:
            out.append(line)
            out.append("  " + canonical)
            inserted = True
            continue
        out.append(line)

    # Stripping can leave `metadata:` with no children (invalid YAML) — drop it.
    # Only ever touch the frontmatter region, never the body.
    if close_idx is None:
        return "\n".join(out)
    cleaned: list[str] = []
    for idx, line in enumerate(out):
        if idx <= close_idx + 2 and line.rstrip() == "metadata:":
            nxt = out[idx + 1] if idx + 1 < len(out) else ""
            if not nxt.startswith((" ", "\t")):
                continue
        cleaned.append(line)
    return "\n".join(cleaned)
