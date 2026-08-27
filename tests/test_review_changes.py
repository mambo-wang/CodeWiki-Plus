#!/usr/bin/env python3
"""Tests for review_changes (code review evidence assembly) + review_checklist.

Run: python3 tests/test_review_changes.py
"""

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.change_analysis import FileChange
from codewiki.mcp.tools.review_checklist import get_checklist
from codewiki.mcp.tools.review_changes import (
    _auto_discover_specs,
    _handle_submit,
    _validate_report,
    handle_review_changes,
)
from codewiki.mcp.tools.workspace_result import resolve_session

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


def test_checklist():
    print("[1] get_checklist (builtin + language + override)")
    # Python change → all + python items
    items = get_checklist(None, ["codewiki/mcp/tools/foo.py"])
    ids = {i["id"] for i in items}
    check("all items included", {"err-handling", "input-validation", "logging"} <= ids)
    check("python items included", "py-bare-except" in ids and "py-encoding" in ids)

    # Non-code change → all only
    items2 = get_checklist(None, ["README.md"])
    ids2 = {i["id"] for i in items2}
    check("no language items for .md", "py-bare-except" not in ids2 and "err-handling" in ids2)

    # Project override: same id replaces, unknown id appends
    with tempfile.TemporaryDirectory() as tmp:
        repowiki = Path(tmp) / "repowiki"
        repowiki.mkdir()
        (repowiki / "review_checklist.yaml").write_text(
            "all:\n"
            "  - id: err-handling\n"
            "    title: 团队错误处理约定\n"
            "    questions: ['q1']\n"
            "  - id: team-style\n"
            "    title: 团队风格\n"
            "    questions: ['q2']\n",
            encoding="utf-8",
        )
        merged = {i["id"]: i for i in get_checklist(tmp, ["a.py"])}
        check("override replaces builtin", merged["err-handling"]["title"] == "团队错误处理约定")
        check("override appends unknown id", "team-style" in merged)

    # Malformed yaml → ignored, builtin still returned
    with tempfile.TemporaryDirectory() as tmp:
        repowiki = Path(tmp) / "repowiki"
        repowiki.mkdir()
        (repowiki / "review_checklist.yaml").write_text(":: not: [valid", encoding="utf-8")
        items3 = get_checklist(tmp, ["a.py"])
        check("malformed yaml degrades to builtin", any(i["id"] == "err-handling" for i in items3))


def test_spec_auto_discover():
    print("[2] _auto_discover_specs")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docs").mkdir()
        spec = root / "docs" / "payment-refactor.md"
        spec.write_text("## 需求\n支付模块重构要求。", encoding="utf-8")
        # Unrelated spec should not match
        other = root / "docs" / "unrelated.md"
        other.write_text("无关文档。", encoding="utf-8")

        changes = [FileChange(path="src/payment/service.py", added_lines=[1])]
        found = _auto_discover_specs(tmp, changes)
        check("stem-match spec discovered", any("payment-refactor" in s["path"] for s in found))
        check("unrelated spec excluded", not any("unrelated" in s["path"] for s in found))

        # No match at all → empty list
        changes2 = [FileChange(path="src/zzz_nothing/foo.py", added_lines=[1])]
        found2 = _auto_discover_specs(tmp, changes2)
        check("no match returns empty", found2 == [])


def test_validate_report():
    print("[3] _validate_report (submit gate)")
    good = {
        "title": "变更评审",
        "findings": [
            {
                "id": "f1",
                "axis": "convention",
                "severity": "major",
                "file": "codewiki/mcp/prompts.py",
                "line": 545,
                "title": "未遵循日志约定",
                "evidence": "print 代替 logger",
                "suggestion": "改用 logging",
                "rule_ref": {"source": "repowiki/notes/x.md", "quote": "…"},
            }
        ],
        "summary": {"total": 1},
    }
    errors, warnings = _validate_report(good, REPO_PATH)
    # stale citation is a tolerated warning, not a rejection
    check("valid report passes", errors == [], detail=str(errors))

    bad_axis = json.loads(json.dumps(good))
    bad_axis["findings"][0]["axis"] = "nope"
    errors, _ = _validate_report(bad_axis, REPO_PATH)
    check("invalid axis rejected", any("axis" in e for e in errors), detail=str(errors))

    missing_evidence = json.loads(json.dumps(good))
    del missing_evidence["findings"][0]["evidence"]
    errors, _ = _validate_report(missing_evidence, REPO_PATH)
    check("missing evidence rejected", any("evidence" in e for e in errors), detail=str(errors))

    empty_findings = {"title": "x", "findings": []}
    errors, _ = _validate_report(empty_findings, REPO_PATH)
    check("empty findings rejected", any("findings" in e for e in errors), detail=str(errors))

    not_dict = "hello"
    errors, _ = _validate_report(not_dict, REPO_PATH)
    check("non-object rejected", errors != [], detail=str(errors))


