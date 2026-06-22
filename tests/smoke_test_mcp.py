#!/usr/bin/env python3
"""Smoke test for CodeWiki MCP tools — verifies core functionality after fixes.

Run: python3 tests/smoke_test_mcp.py
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure codewiki is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codewiki.mcp.session import SessionStore, SessionState
from codewiki.mcp.tools.analysis import handle_analyze_repo, handle_list_components
from codewiki.mcp.tools.code_reader import handle_read_code_components, handle_view_repo_file
from codewiki.mcp.tools.doc_writer import handle_write_doc_file, handle_edit_doc_file

# Use the repo itself as a test target
REPO_PATH = str(Path(__file__).resolve().parent.parent)

_passed = 0
_failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS: {name}")
    else:
        _failed += 1
        print(f"  FAIL: {name} — {detail}")


def main():
    print("=== CodeWiki MCP Smoke Test ===\n")

    store = SessionStore()
    output_dir = tempfile.mkdtemp(prefix="codewiki_smoke_")

    # -- 1. analyze_repo --
    print("[1] analyze_repo")
    result = json.loads(handle_analyze_repo({
        "repo_path": REPO_PATH,
        "output_dir": output_dir,
        "limit": 5,
    }, store))
    check("returns session_id", "session_id" in result, str(result)[:200])
    check("returns pagination", "pagination" in result, str(result.get("pagination", "")))
    check("returns component_index", "component_index" in result, str(result.keys()))
    check("pagination has total", "total" in result.get("pagination", {}), str(result.get("pagination")))

    session_id = result.get("session_id")
    check("session_id is non-empty", session_id and len(session_id) == 12, str(session_id))

    # -- 2. list_components pagination --
    print("\n[2] list_components pagination")
    page1 = json.loads(handle_list_components({
        "session_id": session_id,
        "offset": 0,
        "limit": 5,
    }, store))
    check("page1 returns 5 items", len(page1.get("component_index", [])) == 5, str(len(page1.get("component_index", []))))

    page2 = json.loads(handle_list_components({
        "session_id": session_id,
        "offset": 5,
        "limit": 5,
    }, store))
    check("page2 returns 5 items", len(page2.get("component_index", [])) == 5, str(len(page2.get("component_index", []))))
    check("page2 offset != page1", page2["component_index"][0]["id"] != page1["component_index"][0]["id"], "same items returned")

    # -- 3. view_repo_file path traversal guard --
    print("\n[3] view_repo_file path traversal guard")
    traversal = json.loads(handle_view_repo_file({
        "session_id": session_id,
        "path": "../../etc/passwd",
    }, store))
    check("rejects ../../etc/passwd", "error" in traversal, str(traversal))

    abs_traversal = json.loads(handle_view_repo_file({
        "session_id": session_id,
        "path": "/etc/passwd",
    }, store))
    check("rejects /etc/passwd", "error" in abs_traversal, str(abs_traversal))

    # -- 4. view_repo_file normal read --
    print("\n[4] view_repo_file normal read")
    file_view = handle_view_repo_file({
        "session_id": session_id,
        "path": "pyproject.toml",
    }, store)
    check("reads pyproject.toml", "pyproject" in file_view or "build-system" in file_view, file_view[:100])

    dir_view = handle_view_repo_file({
        "session_id": session_id,
        "path": "codewiki/mcp/tools",
    }, store)
    check("lists directory", "Directory listing" in dir_view, dir_view[:100])

    # -- 5. write_doc_file path traversal guard --
    print("\n[5] write_doc_file path traversal guard")
    traversal_write = json.loads(asyncio.run(handle_write_doc_file_wrapper({
        "session_id": session_id,
        "filename": "../../evil.md",
        "content": "pwned",
    }, store)))
    check("rejects ../../evil.md", "error" in traversal_write, str(traversal_write))

    # -- 6. write_doc_file normal write --
    print("\n[6] write_doc_file normal write")
    normal_write = json.loads(asyncio.run(handle_write_doc_file_wrapper({
        "session_id": session_id,
        "filename": "test_doc.md",
        "content": "# Test\n\n```mermaid\ngraph TD\n  A[Hello] --> B[World]\n```\n",
    }, store)))
    check("creates test_doc.md", normal_write.get("status") == "created", str(normal_write))
    check("file exists on disk", (Path(output_dir) / "test_doc.md").exists(), "")

    # -- 7. edit_doc_file str_replace --
    print("\n[7] edit_doc_file str_replace")
    edit_result = json.loads(asyncio.run(handle_edit_doc_file_wrapper({
        "session_id": session_id,
        "filename": "test_doc.md",
        "command": "str_replace",
        "old_str": "# Test",
        "new_str": "# Test Edited",
    }, store)))
    check("edits file", edit_result.get("status") == "edited", str(edit_result))
    edited_content = (Path(output_dir) / "test_doc.md").read_text()
    check("content updated", "# Test Edited" in edited_content, edited_content[:100])

    # -- 8. edit_doc_file undo --
    print("\n[8] edit_doc_file undo")
    undo_result = json.loads(asyncio.run(handle_edit_doc_file_wrapper({
        "session_id": session_id,
        "filename": "test_doc.md",
        "command": "undo",
    }, store)))
    check("undone", undo_result.get("status") == "undone", str(undo_result))
    check("mermaid_validation in undo", "mermaid_validation" in undo_result, str(undo_result.keys()))
    undone_content = (Path(output_dir) / "test_doc.md").read_text()
    check("content reverted", "# Test\n" in undone_content, undone_content[:100])

    # -- 9. read_code_components cap --
    print("\n[9] read_code_components cap")
    comp_ids = page1["component_index"]
    if comp_ids:
        ids = [c["id"] for c in comp_ids] * 20  # 100 IDs, should be capped to 20
        read_result = handle_read_code_components({
            "session_id": session_id,
            "component_ids": ids,
        }, store)
        check("caps to 20 components", "only first 20" in read_result, read_result[:100])

    # -- 10. close_session --
    print("\n[10] close_session")
    from codewiki.mcp.server import _store as server_store
    # Simulate close_session via store directly
    removed = store.remove(session_id)
    check("session removed", removed, "")
    # Verify session is gone
    gone = store.get(session_id)
    check("session is None after close", gone is None, "")

    # -- 11. SessionStore thread safety --
    print("\n[11] SessionStore thread safety")
    import threading
    errors = []
    def worker():
        try:
            for _ in range(20):
                s = store.create("a", "b", {}, [])
                store.get(s.session_id)
                store.remove(s.session_id)
        except Exception as e:
            errors.append(str(e))
    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check("no concurrent access errors", len(errors) == 0, str(errors[:3]))

    # -- 12. SessionStore max sessions --
    print("\n[12] SessionStore max sessions")
    store2 = SessionStore()
    created = []
    for i in range(15):
        s = store2.create(f"repo{i}", f"out{i}", {}, [])
        created.append(s.session_id)
    check("max 10 sessions enforced", len(store2._sessions) <= 10, f"got {len(store2._sessions)}")

    # -- Summary --
    print(f"\n=== Results: {_passed} passed, {_failed} failed ===")
    return 1 if _failed else 0


async def handle_write_doc_file_wrapper(args, store):
    return await handle_write_doc_file(args, store)


async def handle_edit_doc_file_wrapper(args, store):
    return await handle_edit_doc_file(args, store)


if __name__ == "__main__":
    sys.exit(main())
