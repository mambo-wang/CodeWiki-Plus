"""MCP tool: review_changes — git-diff driven code review evidence assembly.

Answers "is my change *correct*?" after editing code, against four review
axes (short names shared by the ``focus`` enum, the evidence keys and the
report ``axis`` field):

* ``spec``              — SPEC/design docs (explicit paths or auto-discovered)
* ``convention``        — project wiki conventions + L3 Doctrine
* ``module_knowledge``  — pitfall/lesson/decision notes of the changed module
* ``general``           — built-in engineering checklist (+ project override)

The tool is deterministic and holds NO LLM (Doctrine: "tool does
deterministic assembly, reasoning stays with the caller agent"):

* ``mode="prepare"`` — assemble the review context package (diff + annotated
  changed sources + four-axis evidence) and write it to the workspace.
* ``mode="submit"``  — validate and archive the caller's structured review
  report to ``<workspace>/review_reports/``.

Source version rule: ``since`` mode reads sources via ``git show HEAD:<path>``
so the reviewed code matches the diff exactly; uncommitted changes read the
working tree.  Changed lines are annotated with line numbers and a ``>>``
prefix.
"""

from __future__ import annotations

import json
import logging
import posixpath
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.change_analysis import (
    FileChange,
    collect_git_changes,
    locate_changed_components,
    suggest_tests,
    _norm,
)
from codewiki.mcp.tools.review_checklist import get_checklist
from codewiki.mcp.tools.workspace_result import resolve_session, write_result

logger = logging.getLogger(__name__)

_AXES = ("spec", "convention", "module_knowledge", "general")
_SEVERITIES = ("blocker", "major", "minor", "nit")
_SPEC_DIRS = ("docs", "specs", ".scratch", "openspec")
_SPEC_MAX_DEPTH = 3
_SPEC_MAX_HITS = 3
_SPEC_MAX_CHARS = 4000
_CONVENTION_QUERIES = ("编码规范", "命名约定", "日志约定", "错误处理约定", "测试约定")
_SLUG_RE = re.compile(r"[^\w\u4e00-\u9fff-]+")


# ------------------------------------------------------------------
# Source reading (version-aware) + change-line annotation
# ------------------------------------------------------------------

def _read_versioned_lines(git_root: str, rel_path: str, since: Optional[str]) -> List[str]:
    """File lines from HEAD (``since`` mode) or the working tree."""
    if since:
        import git

        repo = git.Repo(git_root, search_parent_directories=True)
        text = repo.git.show(f"HEAD:{rel_path}")
        return text.splitlines()
    p = Path(git_root) / rel_path
    try:
        return p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _annotate_lines(
    lines: List[str],
    start_line: int,
    changed_lines: Set[int],
) -> str:
    """Render ``lines`` with absolute line numbers; changed lines prefixed ``>>``.

    ``lines`` are the component's slice (file line ``start_line`` maps to
    index 0).  Annotation keeps file-level line numbers so findings can cite
    ``file:line`` directly.
    """
    out: List[str] = []
    for i, text in enumerate(lines):
        ln = start_line + i
        mark = ">>" if ln in changed_lines else "  "
        out.append(f"{mark} {ln:>5}  {text}")
    return "\n".join(out)


