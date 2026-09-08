"""General-axis checklists for ``review_changes`` — data-only module.

Two layers:

* **Language-agnostic** — engineering baseline items every change must pass
  (``BUILTIN["all"]``).
* **Per-language** — items selected by the changed file's extension
  (``BUILTIN[lang]``, currently Python only; more languages are P1).

Project override: if ``<repo>/repowiki/review_checklist.yaml`` exists it is
merged at prepare time — an entry with the same ``id`` replaces the builtin
one, unknown ids are appended.  The file is bootstrapped by ``init_wiki``
from the template at ``codewiki/templates/review_checklist.yaml`` (copied
only when absent, so user edits survive re-runs).  Shape of the YAML::

    # repowiki/review_checklist.yaml
    all:
      - id: err-handling
        title: 错误处理
        questions: ["..."]

    python:
      - id: ...
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Extension → checklist language key (lowercased suffix, no dot).
LANG_BY_EXT = {
    ".py": "python",
    ".go": "go",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cpp": "c",
    ".hpp": "c",
    ".cc": "c",
    ".php": "php",
    ".rb": "ruby",
    ".rs": "rust",
}

# Builtin checklist ids grouped by scope.  Titles and questions live in the
# message catalog (``review_checklist.<group>.<id>.*``) so the delivered
# checklist follows the resolved language.  Ids stay here and stay stable —
# project overrides merge on them.
_BUILTIN_CHECKLIST_GROUPS: Dict[str, List[str]] = {
    "all": [
        "err-handling",
        "input-validation",
        "logging",
        "security",
        "concurrency",
        "null-boundary",
        "testability",
        "backward-compat",
        "performance",
        "code-quality",
    ],
    "python": [
        "py-mutable-default",
        "py-bare-except",
        "py-resource-context",
        "py-encoding",
        "py-import-side-effect",
    ],
}


def builtin_checklists() -> Dict[str, List[Dict[str, Any]]]:
    """Resolve the builtin checklist for the current language."""
    from codewiki.mcp import i18n

    out: Dict[str, List[Dict[str, Any]]] = {}
    for group, ids in _BUILTIN_CHECKLIST_GROUPS.items():
        entries: List[Dict[str, Any]] = []
        for cid in ids:
            base = f"review_checklist.{group}.{cid}"
            questions = i18n.t(base + ".questions")
            entries.append(
                {
                    "id": cid,
                    "title": i18n.t(base + ".title"),
                    "questions": [q for q in questions.split("|") if q],
                }
            )
        out[group] = entries
    return out


def load_project_checklist(repo_path: Optional[str]) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """Load ``<repo>/repowiki/review_checklist.yaml`` if present.

    Returns ``None`` when the file is absent or unreadable (malformed YAML is
    logged and ignored — a broken override must not break the review).
    """
    if not repo_path:
        return None
    from codewiki.mcp.tools.workspace_layout import default_output_dir

    p = default_output_dir(Path(repo_path)) / "review_checklist.yaml"
    if not p.exists():
        return None
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML unavailable, falling back to builtin checklist (override: %s)", p)
        return None
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse project checklist %s, falling back to builtin: %s", p, exc)
        return None
    if not isinstance(data, dict):
        logger.warning(
            "Project checklist %s is not a mapping (%s), falling back to builtin",
            p,
            type(data).__name__,
        )
        return None
    out: Dict[str, List[Dict[str, Any]]] = {}
    for key, entries in data.items():
        if not isinstance(entries, list):
            logger.warning("Section %r of %s is not a list, skipped", key, p)
            continue
        valid = [e for e in entries if isinstance(e, dict) and e.get("id")]
        if len(valid) != len(entries):
            logger.warning("Section %r of %s dropped entries missing 'id'", key, p)
        out[str(key)] = valid
    return out


def get_checklist(
    repo_path: Optional[str],
    changed_files: List[str],
) -> List[Dict[str, Any]]:
    """Resolve the merged checklist for a set of changed files.

    Language-agnostic items always included; per-language items added for
    each distinct language among the changed files.  Project overrides merge
    by ``id`` (same id replaces, unknown id appends).
    """
    langs: List[str] = []
    for f in changed_files:
        lang = LANG_BY_EXT.get(Path(f).suffix.lower())
        if lang and lang not in langs:
            langs.append(lang)

    merged: Dict[str, Dict[str, Any]] = {}
    for lang in ["all", *langs]:
        for entry in builtin_checklists().get(lang, []):
            merged[entry["id"]] = dict(entry, lang=lang)

    project = load_project_checklist(repo_path)
    if project:
        for lang in ["all", *langs]:
            for entry in project.get(lang, []):
                merged[entry["id"]] = dict(entry, lang=lang)

    return [merged[k] for k in merged]
