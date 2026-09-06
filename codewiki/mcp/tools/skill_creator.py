"""MCP tool: skill_creator — compile confirmed knowledge into SKILL.md drafts.

skill-creator T2 (issue #25, docs/skill-creator需求与设计方案.md §4.1-§4.3,
ADR-0004): a one-way compiler from confirmed knowledge (scenario blocks,
curated stable pitfall/lesson/decision notes, open issues on existing skills)
into behaviour-instruction SKILL.md drafts in the draft zone
(``repowiki/skills/``). Mode C protocol, mirroring note_consolidation (the
tool does deterministic bookkeeping; the host agent does the writing):

  mode='prepare'
      Zero side effects. Returns the candidate materials not yet absorbed by
      any skill, the open issues grouped per existing skill, the draft-zone
      skill index, a name/description conflict pre-check (token Jaccard
      > 0.6), the graded capacity warning (green / orange=update-only /
      red=merge-first), the anti-fragmentation discipline text and the
      writing system prompt (description = condition + action, five-section
      skeleton, quantified note backlinks, body <= 8KB, no absolute paths
      or secrets).

  mode='submit'
      Takes ``report.skills[]`` = [{name, action(created|updated),
      description, body, source_refs[], summary?, revision_note?}] —
      validates each entry (failures name the exact rule), writes
      ``skills/<name>/SKILL.md`` with OKF frontmatter (render_frontmatter
      round-trip), appends revisions on update, records bidirectional
      provenance (skill ``metadata.source_refs`` ⇄ material
      ``metadata.compiled_into``) and rebuilds the search index. An empty
      report (``no_action``) is a legal round: "material not worth
      compiling" is not an error.

Out of scope here (later tickets): install/retire (#26), the eight SKILL.md
lint checks (#27), recall-side isolation (#28). Draft-zone skills are
indexed but never effective — the two-zone gate (ADR-0004) is physical:
the IDE never scans repowiki/skills/.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from codewiki.mcp.tools.note_consolidation import (
    _append_meta_list,
    _norm_rel,
    _read_body,
    _read_frontmatter,
    _SOFT_DELETE_MARKER,
)

logger = logging.getLogger(__name__)

_VALID_ACTIONS = ("created", "updated")
# Design §4.3-4 / Q4: 8KB body cap (Anthropic skills are typically 1-3KB;
# over-budget means the skill should split or reference the scenario).
_BODY_LIMIT_BYTES = 8 * 1024
# Design §4.5: capacity hard cap 12, orange line 9 (analogous to
# max_scenarios=15 in aggregation_state).
_MAX_SKILLS = 12
_ORANGE_SKILLS = 9
_STALE_DAYS = 90
_SUMMARY_CHARS = 300
_CANDIDATE_LIMIT = 30
_DESCRIPTION_MIN_CHARS = 10
# Design §4.5: name/description conflict pre-check threshold.
_CONFLICT_JACCARD = 0.6
# Only high-value note types are skill material (design §2/§4.1); task
# memories are explicitly excluded (ADR-0002 direct-write, no gate).
_SKILL_NOTE_TYPES = ("pitfall", "lesson", "decision")

# Design §4.3-5 / lint 无敏感串: absolute paths and secret keys are rejected.
_ABS_PATH_RE = re.compile(r"(/Users/|/home/|[A-Za-z]:\\)")
_SECRET_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9]{20,}")
_SENSITIVE_PATTERNS: Tuple[Tuple[str, Any], ...] = (
    ("absolute_path", _ABS_PATH_RE),
    ("secret_key", _SECRET_KEY_RE),
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[a-z0-9]+")

_KIND_ALIASES = {
    "scenario": "scenarios",
    "scenarios": "scenarios",
    "note": "notes",
    "notes": "notes",
    "issue": "issues",
    "issues": "issues",
}

_FRAGMENTATION_DISCIPLINE = (
    "Anti-fragmentation discipline (design §4.5): DEFAULT to UPDATE, not "
    "CREATE. At most ONE new skill per submit batch. Before creating a new "
    "skill, read at least 2 most-similar existing skills and confirm the new "
    "knowledge fits nowhere. ORANGE capacity (9-11 live skills) means UPDATE "
    "only; RED (>=12) means merge/retire first. A name/description Jaccard "
    "similarity > 0.6 with an existing skill is a conflict — update that "
    "skill instead of creating a near-duplicate."
)

_SKILL_WRITING_SYSTEM = (
    "You are the SKILL Compiler (skill-creator, Mode C).\n"
    "Compile CONFIRMED knowledge (scenario blocks, stable pitfall/lesson/"
    "decision notes, open issues on existing skills) into behaviour-"
    "instruction SKILL.md drafts. A skill changes how the IDE agent BEHAVES "
    "when its description matches — it is not retrievable knowledge.\n\n"
    "WRITING RULES (mandatory, design §4.3):\n"
    "1. description = TRIGGER CONDITION + CONCRETE ACTION in one sentence, "
    "e.g. 'ripgrep silently skips binary-detected files — verify empty "
    "search results with grep -a before concluding not found'. Abstract "
    "summaries fail IDE trigger matching.\n"
    "2. Body skeleton — five sections, same as scenario blocks: "
    "工作场景 / 适用条件 / 核心 SOP / 判断逻辑 / 禁忌与反模式.\n"
    "3. Evidence with quantified backlinks: cite in the body "
    "'依据: notes/<file>.md 的 <关键结论>' (note title + key conclusion), "
    "not just source_refs paths.\n"
    "4. Body <= 8KB. Over-budget means split the skill or reference the "
    "scenario instead of restating it.\n"
    "5. NO absolute paths (/Users/..., C:\\..., D:\\repos) and NO secrets or "
    "API keys — submit rejects them.\n"
    "6. Material boundary: scenarios + stable pitfall/lesson/decision notes "
    "+ open issues only. Task memories are NOT skill material (ADR-0002: "
    "direct-write, no confirmation gate).\n\n"
    "STRATEGY (anti-fragmentation):\n"
    "1. Default is UPDATE; at most ONE new skill per batch.\n"
    "2. Before CREATE, read >= 2 most-similar existing skills; the conflict "
    "pre-check in prepare flags Jaccard > 0.6.\n"
    "3. ORANGE capacity means UPDATE only; RED means merge/retire first.\n\n"
    "WORKFLOW:\n"
    "(1) Read the candidate materials listed in prepare (view_repo_file).\n"
    "(2) For revisions of existing skills, fold in their open issues "
    "(flag_issue feedback, grouped in prepare).\n"
    "(3) Call skill_creator(mode='submit', report={skills: [{name, action, "
    "description, body, source_refs, summary?, revision_note?}]}) — the "
    "tool writes the SKILL.md draft (status=draft). Nothing is effective "
    "until install, which is a separate user action (T3).\n"
    "Empty output is legal: when the material is not worth compiling, "
    "submit an empty report (no_action)."
)


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stale_after(output_dir: Path) -> str:
    """``YYYY-MM-DD`` = today + default_stale_days (schema convention, 90)."""
    days = _STALE_DAYS
    try:
        from codewiki.mcp.tools.page_router import load_schema

        raw = (load_schema(output_dir).get("conventions") or {}).get("default_stale_days")
        if raw is not None:
            days = max(1, int(raw))
    except Exception:
        pass
    return (date.today() + timedelta(days=days)).isoformat()


def _est_tokens(text: str) -> int:
    """Rough reading-cost estimate: 1 token per CJK char + 1 per 4 others."""
    cjk = len(_CJK_RE.findall(text))
    return cjk + (len(text) - cjk) // 4


def _tokens(text: str) -> Set[str]:
    """Token set for Jaccard: lowercase word runs + individual CJK chars."""
    toks = set(_WORD_RE.findall((text or "").lower()))
    toks.update(_CJK_RE.findall(text or ""))
    return toks


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _skills_dir(output_dir: Path) -> Path:
    from codewiki.mcp.tools.page_router import get_page_type_dir

    return get_page_type_dir("skill", output_dir)


# --------------------------------------------------------------------------- #
# Draft-zone scan
# --------------------------------------------------------------------------- #
def _scan_skills(output_dir: Path) -> List[Dict[str, Any]]:
    """Draft-zone index: skills/<name>/SKILL.md → name/status/summary/refs."""
    sdir = _skills_dir(output_dir)
    out: List[Dict[str, Any]] = []
    if not sdir.is_dir():
        return out
    for p in sorted(sdir.rglob("SKILL.md")):
        if not p.is_file():
            continue
        fm = _read_frontmatter(p) or {}
        meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
        refs = meta.get("source_refs")
        if isinstance(refs, str):
            refs = [refs]
        if not isinstance(refs, list):
            refs = []
        out.append(
            {
                "name": str(fm.get("name") or p.parent.name),
                "file": _norm_rel(str(p.relative_to(output_dir)), output_dir),
                "status": str(fm.get("status") or "draft"),
                "description": str(fm.get("description") or ""),
                "summary": str(meta.get("summary") or "")[:_SUMMARY_CHARS],
                "source_refs": [
                    _norm_rel(str(r), output_dir) for r in refs if str(r).strip()
                ],
            }
        )
    return out


def _absorbed_paths(skills: List[Dict[str, Any]]) -> Set[str]:
    """Material rel-paths already absorbed by some skill's source_refs."""
    absorbed: Set[str] = set()
    for s in skills:
        absorbed.update(s["source_refs"])
    return absorbed


