"""MCP tool: batch_ingest — bulk import of notes and sources.

Processes a list of items (notes or sources) serially, then performs a
single index rebuild at the end for efficiency.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from codewiki.mcp.session import SessionStore

logger = logging.getLogger(__name__)


def handle_batch_ingest(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Bulk-ingest multiple notes and/or source documents.

    Accepts either an inline ``items`` list or an ``items_file`` path
    pointing to a JSON file with the same structure.  Each item must have
    a ``kind`` field: ``"note"`` or ``"source"``.

    Returns a summary of succeeded/failed items.
    """
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    if session is None and session_id:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    # Resolve items
    items: List[Dict[str, Any]] = arguments.get("items", [])
    items_file = arguments.get("items_file")
    if not items and items_file:
        try:
            p = Path(items_file).expanduser().resolve()
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and "items" in data:
                items = data["items"]
            else:
                return json.dumps({"error": "items_file must contain a list or {items: [...]}"})
        except Exception as e:
            return json.dumps({"error": f"Failed to read items_file: {e}"})

    if not items:
        return json.dumps({"error": "No items to ingest. Provide 'items' or 'items_file'."})

    # Inject session_id into each item if not already set
    if session_id:
        for item in items:
            if "session_id" not in item:
                item["session_id"] = session_id

    # Inject output_dir into each item if not already set
    top_output_dir = arguments.get("output_dir")
    if top_output_dir:
        for item in items:
            if "output_dir" not in item and "session_id" not in item:
                item["output_dir"] = top_output_dir

    # Process items serially
    results: List[Dict[str, Any]] = []
    succeeded = 0
    failed = 0

    from codewiki.mcp.tools.knowledge_loop import handle_ingest_note
    from codewiki.mcp.tools.source_ingest import handle_ingest_source

    for i, item in enumerate(items):
        kind = item.pop("kind", "note")
        try:
            if kind == "note":
                raw = handle_ingest_note(item, store)
            elif kind == "source":
                raw = handle_ingest_source(item, store)
            else:
                results.append({"index": i, "kind": kind, "status": "error",
                                "error": f"Unknown kind: {kind}"})
                failed += 1
                continue

            parsed = json.loads(raw)
            if "error" in parsed:
                results.append({"index": i, "kind": kind, "status": "error",
                                "error": parsed["error"]})
                failed += 1
            else:
                results.append({"index": i, "kind": kind, "status": "ok",
                                "detail": parsed})
                succeeded += 1
        except Exception as e:
            results.append({"index": i, "kind": kind, "status": "error",
                            "error": str(e)})
            failed += 1

    # Single index rebuild at the end
    output_dir = None
    if session:
        output_dir = Path(session.output_dir)
    else:
        od = arguments.get("output_dir")
        if od:
            output_dir = Path(od).expanduser().resolve()

    if output_dir:
        try:
            from codewiki.mcp.tools.wiki_index import rebuild_index, append_log
            append_log(str(output_dir), "batch_ingest",
                       f"批量导入完成: {succeeded} 成功, {failed} 失败")
            rebuild_index(str(output_dir))
        except Exception as e:
            logger.warning("Post-batch index rebuild failed: %s", e)

        # Rebuild search index
        try:
            from codewiki.mcp.tools.wiki_search import build_full_index
            build_full_index(output_dir, session=session)
        except Exception:
            pass

    return json.dumps({
        "status": "completed",
        "total": len(items),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }, indent=2, ensure_ascii=False)
