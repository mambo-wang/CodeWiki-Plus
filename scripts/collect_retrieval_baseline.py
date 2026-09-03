# -*- coding: utf-8 -*-
"""Retrieval baseline collector (§6.4 of the claude-mem borrowing plan).

Runs the fixed 12-query set against the real repo repowiki via
handle_query_wiki on the CURRENT code and snapshots response sizes to
docs/retrieval-baseline.json. Must run BEFORE the P0 changes land — after
that it measures the new behaviour, not the baseline.

Usage: python3 scripts/collect_retrieval_baseline.py [--out docs/retrieval-baseline.json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from codewiki.mcp.tools.knowledge_loop import handle_query_wiki  # noqa: E402

OD = str(REPO / "repowiki")

# --- Fixed query set (12): measurement instrument, not knowledge. ----------
# 4 decision/lesson retrieval style + 4 by_file scenarios (pre-by_file the
# current behaviour is a plain BM25 search scoped by module name) + 4
# check/expand mixed runs.

DECISION_QUERIES = [
    "蒸馏 为什么 必须 异步 后台",
    "memory_items 单表 统一 建模",
    "新鲜度 stale 判定 策略",
    "hooks 家族归并 多智能体",
]

BY_FILE_SCENARIOS = [
    # (label, target file) — current behaviour: BM25 search on module terms
    ("wiki_search", "codewiki/mcp/tools/wiki_search.py"),
    ("knowledge_loop", "codewiki/mcp/tools/knowledge_loop.py"),
    ("registry", "codewiki/mcp/registry.py"),
    ("cache", "codewiki/mcp/cache.py"),
]

CHECK_EXPAND = [
    {"label": "check-蒸馏", "mode": "check", "query": "蒸馏 异步"},
    {"label": "check-schema", "mode": "check", "query": "schema 版本"},
    {"label": "expand-doc", "expand": True, "max_chars": 3000, "query": "MCP 工具 设计"},
    {"label": "expand-big", "expand": True, "max_chars": 20000, "query": "任务记忆 压缩"},
]


def run_query(args: dict) -> dict:
    base = {"output_dir": OD, "max_results": 10}
    base.update(args)
    raw = handle_query_wiki(base, None)
    parsed = json.loads(raw)
    results = parsed.get("results") or []
    return {
        "response_chars": len(raw),
        "result_count": len(results),
        "top_files": [r.get("file", "") for r in results[:3]],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/retrieval-baseline.json")
    opts = ap.parse_args()

    entries = []
    for q in DECISION_QUERIES:
        entries.append({"label": f"decision:{q}", "kind": "decision/lesson", "arguments": {"query": q}, **run_query({"query": q})})
    for label, target in BY_FILE_SCENARIOS:
        q = label  # current behaviour: module-name BM25 search
        entries.append({"label": f"by_file:{target}", "kind": "by_file", "arguments": {"query": q}, **run_query({"query": q})})
    for spec in CHECK_EXPAND:
        label = spec.pop("label")
        entries.append({"label": f"mixed:{label}", "kind": "check/expand", "arguments": spec, **run_query(spec)})

    head = subprocess.run(
        ["git", "log", "-1", "--format=%H %cI"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()

    out = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "git_head": head,
        "purpose": (
            "Fixed 12-query baseline snapshot taken BEFORE the claude-mem "
            "borrowing (P0-1 est_tokens / P0-2 by_file / P0-3 description) "
            "landed. Re-run the same query set after merge and diff "
            "response_chars to validate acceptance #8. The query set is a "
            "measurement instrument, not knowledge — it stays out of repowiki."
        ),
        "queries": entries,
        "summary": {
            "n": len(entries),
            "avg_response_chars": round(sum(e["response_chars"] for e in entries) / len(entries), 1),
            "total_response_chars": sum(e["response_chars"] for e in entries),
        },
    }
    out_path = REPO / opts.out
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"baseline written: {out_path} ({len(entries)} queries, avg {out['summary']['avg_response_chars']} chars)")


if __name__ == "__main__":
    main()
