# -*- coding: utf-8 -*-
"""`codewiki query` — CLI projection of query_wiki (H4, docs/Hook多智能体支持设计方案.md §4).

Lets agents WITHOUT MCP support consume the wiki search: any shell-capable
agent runs this command and reads the delimited text block straight into
its context. This is a *projection layer* — it calls the same
handle_query_wiki handler the MCP tool uses, never a second search
implementation, so CLI and MCP semantics can never drift.

Output shape (delimited block, agent-friendly):

    --- codewiki:query:start ---
    query: <query>
    ...
    --- codewiki:query:end ---

Adoption convention still works in CLI-only environments: agents declare
referenced docs in their reply via the codewiki:referenced-docs comment,
and capture (which is tool-agnostic) parses it later.
"""

from __future__ import annotations

import json
import sys

import click


def _render_result_block(payload: dict) -> str:
    """JSON payload → delimited text block an agent can read inline."""
    lines = []
    lines.append("--- codewiki:query:start ---")
    q = payload.get('query')
    if q:
        lines.append(f"query: {q}")
    lines.append(f"search_method: {payload.get('search_method', '')}")

    cov = payload.get("query_coverage")
    if isinstance(cov, dict):
        matched = ", ".join(cov.get("matched") or [])
        missing = ", ".join(cov.get("missing") or [])
        lines.append(f"matched_terms: {matched or '(none)'}")
        lines.append(f"missing_terms: {missing or '(none)'}")
        if missing:
            lines.append(
                "note: terms in missing_terms appear in NO indexed document — "
                "results may be topically adjacent rather than answers."
            )

    check = payload.get("mode") == "check"
    if check:
        lines.append(f"relevant: {str(payload.get('relevant', False)).lower()}")
        lines.append(f"top_score: {payload.get('top_score', 0)}")
        for r in payload.get("top_results") or []:
            lines.append(f"  - [{r.get('relevance_score', 0)}] {r.get('file', '')} | {r.get('title', '')}")
        hint = payload.get("hint")
        if hint:
            lines.append(f"hint: {hint}")
    else:
        results = payload.get("results") or []
        lines.append(f"results: {len(results)}")
        for r in results:
            lines.append("")
            lines.append(f"## {r.get('title', '')}  (score={r.get('relevance_score', 0)})")
            lines.append(f"file: {r.get('file', '')}")
            lines.append(f"source_type: {r.get('source_type', '')}")
            usage = r.get("usage") or {}
            lines.append(
                f"usage: hit_count={usage.get('hit_count', 0)}, "
                f"adopted_count={usage.get('adopted_count', 0)}"
            )
            matched = r.get("matched_tokens") or []
            if matched:
                lines.append(f"matched_tokens: {', '.join(matched)}")
            note = r.get("note_status")
            if note:
                lines.append(f"note_status: {note}{' [unconfirmed]' if note == 'draft' else ''}")
            snippet = (r.get("snippet") or "").strip()
            if snippet:
                lines.append("")
                lines.append(snippet)
        hint = payload.get("adoption_hint")
        if hint:
            lines.append("")
            lines.append(f"adoption_hint: {hint}")

    lines.append("--- codewiki:query:end ---")
    return "\n".join(lines)


@click.command(name="query")
@click.argument("query")
@click.option("--output-dir", "-o", default=None,
              help="repowiki directory (default: <cwd>/repowiki)")
@click.option("--top", type=int, default=10, show_default=True,
              help="Max results (1-20)")
@click.option("--check", "check_mode", is_flag=True,
              help="Lightweight relevance pre-check: verdict + top titles only, "
                   "no stats recorded. Use before deciding whether a full search "
                   "is worth the tokens.")
@click.option("--scope", default=None,
              help="Limit search to a module name or directory prefix (e.g. 'notes')")
@click.option("--type-filter", "type_filter", default=None,
              help="Filter by page type (module/entity/concept/note/source/...)")
@click.option("--expand", is_flag=False, flag_value="3000", default=None,
              help="Include full page content (optional value: char budget 500-20000)")
def query_command(query, output_dir, top, check_mode, scope, type_filter, expand):
    """Search the wiki from the command line (agent-friendly delimited output).

    Same search engine as the query_wiki MCP tool — BM25 + usage heat +
    authority weighting, with matched/missing term transparency.
    """
    from pathlib import Path

    od = Path(output_dir).expanduser().resolve() if output_dir \
        else Path.cwd() / "repowiki"
    if not od.is_dir():
        click.echo(
            f"error: output dir not found: {od}\n"
            "Pass --output-dir or run from a repo with a generated repowiki/.",
            err=True,
        )
        sys.exit(2)

    arguments = {"output_dir": str(od), "query": query,
                 "max_results": max(1, min(20, top))}
    if check_mode:
        arguments["mode"] = "check"
    if scope:
        arguments["scope"] = scope
    if type_filter:
        arguments["type_filter"] = type_filter
    if expand is not None:
        arguments["expand"] = True
        try:
            arguments["max_chars"] = max(500, min(20000, int(expand)))
        except ValueError:
            arguments["max_chars"] = 3000

    # Reuse the MCP handler verbatim (projection layer — no second engine).
    try:
        from codewiki.mcp.session import SessionStore
        from codewiki.mcp.tools.knowledge_loop import handle_query_wiki
        raw = handle_query_wiki(arguments, SessionStore())
    except Exception as e:  # never crash the agent's shell pipeline
        click.echo(f"error: query failed: {e}", err=True)
        sys.exit(1)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        click.echo(raw)  # handler already returned a text message
        return
    if "error" in payload:
        click.echo(f"error: {payload['error']}", err=True)
        sys.exit(1)

    click.echo(_render_result_block(payload))