# --------------------------------------------------------------------------- #
# Candidate materials
# --------------------------------------------------------------------------- #
def _candidate_scenarios(
    output_dir: Path, absorbed: Set[str], limit: int
) -> List[Dict[str, Any]]:
    """Live scenario blocks not yet absorbed by any skill."""
    from codewiki.mcp.tools.page_router import get_page_type_dir

    sdir = get_page_type_dir("scenario", output_dir)
    out: List[Dict[str, Any]] = []
    if not sdir.is_dir():
        return out
    for p in sorted(sdir.glob("*.md")):
        if not p.is_file():
            continue
        if _read_body(p) == _SOFT_DELETE_MARKER:
            continue  # pending soft-delete
        rel = _norm_rel(str(p.relative_to(output_dir)), output_dir)
        if rel in absorbed:
            continue
        fm = _read_frontmatter(p) or {}
        meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
        body = _read_body(p)
        out.append(
            {
                "file": rel,
                "title": str(fm.get("title") or p.stem),
                "summary": str(meta.get("summary") or "")[:_SUMMARY_CHARS],
                "est_tokens": _est_tokens(body),
            }
        )
        if len(out) >= limit:
            break
    return out


def _candidate_notes(
    output_dir: Path, absorbed: Set[str], limit: int
) -> List[Dict[str, Any]]:
    """Stable pitfall/lesson/decision notes not yet absorbed by any skill."""
    from codewiki.src.config import NOTES_DIR

    ndir = Path(output_dir) / NOTES_DIR
    out: List[Dict[str, Any]] = []
    if not ndir.is_dir():
        return out
    for p in sorted(ndir.glob("*.md")):
        if not p.is_file():
            continue
        fm = _read_frontmatter(p) or {}
        status = str(fm.get("status", "")).lower()
        if status not in ("stable", "confirmed"):
            continue
        if str(fm.get("type", "")).lower() not in _SKILL_NOTE_TYPES:
            continue
        rel = _norm_rel(str(p.relative_to(output_dir)), output_dir)
        if rel in absorbed:
            continue
        body = _read_body(p)
        out.append(
            {
                "file": rel,
                "title": str(fm.get("title") or p.stem),
                "note_type": str(fm.get("type") or ""),
                "preview": body[:_SUMMARY_CHARS],
                "est_tokens": _est_tokens(body),
            }
        )
        if len(out) >= limit:
            break
    return out


