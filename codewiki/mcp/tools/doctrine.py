"""MCP tool: refresh_doctrine — regenerate the L3 Project Operating Doctrine.

Team-memory fusion 阶段二 P3 (设计方案 §4.4): compress confirmed knowledge
(L2 scene blocks + confirmed notes) into ONE highly-refined ``wiki/doctrine.md``
(≤1200 chars) — the project's Operating Doctrine: how to judge, how to execute,
how to avoid mistakes. Not a project summary, not a progress log, not a scene
index.

Mode C protocol (agent is the LLM, tool does deterministic bookkeeping):

  mode='prepare'
      returns the current doctrine, the scenario list with change flags
      (updated since last refresh), statistics (total confirmed notes /
      scenes / changed scenes), the doctrine counter state and the doctrine
      system prompt (six dimensions / five filters / five incremental
      strategies / hard prohibitions / output template).

  mode='submit'
      validates the ≤1200-char hard cap, atomically writes wiki/doctrine.md
      with OKF frontmatter + provenance (source_scenarios), resets the
      doctrine counter and rebuilds the search index.

Constraints honoured: explicit calls only (never automatic); the produced
doctrine lands as status=draft awaiting the normal confirmation gate.
"""

from __future__ import annotations

import json
import logging

from codewiki.src.store import atomic_write
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DOCTRINE_FILENAME = "doctrine.md"
DEFAULT_DOCTRINE_MAX_CHARS = 1200

