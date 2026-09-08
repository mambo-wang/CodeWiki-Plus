"""Inject wiki usage instructions into the target project's AGENTS.md.

Called from ``close_session`` after wiki generation completes.  Uses HTML
comment delimiters so repeated invocations update only the CodeWiki section
without overwriting user-authored content.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Delimiters for the injectable section
_BEGIN_MARKER = "<!-- CodeWiki LLM Wiki -->"
_END_MARKER = "<!-- /CodeWiki LLM Wiki -->"

# Delimiters for the multi-repo workspace conventions section.  Independent
# from the CodeWiki usage block above: the two sections are upserted
# separately and never touch each other.
_WORKSPACE_BEGIN_MARKER = "<!-- CodeWiki Workspace Conventions -->"
_WORKSPACE_END_MARKER = "<!-- /CodeWiki Workspace Conventions -->"

_WORKSPACE_TEMPLATE = (
    Path(__file__).resolve().parents[2] / "templates" / "workspace" / "agents-md-workspace.md.tpl"
)


def _upsert_marked_section(agents_path: Path, begin: str, end: str, section: str) -> str:
    """Insert or replace a marker-delimited section in AGENTS.md.

    - File missing → create it with the section.
    - Markers found → replace only the delimited block, keep the rest.
    - File without markers → append the section at the end.

    Returns ``"created"``, ``"replaced"`` or ``"appended"``.
    """
    if agents_path.exists():
        content = agents_path.read_text(encoding="utf-8")
        begin_idx = content.find(begin)
        end_idx = content.find(end)

        if begin_idx != -1 and end_idx != -1 and end_idx > begin_idx:
            # Replace existing section (keep content before/after)
            before = content[:begin_idx]
            after = content[end_idx + len(end) :]
            new_content = before + section + after
            action = "replaced"
        else:
            # Append section at end
            separator = "\n\n" if not content.endswith("\n") else "\n"
            new_content = content + separator + section + "\n"
            action = "appended"
    else:
        new_content = section + "\n"
        action = "created"

    agents_path.write_text(new_content, encoding="utf-8")
    return action


def write_agents_md(*, repo_path: str, output_dir: str, module_tree: dict | None = None) -> None:
    """Create or update ``<repo_path>/AGENTS.md`` with wiki usage info.

    - If the file does not exist, it is created with the section.
    - If the section markers are found, only the delimited block is replaced.
    - If the file exists but has no markers, the section is appended.

    Failures are logged and silently swallowed — this must never block
    session cleanup.
    """
    _write_agents_md(repo_path, output_dir, module_tree or {})


def remove_codewiki_block(repo_path: str) -> str:
    """Remove the CodeWiki usage block from ``<repo_path>/AGENTS.md``.

    Centralized workspaces keep business repos pure-code — there is no
    in-repo ``repowiki/`` for the block to point at, so the block is a dead
    reference and is removed when the repo is registered (ticket 03).  All
    content outside the markers (the repo's own conventions) is preserved.

    Returns ``"removed"`` | ``"kept (no block)"`` | ``"kept (no AGENTS.md)"``.
    Failures are logged and swallowed — this must never block registration.
    """
    repo_path_p = Path(repo_path)
    agents_path = repo_path_p / "AGENTS.md"
    if not agents_path.exists():
        return "kept (no AGENTS.md)"

    try:
        content = agents_path.read_text(encoding="utf-8")
        begin_idx = content.find(_BEGIN_MARKER)
        end_idx = content.find(_END_MARKER)
        if begin_idx == -1 or end_idx == -1 or end_idx <= begin_idx:
            return "kept (no block)"

        before = content[:begin_idx]
        after = content[end_idx + len(_END_MARKER) :]
        # Avoid leaving a double blank seam where the block used to be.
        before = before.rstrip("\n")
        after = after.lstrip("\n")
        if before and after:
            new_content = before + "\n\n" + after
        else:
            new_content = before + after
        agents_path.write_text(new_content, encoding="utf-8")
        logger.info("Removed CodeWiki block from %s", agents_path)
        return "removed"
    except Exception as e:  # must never block registration
        logger.warning("Failed to remove CodeWiki block from %s: %s", agents_path, e)
        return f"kept (error: {e})"


def _write_agents_md(repo_path: str, output_dir: str, module_tree: dict) -> None:
    """Internal implementation of write_agents_md."""
    repo_path_p = Path(repo_path)
    output_dir_p = Path(output_dir)

    # Relative path from repo root to wiki output (portable across machines)
    try:
        rel_path = os.path.relpath(output_dir_p, repo_path_p).replace("\\", "/")
    except ValueError:
        # On Windows, relpath fails across drives — fall back to absolute
        rel_path = str(output_dir_p).replace("\\", "/")

    # Extract module names from the saved module tree
    modules = _extract_modules(module_tree)

    section = _build_section(rel_path, modules, output_dir_p)
    agents_path = repo_path_p / "AGENTS.md"

    _upsert_marked_section(agents_path, _BEGIN_MARKER, _END_MARKER, section)
    logger.info("Updated AGENTS.md at %s", agents_path)


def write_workspace_conventions(
    *,
    workspace_path: str,
    workspace_name: str,
    layout: str = "colocated",
) -> str:
    """Write the multi-repo workspace conventions section into AGENTS.md.

    The marked block is tool-maintained: it is always overwritten on every
    run, so customizations belong outside the markers (they survive; the
    block content itself does not).

    ``layout`` selects the conventions variant: ``colocated`` (two-hop
    routing, per-repo repowikis) or ``centralized`` (one-hop routing,
    single workspace repowiki).

    Returns ``"created"`` | ``"refreshed"``.
    """
    workspace_path_p = Path(workspace_path)
    agents_path = workspace_path_p / "AGENTS.md"

    from codewiki.mcp.tools.workspace_layout import LAYOUT_CENTRALIZED

    template_name = (
        "agents-md-workspace-centralized.md.tpl"
        if layout == LAYOUT_CENTRALIZED
        else "agents-md-workspace.md.tpl"
    )
    template_path = _WORKSPACE_TEMPLATE.parent / template_name
    body = template_path.read_text(encoding="utf-8").replace("{{WORKSPACE_NAME}}", workspace_name)
    section = f"{_WORKSPACE_BEGIN_MARKER}\n\n{body}\n{_WORKSPACE_END_MARKER}"
    action = _upsert_marked_section(
        agents_path, _WORKSPACE_BEGIN_MARKER, _WORKSPACE_END_MARKER, section
    )
    logger.info("Workspace conventions %s in %s", action, agents_path)
    return "refreshed" if action == "replaced" else "created"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_modules(module_tree: dict) -> list[str]:
    """Recursively collect all module names (top-level + nested children)."""
    names: list[str] = []
    if not module_tree or not isinstance(module_tree, dict):
        return names
    for name, node in module_tree.items():
        names.append(name)
        children = node.get("children") if isinstance(node, dict) else None
        if children and isinstance(children, dict):
            names.extend(_extract_modules(children))
    return names


def _build_section(rel_path: str, modules: list[str], output_dir_p: Path) -> str:
    """Build the delimited Markdown section for AGENTS.md.

    The prose lives in the message catalog (``artifacts.agents_md.*``) so the
    block follows the resolved language; the module listing is computed here.
    """
    from codewiki.mcp import i18n as _i18n

    # Module listing with links (structured wiki layout)
    if modules:
        # V2 (injection budget): cap the module list; overflow collapses to a
        # pointer line so AGENTS.md stops growing linearly with module count.
        try:
            from codewiki.mcp.tools.page_router import load_schema
            from codewiki.mcp.tools.injection_budget import cap_module_lines

            capped = cap_module_lines(modules, output_dir_p, load_schema(str(output_dir_p)))
        except Exception:  # budget must never break AGENTS.md injection
            capped = {"lines": modules, "hidden_count": 0}
        module_lines = "\n".join(
            f"- [{m}]({rel_path}/wiki/modules/{m}.md)" for m in capped["lines"]
        )
        hidden = int(capped.get("hidden_count") or 0)
        overflow = (
            _i18n.t("artifacts.agents_md.modules_overflow", hidden=hidden, rel_path=rel_path)
            if hidden
            else ""
        )
        modules_block = _i18n.t(
            "artifacts.agents_md.modules_block",
            module_lines=module_lines,
            overflow=overflow,
        )
    else:
        modules_block = ""

    return _i18n.t(
        "artifacts.agents_md.main",
        begin_marker=_BEGIN_MARKER,
        end_marker=_END_MARKER,
        rel_path=rel_path,
        modules_block=modules_block,
    )