def _open_issues_per_skill(output_dir: Path) -> List[Dict[str, Any]]:
    """Open flag_issue entries grouped by draft-skill name (design §4.4)."""
    from codewiki.mcp.tools.issue_tracker import _load_issues
    from codewiki.src.config import SKILLS_DIR

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for issue in (_load_issues(output_dir).get("issues") or {}).values():
        if not isinstance(issue, dict):
            continue
        if str(issue.get("status") or "open") != "open":
            continue
        parts = str(issue.get("page_path") or "").replace("\\", "/").split("/")
        if len(parts) < 3 or parts[0] != SKILLS_DIR:
            continue  # not a draft-skill issue
        groups.setdefault(parts[1], []).append(
            {
                "id": str(issue.get("id") or ""),
                "issue_type": str(issue.get("issue_type") or ""),
                "description": str(issue.get("description") or ""),
                "severity": str(issue.get("severity") or "warning"),
                "updated_at": str(issue.get("updated_at") or ""),
            }
        )
    return [{"skill": name, "issues": items} for name, items in sorted(groups.items())]


# --------------------------------------------------------------------------- #
# Capacity & conflict pre-check
# --------------------------------------------------------------------------- #
def _skill_capacity(live_count: int) -> Dict[str, Any]:
    if live_count >= _MAX_SKILLS:
        warning = "red"
    elif live_count >= _ORANGE_SKILLS:
        warning = "orange"
    else:
        warning = "none"
    return {
        "current": live_count,
        "max": _MAX_SKILLS,
        "orange": _ORANGE_SKILLS,
        "warning": warning,
    }