def _build_changed_sources(
    session: Any,
    start_ids: Set[str],
    changes: List[FileChange],
    git_root: str,
    since: Optional[str],
) -> Dict[str, str]:
    """changed_sources: file path → annotated component sources (multi-component joined)."""
    change_by_path: Dict[str, FileChange] = {_norm(c.path): c for c in changes}
    by_file: Dict[str, List[str]] = {}
    components = session.components

    for cid in sorted(start_ids):
        node = components.get(cid)
        if node is None:
            continue
        rel = _norm(getattr(node, "relative_path", "") or "")
        if not rel:
            continue
        start_line = int(getattr(node, "start_line", 0) or 0)
        end_line = int(getattr(node, "end_line", 0) or 0)

        fc = change_by_path.get(rel)
        changed_lines: Set[int] = set()
        if fc is not None:
            changed_lines.update(fc.added_lines)
            changed_lines.update(fc.deleted_anchors)

        if since:
            all_lines = _read_versioned_lines(git_root, rel, since)
        else:
            all_lines = _read_versioned_lines(git_root, rel, None)

        if start_line > 0 and end_line > 0:
            comp_lines = all_lines[max(0, start_line - 1):end_line]
        else:
            comp_lines = all_lines

        header = (
            f"### {cid}\n"
            f"# file: {rel}  lines {start_line}-{end_line}\n"
        )
        body = _annotate_lines(comp_lines, max(1, start_line), changed_lines)
        by_file.setdefault(rel, []).append(header + body)

    # Untracked new files have no graph components, so the loop above cannot
    # reach them.  Include the full working-tree source (all lines are new)
    # so the review target is not empty for brand-new files.
    for fc in changes:
        if not fc.is_untracked:
            continue
        rel = _norm(fc.path)
        if rel in by_file:
            continue
        all_lines = _read_versioned_lines(git_root, rel, None)
        header = (
            f"### {rel} (untracked new file)\n"
            f"# file: {rel}  not in analysis graph — full working-tree source\n"
        )
        body = _annotate_lines(all_lines, 1, set(fc.added_lines))
        by_file[rel] = header + body

    return {f: "\n\n".join(blocks) for f, blocks in by_file.items()}


def _build_target(
    session: Any,
    changes: List[FileChange],
    located: Dict[str, Any],
    git_root: str,
    since: Optional[str],
) -> Dict[str, Any]:
    """Assemble the ``target`` block (diff summary + annotated sources + impact)."""
    start_ids: Set[str] = located["changed_component_ids"]
    components = session.components

    added = sum(len(c.added_lines) for c in changes)
    deleted = sum(len(c.deleted_anchors) for c in changes)

    changed_components: List[Dict[str, Any]] = []
    for cid in sorted(start_ids):
        node = components.get(cid)
        changed_components.append(
            {
                "component_id": cid,
                "name": getattr(node, "name", cid) if node else cid,
                "file_path": _norm(getattr(node, "relative_path", "") or "") if node else "",
                "start_line": int(getattr(node, "start_line", 0) or 0) if node else 0,
                "end_line": int(getattr(node, "end_line", 0) or 0) if node else 0,
                "component_type": getattr(node, "component_type", "unknown") if node else "unknown",
            }
        )

    changed_sources = _build_changed_sources(session, start_ids, changes, git_root, since)

    affected_list: List[Dict[str, Any]] = []
    if start_ids:
        try:
            from codewiki.src.be.dependency_analyzer.topo_sort import (
                build_graph_from_components,
                transitive_impact,
            )

            graph = build_graph_from_components(components)
            result = transitive_impact(
                graph, start_ids, max_depth=10, direction="depended_by", track_paths=False
            )
            for cid, depth in sorted(result["affected"].items(), key=lambda x: (x[1], x[0])):
                node = components.get(cid)
                if node is None:
                    continue
                affected_list.append(
                    {
                        "component_id": cid,
                        "name": getattr(node, "name", cid),
                        "file_path": _norm(getattr(node, "relative_path", "") or ""),
                        "depth": depth,
                    }
                )
        except Exception as exc:  # pragma: no cover - graph build failure degrades, not fatal
            logger.warning("Impact computation failed: %s", exc)

    suggested = suggest_tests(components, {a["component_id"] for a in affected_list} | start_ids,
                              repo_path=session.repo_path)

    return {
        "diff_summary": {
            "changed_files": len(changes),
            "added_lines": added,
            "deleted_lines": deleted,
        },
        "changed_components": changed_components,
        "changed_sources": changed_sources,
        "affected_components": affected_list,
        "suggested_tests": suggested,
    }


# ------------------------------------------------------------------
# Axis evidence collectors (deterministic)
# ------------------------------------------------------------------

