"""MCP tool: init_wiki — initialize a Wiki workspace for a project.

Creates the output directory structure, copies the annotated schema.yaml
template (preserving comments), and injects wiki usage instructions into
the project's AGENTS.md.  This is a zero-config bootstrap: run it once
before starting any wiki generation or knowledge ingestion workflow.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Schema template: prefer package-bundled copy, fall back to repo root (dev mode)
_SCHEMA_TEMPLATE_PKG = Path(__file__).resolve().parents[2] / "templates" / "schema.yaml"
_SCHEMA_TEMPLATE_ROOT = Path(__file__).resolve().parents[3] / "schema.yaml"
_SCHEMA_TEMPLATE = _SCHEMA_TEMPLATE_PKG if _SCHEMA_TEMPLATE_PKG.exists() else _SCHEMA_TEMPLATE_ROOT

# Ontology template: project-level term normalization for search
_ONTOLOGY_TEMPLATE_PKG = Path(__file__).resolve().parents[2] / "templates" / "ontology.yaml"
_ONTOLOGY_TEMPLATE = _ONTOLOGY_TEMPLATE_PKG if _ONTOLOGY_TEMPLATE_PKG.exists() else None

# Review checklist override template: project-level merge layer for review_changes
_REVIEW_CHECKLIST_TEMPLATE_PKG = (
    Path(__file__).resolve().parents[2] / "templates" / "review_checklist.yaml"
)
_REVIEW_CHECKLIST_TEMPLATE = (
    _REVIEW_CHECKLIST_TEMPLATE_PKG if _REVIEW_CHECKLIST_TEMPLATE_PKG.exists() else None
)

# Subdirectories to create under output_dir
_WIKI_SUBDIRS = [
    "wiki/modules",
    "wiki/entities",
    "wiki/concepts",
    "wiki/sources",
    "wiki/comparisons",
    "wiki/queries",
    "notes",
]


def initialize_wiki_tree(
    repo_path_p: Path, output_dir_p: Path, *, overwrite_schema: bool = True
) -> dict:
    """Create the wiki directory tree and copy template assets.

    Shared by ``init_wiki`` (single repo) and workspace initialization.

    Returns a dict with keys ``created_dirs``, ``schema_yaml``,
    ``ontology_yaml`` and ``review_checklist_yaml``.  With
    ``overwrite_schema=False`` an existing ``schema.yaml`` is kept untouched
    (workspace re-runs must not clobber user customizations).
    """
    results: dict = {
        "created_dirs": [],
        "schema_yaml": None,
        "ontology_yaml": None,
        "review_checklist_yaml": None,
    }

    for subdir in _WIKI_SUBDIRS:
        dir_path = output_dir_p / subdir
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            results["created_dirs"].append(str(dir_path))

    # Ensure the output_dir itself is recorded if freshly created
    if not output_dir_p.exists():
        output_dir_p.mkdir(parents=True, exist_ok=True)
    if str(output_dir_p) not in results["created_dirs"]:
        results["created_dirs"].insert(0, str(output_dir_p))

    # ── Copy schema.yaml (preserve comments) ─────────────────────────────
    schema_dest = output_dir_p / "schema.yaml"
    if _SCHEMA_TEMPLATE.exists():
        if overwrite_schema or not schema_dest.exists():
            # Raw copy preserves all comments and formatting
            shutil.copy2(str(_SCHEMA_TEMPLATE), str(schema_dest))
            results["schema_yaml"] = str(schema_dest)
            logger.info("Copied schema.yaml template to %s", schema_dest)
        else:
            results["schema_yaml"] = str(schema_dest) + " (already exists, skipped)"
    else:
        results["schema_yaml"] = f"WARNING: template not found at {_SCHEMA_TEMPLATE}"
        logger.warning("schema.yaml template not found: %s", _SCHEMA_TEMPLATE)

    # ── Copy ontology.yaml (term normalization for search) ──────────────
    if _ONTOLOGY_TEMPLATE and _ONTOLOGY_TEMPLATE.exists():
        onto_dest = output_dir_p / "ontology.yaml"
        if not onto_dest.exists():
            shutil.copy2(str(_ONTOLOGY_TEMPLATE), str(onto_dest))
            results["ontology_yaml"] = str(onto_dest)
            logger.info("Copied ontology.yaml template to %s", onto_dest)
        else:
            results["ontology_yaml"] = str(onto_dest) + " (already exists, skipped)"

    # ── Copy review_checklist.yaml (review_changes override) ────────────
    # Skip when present: users customize this file, init must not clobber it.
    if _REVIEW_CHECKLIST_TEMPLATE and _REVIEW_CHECKLIST_TEMPLATE.exists():
        checklist_dest = output_dir_p / "review_checklist.yaml"
        if not checklist_dest.exists():
            shutil.copy2(str(_REVIEW_CHECKLIST_TEMPLATE), str(checklist_dest))
            results["review_checklist_yaml"] = str(checklist_dest)
            logger.info("Copied review_checklist.yaml template to %s", checklist_dest)
        else:
            results["review_checklist_yaml"] = str(checklist_dest) + " (already exists, skipped)"

    return results


def handle_init_wiki(arguments: dict) -> str:
    """Initialize a Wiki workspace: create dirs, copy schema.yaml, write AGENTS.md.

    Parameters (from arguments dict):
        repo_path: Repository root (default: cwd). AGENTS.md is written here.
        output_dir: Wiki output directory (default: <repo_path>/repowiki).

    Returns:
        JSON string with created paths and status.
    """
    repo_path = arguments.get("repo_path", "").strip()
    output_dir = arguments.get("output_dir", "").strip()

    # Resolve repo_path
    if not repo_path:
        repo_path = os.getcwd()
    repo_path_p = Path(repo_path).resolve()

    # Validate repo_path exists and is a directory — avoid silently creating
    # a wiki in a non-existent path or inside a file due to a typo.
    if not repo_path_p.exists():
        return json.dumps(
            {"error": f"repo_path does not exist: {repo_path_p}. Provide a valid repository path."},
            ensure_ascii=False,
        )
    if not repo_path_p.is_dir():
        return json.dumps(
            {
                "error": f"repo_path is not a directory: {repo_path_p}. "
                "Provide a valid repository directory path."
            },
            ensure_ascii=False,
        )

    # Resolve output_dir
    if not output_dir:
        output_dir_p = repo_path_p / "repowiki"
    elif os.path.isabs(output_dir):
        output_dir_p = Path(output_dir).resolve()
    else:
        output_dir_p = (repo_path_p / output_dir).resolve()

    results: dict = {
        "repo_path": str(repo_path_p),
        "output_dir": str(output_dir_p),
        "created_dirs": [],
        "schema_yaml": None,
        "ontology_yaml": None,
        "review_checklist_yaml": None,
        "agents_md": None,
    }

    # ── Steps 1-2: Create directory structure and copy template assets ──
    tree = initialize_wiki_tree(repo_path_p, output_dir_p, overwrite_schema=True)
    results["created_dirs"] = tree["created_dirs"]
    results["schema_yaml"] = tree["schema_yaml"]
    results["ontology_yaml"] = tree["ontology_yaml"]
    results["review_checklist_yaml"] = tree["review_checklist_yaml"]

    # ── Step 3: Write AGENTS.md ─────────────────────────────────────────
    try:
        from codewiki.mcp.tools.agents_md import write_agents_md

        write_agents_md(
            repo_path=str(repo_path_p),
            output_dir=str(output_dir_p),
            module_tree=None,
        )
        agents_path = repo_path_p / "AGENTS.md"
        results["agents_md"] = str(agents_path)
        logger.info("Wrote AGENTS.md at %s", agents_path)
    except Exception as e:
        results["agents_md"] = f"WARNING: failed to write AGENTS.md: {e}"
        logger.warning("Failed to write AGENTS.md: %s", e)

    results["status"] = "ok"
    results["next_steps"] = (
        "Wiki workspace initialized. Next: "
        "1) Edit schema.yaml to set 'purpose' and adjust conventions; "
        "2) Edit ontology.yaml to define project terms and aliases for search; "
        "3) Optionally edit review_checklist.yaml to add team review rules "
        "(merged into review_changes, same id overrides builtin); "
        "4) Run analyze_repo to parse code and generate docs; "
        "5) Or use ingest_note/query_wiki for knowledge management."
    )
    return json.dumps(results, ensure_ascii=False, indent=2)