def _conflict_precheck(
    topic: Optional[str], skills: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Jaccard(>0.6) conflict pre-check of *topic* against existing skills."""
    if not (topic or "").strip():
        return {
            "provided": False,
            "warnings": [],
            "note": (
                "Pass topic=<planned skill name> to pre-check name/description "
                "conflicts (Jaccard > 0.6) against existing skills."
            ),
        }
    toks = _tokens(topic)
    warnings: List[Dict[str, Any]] = []
    for s in skills:
        sim_name = _jaccard(toks, _tokens(s["name"]))
        sim_desc = _jaccard(toks, _tokens(s["description"]))
        best, field = (sim_name, "name") if sim_name >= sim_desc else (sim_desc, "description")
        if best > _CONFLICT_JACCARD:
            warnings.append(
                {
                    "skill": s["name"],
                    "field": field,
                    "similarity": round(best, 3),
                    "message": (
                        f"topic '{topic}' is highly similar to skill "
                        f"'{s['name']}' ({field}, Jaccard {best:.2f} > "
                        f"{_CONFLICT_JACCARD}) — prefer UPDATE over CREATE."
                    ),
                }
            )
    return {"provided": True, "threshold": _CONFLICT_JACCARD, "warnings": warnings}


# --------------------------------------------------------------------------- #
# Submit: validation + writing
# --------------------------------------------------------------------------- #
def _validate_entry(
    entry: Dict[str, Any], output_dir: Path
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Validate one report entry. Returns (error|None, normalized values)."""
    from codewiki.src.store import slugify

    name = str(entry.get("name") or "").strip()
    action = str(entry.get("action") or "").lower()
    description = str(entry.get("description") or "").strip()
    body = entry.get("body")
    body = body if isinstance(body, str) else ""

    def _err(rule: str, message: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        return (
            {"name": name or "<missing>", "rule": rule, "message": message},
            {},
        )

    # name slug compliance: slugify(name) == name == directory name
    if not name or slugify(name) != name:
        return _err(
            "name_slug",
            f"name '{name}' is not a valid slug (slugify mismatch); the "
            "directory name must equal slugify(name).",
        )
    if action not in _VALID_ACTIONS:
        return _err(
            "action_invalid",
            f"action '{action}' invalid; expected one of created|updated.",
        )
    if len(description) < _DESCRIPTION_MIN_CHARS:
        return _err(
            "description_trigger",
            f"description must be non-empty and carry trigger semantics "
            f"(condition + action, >= {_DESCRIPTION_MIN_CHARS} chars); got "
            f"{len(description)}.",
        )
    if not body.strip():
        return _err("body_required", "body is required (the skill instructions).")
    if len(body.encode("utf-8")) > _BODY_LIMIT_BYTES:
        return _err(
            "body_too_large",
            f"body is {len(body.encode('utf-8'))} bytes; the cap is "
            f"{_BODY_LIMIT_BYTES} (split the skill or reference the scenario).",
        )

    raw_refs = entry.get("source_refs")
    if not isinstance(raw_refs, list) or not raw_refs:
        return _err(
            "source_refs_required",
            "source_refs must be a non-empty list of material paths "
            "(wiki/scenarios/... or notes/...).",
        )
    refs: List[str] = []
    for r in raw_refs:
        # Reject traversal BEFORE normalizing: _norm_rel's lstrip("./") would
        # silently turn "../../etc/passwd" into "etc/passwd", bypassing the
        # escape check below (and note_consolidation's helper shares this
        # quirk, so the check happens here on the RAW string).
        raw = str(r).replace("\\", "/").strip()
        if raw.startswith("../") or "/../" in f"/{raw}" or raw.startswith("/"):
            return _err("source_refs_invalid", f"source_ref '{raw}' escapes output_dir.")
        rel = _norm_rel(raw, output_dir)
        if not rel:
            continue
        try:
            (Path(output_dir) / rel).resolve().relative_to(Path(output_dir).resolve())
        except ValueError:
            return _err("source_refs_invalid", f"source_ref '{rel}' escapes output_dir.")
        refs.append(rel)
    if not refs:
        return _err("source_refs_required", "source_refs must contain at least one path.")

    # Sensitive strings: absolute paths / secret keys in description or body.
    scan_text = f"{description}\n{body}"
    for kind, pattern in _SENSITIVE_PATTERNS:
        m = pattern.search(scan_text)
        if m:
            return _err(
                "sensitive_content",
                f"sensitive {kind} pattern matched ('{m.group(0)}'); absolute "
                "paths and secrets are forbidden in skill bodies.",
            )

    path = _skills_dir(output_dir) / name / "SKILL.md"
    if action == "created" and path.is_file():
        return _err(
            "name_conflict",
            f"skills/{name}/SKILL.md already exists; use action='updated' "
            "(or retire + re-create).",
        )
    if action == "updated" and not path.is_file():
        return _err(
            "not_found",
            f"skills/{name}/SKILL.md not found; action='updated' requires an "
            "existing draft.",
        )

    return (
        None,
        {
            "name": name,
            "action": action,
            "description": description,
            "body": body.strip(),
            "source_refs": refs,
            "summary": str(entry.get("summary") or "").strip()[:_SUMMARY_CHARS],
            "revision_note": str(entry.get("revision_note") or "").strip(),
            "path": path,
        },
    )


def _render_skill_doc(
    fm: Dict[str, Any], body: str
) -> str:
    from codewiki.src.frontmatter import render_frontmatter

    return render_frontmatter(fm) + "\n" + body + "\n"


def _create_skill_file(values: Dict[str, Any], output_dir: Path) -> bool:
    """Write a brand-new draft skill (OKF frontmatter, design §4.2)."""
    from codewiki.src.config import actor_id
    from codewiki.src.store import locked_write

    fm: Dict[str, Any] = {
        "name": values["name"],
        "description": values["description"],
        "type": "Skill",
        "status": "draft",
        "generated": {"by": actor_id(), "at": _now_iso()},
        "stale_after": _stale_after(output_dir),
        "metadata": {
            "summary": values["summary"],
            "source_refs": values["source_refs"],
            "revisions": [
                {
                    "at": _now_iso(),
                    "reason": values["revision_note"] or "created from candidate materials",
                    "source": "skill_creator",
                }
            ],
        },
    }
    try:
        values["path"].parent.mkdir(parents=True, exist_ok=True)
        locked_write(values["path"], _render_skill_doc(fm, values["body"]))
        return True
    except OSError as e:
        logger.warning("skill create failed for %s: %s", values["name"], e)
        return False


def _update_skill_file(values: Dict[str, Any], output_dir: Path) -> bool:
    """Merge the report into an existing draft: append revision, refresh fields."""
    from codewiki.src.frontmatter import parse_frontmatter
    from codewiki.src.store import locked_rmw

    def _transform(text: str) -> Optional[str]:
        fm, _old_body = parse_frontmatter(text)
        if not fm:
            fm = {}
        fm["name"] = values["name"]
        fm["description"] = values["description"]
        fm["type"] = "Skill"
        fm["stale_after"] = _stale_after(output_dir)
        meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
        refs = meta.get("source_refs")
        if isinstance(refs, str):
            refs = [refs]
        if not isinstance(refs, list):
            refs = []
        merged = list(refs)
        for r in values["source_refs"]:
            if r not in merged:
                merged.append(r)
        meta["source_refs"] = merged
        if values["summary"]:
            meta["summary"] = values["summary"]
        revisions = meta.get("revisions")
        if not isinstance(revisions, list):
            revisions = []
        revisions.append(
            {
                "at": _now_iso(),
                "reason": values["revision_note"] or "updated via skill_creator",
                "source": "skill_creator",
            }
        )
        meta["revisions"] = revisions
        fm["metadata"] = meta
        return _render_skill_doc(fm, values["body"])

    try:
        return locked_rmw(values["path"], _transform) is not None
    except OSError as e:
        logger.warning("skill update failed for %s: %s", values["name"], e)
        return False


def _write_backlinks(values: Dict[str, Any], output_dir: Path) -> int:
    """Append the skill path to each material's metadata.compiled_into."""
    skill_rel = _norm_rel(str(values["path"].relative_to(output_dir)), output_dir)
    linked = 0
    for ref in values["source_refs"]:
        target = Path(output_dir) / ref
        if target.is_file() and _append_meta_list(target, "compiled_into", [skill_rel]):
            linked += 1
    return linked


# --------------------------------------------------------------------------- #
# Tool handler
# --------------------------------------------------------------------------- #
def handle_skill_creator(arguments: Dict[str, Any], store: Any) -> str:
    """Compile confirmed knowledge into draft-zone SKILL.md assets (Mode C)."""
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    if session is None and session_id:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    try:
        from codewiki.mcp.tools.store_bridge import resolve_output_dir

        output_dir = resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    mode = str(arguments.get("mode") or "prepare").lower()
    if mode in ("install", "retire"):
        return json.dumps(
            {
                "error": (
                    f"mode='{mode}' is not implemented yet (T3, issue #26); "
                    "this build covers prepare and submit only."
                )
            }
        )
    if mode not in ("prepare", "submit"):
        return json.dumps(
            {"error": f"Invalid mode '{mode}'. Expected one of: prepare, submit."}
        )

    # ---- mode == "prepare" (zero side effects) ---- #
    if mode == "prepare":
        try:
            limit = min(200, max(1, int(arguments.get("limit") or _CANDIDATE_LIMIT)))
        except (TypeError, ValueError):
            limit = _CANDIDATE_LIMIT

        kinds = {"scenarios", "notes", "issues"}
        raw_sources = arguments.get("sources")
        if isinstance(raw_sources, str):
            raw_sources = [raw_sources]
        if isinstance(raw_sources, list):
            mapped = {
                _KIND_ALIASES.get(str(s).strip().lower()) for s in raw_sources
            } - {None}
            if mapped:
                kinds = mapped

        skills = _scan_skills(output_dir)
        absorbed = _absorbed_paths(skills)
        scenarios = (
            _candidate_scenarios(output_dir, absorbed, limit)
            if "scenarios" in kinds
            else []
        )
        notes = _candidate_notes(output_dir, absorbed, limit) if "notes" in kinds else []
        open_issues = _open_issues_per_skill(output_dir) if "issues" in kinds else []
        capacity = _skill_capacity(len(skills))
        conflict = _conflict_precheck(arguments.get("topic"), skills)

        return json.dumps(
            {
                "status": "prepared",
                "mode": "prepare",
                "candidates": {
                    "scenarios": scenarios,
                    "notes": notes,
                    "total": len(scenarios) + len(notes),
                },
                "open_issues_by_skill": open_issues,
                "skills_index": [
                    {k: s[k] for k in ("name", "file", "status", "summary")}
                    for s in skills
                ],
                "conflict_precheck": conflict,
                "capacity": capacity,
                "fragmentation_discipline": _FRAGMENTATION_DISCIPLINE,
                "system_prompt": _SKILL_WRITING_SYSTEM,
                "next": (
                    "(1) Read the candidate materials (view_repo_file); (2) for "
                    "existing skills, fold in their open issues; (3) default to "
                    "UPDATE — at most ONE new skill per batch, read >= 2 similar "
                    "skills before CREATE; (4) obey the capacity warning (orange = "
                    "update only, red = merge/retire first); (5) submit the report "
                    "with skill_creator(mode='submit'). Empty output (no_action) is "
                    "legal when the material is not worth compiling."
                ),
            },
            indent=2,
            ensure_ascii=False,
        )

    # ---- mode == "submit" ---- #
    report = arguments.get("report")
    if isinstance(report, str):
        try:
            report = json.loads(report)
        except json.JSONDecodeError:
            return json.dumps({"error": "report must be a JSON object."})
    if not isinstance(report, dict) or not isinstance(report.get("skills"), list):
        return json.dumps(
            {
                "error": (
                    "mode='submit' requires 'report': {skills: [{name, action, "
                    "description, body, source_refs, summary?, revision_note?}]} "
                    "with action in created|updated (skills may be empty)."
                )
            }
        )
    entries = report["skills"]
    if not entries:
        return json.dumps(
            {
                "status": "no_action",
                "mode": "submit",
                "message": (
                    "Empty skill report accepted (no_action) — material judged "
                    "not worth compiling; nothing was written."
                ),
            },
            ensure_ascii=False,
        )

    # Per-entry validation (nothing written until all entries pass).
    errors: List[Dict[str, Any]] = []
    validated: List[Dict[str, Any]] = []
    seen_names: Set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append({"name": "<invalid>", "rule": "entry_invalid", "message": "not an object"})
            continue
        err, values = _validate_entry(entry, output_dir)
        if err:
            errors.append(err)
            continue
        if values["name"] in seen_names:
            errors.append(
                {
                    "name": values["name"],
                    "rule": "duplicate_name",
                    "message": "the same skill name appears twice in this report.",
                }
            )
            continue
        seen_names.add(values["name"])
        validated.append(values)

    # Batch-level anti-fragmentation & capacity enforcement (design §4.5).
    created = [v for v in validated if v["action"] == "created"]
    if len(created) > 1:
        errors.append(
            {
                "name": None,
                "rule": "batch_fragmentation",
                "message": (
                    f"{len(created)} skills marked created in one batch; at most "
                    "ONE new skill per batch (default to UPDATE)."
                ),
            }
        )
    if created:
        live = len(_scan_skills(output_dir))
        capacity = _skill_capacity(live)
        if capacity["warning"] == "red":
            errors.append(
                {
                    "name": None,
                    "rule": "capacity_red",
                    "message": (
                        f"capacity RED: {live} live skills >= {_MAX_SKILLS}; merge "
                        "or retire existing skills before creating new ones."
                    ),
                }
            )
        elif capacity["warning"] == "orange":
            errors.append(
                {
                    "name": None,
                    "rule": "capacity_orange",
                    "message": (
                        f"capacity ORANGE: {live} live skills >= {_ORANGE_SKILLS}; "
                        "UPDATE only — no new skills."
                    ),
                }
            )

    if errors:
        return json.dumps(
            {
                "status": "error",
                "mode": "submit",
                "errors": errors,
                "message": (
                    f"{len(errors)} validation error(s); nothing was written. "
                    "Fix the reported rules and re-submit."
                ),
            },
            indent=2,
            ensure_ascii=False,
        )

    # Write drafts + bidirectional provenance.
    processed: List[Dict[str, Any]] = []
    for values in validated:
        ok = (
            _create_skill_file(values, output_dir)
            if values["action"] == "created"
            else _update_skill_file(values, output_dir)
        )
        if not ok:
            processed.append(
                {
                    "name": values["name"],
                    "action": values["action"],
                    "status": "write_failed",
                }
            )
            continue
        backlinks = _write_backlinks(values, output_dir)
        fm = _read_frontmatter(values["path"]) or {}
        meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
        revisions = meta.get("revisions")
        processed.append(
            {
                "name": values["name"],
                "action": values["action"],
                "file": _norm_rel(str(values["path"].relative_to(output_dir)), output_dir),
                "revisions": len(revisions) if isinstance(revisions, list) else 0,
                "backlinks": backlinks,
            }
        )

    # Rebuild the search index so the drafts are lintable/queryable metadata
    # immediately (recall-side isolation is T5, issue #28).
    index_result = None
    try:
        from codewiki.mcp.tools.wiki_search import build_full_index

        index_result = build_full_index(output_dir)
    except Exception as e:  # indexing is best-effort
        logger.warning("search index rebuild failed after skill submit: %s", e)

    live = len(_scan_skills(output_dir))
    return json.dumps(
        {
            "status": "completed",
            "mode": "submit",
            "processed": processed,
            "capacity": _skill_capacity(live),
            **({"index": index_result} if index_result else {}),
            "message": (
                f"Skill submit recorded: {len(processed)} operation(s), drafts "
                "landed in the draft zone (status=draft, NOT effective — install "
                "is a separate user action, T3). Source materials got "
                "compiled_into backlinks; prompt the user to review the drafts."
            ),
        },
        indent=2,
        ensure_ascii=False,
    )