def _read_spec_file(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:_SPEC_MAX_CHARS]
    except OSError:
        return None


def _auto_discover_specs(git_root: str, changes: List[FileChange]) -> List[Dict[str, str]]:
    """Stem/dir-name match inside docs/specs/.scratch/openspec (depth ≤ 3)."""
    stems: Set[str] = set()
    for c in changes:
        p = _norm(c.path)
        stem = Path(p).stem
        if stem:
            stems.add(stem)
        dirname = posixpath.dirname(p)
        if dirname:
            stems.add(dirname.rsplit("/", 1)[-1])

    candidates: List[Dict[str, Any]] = []
    root = Path(git_root)
    for dname in _SPEC_DIRS:
        base = root / dname
        if not base.is_dir():
            continue
        for p in base.rglob("*.md"):
            rel = p.relative_to(root)
            if len(rel.parts) > _SPEC_MAX_DEPTH + 1:
                continue
            cand_stem = p.stem
            score = 0
            for stem in stems:
                low_stem, low_cand = stem.lower(), cand_stem.lower()
                if low_cand == low_stem:
                    score = max(score, 2)
                elif low_stem in low_cand or low_cand in low_stem:
                    score = max(score, 1)
            if score:
                candidates.append({"path": str(p), "score": score})

    candidates.sort(key=lambda x: -x["score"])
    sources: List[Dict[str, str]] = []
    for cand in candidates[:_SPEC_MAX_HITS]:
        text = _read_spec_file(Path(cand["path"]))
        if text:
            sources.append({"path": cand["path"], "excerpt": text})
    return sources


def _collect_spec_evidence(
    repo_path: str,
    git_root: str,
    changes: List[FileChange],
    spec_paths: List[str],
) -> Dict[str, Any]:
    sources: List[Dict[str, str]] = []
    for sp in spec_paths or []:
        p = Path(sp)
        if not p.is_absolute():
            p = Path(repo_path) / sp
        if not p.is_file():
            continue
        text = _read_spec_file(p)
        if text:
            sources.append({"path": str(p), "excerpt": text})

    if not sources:
        sources = _auto_discover_specs(git_root, changes)

    note = ""
    if not sources:
        note = "未找到 SPEC——仅能评审通用正确性，无法查缺失/超范围"
    return {"found": bool(sources), "sources": sources, "note": note}