def test_submit_archive():
    print("[4] _handle_submit (archive to workspace/review_reports)")
    with tempfile.TemporaryDirectory() as tmp:
        fake_ws = SimpleNamespace(root=Path(tmp))
        fake_session = SimpleNamespace(workspace=fake_ws, repo_path=REPO_PATH)
        report = {
            "title": "测试评审报告",
            "findings": [
                {
                    "id": "f1",
                    "axis": "general",
                    "severity": "nit",
                    "file": "a.py",
                    "title": "t",
                    "evidence": "e",
                    "suggestion": "s",
                }
            ],
        }
        out = json.loads(_handle_submit({"report": report}, fake_session))
        check("submit returns submitted", out.get("status") == "submitted", detail=str(out))
        rdir = Path(tmp) / "review_reports"
        files = list(rdir.glob("*.json"))
        check("report file archived", len(files) == 1)
        if files:
            saved = json.loads(files[0].read_text(encoding="utf-8"))
            check("archived content intact", saved["title"] == "测试评审报告")

        bad = json.loads(json.dumps(report))
        bad["findings"][0]["severity"] = "fatal"
        out2 = json.loads(_handle_submit({"report": bad}, fake_session))
        check("invalid report rejected on submit", out2.get("status") == "rejected")


def test_prepare_end_to_end():
    print("[5] handle_review_changes prepare (end-to-end on this repo)")
    store = SessionStore()
    session = resolve_session({"repo_path": REPO_PATH}, store)
    if session is None:
        from codewiki.mcp.tools.analysis import handle_analyze_repo

        print("  (no cached session — running analyze_repo first, this may take a while)")
        handle_analyze_repo({"repo_path": REPO_PATH}, store)

    out = json.loads(handle_review_changes({"repo_path": REPO_PATH, "mode": "prepare"}, store))
    check("prepare status", out.get("status") == "prepared", detail=str(out)[:200])
    check("workspace file written", isinstance(out.get("file"), str), detail=str(out)[:200])

    # The compact response is a file side-channel: read the full package back.
    pkg = json.loads(Path(out["file"]).read_text(encoding="utf-8"))
    check("target present", "target" in pkg)
    check("evidence has general axis", "general" in pkg.get("evidence", {}))
    check("evidence has convention axis", "convention" in pkg.get("evidence", {}))
    check("evidence has module_knowledge axis", "module_knowledge" in pkg.get("evidence", {}))
    check("evidence has spec axis", "spec" in pkg.get("evidence", {}))
    check("changed_sources annotated", bool(pkg["target"].get("changed_sources")))

    # focus restrict
    out_focus = json.loads(
        handle_review_changes(
            {"repo_path": REPO_PATH, "mode": "prepare", "focus": "general"}, store
        )
    )
    pkg_focus = json.loads(Path(out_focus["file"]).read_text(encoding="utf-8"))
    ev = pkg_focus.get("evidence", {})
    check("focus=general restricts axes", set(ev.keys()) == {"general"}, detail=str(ev.keys()))

    # invalid mode
    out_bad = json.loads(handle_review_changes({"repo_path": REPO_PATH, "mode": "nope"}, store))
    check("invalid mode rejected", "error" in out_bad, detail=str(out_bad)[:200])


def test_axis_key_mapping():
    print("[6] evidence collectors map query_wiki result keys (file/relevance_score)")
    import codewiki.mcp.tools.review_changes as rc

    with tempfile.TemporaryDirectory() as tmp:
        repowiki = Path(tmp)
        (repowiki / "notes").mkdir()
        (repowiki / "notes" / "note-1.md").write_text(
            "---\ntitle: 支付坑\ntype: pitfall\nrelated_modules: [codewiki/mcp/tools]\n---\n正文\n",
            encoding="utf-8",
        )
        fake_session = SimpleNamespace(output_dir=repowiki, repo_path=tmp)

        def fake_query(store, session, arguments):
            if arguments.get("mode") == "overview":
                return {"doctrine": "DOCTRINE"}
            return {
                "results": [
                    {
                        "source": "note",
                        "file": "notes/note-1.md",
                        "title": "支付坑",
                        "snippet": "支付模块的坑",
                        "relevance_score": 2.5,
                    }
                ]
            }

        orig = rc._query_wiki
        rc._query_wiki = fake_query
        try:
            conv = rc._collect_convention_evidence(None, fake_session)
            check("convention hits non-empty", bool(conv["hits"]), str(conv["hits"])[:200])
            if conv["hits"]:
                check(
                    "convention path from file key",
                    conv["hits"][0]["path"] == "notes/note-1.md",
                    str(conv["hits"][0]),
                )
                check(
                    "convention score from relevance_score",
                    conv["hits"][0]["score"] == 2.5,
                    str(conv["hits"][0]),
                )
            check("doctrine extracted", conv.get("doctrine") == "DOCTRINE", str(conv)[:120])

            changes = [FileChange(path="codewiki/mcp/tools/foo.py", added_lines=[1])]
            mod = rc._collect_module_evidence(None, fake_session, changes, set())
            check("module_knowledge hits non-empty", bool(mod["hits"]), str(mod)[:200])
            if mod["hits"]:
                h = mod["hits"][0]
                check("module path from file key", h["path"] == "notes/note-1.md", str(h))
                check("module type from note frontmatter", h["type"] == "pitfall", str(h))
                check(
                    "module related_modules from note frontmatter",
                    h["related_modules"] == ["codewiki/mcp/tools"],
                    str(h),
                )
                check("module score from relevance_score", h["score"] == 2.5, str(h))
        finally:
            rc._query_wiki = orig


def main():
    print("=== review_changes Tests ===\n")
    test_checklist()
    test_spec_auto_discover()
    test_validate_report()
    test_submit_archive()
    test_prepare_end_to_end()
    test_axis_key_mapping()
    print(f"\n=== Result: {_passed} passed, {_failed} failed ===")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
