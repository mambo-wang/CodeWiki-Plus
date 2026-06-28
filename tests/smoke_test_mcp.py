#!/usr/bin/env python3
"""Smoke test for CodeWiki MCP tools — verifies core functionality after
the file-side-channel optimization.

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
from codewiki.mcp.tools.analysis import handle_analyze_repo
from codewiki.mcp.tools.code_reader import handle_read_code_components
from codewiki.mcp.tools.doc_writer import handle_write_doc_file, handle_edit_doc_file
from codewiki.mcp.tools.crosslink import handle_list_dependencies
from codewiki.mcp.tools.wiki_lint import handle_lint_wiki
from codewiki.mcp.tools.knowledge_loop import handle_ingest_note, handle_query_wiki

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
    print("=== CodeWiki MCP Smoke Test (File-Side-Channel) ===\n")

    store = SessionStore()
    output_dir = tempfile.mkdtemp(prefix="codewiki_smoke_")

    # -- 1. analyze_repo --
    print("[1] analyze_repo")
    result = json.loads(handle_analyze_repo({
        "repo_path": REPO_PATH,
        "output_dir": output_dir,
    }, store))
    check("returns session_id", "session_id" in result, str(result)[:200])
    check("returns workspace_dir", "workspace_dir" in result, str(result.keys()))
    check("returns stats", "stats" in result, str(result.keys()))
    check("returns files", "files" in result, str(result.keys()))
    check("stats has total_components",
          "total_components" in result.get("stats", {}),
          str(result.get("stats")))
    check("stats has total_leaf_nodes",
          "total_leaf_nodes" in result.get("stats", {}),
          str(result.get("stats")))

    session_id = result.get("session_id")
    workspace_dir = result.get("workspace_dir")
    check("session_id is non-empty", session_id and len(session_id) == 12, str(session_id))
    check("workspace_dir exists on disk",
          workspace_dir and Path(workspace_dir).is_dir(),
          str(workspace_dir))

    # -- 2. Workspace files verification --
    print("\n[2] Workspace files verification")
    ws = Path(workspace_dir)
    check("component_index.json exists", (ws / "component_index.json").exists(), "")
    check("leaf_nodes.json exists", (ws / "leaf_nodes.json").exists(), "")
    check("languages.json exists", (ws / "languages.json").exists(), "")
    check("summary.json exists", (ws / "summary.json").exists(), "")
    check("sources/ directory exists", (ws / "sources").is_dir(), "")

    # Read component_index.json and verify structure
    comp_index = json.loads((ws / "component_index.json").read_text(encoding="utf-8"))
    check("component_index is a list", isinstance(comp_index, list), type(comp_index).__name__)
    check("component_index non-empty", len(comp_index) > 0, f"len={len(comp_index)}")
    if comp_index:
        first = comp_index[0]
        check("component has id/type/file",
              all(k in first for k in ("id", "type", "file")),
              str(first.keys()))

    # Read leaf_nodes.json
    leaf_nodes = json.loads((ws / "leaf_nodes.json").read_text(encoding="utf-8"))
    check("leaf_nodes is a list", isinstance(leaf_nodes, list), type(leaf_nodes).__name__)
    total_leaf = result["stats"]["total_leaf_nodes"]
    check("leaf_nodes matches stats count",
          len(leaf_nodes) == total_leaf,
          f"file={len(leaf_nodes)} vs stats={total_leaf}")

    # -- 3. read_code_components (writes to workspace files) --
    print("\n[3] read_code_components")
    if comp_index:
        ids = [c["id"] for c in comp_index[:5]]
        read_result = json.loads(handle_read_code_components({
            "session_id": session_id,
            "component_ids": ids,
        }, store))
        check("returns written count", "written" in read_result, str(read_result.keys()))
        check("returns source_dir", "source_dir" in read_result, str(read_result.keys()))
        check("returns files mapping", "files" in read_result, str(read_result.keys()))
        check("written == requested",
              read_result.get("written") == len(ids),
              f"written={read_result.get('written')}, requested={len(ids)}")

        # Verify source files exist on disk
        source_dir = Path(read_result["source_dir"])
        check("source_dir exists", source_dir.is_dir(), str(source_dir))
        for fname, cid in read_result.get("files", {}).items():
            src_file = source_dir / fname
            if src_file.exists():
                content = src_file.read_text(encoding="utf-8")
                check(f"source file has content ({fname})",
                      len(content) > 0, f"empty: {fname}")
                check(f"source file has header ({fname})",
                      "Component:" in content, f"no header: {fname[:50]}")
                break  # just check first one

    # -- 4. read_code_components no cap (removed 20-component limit) --
    print("\n[4] read_code_components no cap")
    if len(comp_index) > 20:
        many_ids = [c["id"] for c in comp_index[:30]]
        many_result = json.loads(handle_read_code_components({
            "session_id": session_id,
            "component_ids": many_ids,
        }, store))
        check("no 20-component cap",
              many_result.get("written") == 30,
              f"written={many_result.get('written')}")

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

    # -- 9. Schema auto-generation --
    print("\n[9] Schema auto-generation (LLM Wiki)")
    schema_path = Path(output_dir) / "schema.yaml"
    check("schema.yaml exists", schema_path.exists(), f"not found in {output_dir}")
    if schema_path.exists():
        schema_content = schema_path.read_text(encoding="utf-8")
        check("schema has version", "version:" in schema_content, schema_content[:200])
        check("schema has project", "project:" in schema_content, schema_content[:200])
        check("schema has conventions", "conventions:" in schema_content, schema_content[:200])
        check("schema has languages", "languages:" in schema_content, schema_content[:200])

    # -- 10. list_dependencies --
    print("\n[10] list_dependencies (LLM Wiki)")
    deps_result = json.loads(handle_list_dependencies({
        "session_id": session_id,
        "direction": "both",
        "limit": 10,
    }, store))
    check("returns dependencies", "dependencies" in deps_result, str(deps_result.keys())[:200])
    check("returns pagination", "pagination" in deps_result, str(deps_result.keys())[:200])
    if deps_result.get("dependencies"):
        first_dep = deps_result["dependencies"][0]
        check("dep has source/target", "source" in first_dep and "target" in first_dep, str(first_dep.keys()))

    # Module-level dependencies
    deps_module = json.loads(handle_list_dependencies({
        "session_id": session_id,
        "module_level": True,
        "limit": 5,
    }, store))
    check("module_level works",
          "pagination" in deps_module,
          str(deps_module.keys())[:200])

    # -- 11. lint_wiki --
    print("\n[11] lint_wiki (LLM Wiki)")
    lint_result = json.loads(handle_lint_wiki({
        "session_id": session_id,
        "checks": ["all"],
    }, store))
    check("returns total_issues", "total_issues" in lint_result, str(lint_result.keys())[:200])
    check("returns by_severity", "by_severity" in lint_result, str(lint_result.keys())[:200])
    check("returns issues list", "issues" in lint_result, str(lint_result.keys())[:200])
    check("returns summary", "summary" in lint_result, str(lint_result.keys())[:200])
    check("checks_run includes all",
          len(lint_result.get("checks_run", [])) > 0,
          str(lint_result.get("checks_run")))

    # Lint without session (output_dir mode)
    lint_nosess = json.loads(handle_lint_wiki({
        "output_dir": output_dir,
        "checks": ["broken_links"],
    }, store))
    check("lint works without session",
          "total_issues" in lint_nosess,
          str(lint_nosess.keys())[:200])

    # -- 12. ingest_note --
    print("\n[12] ingest_note (LLM Wiki)")
    note_result = json.loads(handle_ingest_note({
        "session_id": session_id,
        "note_type": "decision",
        "title": "Smoke test decision",
        "content": "This is a test decision note for the smoke test. We chose to use MCP tools for documentation generation.",
    }, store))
    check("note ingested", note_result.get("status") == "ingested", str(note_result))
    check("note_path exists", "note_path" in note_result, str(note_result.keys())[:200])
    if note_result.get("note_path"):
        note_file = Path(note_result["note_path"])
        check("note file created", note_file.exists(), str(note_file))
        if note_file.exists():
            note_content = note_file.read_text(encoding="utf-8")
            check("note has frontmatter", "---" in note_content, note_content[:100])

    # Check decisions_index.json
    index_path = Path(output_dir) / "decisions_index.json"
    check("decisions_index.json exists", index_path.exists(), "")
    if index_path.exists():
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
        check("index has entries", len(index_data.get("entries", [])) > 0, str(index_data))

    # Duplicate protection
    note_dup = json.loads(handle_ingest_note({
        "session_id": session_id,
        "note_type": "decision",
        "title": "Smoke test decision",
        "content": "This is a different content for duplicate detection.",
    }, store))
    check("duplicate handled (still ingested)",
          note_dup.get("status") == "ingested",
          str(note_dup))

    # -- 13. query_wiki --
    print("\n[13] query_wiki (LLM Wiki)")
    query_result = json.loads(handle_query_wiki({
        "session_id": session_id,
        "query": "test decision MCP",
        "include_notes": True,
    }, store))
    check("returns results", "results" in query_result, str(query_result.keys())[:200])
    check("returns context_package", "context_package" in query_result, str(query_result.keys())[:200])
    check("returns keywords", "keywords" in query_result, str(query_result.keys())[:200])
    # Should find the ingested note
    note_results = [r for r in query_result.get("results", []) if r.get("source") == "note"]
    check("finds ingested note", len(note_results) > 0,
          f"note results: {len(note_results)}, total: {len(query_result.get('results', []))}")

    # Query without session (output_dir mode)
    query_nosess = json.loads(handle_query_wiki({
        "output_dir": output_dir,
        "query": "test",
    }, store))
    check("query works without session",
          "results" in query_nosess,
          str(query_nosess.keys())[:200])

    # -- 14. close_session with workspace cleanup --
    print("\n[14] close_session with workspace cleanup")
    check("workspace exists before close", ws.exists(), "")
    # Simulate close_session cleanup
    session = store.get(session_id)
    if session and session.workspace:
        session.workspace.cleanup()
    removed = store.remove(session_id)
    check("session removed", removed, "")
    check("workspace dir cleaned up", not ws.exists(), f"still exists: {ws}")

    # -- 15. SessionStore thread safety --
    print("\n[15] SessionStore thread safety")
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

    # -- 16. SessionStore max sessions --
    print("\n[16] SessionStore max sessions")
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
