# -*- coding: utf-8 -*-
"""MCP tool: report_outcome — the third telemetry event
(docs/负反馈与经验通道设计方案.md §三).

Existing signals: ``hit`` (I saw it), ``adopted`` (I cited it). This tool
adds the missing third link — **outcome**: after actually USING a doc, did
the work succeed? A thin telemetry shell in the same family as
``record_hit`` / ``record_adopted``: appends one jsonl event, never touches
frontmatter (no 5th frontmatter write path), no confirm gate — telemetry is
not landed knowledge (ADR-0002 posture, same as task memories).

Collection timing is caller-owned: the agent reports at the natural end of
a task (tests green / failure diagnosed) — the only moment it can honestly
judge the result. ``task_id`` is best-effort (explicit param, else the
source session's binding); ``note`` is an optional one-line context whose
failure reasons are the raw material for negative_examples (§四).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from codewiki.mcp.session import SessionStore

logger = logging.getLogger(__name__)

_VALID_RESULTS = ("success", "failure")


def _norm_doc(raw: str) -> str:
    """Normalise to the query_wiki ``file`` field shape (forward slashes,
    no leading ``./`` or ``/``). Empty/junk (upward traversal) → ''."""
    p = (raw or "").strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    p = p.lstrip("/")
    if not p or ".." in p.split("/"):
        return ""
    return p


def handle_report_outcome(arguments: Dict[str, Any], store: SessionStore) -> str:
    """Record how using a wiki/note doc turned out (success | failure)."""
    from codewiki.mcp.tools.workspace_result import resolve_session

    session = resolve_session(arguments, store)
    if session:
        output_dir = Path(session.output_dir).expanduser().resolve()
    else:
        rp = arguments.get("repo_path")
        if not rp:
            return json.dumps({"error": "repo_path is required (or pass an active session)."})
        from codewiki.mcp.tools.workspace_layout import default_output_dir

        output_dir = default_output_dir(Path(rp).expanduser().resolve())

    # ---- validate inputs -------------------------------------------------
    doc = _norm_doc(str(arguments.get("doc") or ""))
    if not doc:
        return json.dumps({"error": "doc is required (the used doc's repo-relative path)."})
    result = str(arguments.get("result") or "").strip().lower()
    if result not in _VALID_RESULTS:
        return json.dumps({"error": "result must be 'success' or 'failure' (binary, no grading)."})
    note = str(arguments.get("note") or "").strip()

    # The doc must exist under the wiki — an outcome about a path that is
    # not there cannot be linked to anything downstream (same posture as
    # adoption's existence filter).
    if not (output_dir / doc).exists():
        return json.dumps({"error": f"doc not found under the wiki: {doc}"})

    # ---- task_id: explicit param > session binding (best-effort) ---------
    task_id = str(arguments.get("task_id") or "").strip()
    source_session_id = str(arguments.get("source_session_id") or "").strip()
    adopted_key = ""
    try:
        from codewiki.mcp.tools import telemetry
        from codewiki.src.store import KnowledgeStore

        ks = KnowledgeStore(output_dir)
        if not task_id and source_session_id:
            task_id = ks.read_binding(source_session_id) or ks.read_archived_binding(
                source_session_id
            )

        # adopted 关联（design §三）：同 doc（同任务谱系）既有 adopted 事件
        # 存在时，把它的 key 抄进 outcome 事件，建立「引用→结果」链。
        # keys=None（无任何谱系线索）→ doc 级最近一次采纳；keys=set()（任务
        # 谱系已知但无匹配采纳）→ 不抄——别任务的采纳不得挂到本任务头上。
        keys = None
        if source_session_id:
            from codewiki.src.config import user_id

            keys = {f"{user_id(output_dir)}/{source_session_id}"}
        elif task_id:
            from codewiki.src.config import user_id

            uid = user_id(output_dir)
            keys = {f"{uid}/{sid}" for sid in ks.session_ids_for_task(task_id)}
        adopted_key = telemetry.last_adopted_key_for_doc(output_dir, doc, keys)

        telemetry.record_outcome(
            output_dir, doc, result, task_id=task_id, note=note, adopted_key=adopted_key
        )
    except Exception as e:
        logger.warning("report_outcome: failed to record (%s)", e, exc_info=True)
        return json.dumps({"error": f"failed to record outcome: {e}"})

    payload: Dict[str, Any] = {"status": "recorded", "doc": doc, "result": result}
    if task_id:
        payload["task_id"] = task_id
    if adopted_key:
        payload["adopted_key"] = adopted_key
    if note:
        payload["note"] = note
    return json.dumps(payload, indent=2, ensure_ascii=False)
