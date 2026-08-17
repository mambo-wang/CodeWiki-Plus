"""P2 aggregation state: counters, thresholds and proactive hints.

Team-memory fusion 阶段二（设计方案 §4.5）：

- ``.meta/aggregate_state.json`` 记录两个计数器（自上次聚合/刷新以来新增的
  confirmed 笔记数）与上次提醒位置；
- confirm_note / batch_set_status 确认成功时 ``record_confirmations`` 递增
  计数器，``build_aggregation_hint`` 做确定性越线判定并生成 ``aggregation_hint``
  （§4.5.2 防遗忘设计）——工具只负责"记得提醒"，是否执行由用户拍板；
- ``mark_consolidated`` 在 consolidate_notes(submit) 成功时归零聚合计数器。

全部为纯确定性逻辑，无 LLM、无后台任务，遵守"永不自动聚合"约束。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Defaults; schema.yaml ``conventions.aggregation`` may override.
DEFAULT_CONSOLIDATION_THRESHOLD = 10
DEFAULT_DOCTRINE_THRESHOLD = 50
DEFAULT_HINT_INTERVAL = 5
DEFAULT_MAX_SCENARIOS = 15

_META_DIR = ".meta"
_STATE_FILENAME = "aggregate_state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _state_path(output_dir: Path) -> Path:
    return Path(output_dir) / _META_DIR / _STATE_FILENAME


def default_state() -> Dict[str, Any]:
    return {
        "notes_since_last_consolidation": 0,
        "notes_since_last_doctrine": 0,
        "last_consolidation_at": None,
        "last_doctrine_at": None,
        "last_hinted_counter": {"consolidation": 0, "doctrine": 0},
    }


def load_state(output_dir: Path) -> Dict[str, Any]:
    """Read aggregate_state.json merged over defaults (best-effort)."""
    state = default_state()
    try:
        raw = _state_path(output_dir).read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            for k, v in data.items():
                if k == "last_hinted_counter" and isinstance(v, dict):
                    state["last_hinted_counter"].update({
                        kk: int(vv) for kk, vv in v.items()
                        if kk in ("consolidation", "doctrine")
                        and isinstance(vv, (int, float))
                    })
                elif k in state:
                    state[k] = v
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return state


def save_state(output_dir: Path, state: Dict[str, Any]) -> None:
    """Atomic write (tmp + os.replace), aligned with task-memory conventions."""
    path = _state_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (".aggregate_state.tmp." + str(os.getpid()))
    try:
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("aggregate_state save failed: %s", e)
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def read_config(output_dir: Path) -> Dict[str, int]:
    """Thresholds from schema.yaml ``conventions.aggregation`` with fallbacks."""
    cfg = {
        "consolidation_threshold": DEFAULT_CONSOLIDATION_THRESHOLD,
        "doctrine_threshold": DEFAULT_DOCTRINE_THRESHOLD,
        "hint_interval": DEFAULT_HINT_INTERVAL,
        "max_scenarios": DEFAULT_MAX_SCENARIOS,
    }
    try:
        from codewiki.mcp.tools.page_router import load_schema
        schema = load_schema(str(output_dir)) or {}
        agg = (schema.get("conventions") or {}).get("aggregation") or {}
        for key in cfg:
            if key in agg:
                try:
                    cfg[key] = max(1, int(agg[key]))
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    return cfg


def record_confirmations(output_dir: Path, count: int = 1) -> Dict[str, Any]:
    """Increment both counters (only confirmed knowledge drives L2/L3)."""
    if count <= 0:
        return load_state(output_dir)
    state = load_state(output_dir)
    state["notes_since_last_consolidation"] = (
        int(state.get("notes_since_last_consolidation") or 0) + count
    )
    state["notes_since_last_doctrine"] = (
        int(state.get("notes_since_last_doctrine") or 0) + count
    )
    save_state(output_dir, state)
    return state


def build_aggregation_hint(
    output_dir: Path,
    state: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """§4.5.2 threshold-crossing hint (deterministic, tool-side).

    Fires when ``counter >= threshold`` and at least ``hint_interval`` new
    confirmations accumulated since the last hint — avoids nagging on every
    confirm. When fired, ``last_hinted_counter`` advances (persisted) so a
    declined hint stays quiet until further confirmations arrive. The caller
    (confirm_note / batch_set_status) embeds the returned dict into its
    response; the host agent must ASK the user before acting (§4.5.2 contract).
    """
    if state is None:
        state = load_state(output_dir)
    cfg = read_config(output_dir)
    hinted = state.setdefault("last_hinted_counter", {"consolidation": 0, "doctrine": 0})

    c_counter = int(state.get("notes_since_last_consolidation") or 0)
    d_counter = int(state.get("notes_since_last_doctrine") or 0)
    c_due = (
        c_counter >= cfg["consolidation_threshold"]
        and (c_counter - int(hinted.get("consolidation") or 0)) >= cfg["hint_interval"]
    )
    d_due = (
        d_counter >= cfg["doctrine_threshold"]
        and (d_counter - int(hinted.get("doctrine") or 0)) >= cfg["hint_interval"]
    )
    if not (c_due or d_due):
        return None

    messages = []
    if c_due:
        messages.append(
            f"{c_counter} notes confirmed since last consolidation "
            f"(threshold >= {cfg['consolidation_threshold']}): suggest running "
            "consolidate_notes — ask the user first, never run it silently."
        )
        hinted["consolidation"] = c_counter
    if d_due:
        messages.append(
            f"{d_counter} notes confirmed since last doctrine refresh "
            f"(threshold >= {cfg['doctrine_threshold']}): suggest refresh_doctrine "
            "after consolidation — ask the user first."
        )
        hinted["doctrine"] = d_counter
    save_state(output_dir, state)

    return {
        "consolidation_due": c_due,
        "doctrine_due": d_due,
        "counters": {
            "notes_since_last_consolidation": c_counter,
            "notes_since_last_doctrine": d_counter,
        },
        "thresholds": {
            "consolidation": cfg["consolidation_threshold"],
            "doctrine": cfg["doctrine_threshold"],
        },
        "message": " ".join(messages),
    }


def mark_consolidated(output_dir: Path) -> Dict[str, Any]:
    """Reset the consolidation counter after a successful consolidate submit."""
    state = load_state(output_dir)
    state["notes_since_last_consolidation"] = 0
    state["last_consolidation_at"] = _now_iso()
    save_state(output_dir, state)
    return state


def aggregation_summary(output_dir: Path) -> Dict[str, Any]:
    """Read-only section for wiki_stats / get_task_context responses."""
    state = load_state(output_dir)
    cfg = read_config(output_dir)
    return {
        "notes_since_last_consolidation": int(state.get("notes_since_last_consolidation") or 0),
        "notes_since_last_doctrine": int(state.get("notes_since_last_doctrine") or 0),
        "last_consolidation_at": state.get("last_consolidation_at"),
        "last_doctrine_at": state.get("last_doctrine_at"),
        "consolidation_threshold": cfg["consolidation_threshold"],
        "doctrine_threshold": cfg["doctrine_threshold"],
    }
