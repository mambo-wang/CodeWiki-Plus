#!/usr/bin/env python3
"""Smoke test for CodeWiki MCP tools — verifies core functionality after
the file-side-channel optimization.

Run: python3 tests/smoke_test_mcp.py
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

# Ensure codewiki is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.analysis import handle_analyze_repo
from codewiki.mcp.tools.code_reader import handle_read_code_components
from codewiki.mcp.tools.doc_writer import handle_write_doc_file, handle_edit_doc_file
from codewiki.mcp.tools.crosslink import handle_list_dependencies
from codewiki.mcp.tools.wiki_lint import handle_lint_wiki
from codewiki.mcp.tools.knowledge_loop import (
    handle_confirm_note,
    handle_ingest_note,
    handle_query_wiki,
    handle_reject_note,
)
from codewiki.mcp.tools.component_list import handle_list_components
from codewiki.mcp.tools.capture_conversation import handle_capture_conversation
from codewiki.mcp.tools.distill_conversation import handle_distill_conversation

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
    result = json.loads(
        handle_analyze_repo(
            {
                "repo_path": REPO_PATH,
                "output_dir": output_dir,
            },
            store,
        )
    )
    check("returns session_id", "session_id" in result, str(result)[:200])
    check("returns workspace_dir", "workspace_dir" in result, str(result.keys()))
    check("returns stats", "stats" in result, str(result.keys()))
    check("returns files", "files" in result, str(result.keys()))
    check(
        "stats has total_components",
        "total_components" in result.get("stats", {}),
        str(result.get("stats")),
    )
    check(
        "stats has total_leaf_nodes",
        "total_leaf_nodes" in result.get("stats", {}),
        str(result.get("stats")),
    )

    session_id = result.get("session_id")
    workspace_dir = result.get("workspace_dir")
    check("session_id is non-empty", session_id and len(session_id) == 12, str(session_id))
    check(
        "workspace_dir exists on disk",
        workspace_dir and Path(workspace_dir).is_dir(),
        str(workspace_dir),
    )

    # -- 2. Workspace files + list_components --
    print("\n[2] Workspace files + list_components")
    ws = Path(workspace_dir)
    check("summary.json exists", (ws / "summary.json").exists(), "")
    check("sources/ directory exists", (ws / "sources").is_dir(), "")

    # Read summary.json for stats
    summary = json.loads((ws / "summary.json").read_text(encoding="utf-8"))
    check("summary has total_components", "total_components" in summary, str(summary.keys()))
    check("summary has total_leaf_nodes", "total_leaf_nodes" in summary, str(summary.keys()))
    check("summary has languages", "languages" in summary, str(summary.keys()))

    # Use list_components tool to get component index
    lc_result = json.loads(
        handle_list_components(
            {
                "session_id": session_id,
            },
            store,
        )
    )
    check("list_components returns file", "file" in lc_result, str(lc_result.keys())[:200])
    check("list_components returns total", "total" in lc_result, str(lc_result.keys())[:200])
    check(
        "list_components total > 0",
        lc_result.get("total", 0) > 0,
        f"total={lc_result.get('total')}",
    )

    # Read the workspace file with full component list
    comp_list_file = Path(lc_result["file"])
    check("component_list.json exists", comp_list_file.exists(), str(comp_list_file))
    comp_list_data = json.loads(comp_list_file.read_text(encoding="utf-8"))
    comp_index = comp_list_data.get("components", [])
    check("component_index is a list", isinstance(comp_index, list), type(comp_index).__name__)
    check("component_index non-empty", len(comp_index) > 0, f"len={len(comp_index)}")
    if comp_index:
        first = comp_index[0]
        check(
            "component has id/type/file",
            all(k in first for k in ("id", "type", "file")),
            str(first.keys()),
        )

    # Test summary mode
    print("\n[2b] list_components summary mode")
    summ_result = json.loads(
        handle_list_components(
            {
                "session_id": session_id,
                "summary": True,
            },
            store,
        )
    )
    check("summary returns file", "file" in summ_result, str(summ_result.keys())[:200])
    check(
        "summary returns total_files", "total_files" in summ_result, str(summ_result.keys())[:200]
    )
    check(
        "summary returns mode",
        summ_result.get("mode") == "summary",
        f"mode={summ_result.get('mode')}",
    )
    check(
        "summary total_files > 0",
        summ_result.get("total_files", 0) > 0,
        f"total_files={summ_result.get('total_files')}",
    )

    # Read the summary file and validate structure
    summ_file = Path(summ_result["file"])
    check("component_summary.json exists", summ_file.exists(), str(summ_file))
    summ_data = json.loads(summ_file.read_text(encoding="utf-8"))
    files_dict = summ_data.get("files", {})
    check("summary has files dict", isinstance(files_dict, dict), type(files_dict).__name__)
    check("summary files non-empty", len(files_dict) > 0, f"len={len(files_dict)}")
    if files_dict:
        sample_file = next(iter(files_dict))
        sample_info = files_dict[sample_file]
        check("file entry has count", "count" in sample_info, str(sample_info.keys()))
        check("file entry has types", "types" in sample_info, str(sample_info.keys()))
        check("file entry has classes", "classes" in sample_info, str(sample_info.keys()))
    # Summary should be smaller than full list
    summ_size = summ_file.stat().st_size
    full_size = comp_list_file.stat().st_size
    check(
        "summary smaller than full", summ_size < full_size, f"summary={summ_size}, full={full_size}"
    )

    # -- 3. read_code_components (writes to workspace files) --
    print("\n[3] read_code_components")
    if comp_index:
        ids = [c["id"] for c in comp_index[:5]]
        read_result = json.loads(
            handle_read_code_components(
                {
                    "session_id": session_id,
                    "component_ids": ids,
                },
                store,
            )
        )
        check("returns written count", "written" in read_result, str(read_result.keys()))
        check("returns source_dir", "source_dir" in read_result, str(read_result.keys()))
        check("returns files mapping", "files" in read_result, str(read_result.keys()))
        check(
            "written == requested",
            read_result.get("written") == len(ids),
            f"written={read_result.get('written')}, requested={len(ids)}",
        )

        # Verify source files exist on disk
        source_dir = Path(read_result["source_dir"])
        check("source_dir exists", source_dir.is_dir(), str(source_dir))
        for fname, cid in read_result.get("files", {}).items():
            src_file = source_dir / fname
            if src_file.exists():
                content = src_file.read_text(encoding="utf-8")
                check(f"source file has content ({fname})", len(content) > 0, f"empty: {fname}")
                check(
                    f"source file has header ({fname})",
                    "Component:" in content,
                    f"no header: {fname[:50]}",
                )
                break  # just check first one

    # -- 4. read_code_components no cap (removed 20-component limit) --
    print("\n[4] read_code_components no cap")
    if len(comp_index) > 20:
        many_ids = [c["id"] for c in comp_index[:30]]
        many_result = json.loads(
            handle_read_code_components(
                {
                    "session_id": session_id,
                    "component_ids": many_ids,
                },
                store,
            )
        )
        check(
            "no 20-component cap",
            many_result.get("written") == 30,
            f"written={many_result.get('written')}",
        )

    # -- 5. write_doc_file path traversal guard --
    print("\n[5] write_doc_file path traversal guard")
    traversal_write = json.loads(
        asyncio.run(
            handle_write_doc_file_wrapper(
                {
                    "session_id": session_id,
                    "filename": "../../evil.md",
                    "content": "pwned",
                },
                store,
            )
        )
    )
    check("rejects ../../evil.md", "error" in traversal_write, str(traversal_write))

    # -- 6. write_doc_file normal write --
    print("\n[6] write_doc_file normal write")
    normal_write = json.loads(
        asyncio.run(
            handle_write_doc_file_wrapper(
                {
                    "session_id": session_id,
                    "filename": "test_doc.md",
                    "content": "# Test\n\n```mermaid\ngraph TD\n  A[Hello] --> B[World]\n```\n",
                },
                store,
            )
        )
    )
    check("creates test_doc.md", normal_write.get("status") == "created", str(normal_write))
    # write_doc_file routes pages by page_type (default: wiki/modules/); use returned path
    doc_file = Path(normal_write.get("path") or (Path(output_dir) / "test_doc.md"))
    check("file exists on disk", doc_file.exists(), str(doc_file))

    # -- 7. edit_doc_file str_replace --
    print("\n[7] edit_doc_file str_replace")
    edit_result = json.loads(
        asyncio.run(
            handle_edit_doc_file_wrapper(
                {
                    "session_id": session_id,
                    "filename": "test_doc.md",
                    "command": "str_replace",
                    "old_string": "# Test",
                    "new_string": "# Test Edited",
                },
                store,
            )
        )
    )
    check("edits file", edit_result.get("status") == "edited", str(edit_result))
    edited_content = doc_file.read_text()
    check("content updated", "# Test Edited" in edited_content, edited_content[:100])

    # -- 8. edit_doc_file undo --
    print("\n[8] edit_doc_file undo")
    undo_result = json.loads(
        asyncio.run(
            handle_edit_doc_file_wrapper(
                {
                    "session_id": session_id,
                    "filename": "test_doc.md",
                    "command": "undo",
                },
                store,
            )
        )
    )
    check("undone", undo_result.get("status") == "undone", str(undo_result))
    check(
        "mermaid_validation in undo", "mermaid_validation" in undo_result, str(undo_result.keys())
    )
    undone_content = doc_file.read_text()
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
    deps_result = json.loads(
        handle_list_dependencies(
            {
                "session_id": session_id,
                "direction": "both",
                "limit": 10,
            },
            store,
        )
    )
    check(
        "returns file or deps",
        "file" in deps_result or "dependencies" in deps_result,
        str(deps_result.keys())[:200],
    )
    # Data may be in workspace file (file-side-channel)
    if "file" in deps_result:
        deps_file = Path(deps_result["file"])
        deps_data = json.loads(deps_file.read_text(encoding="utf-8"))
        check(
            "deps file has dependencies", "dependencies" in deps_data, str(deps_data.keys())[:200]
        )
        check("returns total_deps", "total_deps" in deps_result, str(deps_result.keys())[:200])
        if deps_data.get("dependencies"):
            first_dep = deps_data["dependencies"][0]
            check(
                "dep has source/target",
                "source" in first_dep and "target" in first_dep,
                str(first_dep.keys()),
            )
    else:
        check("returns dependencies", "dependencies" in deps_result, str(deps_result.keys())[:200])
        check("returns total_deps", "total_deps" in deps_result, str(deps_result.keys())[:200])
        if deps_result.get("dependencies"):
            first_dep = deps_result["dependencies"][0]
            check(
                "dep has source/target",
                "source" in first_dep and "target" in first_dep,
                str(first_dep.keys()),
            )

    # Module-level dependencies
    deps_module = json.loads(
        handle_list_dependencies(
            {
                "session_id": session_id,
                "module_level": True,
                "limit": 5,
            },
            store,
        )
    )
    check(
        "module_level works",
        "file" in deps_module or "pagination" in deps_module,
        str(deps_module.keys())[:200],
    )

    # -- 11. lint_wiki --
    print("\n[11] lint_wiki (LLM Wiki)")
    lint_result = json.loads(
        handle_lint_wiki(
            {
                "session_id": session_id,
                "checks": ["all"],
            },
            store,
        )
    )
    check("returns total_issues", "total_issues" in lint_result, str(lint_result.keys())[:200])
    check("returns by_severity", "by_severity" in lint_result, str(lint_result.keys())[:200])
    check("returns summary", "summary" in lint_result, str(lint_result.keys())[:200])
    # issues list may be in workspace file (file-side-channel)
    if "file" in lint_result:
        lint_file = Path(lint_result["file"])
        lint_data = json.loads(lint_file.read_text(encoding="utf-8"))
        check("returns issues list", "issues" in lint_data, str(lint_data.keys())[:200])
        check(
            "checks_run includes all",
            len(lint_data.get("checks_run", [])) > 0,
            str(lint_data.get("checks_run")),
        )
    else:
        check("returns issues list", "issues" in lint_result, str(lint_result.keys())[:200])
        check(
            "checks_run includes all",
            len(lint_result.get("checks_run", [])) > 0,
            str(lint_result.get("checks_run")),
        )

    # Lint without session (output_dir mode)
    lint_nosess = json.loads(
        handle_lint_wiki(
            {
                "output_dir": output_dir,
                "checks": ["broken_links"],
            },
            store,
        )
    )
    check(
        "lint works without session", "total_issues" in lint_nosess, str(lint_nosess.keys())[:200]
    )

    # -- 12. ingest_note --
    print("\n[12] ingest_note (LLM Wiki)")
    note_result = json.loads(
        handle_ingest_note(
            {
                "session_id": session_id,
                "note_type": "decision",
                "title": "Smoke test decision",
                "content": "This is a test decision note for the smoke test. We chose to use MCP tools for documentation generation.",
            },
            store,
        )
    )
    check("note ingested", note_result.get("status") == "ingested", str(note_result))
    check("note_path exists", "note_path" in note_result, str(note_result.keys())[:200])
    if note_result.get("note_path"):
        note_file = Path(note_result["note_path"])
        check("note file created", note_file.exists(), str(note_file))
        if note_file.exists():
            note_content = note_file.read_text(encoding="utf-8")
            check("note has frontmatter", "---" in note_content, note_content[:100])

    # Notes are indexed via BM25/SQLite + wiki index.md (decisions_index.json removed)
    wiki_index_path = Path(output_dir) / "wiki" / "index.md"
    check("wiki index.md exists", wiki_index_path.exists(), str(wiki_index_path))

    # Duplicate protection
    note_dup = json.loads(
        handle_ingest_note(
            {
                "session_id": session_id,
                "note_type": "decision",
                "title": "Smoke test decision",
                "content": "This is a different content for duplicate detection.",
            },
            store,
        )
    )
    check("duplicate handled (still ingested)", note_dup.get("status") == "ingested", str(note_dup))

    # -- 13. query_wiki --
    print("\n[13] query_wiki (LLM Wiki)")
    query_result = json.loads(
        handle_query_wiki(
            {
                "session_id": session_id,
                "query": "test decision MCP",
                "include_notes": True,
            },
            store,
        )
    )
    check("returns results", "results" in query_result, str(query_result.keys())[:200])
    check(
        "returns context_package", "context_package" in query_result, str(query_result.keys())[:200]
    )
    check("returns keywords", "keywords" in query_result, str(query_result.keys())[:200])
    # Should find the ingested note
    note_results = [r for r in query_result.get("results", []) if r.get("source") == "note"]
    check(
        "finds ingested note",
        len(note_results) > 0,
        f"note results: {len(note_results)}, total: {len(query_result.get('results', []))}",
    )

    # Query without session (output_dir mode)
    query_nosess = json.loads(
        handle_query_wiki(
            {
                "output_dir": output_dir,
                "query": "test",
            },
            store,
        )
    )
    check("query works without session", "results" in query_nosess, str(query_nosess.keys())[:200])

    # -- 13b. OKF v0.2 lifecycle & conformance --
    print("\n[13b] OKF v0.2 lifecycle & conformance")
    # write_doc_file injects OKF frontmatter (type/generated/stale_after)
    okf_doc = doc_file.read_text(encoding="utf-8")
    check("doc starts with frontmatter", okf_doc.startswith("---"), okf_doc[:80])
    check("doc frontmatter has type", "type:" in okf_doc, okf_doc[:300])
    check("doc frontmatter has generated", "generated:" in okf_doc, okf_doc[:300])
    check("doc frontmatter has stale_after", "stale_after:" in okf_doc, okf_doc[:300])

    # ingest_note defaults to status=draft with OKF provenance fields
    okf_note_path = Path(note_result.get("note_path", ""))
    if okf_note_path.exists():
        okf_note = okf_note_path.read_text(encoding="utf-8")
        check("note status defaults to draft", "status: draft" in okf_note, okf_note[:400])
        check("note has generated", "generated:" in okf_note, okf_note[:400])
        check("note has stale_after", "stale_after:" in okf_note, okf_note[:400])

    # confirm_note promotes draft -> stable and records a verified event
    confirm_result = json.loads(
        handle_confirm_note(
            {
                "session_id": session_id,
                "note_file": okf_note_path.name,
                "by": "human:smoke-tester",
            },
            store,
        )
    )
    check(
        "confirm_note returns stable", confirm_result.get("status") == "stable", str(confirm_result)
    )
    okf_note2 = okf_note_path.read_text(encoding="utf-8")
    check("note promoted to stable", "status: stable" in okf_note2, okf_note2[:400])
    check(
        "note records verified event",
        "verified:" in okf_note2 and "human:smoke-tester" in okf_note2,
        okf_note2[:400],
    )

    # reject_note marks the duplicate note as deprecated
    dup_note_path = Path(note_dup.get("note_path", ""))
    if dup_note_path.exists():
        reject_result = json.loads(
            handle_reject_note(
                {
                    "session_id": session_id,
                    "note_file": dup_note_path.name,
                    "reason": "smoke-test cleanup",
                },
                store,
            )
        )
        check(
            "reject_note returns deprecated",
            reject_result.get("status") == "deprecated",
            str(reject_result),
        )
        dup_note = dup_note_path.read_text(encoding="utf-8")
        check("rejected note marked deprecated", "status: deprecated" in dup_note, dup_note[:400])

    # wiki/index.md declares okf_version (§12)
    okf_index = wiki_index_path.read_text(encoding="utf-8")
    check("index.md declares okf_version", "okf_version" in okf_index, okf_index[:200])

    # okf_conformance lint check runs standalone without error
    lint_okf = json.loads(
        handle_lint_wiki(
            {
                "output_dir": output_dir,
                "checks": ["okf_conformance"],
            },
            store,
        )
    )
    check("okf_conformance check runs", "total_issues" in lint_okf, str(lint_okf.keys())[:200])
    # The freshly generated docs/notes are conformant: no errors expected
    okf_errors = 0
    if "file" in lint_okf:
        okf_data = json.loads(Path(lint_okf["file"]).read_text(encoding="utf-8"))
        okf_errors = len([i for i in okf_data.get("issues", []) if i.get("severity") == "error"])
    else:
        okf_errors = len([i for i in lint_okf.get("issues", []) if i.get("severity") == "error"])
    check("no okf_conformance errors on fresh bundle", okf_errors == 0, f"errors={okf_errors}")

    # -- 14. close_session with workspace cleanup --
    print("\n[14] close_session with workspace cleanup")
    check("workspace exists before close", ws.exists(), "")
    # Simulate close_session cleanup
    session = store.get(session_id)
    if session and session.workspace:
        session.workspace.cleanup()
    removed = store.remove(session_id)
    check("session removed", removed, "")
    # Shared per-repo workspace persists by design; cleanup() only empties sources/
    sources_dir = ws / "sources"
    leftover = [f for f in sources_dir.iterdir() if f.is_file()] if sources_dir.exists() else []
    check("workspace sources cleaned up", not leftover, f"leftover: {leftover[:3]}")

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

    # -- 17. capture_conversation (team-memory fusion: ingest half) --
    print("\n[17] capture_conversation (team-memory fusion)")
    conv = [
        {"role": "user", "content": "How do I add a new MCP tool?"},
        {
            "role": "assistant",
            "content": "Register it in registry.py via _register(Tool(...), ...).",
        },
        {"role": "user", "content": "Thanks, got it."},
    ]
    cap_result = json.loads(
        handle_capture_conversation(
            {
                "output_dir": output_dir,
                "conversation": conv,
                "link_to": "registry.py",
            },
            store,
        )
    )
    check(
        "capture_conversation returns captured",
        cap_result.get("status") == "captured",
        str(cap_result),
    )
    check("capture reports turn_count", cap_result.get("turn_count") == 3, str(cap_result))
    conv_path = Path(output_dir) / cap_result.get("stored_at", "")
    check("conversation file written to raw/", conv_path.exists(), str(conv_path))
    if conv_path.exists():
        conv_text = conv_path.read_text(encoding="utf-8")
        check("raw file has frontmatter", conv_text.startswith("---"), conv_text[:80])
        check("raw file records content_hash", "content_hash:" in conv_text, conv_text[:200])
        check("raw file records link_to", "link_to:" in conv_text, conv_text[:200])

    # Deduplication: capturing the same conversation again yields duplicate
    cap_dup = json.loads(
        handle_capture_conversation(
            {
                "output_dir": output_dir,
                "conversation": conv,
                "link_to": "registry.py",
            },
            store,
        )
    )
    check("duplicate capture detected", cap_dup.get("status") == "duplicate", str(cap_dup))
    check(
        "only one raw conv file after dedup",
        len(list((Path(output_dir) / "raw").glob("conv-*.md"))) == 1,
        "expected exactly 1",
    )

    # Session-scoped supersede: Stop / PreCompact re-fire the same IDE session
    # with a growing transcript. Re-capturing the same source_session_id must
    # replace the session's pending raw file instead of adding incremental
    # copies (see team-memory-hook.md "同会话覆盖式去重").
    conv_s1 = [
        {"role": "user", "content": "supersede check turn 1"},
        {"role": "assistant", "content": "answer 1"},
    ]
    cap_s1 = json.loads(
        handle_capture_conversation(
            {
                "output_dir": output_dir,
                "conversation": conv_s1,
                "source_session_id": "ide-sess-supersede",
            },
            store,
        )
    )
    check(
        "first session capture ok",
        cap_s1.get("status") == "captured" and not cap_s1.get("superseded"),
        str(cap_s1),
    )
    _n_after_s1 = len(list((Path(output_dir) / "raw").glob("conv-*.md")))

    cap_s2 = json.loads(
        handle_capture_conversation(
            {
                "output_dir": output_dir,
                "conversation": conv_s1 + [{"role": "user", "content": "supersede check turn 2"}],
                "source_session_id": "ide-sess-supersede",
            },
            store,
        )
    )
    check("same-session recapture supersedes", cap_s2.get("superseded") is True, str(cap_s2))
    check(
        "supersede keeps a single raw file",
        len(list((Path(output_dir) / "raw").glob("conv-*.md"))) == _n_after_s1,
        f"expected {_n_after_s1}",
    )
    _sup_path = Path(output_dir) / cap_s2.get("stored_at", "")
    if _sup_path.exists():
        check(
            "superseded file has the longer transcript",
            "turn_count: 3" in _sup_path.read_text(encoding="utf-8"),
            str(cap_s2),
        )

    # Identical re-capture of the superseded content still hits hash dedup
    cap_s3 = json.loads(
        handle_capture_conversation(
            {
                "output_dir": output_dir,
                "conversation": conv_s1 + [{"role": "user", "content": "supersede check turn 2"}],
                "source_session_id": "ide-sess-supersede",
            },
            store,
        )
    )
    check("identical recapture is a duplicate", cap_s3.get("status") == "duplicate", str(cap_s3))

    # query_wiki should NOT surface raw captures (raw/ is excluded from index)
    q_after = json.loads(
        handle_query_wiki(
            {
                "output_dir": output_dir,
                "query": "add a new MCP tool",
            },
            store,
        )
    )
    raw_hits = [r for r in q_after.get("results", []) if "raw" in str(r.get("path", ""))]
    check("query_wiki excludes raw captures", len(raw_hits) == 0, f"raw hits: {len(raw_hits)}")

    # -- 18. distill_conversation (team-memory fusion: extract half) --
    print("\n[18] distill_conversation (team-memory fusion)")

    _raw_before = list((Path(output_dir) / "raw").glob("conv-*.md"))

    async def _fake_llm(prompt, system):
        return json.dumps(
            {
                "notes": [
                    {
                        "title": "Adding an MCP tool requires registry.py registration",
                        "note_type": "decision",
                        "related_modules": ["mcp"],
                        "tags": ["mcp"],
                        "content": "## Background\nUser asked how to add an MCP tool.\n## Decision\nRegister via _register(Tool(...), handler_path=..., mode='thread') in registry.py.",
                    }
                ]
            }
        )

    dist = json.loads(
        handle_distill_conversation(
            {
                "output_dir": output_dir,
                "llm": _fake_llm,
            },
            store,
        )
    )
    check("distill returns completed", dist.get("status") == "completed", str(dist))
    check("distill created >=1 note", dist.get("notes_created", 0) >= 1, str(dist))

    if _raw_before:
        # raw files captured in [17] should be deleted after distillation
        _raw_after = list((Path(output_dir) / "raw").glob("conv-*.md"))
        check(
            "raw captures deleted after distill",
            len(_raw_after) == 0,
            f"remaining: {[p.name for p in _raw_after]}",
        )

    # a draft note should now exist and be queryable with [unconfirmed] prefix
    q_note = json.loads(
        handle_query_wiki(
            {
                "output_dir": output_dir,
                "query": "registry.py registration MCP tool",
            },
            store,
        )
    )
    draft_hit = [
        r
        for r in q_note.get("results", [])
        if "registry" in str(r.get("title", "")).lower() or "unconfirmed" in str(r)
    ]
    check("distilled draft note is queryable", len(draft_hit) >= 1, f"hits: {len(draft_hit)}")

    # golden-set: LLM JSON parser must extract structured notes (anti-hallucination)
    from codewiki.mcp.tools.distill_conversation import _parse_llm_notes

    golden = (
        '```json\n{"notes":[{"title":"Use status=draft","note_type":"decision",'
        '"related_modules":["notes"],"content":"## Decision\\nX"}]}\n```'
    )
    parsed = _parse_llm_notes(golden)
    check("golden parse yields one note", len(parsed) == 1, str(parsed))
    if parsed:
        check(
            "golden note_type preserved", parsed[0].get("note_type") == "decision", str(parsed[0])
        )
        check(
            "golden strips markdown fences",
            parsed[0].get("title") == "Use status=draft",
            str(parsed[0]),
        )
    bad = _parse_llm_notes("totally not json")
    check("non-json yields no notes (no hallucinated draft)", bad == [], str(bad))

    # -- 19. distill_conversation Mode C (agent-driven prepare/submit) --
    print("\n[19] distill_conversation Mode C (agent-driven prepare/submit)")

    conv_c1 = [
        {"role": "user", "content": "Why does analyze_repo hang inside MCP?"},
        {
            "role": "assistant",
            "content": "git subprocess inherited the MCP stdin pipe; pass stdin=DEVNULL.",
        },
    ]
    conv_c2 = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi, how can I help?"},
    ]
    cap_c1 = json.loads(
        handle_capture_conversation(
            {
                "output_dir": output_dir,
                "conversation": conv_c1,
                "source_session_id": "mode-c-sess-1",
            },
            store,
        )
    )
    cap_c2 = json.loads(
        handle_capture_conversation(
            {
                "output_dir": output_dir,
                "conversation": conv_c2,
                "source_session_id": "mode-c-sess-2",
            },
            store,
        )
    )
    cid1 = cap_c1.get("conversation_id")
    cid2 = cap_c2.get("conversation_id")
    check(
        "mode-C captures ready",
        cap_c1.get("status") == "captured" and cap_c2.get("status") == "captured",
        f"{cap_c1} / {cap_c2}",
    )

    prep = json.loads(
        handle_distill_conversation({"output_dir": output_dir, "mode": "prepare"}, store)
    )
    check("prepare returns prepared", prep.get("status") == "prepared", str(prep)[:200])
    check(
        "prepare exposes system prompt",
        "knowledge distillation engine" in prep.get("system_prompt", ""),
        "",
    )
    ids = {c.get("conversation_id") for c in prep.get("captures", [])}
    check("prepare lists both captures", {cid1, cid2} <= ids, str(ids))
    check(
        "prepare carries preview transcripts",
        any("stdin=DEVNULL" in c.get("preview", "") for c in prep.get("captures", [])),
        "",
    )

    # The test plays the host agent: one real note for c1, nothing for c2
    submit = json.loads(
        handle_distill_conversation(
            {
                "output_dir": output_dir,
                "mode": "submit",
                "distilled": {
                    cid1: {
                        "notes": [
                            {
                                "title": "MCP subprocesses must set stdin=DEVNULL",
                                "note_type": "pitfall",
                                "related_modules": ["mcp"],
                                "tags": ["mcp", "subprocess"],
                                "content": (
                                    "## Background\nanalyze_repo hung inside MCP.\n"
                                    "## Root cause\ngit inherited the MCP stdin pipe.\n"
                                    "## Fix\nPass stdin=subprocess.DEVNULL to every subprocess call."
                                ),
                            }
                        ]
                    },
                    cid2: {"notes": []},
                },
            },
            store,
        )
    )
    check("submit returns completed", submit.get("status") == "completed", str(submit)[:200])
    check("submit created exactly 1 note", submit.get("notes_created") == 1, str(submit)[:200])
    by_cid = {r.get("conversation_id"): r for r in submit.get("distilled", [])}
    check("c1 distilled", by_cid.get(cid1, {}).get("status") == "completed", str(by_cid.get(cid1)))
    check(
        "c2 no_knowledge",
        by_cid.get(cid2, {}).get("status") == "no_knowledge",
        str(by_cid.get(cid2)),
    )
    check("c1 raw deleted", not (Path(output_dir) / "raw" / f"{cid1}.md").exists(), str(cid1))
    _c2_path = Path(output_dir) / "raw" / f"{cid2}.md"
    # no_knowledge raws are noise and cleaned up by distill_conversation
    # (see tests/test_distill_cleanup.py); keep_raw is the only opt-in that
    # preserves the raw file.
    check("c2 raw deleted on no_knowledge", not _c2_path.exists(), str(_c2_path))

    # Missing extraction result leaves the raw file untouched (still pending)
    cap_c3 = json.loads(
        handle_capture_conversation(
            {
                "output_dir": output_dir,
                "conversation": [{"role": "user", "content": "pending leftover"}],
                "source_session_id": "mode-c-sess-3",
            },
            store,
        )
    )
    cid3 = cap_c3.get("conversation_id")
    sub2 = json.loads(
        handle_distill_conversation(
            {
                "output_dir": output_dir,
                "mode": "submit",
                "distilled": {"conv-nonexistent": {"notes": []}},
            },
            store,
        )
    )
    by_cid2 = {r.get("conversation_id"): r for r in sub2.get("distilled", [])}
    check(
        "missing result reported",
        by_cid2.get(cid3, {}).get("status") == "missing_result",
        str(sub2)[:200],
    )
    _c3_path = Path(output_dir) / "raw" / f"{cid3}.md"
    check(
        "raw untouched on missing result",
        _c3_path.exists() and "status: pending" in _c3_path.read_text(encoding="utf-8"),
        str(_c3_path),
    )

    # Error paths
    bad_mode = json.loads(
        handle_distill_conversation({"output_dir": output_dir, "mode": "bogus"}, store)
    )
    check("invalid mode rejected", "error" in bad_mode, str(bad_mode))
    no_map = json.loads(
        handle_distill_conversation({"output_dir": output_dir, "mode": "submit"}, store)
    )
    check("submit without distilled rejected", "error" in no_map, str(no_map))

    # The Mode-C draft note should be queryable like any other draft
    q_c = json.loads(
        handle_query_wiki(
            {
                "output_dir": output_dir,
                "query": "stdin DEVNULL MCP subprocess",
            },
            store,
        )
    )
    hit_c = [
        r
        for r in q_c.get("results", [])
        if "DEVNULL" in str(r.get("title", "")) or "stdin" in str(r)
    ]
    check("mode-C draft note queryable", len(hit_c) >= 1, f"hits: {len(hit_c)}")

    # -- Summary --
    print(f"\n=== Results: {_passed} passed, {_failed} failed ===")
    return 1 if _failed else 0


async def handle_write_doc_file_wrapper(args, store):
    return await handle_write_doc_file(args, store)


async def handle_edit_doc_file_wrapper(args, store):
    return await handle_edit_doc_file(args, store)


if __name__ == "__main__":
    sys.exit(main())
