"""MCP tools: write_doc_file + edit_doc_file.

These tools create and edit markdown documentation files in the output
directory, with automatic Mermaid diagram validation after every write.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from codewiki.mcp.session import SessionState, SessionStore

logger = logging.getLogger(__name__)


async def _validate_mermaid(file_path: str, relative_path: str) -> str:
    """Run Mermaid validation and return the result string."""
    try:
        from codewiki.src.be.utils import validate_mermaid_diagrams
        return await validate_mermaid_diagrams(file_path, relative_path)
    except Exception as e:
        return f"Mermaid validation skipped: {e}"


def _ensure_parent_dirs(path: Path) -> None:
    """Create parent directories if they don't exist."""
    path.parent.mkdir(parents=True, exist_ok=True)


async def handle_write_doc_file(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Create a new documentation file in the output directory."""
    session_id = arguments["session_id"]
    session = store.get(session_id)
    if session is None:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    filename = arguments["filename"]
    if not filename.endswith(".md"):
        filename += ".md"
    content = arguments["content"]

    doc_path = Path(session.output_dir) / filename
    _ensure_parent_dirs(doc_path)

    if doc_path.exists():
        return json.dumps({
            "error": f"File already exists: {filename}. Use edit_doc_file to modify it."
        })

    doc_path.write_text(content, encoding="utf-8")

    # Mermaid validation
    mermaid_result = await _validate_mermaid(str(doc_path), filename)

    result = {
        "status": "created",
        "path": str(doc_path),
        "filename": filename,
        "lines": content.count("\n") + 1,
        "mermaid_validation": mermaid_result,
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


async def handle_edit_doc_file(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Edit an existing documentation file (str_replace, insert, or undo)."""
    session_id = arguments["session_id"]
    session = store.get(session_id)
    if session is None:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    filename = arguments["filename"]
    if not filename.endswith(".md"):
        filename += ".md"

    doc_path = Path(session.output_dir) / filename
    command = arguments["command"]

    if command == "undo":
        # Undo via registry history
        history_key = str(doc_path)
        history = session.registry.get("file_history", "{}")
        file_history = json.loads(history) if isinstance(history, str) else history
        path_history = file_history.get(history_key, [])
        if not path_history:
            return json.dumps({"error": f"No edit history found for {filename}."})
        old_content = path_history.pop()
        file_history[history_key] = path_history
        session.registry["file_history"] = json.dumps(file_history)
        doc_path.write_text(old_content, encoding="utf-8")
        return json.dumps({"status": "undone", "filename": filename})

    if not doc_path.exists():
        return json.dumps({"error": f"File not found: {filename}. Use write_doc_file to create it."})

    # Save current content to history before editing
    current_content = doc_path.read_text(encoding="utf-8")
    history_key = str(doc_path)
    history = session.registry.get("file_history", "{}")
    file_history = json.loads(history) if isinstance(history, str) else history
    file_history.setdefault(history_key, []).append(current_content)
    session.registry["file_history"] = json.dumps(file_history)

    if command == "str_replace":
        old_str = arguments.get("old_str")
        new_str = arguments.get("new_str", "")
        if old_str is None:
            return json.dumps({"error": "old_str is required for str_replace."})

        occurrences = current_content.count(old_str)
        if occurrences == 0:
            return json.dumps({"error": f"old_str not found in {filename}."})
        if occurrences > 1:
            return json.dumps({"error": f"old_str appears {occurrences} times in {filename}. Make it unique."})

        new_content = current_content.replace(old_str, new_str, 1)
        doc_path.write_text(new_content, encoding="utf-8")

        # Snippet around the edit
        replacement_line = current_content.split(old_str)[0].count("\n")
        lines = new_content.split("\n")
        start = max(0, replacement_line - 4)
        end = min(len(lines), replacement_line + new_str.count("\n") + 5)
        snippet = "\n".join(f"{i + start + 1:6}\t{lines[i]}" for i in range(start, end))

    elif command == "insert":
        insert_line = arguments.get("insert_line", 0)
        new_str = arguments.get("new_str", "")
        if not new_str:
            return json.dumps({"error": "new_str is required for insert."})

        lines = current_content.split("\n")
        insert_line = max(0, min(insert_line, len(lines)))
        new_str_lines = new_str.split("\n")
        lines = lines[:insert_line] + new_str_lines + lines[insert_line:]
        new_content = "\n".join(lines)
        doc_path.write_text(new_content, encoding="utf-8")

        start = max(0, insert_line - 4)
        end = min(len(lines), insert_line + len(new_str_lines) + 4)
        snippet = "\n".join(f"{i + start + 1:6}\t{lines[i]}" for i in range(start, end))

    else:
        return json.dumps({"error": f"Unknown command: {command}. Use str_replace, insert, or undo."})

    # Mermaid validation
    mermaid_result = await _validate_mermaid(str(doc_path), filename)

    result = {
        "status": "edited",
        "command": command,
        "filename": filename,
        "snippet": snippet,
        "mermaid_validation": mermaid_result,
    }
    return json.dumps(result, indent=2, ensure_ascii=False)