def _query_wiki(store: SessionStore, session: Any, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Run handle_query_wiki and parse the JSON response (best-effort)."""
    from codewiki.mcp.tools.knowledge_loop import handle_query_wiki

    call = {"repo_path": session.repo_path, "output_dir": session.output_dir, **arguments}
    try:
        return json.loads(handle_query_wiki(call, store))
    except Exception as exc:
        logger.warning("query_wiki failed (%s): %s", arguments.get("query") or arguments.get("mode"), exc)
        return {}


def _collect_convention_evidence(store: SessionStore, session: Any) -> Dict[str, Any]:
    hits: List[Dict[str, Any]] = []
    for q in _CONVENTION_QUERIES:
        r = _query_wiki(store, session, {"query": q, "include_notes": True, "max_results": 3})
        for item in r.get("results", []):
            hits.append(
                {
                    # query_wiki result entries key the relative path as "file"
                    # and the score as "relevance_score" (not "path"/"score").
                    "path": item.get("file") or item.get("path", ""),
                    "title": item.get("title", ""),
                    "excerpt": item.get("excerpt", "") or item.get("snippet", ""),
                    "score": item.get("relevance_score", item.get("score")),
                }
            )

    r = _query_wiki(store, session, {"mode": "overview"})
    doctrine = r.get("doctrine", "") or ""

    return {"queries": list(_CONVENTION_QUERIES), "hits": hits, "doctrine": doctrine}


def _note_metadata(output_dir: Any, rel_path: str) -> tuple[str, List[str]]:
    """Best-effort note frontmatter lookup for ``type`` / ``related_modules``.

    query_wiki result entries carry ``file``/``title``/``relevance_score`` but
    not the note's frontmatter ``type`` or ``related_modules``; read them from
    the note file directly. Notes only; defensive — any failure yields
    ``("", [])``.
    """
    if not rel_path.startswith("notes/"):
        return "", []
    try:
        from codewiki.mcp.tools.knowledge_loop import _extract_frontmatter_block

        text = (Path(output_dir) / rel_path).read_text(encoding="utf-8", errors="replace")
        fm = _extract_frontmatter_block(text)
        related = fm.get("related_modules") or []
        if isinstance(related, str):
            related = [related]
        return str(fm.get("type", "") or ""), [str(m) for m in related]
    except Exception:
        return "", []


def _collect_module_evidence(
    store: SessionStore,
    session: Any,
    changes: List[FileChange],
    start_ids: Set[str],
) -> Dict[str, Any]:
    dirs: List[str] = []
    for c in changes:
        d = posixpath.dirname(_norm(c.path))
        if d and d not in dirs:
            dirs.append(d)

    names: List[str] = []
    for cid in sorted(start_ids):
        node = session.components.get(cid)
        if node is not None:
            nm = getattr(node, "name", "")
            if nm and nm not in names:
                names.append(nm)

    queries = list(dirs) + names
    hits: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for q in queries:
        r = _query_wiki(store, session, {"query": q, "include_notes": True, "max_results": 5})
        for item in r.get("results", []):
            # query_wiki result entries key the relative path as "file" and
            # the score as "relevance_score" — not "path"/"score".
            path = item.get("file") or item.get("path", "")
            if not path or path in seen:
                continue
            seen.add(path)
            note_type, related = _note_metadata(session.output_dir, path)
            hits.append(
                {
                    "path": path,
                    "title": item.get("title", ""),
                    "type": note_type or item.get("type", ""),
                    "excerpt": item.get("excerpt", "") or item.get("snippet", ""),
                    "score": item.get("relevance_score", item.get("score")),
                    "related_modules": related or item.get("related_modules") or [],
                }
            )

    # Relevance sort: notes whose related_modules intersect the changed dirs first.
    def _rel_key(h: Dict[str, Any]) -> int:
        mods = set(h.get("related_modules") or [])
        return 0 if mods & set(dirs) else 1

    hits.sort(key=lambda h: (_rel_key(h), -(h.get("score") or 0)))

    return {"modules": dirs, "queries": queries, "hits": hits}


def _collect_general_evidence(repo_path: str, changes: List[FileChange]) -> Dict[str, Any]:
    changed_files = [_norm(c.path) for c in changes if c.path]
    return {"checklist": get_checklist(repo_path, changed_files)}


# ------------------------------------------------------------------
# Submit: report validation + archiving
# ------------------------------------------------------------------

def _slugify(title: str) -> str:
    slug = _SLUG_RE.sub("-", title).strip("-")
    return slug[:40] or "report"


def _validate_report(report: Any, repo_path: str) -> tuple[List[str], List[str]]:
    """Validate a review report. Returns ``(errors, warnings)``.

    Field/type/enum violations are errors (reject).  A ``rule_ref.source``
    pointing at a file that no longer exists is a warning only — the report
    is a historical record, a stale citation is tolerable.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(report, dict):
        return ["report must be a JSON object"], []

    if not isinstance(report.get("title"), str) or not report["title"].strip():
        errors.append("report.title must be a non-empty string")

    findings = report.get("findings")
    if not isinstance(findings, list) or not findings:
        errors.append("report.findings must be a non-empty list")
        return errors, warnings

    for i, f in enumerate(findings):
        tag = f"findings[{i}]"
        if not isinstance(f, dict):
            errors.append(f"{tag} must be an object")
            continue
        if not isinstance(f.get("id"), str) or not f["id"].strip():
            errors.append(f"{tag}.id must be a non-empty string")
        if f.get("axis") not in _AXES:
            errors.append(f"{tag}.axis must be one of {_AXES}")
        if f.get("severity") not in _SEVERITIES:
            errors.append(f"{tag}.severity must be one of {_SEVERITIES}")
        if not isinstance(f.get("file"), str) or not f["file"].strip():
            errors.append(f"{tag}.file must be a non-empty string")
        if "line" in f and f["line"] is not None and not isinstance(f["line"], int):
            errors.append(f"{tag}.line must be an integer or omitted")
        if not isinstance(f.get("title"), str) or not f["title"].strip():
            errors.append(f"{tag}.title must be a non-empty string")
        if not isinstance(f.get("evidence"), str) or not f["evidence"].strip():
            errors.append(f"{tag}.evidence must be a non-empty string")
        if not isinstance(f.get("suggestion"), str) or not f["suggestion"].strip():
            errors.append(f"{tag}.suggestion must be a non-empty string")

        rule_ref = f.get("rule_ref")
        if rule_ref is not None:
            if not isinstance(rule_ref, dict):
                errors.append(f"{tag}.rule_ref must be an object when present")
            else:
                source = rule_ref.get("source")
                if source is not None and isinstance(source, str) and source:
                    sp = Path(source)
                    if not sp.is_absolute():
                        sp = Path(repo_path) / source
                    if not sp.exists():
                        warnings.append(f"{tag}.rule_ref.source no longer exists: {source}")

    summary = report.get("summary")
    if summary is not None and not isinstance(summary, dict):
        errors.append("report.summary must be an object when present")

    return errors, warnings


def _handle_submit(arguments: Dict[str, Any], session: Any) -> str:
    report = arguments.get("report")
    errors, warnings = _validate_report(report, session.repo_path)
    if errors:
        return json.dumps({"status": "rejected", "errors": errors}, ensure_ascii=False)

    workspace = getattr(session, "workspace", None)
    if workspace is None:
        return json.dumps({"error": "Session workspace not initialized."}, ensure_ascii=False)

    rdir = workspace.root / "review_reports"
    rdir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    fpath = rdir / f"{ts}-{_slugify(report['title'])}.json"
    fpath.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    out: Dict[str, Any] = {
        "status": "submitted",
        "report_file": str(fpath),
        "note_hint": "关键发现可用 ingest_note 沉淀（须用户确认）；报告不进 query_wiki 检索",
    }
    if warnings:
        out["warnings"] = warnings
    return json.dumps(out, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------
# Main handler
# ------------------------------------------------------------------

def handle_review_changes(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Assemble review evidence (prepare) or archive a review report (submit).

    Parameters (via *arguments*)
    ----------------------------
    repo_path : str
        Repository path. Auto-restores the session from the SQLite cache.
    mode : str
        ``"prepare"`` (assemble the review context package) | ``"submit"``
        (validate and archive the caller's report).
    since : str, optional
        Committed range ``git diff <since>..HEAD``; omitted = uncommitted
        changes.  In ``since`` mode changed sources are read from HEAD.
    spec_paths : list[str], optional
        Explicit SPEC/design doc paths (relative to repo_path or absolute).
        Auto-discovery inside docs/specs/.scratch/openspec runs only when no
        explicit path yields a readable file.
    focus : str, optional
        Restrict evidence assembly to one axis: ``all`` (default) | ``spec``
        | ``convention`` | ``module_knowledge`` | ``general``.
    report : object, optional (submit only)
        The caller's review report ``{title, findings, summary}``.
    """
    session = resolve_session(arguments, store)
    if session is None:
        return json.dumps(
            {"error": "Session not found. Provide a valid repo_path pointing to a previously analyzed repository."},
            ensure_ascii=False,
        )

    mode = arguments.get("mode", "prepare")
    if mode not in ("prepare", "submit"):
        return json.dumps({"error": f"Invalid mode {mode!r}: expected 'prepare' or 'submit'."}, ensure_ascii=False)

    if mode == "submit":
        return _handle_submit(arguments, session)

    # --- prepare -------------------------------------------------------
    since = arguments.get("since") or None
    spec_paths: List[str] = list(arguments.get("spec_paths") or [])
    focus = arguments.get("focus", "all")
    if focus not in ("all",) + _AXES:
        return json.dumps({"error": f"Invalid focus {focus!r}: expected 'all' or one of {_AXES}."}, ensure_ascii=False)

    try:
        git_info = collect_git_changes(session.repo_path, since=since, worktree=True)
    except ValueError as exc:
        return json.dumps({"error": f"Git analysis failed: {exc}"}, ensure_ascii=False)
    except Exception as exc:
        logger.warning("Git collection failed for %s: %s", session.repo_path, exc)
        return json.dumps({"error": f"Git analysis failed: {exc}"}, ensure_ascii=False)

    changes: List[FileChange] = git_info["changes"]
    if not changes:
        # No changes: still go through the workspace file side-channel so the
        # MCP response shape is consistent (always carries "file") regardless
        # of whether the range has diffs — callers (and tests) should not have
        # to branch on an early-returned compact dict.
        empty_result: Dict[str, Any] = {
            "status": "prepared",
            "query": {"repo_path": session.repo_path, "since": since, "focus": focus},
            "target": {
                "diff_summary": {"changed_files": 0, "added_lines": 0, "deleted_lines": 0},
                "changed_components": [], "changed_sources": {}, "affected_components": [],
                "suggested_tests": [],
            },
            "evidence": {},
            "hint": "No source-code changes found for the requested range.",
        }
        response = write_result(
            session,
            "review_context.json",
            empty_result,
            summary={
                "status": "prepared",
                "changed_files": 0,
                "changed_components": 0,
                "spec_found": False,
                "evidence_axes": [],
                "hint": "No source-code changes found for the requested range.",
            },
        )
        return json.dumps(response, indent=2, ensure_ascii=False)

    located = locate_changed_components(session.components, changes)
    start_ids: Set[str] = located["changed_component_ids"]

    target = _build_target(session, changes, located, git_info["git_root"], since)

    evidence: Dict[str, Any] = {}
    if focus in ("all", "spec"):
        evidence["spec"] = _collect_spec_evidence(
            session.repo_path, git_info["git_root"], changes, spec_paths
        )
    if focus in ("all", "convention"):
        evidence["convention"] = _collect_convention_evidence(store, session)
    if focus in ("all", "module_knowledge"):
        evidence["module_knowledge"] = _collect_module_evidence(store, session, changes, start_ids)
    if focus in ("all", "general"):
        evidence["general"] = _collect_general_evidence(session.repo_path, changes)

    hint = (
        "以 target 为评审对象、evidence 为依据执行评审（裁决顺序 spec > convention > "
        "module_knowledge > general）；产出 findings 后可用 mode=submit 落盘。"
    )
    if located["untracked_files"]:
        hint += (
            f"\n注意：{len(located['untracked_files'])} 个 untracked 新文件不在分析图谱内，"
            "changed_sources 已附其全文（非函数级切片）。可先运行 analyze_repo 增量分析后重新 prepare，"
            "以获得组件级定位。"
        )
    full_result: Dict[str, Any] = {
        "status": "prepared",
        "query": {
            "repo_path": session.repo_path,
            "since": since,
            "focus": focus,
            "source": git_info["source"],
        },
        "target": target,
        "evidence": evidence,
        "hint": hint,
    }
    if located["file_level_changes"]:
        full_result["file_level_changes"] = located["file_level_changes"]
    if located["deleted_unlocated"]:
        full_result["deleted_unlocated"] = located["deleted_unlocated"]
    if located["untracked_files"]:
        full_result["untracked_files"] = located["untracked_files"]

    response = write_result(
        session,
        "review_context.json",
        full_result,
        summary={
            "status": "prepared",
            "changed_files": len(changes),
            "changed_components": len(start_ids),
            "spec_found": evidence.get("spec", {}).get("found"),
            "evidence_axes": sorted(evidence.keys()),
            "hint": "Read the file for the full review context package.",
        },
    )
    return json.dumps(response, indent=2, ensure_ascii=False)
