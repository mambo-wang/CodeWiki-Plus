"""MCP tool: consolidate_notes — consolidate confirmed notes into L2 scene blocks.

Team-memory fusion 阶段二 P2 (设计方案 §4.3): upgrade fragmented confirmed
notes into a bounded set (≤15) of reusable work-method scene blocks under
``wiki/scenarios/`` — SOP / judgment logic / taboos / principles / experience.

Mode C protocol (agent is the LLM, tool does deterministic bookkeeping):

  mode='prepare'
      returns pending confirmed notes (stable, not yet consolidated), the
      current scenarios index (file/title/summary/heat), a graded capacity
      warning and the consolidation system prompt. The host agent reads notes
      and scene files, then writes/updates scene blocks with
      write_doc_file(page_type="scenario").

  mode='submit'
      takes ``report.scenarios`` — [{file, action, source_notes[], summary?,
      heat?}] with action ∈ created|updated|merged|deleted — validates the
      files, stamps summary/heat into frontmatter, records provenance
      (scenario.metadata.source_notes ⇄ note.metadata.consolidated_into),
      cleans up [DELETED] soft-delete markers, enforces the capacity limit,
      resets the aggregation counter and rebuilds the search index.

Constraints honoured: never consolidates automatically (explicit calls only),
never writes knowledge itself (the agent does), confirmation gates untouched
(source notes are retired by the agent via reject_note, not by this tool).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_VALID_ACTIONS = ("created", "updated", "merged", "deleted")
_SOFT_DELETE_MARKER = "[DELETED]"
_PENDING_NOTES_LIMIT = 50
_SUMMARY_CHARS = 300

_CONSOLIDATE_SYSTEM = (
    "You are the Team Work Method Memory Consolidation Architect.\n"
    "Your job is NOT to retell project history: consolidate fragmented "
    "CONFIRMED notes into reusable work-method scene blocks. From the notes, "
    "distill:\n"
    "  - SOP: how similar work should be done step by step (and why)\n"
    "  - Judgment logic: decision criteria, priorities, trade-off reasons\n"
    "  - Taboos / anti-patterns: what must not be done again, failure modes\n"
    "  - Principles: constraints and standards to keep long term\n"
    "  - Experience: reusable methods for agents and the team\n"
    "Facts, tasks and statuses are kept only as the SOURCE and APPLICABILITY "
    "CONDITIONS of a method. Never produce project diaries, chat summaries, "
    "task lists, personal profiles, or BATCH/REPORT/SUMMARY aggregate files.\n\n"
    "STRATEGY (mandatory):\n"
    "1. Default is UPDATE, not CREATE. When torn between UPDATE and CREATE, "
    "UPDATE.\n"
    "2. Before CREATE you must read at least 2 most-similar existing scene "
    "files and confirm the new knowledge truly fits nowhere; at most ONE new "
    "scene per batch.\n"
    "3. Merge priority: overlapping work object > same project chain > same "
    "method system > lowest heat.\n"
    "4. Capacity: the scenarios directory has a hard cap (see the capacity "
    "warning in prepare). RED means merge first until below the cap; ORANGE "
    "means UPDATE only; YELLOW means prefer UPDATE/MERGE.\n"
    "5. Heat: new scene heat=1; updated heat=old+1; merged heat=sum+1.\n"
    "6. Conflicts: when new knowledge contradicts an existing scene, record "
    "it under the evolution/open-questions sections; do not silently "
    "overwrite.\n"
    "7. Deleting a scene: rewrite its content to exactly [DELETED] via "
    "write_doc_file/edit_doc_file; the tool removes marked files on submit.\n\n"
    "SCENE FILE CONTENT (each file ≤1500 chars, Markdown, sections):\n"
    "## Work context        — which projects/tasks/method systems this applies to\n"
    "## Applicability       — when the method applies (phase, risk, constraints)\n"
    "## Core SOP            — THE key section: reusable steps, each with rationale\n"
    "## Judgment logic      — decision criteria and trade-off reasons\n"
    "## Taboos & anti-patterns — what to avoid, why, and the correct alternative\n"
    "## Key evidence        — optional; only facts that support the SOP/logic\n"
    "## Related tasks & assets — optional; follow-ups (owner/deadline), docs/PRs\n"
    "## Evolution           — optional; method/rule changes only, not progress\n"
    "## Open questions      — optional; unresolved items affecting the method\n\n"
    "WORKFLOW:\n"
    "(1) Read the pending notes listed in prepare (view_repo_file); group them "
    "by work object / method system (metadata.scene helps).\n"
    "(2) Read the existing scene files you plan to touch.\n"
    "(3) Write scene blocks with write_doc_file(page_type='scenario', ...) — "
    "filenames: letters/digits/CJK/-/_ only, .md suffix, no spaces or "
    "punctuation.\n"
    "(4) For notes fully absorbed by a scene, call reject_note with "
    "reason='consolidated into <scene title>' so they retire from search.\n"
    "(5) Call consolidate_notes(mode='submit', report=...) listing every scene "
    "you created/updated/merged/deleted with its absorbed source notes, plus "
    "a 30-40-word summary and the heat value per scene.\n"
    "Ask the user before starting if the preparation context suggests the "
    "consolidation was tool-initiated by a reminder."
)


# --------------------------------------------------------------------------- #
# Frontmatter helpers (YAML round-trip, aligned with _apply_status_to_file)
# --------------------------------------------------------------------------- #
def _read_frontmatter(path: Path) -> Optional[Dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end < 0:
        return None
    try:
        import yaml

        data = yaml.safe_load(text[3:end])
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _read_body(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    if text.startswith("---"):
        end = text.find("---", 3)
        if end >= 0:
            return text[end + 3 :].strip()
    return text.strip()


def _update_frontmatter_meta(path: Path, updates: Dict[str, Any]) -> bool:
    """Merge *updates* into the frontmatter ``metadata`` mapping (round-trip)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if not text.startswith("---"):
        return False
    end = text.find("---", 3)
    if end < 0:
        return False
    try:
        import yaml

        data = yaml.safe_load(text[3:end])
        if not isinstance(data, dict):
            return False
        meta = data.get("metadata")
        if not isinstance(meta, dict):
            meta = {}
        meta.update(updates)
        data["metadata"] = meta
        new_fm = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
        path.write_text(f"---\n{new_fm}---{text[end + 3 :]}", encoding="utf-8")
        return True
    except Exception as e:
        logger.warning("frontmatter update failed for %s: %s", path, e)
        return False