_DOCTRINE_SYSTEM = (
    "You are the Team Operating Doctrine Architect.\n"
    "Combine the existing doctrine (if any) with the changed L2 scene blocks "
    "and confirmed notes to produce ONE highly-refined Project Operating "
    "Doctrine. It is NOT a project summary, progress log, scene index or fact "
    "collection — it must help any agent or teammate facing NEW tasks know "
    "how to judge, how to execute, and how to avoid mistakes.\n\n"
    "SIX DIMENSIONS to distill:\n"
    "1. SOP — how similar tasks should be done\n"
    "2. Principle — long-term working principles\n"
    "3. Decision Logic — criteria for trade-offs\n"
    "4. Boundary — what must not be done / not automated\n"
    "5. Anti-pattern — practices that cause errors or pollute knowledge\n"
    "6. Agent Rule — rules agents must follow when working/updating memory\n"
    "Project facts, task states and asset names are EVIDENCE only; write them "
    "into the doctrine only when they abstract into cross-scenario rules.\n\n"
    "FIVE FILTERS before writing anything (skip the item if ANY fails):\n"
    "generality (applies beyond one project/task) | completeness "
    "(understandable without the original context) | executability (an agent can "
    "change behavior based on it) | stability (long-lived, not one-shot state) "
    "| conciseness (cannot be shorter or merged into an existing principle).\n\n"
    "INCREMENTAL STRATEGY — judge per changed scene; keep compressing, never "
    "just append:\n"
    "REINFORCE (new scene backs an existing principle: fold in or leave) | "
    "SUPPLEMENT (new general SOP/taboo/logic/rule) | REVISE (old principle "
    "overturned or boundary clarified) | REFACTOR (doctrine grew scattered/"
    "project-specific: compress-rewrite) | NO-CHANGE (only project state or "
    "low-level facts: do not update).\n\n"
    "HARD PROHIBITIONS:\n"
    "- Exceeding the char cap (the tool rejects it)\n"
    "- Project-bound fragments ('v2 will optimize X') nobody understands "
    "outside that project\n"
    "- Progress logs / who-did-what unless abstracted into a method\n"
    "- Low-level fact piles (names/versions/PR numbers) unless they are "
    "reusable paradigms\n"
    "- Semantically incomplete rules (every principle must stand alone with "
    "action object + applicability or judgment logic)\n"
    "- Personal profiling (member personality/preferences/emotions)\n"
    "- Speculation without scene evidence\n\n"
    "OUTPUT TEMPLATE (Markdown; sections may be trimmed; total <= the char "
    "cap):\n"
    "# Team Operating Doctrine\n"
    "> Operating Thesis: [one sentence — the single most general working "
    "method or agent rule of this project]\n"
    "## Core Principles\n"
    "- [principle]: [applicability / judgment logic / why it matters]\n"
    "## Reusable SOPs\n"
    "- [SOP name]: when [trigger], first [step1], then [step2], finally "
    "[output/acceptance]\n"
    "## Decision Logic\n"
    "- when [scenario], prefer [A] over [B] because [reason]\n"
    "## Boundaries & Anti-patterns\n"
    "- do not [wrong practice]; instead [recommended practice], because "
    "[reason]\n"
    "## Agent Rules\n"
    "- agents should [behavior rule] to avoid [risk]\n"
    "---\n"
    "> Last updated: [time] · Source scenes: [n] · Total notes: [m]\n\n"
    "Submit ONLY the final doctrine Markdown via refresh_doctrine(mode="
    "'submit', content=...). Do not include your analysis."
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _doctrine_path(output_dir: Path) -> Path:
    from codewiki.src.config import WIKI_DIR

    return Path(output_dir) / WIKI_DIR / DOCTRINE_FILENAME


def _max_chars(output_dir: Path) -> int:
    try:
        from codewiki.mcp.tools.page_router import load_schema

        schema = load_schema(str(output_dir)) or {}
        v = (schema.get("conventions") or {}).get("aggregation", {}).get("doctrine_max_chars")
        if v:
            return max(200, int(v))
    except Exception:
        pass
    return DEFAULT_DOCTRINE_MAX_CHARS


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


def _scene_updated_after(path: Path, last_doctrine_at: Optional[str]) -> bool:
    """A scene counts as changed when its generated.at (fallback: file mtime)
    is newer than the last doctrine refresh. Missing timestamp → conservative
    True (treat as changed), aligned with persona-generator behaviour."""
    if not last_doctrine_at:
        return True
    try:
        threshold = datetime.fromisoformat(str(last_doctrine_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    try:
        import yaml

        text = path.read_text(encoding="utf-8")
        end = text.find("---", 3)
        fm = yaml.safe_load(text[3:end]) if text.startswith("---") and end > 0 else {}
        gen = (fm or {}).get("generated")
        at = gen.get("at") if isinstance(gen, dict) else None
        if at:
            return datetime.fromisoformat(str(at).replace("Z", "+00:00")) > threshold
    except Exception:
        pass
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return mtime > threshold
    except OSError:
        return True


# --------------------------------------------------------------------------- #
# Tool handler
# --------------------------------------------------------------------------- #
def handle_refresh_doctrine(arguments: Dict[str, Any], store: Any) -> str:
    """Regenerate wiki/doctrine.md (L3 Project Operating Doctrine), Mode C."""
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    if session is None and session_id:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    if session:
        output_dir = Path(session.output_dir).expanduser().resolve()
    elif arguments.get("output_dir"):
        output_dir = Path(arguments["output_dir"]).expanduser().resolve()
    elif arguments.get("repo_path"):
        output_dir = Path(arguments["repo_path"]).expanduser().resolve() / "repowiki"
    else:
        return json.dumps(
            {"error": "output_dir or repo_path is required (or pass an active session)."}
        )

    mode = str(arguments.get("mode") or "prepare").lower()
    if mode not in ("prepare", "submit"):
        return json.dumps({"error": f"Invalid mode '{mode}'. Expected one of: prepare, submit."})

    from codewiki.mcp.tools import aggregation_state as agg

    if mode == "prepare":
        from codewiki.mcp.tools.note_consolidation import _scan_scenarios
        from codewiki.src.config import NOTES_DIR

        state = agg.load_state(output_dir)
        cfg = agg.read_config(output_dir)
        current = _read_body(_doctrine_path(output_dir))

        scenarios = _scan_scenarios(output_dir)
        last_at = state.get("last_doctrine_at")
        changed: List[Dict[str, Any]] = []
        for sc in scenarios:
            if _scene_updated_after(output_dir / sc["file"], last_at):
                changed.append(sc)

        # Confirmed-note census (drives the 'Total notes' footer + readiness)
        confirmed = 0
        notes_dir = Path(output_dir) / NOTES_DIR
        if notes_dir.is_dir():
            for p in notes_dir.glob("*.md"):
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if "\nstatus: stable" in text or "\nstatus: confirmed" in text:
                    confirmed += 1

        doctrine_counter = int(state.get("notes_since_last_doctrine") or 0)
        trigger = (
            f"counter {doctrine_counter} >= threshold {cfg['doctrine_threshold']}"
            if doctrine_counter >= cfg["doctrine_threshold"]
            else f"manual refresh (counter {doctrine_counter} < threshold "
            f"{cfg['doctrine_threshold']})"
        )
        return json.dumps(
            {
                "status": "prepared",
                "mode": "prepare",
                "trigger": trigger,
                "doctrine_exists": bool(current),
                "current_doctrine": current,
                "char_cap": _max_chars(output_dir),
                "stats": {
                    "confirmed_notes": confirmed,
                    "scenes": len(scenarios),
                    "changed_scenes": len(changed),
                },
                "changed_scenes": changed,
                "scenarios_index": scenarios,
                "system_prompt": _DOCTRINE_SYSTEM,
                "next": (
                    "Read the changed scene files (view_repo_file) plus the current "
                    "doctrine; apply the six dimensions / five filters / incremental "
                    "strategy; then submit the FINAL doctrine Markdown (<= the char "
                    "cap) via mode='submit'. If changes only carry project state or "
                    "low-level facts, choose NO-CHANGE and skip the refresh. When "
                    "this refresh was prompted by an aggregation_hint reminder, ask "
                    "the user first."
                ),
            },
            indent=2,
            ensure_ascii=False,
        )

    # ---- mode == "submit" ----
    content = str(arguments.get("content") or "").strip()
    if not content:
        return json.dumps(
            {"error": "mode='submit' requires non-empty 'content' (the final doctrine Markdown)."}
        )

    cap = _max_chars(output_dir)
    if len(content) > cap:
        return json.dumps(
            {
                "status": "rejected",
                "error": (
                    f"Doctrine exceeds the hard cap: {len(content)} > {cap} chars. "
                    "Compress further (merge principles, drop project-bound "
                    "fragments) and re-submit."
                ),
                "chars": len(content),
                "char_cap": cap,
            },
            indent=2,
            ensure_ascii=False,
        )

    from codewiki.mcp.tools.note_consolidation import _scan_scenarios

    scenarios = _scan_scenarios(output_dir)

    # OKF frontmatter (status=draft: the doctrine passes the normal
    # confirmation gate via confirm_note / batch_set_status like other pages).
    try:
        from codewiki.mcp.tools.knowledge_loop import _okf_actor

        actor = _okf_actor(arguments.get("by"))
    except Exception:
        actor = "codewiki"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = agg.load_state(output_dir)
    scene_files = [sc["file"] for sc in scenarios]
    fm_lines = [
        "---",
        "type: Doctrine",
        'title: "Team Operating Doctrine"',
        "status: draft",
        f"generated: {{ by: {actor}, at: {now} }}",
        "metadata:",
        f"  source_scenarios: {json.dumps(scene_files, ensure_ascii=False)}",
        f"  notes_at_refresh: {int(state.get('notes_since_last_doctrine') or 0)}",
        "---",
    ]
    path = _doctrine_path(output_dir)
    try:
        atomic_write(path, "\n".join(fm_lines) + "\n\n" + content + "\n")
    except OSError as e:
        return json.dumps({"error": f"Failed to write doctrine: {e}"})

    new_state = agg.mark_doctrine_refreshed(output_dir)

    try:
        from codewiki.mcp.tools.wiki_search import build_full_index

        build_full_index(output_dir)
    except Exception as e:
        logger.warning("search index rebuild failed after doctrine refresh: %s", e)

    return json.dumps(
        {
            "status": "completed",
            "mode": "submit",
            "doctrine_file": str(path.relative_to(output_dir)).replace("\\", "/"),
            "chars": len(content),
            "char_cap": cap,
            "source_scenarios": len(scene_files),
            "counters": {
                "notes_since_last_doctrine": int(new_state.get("notes_since_last_doctrine") or 0),
                "notes_since_last_consolidation": int(
                    new_state.get("notes_since_last_consolidation") or 0
                ),
            },
            "message": (
                "Doctrine written as status=draft — review it and promote via "
                "confirm_note(note_file='wiki/doctrine.md') or batch_set_status. "
                "query_wiki(mode='overview') now injects it automatically."
            ),
        },
        indent=2,
        ensure_ascii=False,
    )
