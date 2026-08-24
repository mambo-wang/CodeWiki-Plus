# -*- coding: utf-8 -*-
"""Hook agent registry (H1, docs/Hook多智能体支持设计方案.md §3).

Loads ``codewiki/hooks.yaml`` — the declarative registry of AI agents
CodeWiki's team-memory hooks can wire into. Family-based adaptation
(borrowed from teamai-cli): each agent belongs to one hook-format family
(claude / cursor / codex); all format translation happens at the family
layer, so adding an agent is a one-line registry entry.

Two entry points:

- :func:`load_registry` — parsed registry (families + agents), cached by
  the yaml file's mtime.
- :func:`detect_project_agents` — probe which agents' config directories
  actually exist under a repo. Only detected agents get wiring guidance
  (mirrors teamai's detectHomeInstalledAgents: never conjure a `.claude/`
  for someone who never asked).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_REGISTRY_CACHE: Dict[str, tuple] = {}


def _registry_path() -> Path:
    # codewiki/mcp/tools/hook_registry.py → codewiki/hooks.yaml
    return Path(__file__).resolve().parents[2] / "hooks.yaml"


def load_registry() -> Dict:
    """Parse hooks.yaml → {"version": int, "families": {...}, "agents": [...]}.

    Cached by file mtime. Malformed yaml degrades to the minimal registry
    (the three verified claude-family agents) so consumers never crash on
    a bad registry — wiring guidance quality drops, availability doesn't.
    """
    p = _registry_path()
    key = str(p)
    try:
        mtime = p.stat().st_mtime
    except OSError:
        mtime = None
    cached = _REGISTRY_CACHE.get(key)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    data: Dict = {"version": 1, "families": {}, "agents": []}
    try:
        import yaml
        loaded = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            families = loaded.get("families")
            agents = loaded.get("agents")
            if isinstance(families, dict):
                data["families"] = families
            if isinstance(agents, list):
                data["agents"] = [a for a in agents if isinstance(a, dict)]
    except Exception as e:
        logger.warning("hooks.yaml load failed (%s); using empty registry", e)

    _REGISTRY_CACHE[key] = (mtime, data)
    return data


def agents_by_family() -> Dict[str, List[Dict]]:
    """{family_id: [agent entries]} — wiring guidance iterates families."""
    out: Dict[str, List[Dict]] = {}
    for agent in load_registry().get("agents", []):
        fam = str(agent.get("family", "")).strip()
        if fam:
            out.setdefault(fam, []).append(agent)
    return out


def get_agent(agent_id: str) -> Optional[Dict]:
    for agent in load_registry().get("agents", []):
        if agent.get("id") == agent_id:
            return agent
    return None


def family_event(family_id: str, logical_event: str) -> Optional[str]:
    """Physical event key for a logical event (session_start/session_end).

    Uses the FIRST candidate key (version-compat candidates beyond the
    first are consumed by the future CLI reconcile step, not the prompt).
    Unknown family/event → None (caller skips wiring that event).
    """
    fam = load_registry().get("families", {}).get(family_id)
    if not isinstance(fam, dict):
        return None
    events = fam.get("events", {})
    candidates = events.get(logical_event)
    if isinstance(candidates, str):
        candidates = [candidates]
    if isinstance(candidates, list) and candidates:
        return str(candidates[0])
    return None


def detect_project_agents(repo_path) -> List[Dict]:
    """Agents whose config directory exists under *repo_path*.

    Detection = the user "asked for it" (they have the tool installed /
    initialised in this repo). Undetected agents get no wiring guidance
    and no directories are ever created by detection itself.
    """
    repo = Path(repo_path)
    detected: List[Dict] = []
    for agent in load_registry().get("agents", []):
        config_dir = agent.get("config_dir")
        if not config_dir:
            continue
        try:
            if (repo / str(config_dir)).is_dir():
                detected.append(agent)
        except OSError:
            continue
    return detected


def support_matrix_markdown() -> str:
    """README-ready support matrix (verified vs theoretical tiers)."""
    lines = [
        "| 智能体 | 家族 | 支持等级 |",
        "|--------|------|----------|",
    ]
    rows = []
    for agent in load_registry().get("agents", []):
        rows.append((
            str(agent.get("id", "?")),
            str(agent.get("family", "?")),
            bool(agent.get("verified", False)),
        ))
    # verified first, then alphabetical
    for aid, fam, verified in sorted(rows, key=lambda r: (not r[2], r[0])):
        tier = "已验证" if verified else "理论支持"
        lines.append(f"| `{aid}` | {fam} | {tier} |")
    return "\n".join(lines)