def _append_meta_list(path: Path, key: str, values: List[str]) -> bool:
    """Append *values* to a list field under metadata (deduplicated)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if not text.startswith("---"):
        return False
    end = text.find("---", 3)
    if end < 0:
        return False
    try:
        import yaml

        data = yaml.safe_load(text[3:end])
        if not isinstance(data, dict):
            return False
        meta = data.get("metadata")
        if not isinstance(meta, dict):
            meta = {}
        existing = meta.get(key)
        if isinstance(existing, str):
            existing = [existing]
        if not isinstance(existing, list):
            existing = []
        for v in values:
            if v and v not in existing:
                existing.append(v)
        meta[key] = existing
        data["metadata"] = meta
        new_fm = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
        path.write_text(f"---\n{new_fm}---{text[end + 3 :]}", encoding="utf-8")
        return True
    except Exception as e:
        logger.warning("frontmatter list append failed for %s: %s", path, e)
        return False


def _norm_rel(p: str, output_dir: Path) -> str:
    return str(p).replace("\\", "/").lstrip("./")


# --------------------------------------------------------------------------- #
# Directory scans
# --------------------------------------------------------------------------- #
def _scenarios_dir(output_dir: Path) -> Path:
    from codewiki.src.config import WIKI_DIR, PAGE_TYPE_DIRS

    return Path(output_dir) / WIKI_DIR / PAGE_TYPE_DIRS["scenario"]


def _scan_scenarios(output_dir: Path) -> List[Dict[str, Any]]:
    """Index of live scene blocks: file/title/summary/heat/updated."""
    sdir = _scenarios_dir(output_dir)
    out: List[Dict[str, Any]] = []
    if not sdir.is_dir():
        return out
    for p in sorted(sdir.glob("*.md")):
        if _read_body(p) == _SOFT_DELETE_MARKER:
            continue  # pending soft-delete, excluded from index & capacity
        fm = _read_frontmatter(p) or {}
        meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
        try:
            heat = int(meta.get("heat") or 0)
        except (TypeError, ValueError):
            heat = 0
        out.append(
            {
                "file": _norm_rel(str(p.relative_to(output_dir)), output_dir),
                "title": fm.get("title") or p.stem,
                "summary": str(meta.get("summary") or "")[:_SUMMARY_CHARS],
                "heat": heat,
                "updated": str(fm.get("generated", {}).get("at", ""))
                if isinstance(fm.get("generated"), dict)
                else "",
            }
        )
    return out


def _pending_confirmed_notes(output_dir: Path, limit: int) -> List[Dict[str, Any]]:
    """Stable notes not yet absorbed into a scene block (no consolidated_into)."""
    from codewiki.src.config import NOTES_DIR

    notes_dir = Path(output_dir) / NOTES_DIR
    out: List[Dict[str, Any]] = []
    if not notes_dir.is_dir():
        return out
    for p in sorted(notes_dir.glob("*.md")):
        fm = _read_frontmatter(p) or {}
        status = str(fm.get("status", "")).lower()
        if status not in ("stable", "confirmed"):
            continue
        meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
        if meta.get("consolidated_into"):
            continue  # already absorbed
        body = _read_body(p)
        scene = ""
        if isinstance(meta.get("scene"), str):
            scene = meta["scene"]
        out.append(
            {
                "file": _norm_rel(str(p.relative_to(output_dir)), output_dir),
                "title": fm.get("title") or p.stem,
                "note_type": fm.get("type") or "general",
                "scene": scene,
                "severity": str(meta.get("severity") or ""),
                "preview": body[:_SUMMARY_CHARS],
            }
        )
        if len(out) >= limit:
            break
    return out


def _cleanup_soft_deleted(output_dir: Path) -> List[str]:
    """Unlink scene files whose body is exactly the [DELETED] marker."""
    removed: List[str] = []
    sdir = _scenarios_dir(output_dir)
    if not sdir.is_dir():
        return removed
    for p in sdir.glob("*.md"):
        if _read_body(p) == _SOFT_DELETE_MARKER:
            try:
                p.unlink()
                removed.append(_norm_rel(str(p.relative_to(output_dir)), output_dir))
            except OSError:
                pass
    return removed


# --------------------------------------------------------------------------- #
# Capacity
# --------------------------------------------------------------------------- #
def _capacity(output_dir: Path, live_count: int) -> Dict[str, Any]:
    from codewiki.mcp.tools.aggregation_state import read_config

    max_scenes = read_config(output_dir)["max_scenarios"]
    if live_count >= max_scenes:
        warning = "red"
    elif live_count == max_scenes - 1:
        warning = "orange"
    elif live_count >= max_scenes - 3:
        warning = "yellow"
    else:
        warning = "none"
    return {"current": live_count, "max": max_scenes, "warning": warning}


# --------------------------------------------------------------------------- #
# Tool handler
# --------------------------------------------------------------------------- #
def _resolve_output_dir(session: Optional[Any], arguments: Dict[str, Any]) -> Path:
    """Resolve the output directory — delegates to the shared store bridge.

    (Layout-aware: centralized members route to the workspace-root corpus,
    matching every other tool — this module previously used the plain
    ``<repo>/repowiki`` path, a latent divergence under centralized layouts.)
    """
    from codewiki.mcp.tools.store_bridge import resolve_output_dir

    return resolve_output_dir(session, arguments)


def handle_consolidate_notes(arguments: Dict[str, Any], store: Any) -> str:
    """Consolidate confirmed notes into L2 work-method scene blocks (Mode C)."""
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    if session is None and session_id:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    try:
        output_dir = _resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    mode = str(arguments.get("mode") or "prepare").lower()
    if mode not in ("prepare", "submit"):
        return json.dumps({"error": f"Invalid mode '{mode}'. Expected one of: prepare, submit."})

    from codewiki.mcp.tools import aggregation_state as agg

    if mode == "prepare":
        limit = min(200, max(1, int(arguments.get("limit") or _PENDING_NOTES_LIMIT)))
        scenarios = _scan_scenarios(output_dir)
        capacity = _capacity(output_dir, len(scenarios))
        pending = _pending_confirmed_notes(output_dir, limit)
        state = agg.load_state(output_dir)
        cfg = agg.read_config(output_dir)
        return json.dumps(
            {
                "status": "prepared",
                "mode": "prepare",
                "counters": {
                    "notes_since_last_consolidation": int(
                        state.get("notes_since_last_consolidation") or 0
                    ),
                    "consolidation_threshold": cfg["consolidation_threshold"],
                    "last_consolidation_at": state.get("last_consolidation_at"),
                },
                "capacity": capacity,
                "pending_notes": pending,
                "pending_total": len(pending),
                "scenarios_index": scenarios,
                "system_prompt": _CONSOLIDATE_SYSTEM,
                "next": (
                    "(1) Read pending notes (view_repo_file) — metadata.scene groups "
                    "related ones; (2) read the scene files you plan to UPDATE/MERGE; "
                    "(3) write blocks with write_doc_file(page_type='scenario'); obey "
                    "the capacity warning (red=merge first, orange=update only); "
                    "(4) reject_note fully-absorbed source notes with "
                    "reason='consolidated into <scene title>'; (5) submit the report. "
                    "If this consolidation was triggered by an aggregation_hint "
                    "reminder, confirm with the user before starting."
                ),
            },
            indent=2,
            ensure_ascii=False,
        )

    # ---- mode == "submit" ----
    report = arguments.get("report")
    if isinstance(report, str):
        try:
            report = json.loads(report)
        except json.JSONDecodeError:
            return json.dumps({"error": "report must be a JSON object."})
    if not isinstance(report, dict):
        return json.dumps(
            {
                "error": (
                    "mode='submit' requires 'report': {scenarios: [{file, action, "
                    "source_notes, summary?, heat?}]} with action in "
                    "created|updated|merged|deleted."
                ),
            }
        )
    entries = report.get("scenarios")
    if not isinstance(entries, list) or not entries:
        return json.dumps({"error": "report.scenarios must be a non-empty list."})

    processed: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append({"entry": str(entry), "error": "not an object"})
            continue
        rel = _norm_rel(str(entry.get("file") or ""), output_dir)
        action = str(entry.get("action") or "").lower()
        if not rel:
            errors.append({"entry": str(entry), "error": "missing file"})
            continue
        if action not in _VALID_ACTIONS:
            errors.append({"file": rel, "error": f"invalid action '{action}'"})
            continue
        path = output_dir / rel
        # Path safety: keep everything inside output_dir
        try:
            path.resolve().relative_to(Path(output_dir).resolve())
        except ValueError:
            errors.append({"file": rel, "error": "path escapes output_dir"})
            continue

        if action == "deleted":
            if path.is_file():
                if _read_body(path) != _SOFT_DELETE_MARKER:
                    errors.append(
                        {
                            "file": rel,
                            "error": "action=deleted requires the file body to be exactly [DELETED]",
                        }
                    )
                    continue
            processed.append({"file": rel, "action": "deleted"})
            continue

        if not path.is_file():
            errors.append({"file": rel, "error": "scene file not found"})
            continue
        fm = _read_frontmatter(path)
        if fm is None or str(fm.get("type", "")).lower() != "scenario":
            errors.append(
                {
                    "file": rel,
                    "error": "frontmatter must carry type: Scenario (write via write_doc_file page_type='scenario')",
                }
            )
            continue

        # Provenance: scene ← source notes (bidirectional links)
        source_notes = [
            _norm_rel(str(s), output_dir)
            for s in (entry.get("source_notes") or [])
            if str(s).strip()
        ]
        if source_notes:
            _append_meta_list(path, "source_notes", source_notes)
            from codewiki.src.config import NOTES_DIR

            notes_dir = Path(output_dir) / NOTES_DIR
            for src in source_notes:
                note_path = Path(output_dir) / src
                if note_path.is_file():
                    _append_meta_list(note_path, "consolidated_into", [rel])
                elif (notes_dir / Path(src).name).is_file():
                    _append_meta_list(notes_dir / Path(src).name, "consolidated_into", [rel])

        # Stamp summary/heat (agent-reported, deterministic write)
        meta_updates: Dict[str, Any] = {}
        summary = str(entry.get("summary") or "").strip()
        if summary:
            meta_updates["summary"] = summary[:_SUMMARY_CHARS]
        heat = entry.get("heat")
        if heat is not None:
            try:
                meta_updates["heat"] = max(0, int(heat))
            except (TypeError, ValueError):
                pass
        if meta_updates:
            _update_frontmatter_meta(path, meta_updates)

        processed.append(
            {
                "file": rel,
                "action": action,
                "source_notes": len(source_notes),
            }
        )

    if errors:
        return json.dumps(
            {
                "status": "error",
                "mode": "submit",
                "errors": errors,
                "processed": processed,
                "message": (
                    f"{len(errors)} report entr(y/ies) failed validation; counters "
                    "NOT reset. Fix the reported issues and re-submit."
                ),
            },
            indent=2,
            ensure_ascii=False,
        )

    # Soft-delete cleanup + capacity enforcement
    removed = _cleanup_soft_deleted(output_dir)
    live = _scan_scenarios(output_dir)
    capacity = _capacity(output_dir, len(live))
    if capacity["warning"] == "red":
        return json.dumps(
            {
                "status": "capacity_exceeded",
                "mode": "submit",
                "processed": processed,
                "removed_deleted": removed,
                "capacity": capacity,
                "message": (
                    f"Scenario count {capacity['current']} exceeds the cap "
                    f"{capacity['max']}. MERGE similar scenes (and mark the losers "
                    "[DELETED]) until below the cap, then re-submit. Counters NOT reset."
                ),
            },
            indent=2,
            ensure_ascii=False,
        )

    state = agg.mark_consolidated(output_dir)

    # P3 cascade hint (§4.5.2): scenes were just refreshed — if the doctrine
    # counter is also over its threshold, this is the natural moment to run
    # refresh_doctrine. Still a hint only: the agent must ask the user.
    doctrine_hint = None
    try:
        cfg = agg.read_config(output_dir)
        d_counter = int(state.get("notes_since_last_doctrine") or 0)
        if d_counter >= cfg["doctrine_threshold"]:
            doctrine_hint = {
                "doctrine_due": True,
                "notes_since_last_doctrine": d_counter,
                "doctrine_threshold": cfg["doctrine_threshold"],
                "message": (
                    "Scenes were just consolidated and the doctrine counter is "
                    "over its threshold — suggest refresh_doctrine next. Ask "
                    "the user first, never run it silently."
                ),
            }
    except Exception:
        pass

    # Rebuild the search index so scene blocks become queryable immediately.
    try:
        from codewiki.mcp.tools.wiki_search import build_full_index

        build_full_index(output_dir)
    except Exception as e:  # indexing is best-effort
        logger.warning("search index rebuild failed after consolidate: %s", e)

    return json.dumps(
        {
            "status": "completed",
            "mode": "submit",
            "processed": processed,
            "removed_deleted": removed,
            "capacity": capacity,
            "counters": {
                "notes_since_last_consolidation": int(
                    state.get("notes_since_last_consolidation") or 0
                ),
                "notes_since_last_doctrine": int(state.get("notes_since_last_doctrine") or 0),
            },
            **({"doctrine_hint": doctrine_hint} if doctrine_hint else {}),
            "message": (
                f"Consolidation recorded: {len(processed)} scene operation(s). "
                "Counter reset. Confirm the new/updated scene blocks are reviewed; "
                "source notes absorbed into scenes should be retired via reject_note."
            ),
        },
        indent=2,
        ensure_ascii=False,
    )
