"""One-shot: remove the retired `output_dir` inputSchema property from
write-path/lifecycle/management tools in codewiki/mcp/registry.py.

Read-only tools keep `output_dir` (explicit addressing for cross-repo /
isolated-kb search is still legitimate).

Usage:
    uv run python scripts/_strip_output_dir.py            # dry run (no writes)
    uv run python scripts/_strip_output_dir.py --apply    # rewrite registry.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REGISTRY = Path(__file__).resolve().parent.parent / "codewiki/mcp/registry.py"

NAME_RE = re.compile(r'name="([a-z_0-9]+)"')

# Write-path / lifecycle / analysis / management tools whose output_dir
# parameter is retired (output_dir is derived from repo_path by layout).
DELETE = {
    "analyze_repo", "write_doc_file", "edit_doc_file", "save_module_tree",
    "close_session", "stamp_evidence", "ingest_note", "confirm_note",
    "batch_set_status", "reject_note", "ingest_source", "retract_source",
    "capture_conversation", "distill_conversation", "consolidate_notes",
    "refresh_doctrine", "batch_ingest", "flag_issue", "analyze_workspace",
    "generate_docs", "init_wiki", "init_workspace", "create_task",
    "list_tasks", "get_task", "complete_task", "delete_task",
    "set_session_task", "add_task_memory", "get_task_context",
    "compact_task_memories",
}


def owner_tool(lines: list[str], key_idx: int) -> str | None:
    """Nearest preceding top-level `name=` belonging to this property."""
    for j in range(key_idx - 1, -1, -1):
        m = NAME_RE.search(lines[j])
        if m:
            return m.group(1)
    return None


def property_end(lines: list[str], start: int) -> int:
    """Index of the line that closes the `{` opened on *start* (line-local)."""
    depth = 0
    for i in range(start, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth == 0:
            return i
    raise ValueError(f"unbalanced braces at line {start + 1}")


def main() -> int:
    apply = "--apply" in sys.argv
    text = REGISTRY.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    drop_lines: set[int] = set()
    actions: list[str] = []
    seen: set[str] = set()
    for idx, line in enumerate(lines):
        if '"output_dir": {' not in line:
            continue
        owner = owner_tool(lines, idx)
        if owner is None or owner not in DELETE:
            continue
        if owner in seen:
            # Defensive: at most one output_dir property per tool.
            continue
        seen.add(owner)
        end = property_end(lines, idx)
        drop = set(range(idx, end + 1))
        drop_lines |= drop
        actions.append(f"{owner}: dropping lines {idx + 1}-{end + 1}")

    new_text = "".join(l for i, l in enumerate(lines) if i not in drop_lines)
    try:
        ast.parse(new_text)
    except SyntaxError as exc:
        print(f"SYNTAX ERROR after edit: {exc}")
        return 1

    print(f"Tools touched: {len(actions)}; lines dropped: {len(drop_lines)}")
    print("\n".join(actions))
    untouched = sorted(t for t in DELETE if t not in seen)
    if untouched:
        print(f"NOT FOUND (check manually): {untouched}")
    if apply:
        REGISTRY.write_text(new_text, encoding="utf-8")
        print("Applied.")
    else:
        print("Dry run — pass --apply to rewrite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
