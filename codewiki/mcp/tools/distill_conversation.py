"""MCP tool: distill_conversation — distill a raw conversation into wiki notes.

distill_conversation is the *extract* half of the team-memory fusion loop
(spec: SPEC-conversation-to-wiki.md, ticket T2). It is the stateless partner
to capture_conversation: it does NOT hold an LLM. The LLM is injected by the
caller, matching the project-wide rule "LLM is heavy work and must be supplied
by the caller, never baked into a tool".

Two invocation modes:

  Mode A (direct, recommended for subagents):
      caller passes ``llm`` — an async callable ``async def llm(prompt, system)
      -> str`` — typically CodeBuddy's model. The tool awaits it inline.

  Mode B (background, recommended for web/worker):
      caller passes ``run_in_background=True`` (and NO ``llm``). A daemon thread
      is spawned that lazily builds an OpenAI-compatible LLM from the
      MAIN_MODEL / LLM_BASE_URL / LLM_API_KEY environment variables and records
      progress in ``repowiki/distill-jobs.json``.

  Mode C (agent-driven, recommended for IDE agents over MCP JSON):
      the host agent itself is the LLM. First call ``mode='prepare'`` to receive
      the pending transcripts plus the distillation system prompt; the agent
      extracts knowledge with its own model, then calls ``mode='submit'`` with
      ``distilled={conversation_id: <notes JSON>}`` so the tool performs the
      deterministic half (parse, dedup, ingest drafts, raw cleanup, index
      rebuild). Works over plain MCP JSON where a callable cannot be injected.

After distillation the produced note(s) are written via handle_ingest_note with
status=draft, awaiting human/agent confirm_note. The raw transcript is then
deleted unless its frontmatter carried keep_raw: true.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# note_type values accepted by ingest_note (see agents_md.py routing table)
_VALID_NOTE_TYPES = {
    "decision", "lesson", "pitfall", "architecture",
    "workaround", "known_issue", "general",
}

# System prompt: instruct the LLM to emit one JSON object with a list of notes,
# each following OKF note shape (## sections, title, note_type, related_modules).
_DISTILL_SYSTEM = (
    "You are a knowledge distillation engine for a software project wiki.\n"
    "Given a raw conversation transcript between a user and an assistant, extract "
    "reusable, durable knowledge worth persisting. Ignore chit-chat, greetings, "
    "transient task state, and anything already obvious from the code.\n\n"
    "Prefer KNOWLEDGE that a future agent or teammate would benefit from:\n"
    "  - decisions (with rationale / alternatives considered)\n"
    "  - lessons (corrected assumptions, debugging insights)\n"
    "  - pitfalls (gotchas, easy-to-misuse APIs)\n"
    "  - architecture (non-obvious structural facts)\n"
    "  - workarounds (temporary fixes + recovery condition)\n\n"
    "Return ONLY a single JSON object (no markdown fences) shaped exactly as:\n"
    "{\n"
    '  "notes": [\n'
    "    {\n"
    '      "title": "Short imperative/declarative title",\n'
    '      "note_type": "decision | lesson | pitfall | architecture | workaround",\n'
    '      "related_modules": ["module_slug"],\n'
    '      "tags": ["optional", "keywords"],\n'
    '      "content": "Full OKF note body in Markdown. Use H2 (##) sections such as '
    '## Background, ## Decision/正确做法, ## Rationale, ## Root cause, ## Recovery. '
    'Reuse exact names, paths, and code snippets from the conversation."\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "If the conversation contains no durable knowledge, return {\"notes\": []}."
)

_NOTE_TYPE_HINT = "Allowed note_type values: " + ", ".join(sorted(_VALID_NOTE_TYPES)) + "."

# Relevance score at/above which an existing note/ in notes/ is treated as a
# near-duplicate of a candidate draft (suppressed or merged instead of created).
_DEDUP_THRESHOLD = 0.6

# When the candidate title and an existing note title share this fraction of
# tokens (by Jaccard), it is a strong duplicate signal even at a slightly
# lower BM25 score.
_TITLE_SIMILARITY_THRESHOLD = 0.5


# --------------------------------------------------------------------------- #
# Argument / path resolution
# --------------------------------------------------------------------------- #
def _resolve_output_dir(
    session: Optional[Any],
    arguments: Dict[str, Any],
) -> Path:
    if session:
        return Path(session.output_dir).expanduser().resolve()
    od = arguments.get("output_dir")
    if od:
        return Path(od).expanduser().resolve()
    rp = arguments.get("repo_path")
    if rp:
        return Path(rp).expanduser().resolve() / "repowiki"
    raise ValueError("output_dir or repo_path is required (or pass an active session).")


def _resolve_raw_path(arguments: Dict[str, Any], output_dir: Path) -> Optional[Path]:
    """Find the raw conversation markdown file to distill.

    Resolution order:
      1. An explicit ``raw_path`` argument (abs / relative-to-output_dir / bare name).
      2. A ``conversation_id`` matching conv-<id>.md.
      3. All conv-*.md files under repowiki/raw/ (batch mode).
    Returns None when no explicit target is given (== batch over all raw files).
    """
    from codewiki.src.config import RAW_DIR

    raw_dir = output_dir / RAW_DIR
    rp = arguments.get("raw_path")
    if rp:
        p = Path(rp)
        if not p.is_absolute():
            # could be "raw/conv-x.md" or "conv-x.md"
            cand = output_dir / p
            if cand.exists():
                return cand
            cand2 = raw_dir / p.name
            if cand2.exists():
                return cand2
        elif p.exists():
            return p
        return None

    cid = arguments.get("conversation_id")
    if cid:
        direct = raw_dir / f"{cid}.md"
        if direct.exists():
            return direct
        alt = raw_dir / f"conv-{cid}.md"
        if alt.exists():
            return alt
        return None

    return None  # batch mode: caller decides scope


def _iter_raw_files(raw_dir: Path) -> List[Path]:
    if not raw_dir.exists():
        return []
    files = [p for p in raw_dir.glob("conv-*.md")]
    # Only not-yet-distilled files
    out = []
    for p in sorted(files):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        m = re.search(r"^status:\s*(\w+)", text, re.MULTILINE)
        if m and m.group(1) == "distilled":
            continue
        out.append(p)
    return out


# --------------------------------------------------------------------------- #
# Frontmatter parsing helpers
# --------------------------------------------------------------------------- #
def _parse_frontmatter(path: Path) -> Dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]
    meta: Dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta


def _extract_turns(text: str) -> str:
    """Pull the transcript body after the frontmatter for LLM input."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            body = text[end + 4:]
        else:
            body = text
    else:
        body = text
    body = body.strip()
    # Drop a leading "# Conversation Transcript" heading line if present
    if body.startswith("# Conversation Transcript"):
        body = body.split("\n", 1)[1].strip() if "\n" in body else ""
    return body


def _safe_rel(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _title_tokens(title: str) -> set:
    """Lowercased word tokens for a title (for Jaccard similarity)."""
    return {t for t in re.split(r"[\s_\-/]+", title.lower()) if t}


def _title_similarity(a: str, b: str) -> float:
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _find_existing_note(
    candidate_title: str,
    candidate_type: str,
    output_dir: Path,
    store: Any,
) -> Optional[Dict[str, Any]]:
    """Look for a near-duplicate of a candidate draft inside this output_dir's notes/.

    Dedup scope is strictly the current ``output_dir/notes/`` directory (a
    filesystem scan), NOT the global search index. This keeps distillation
    idempotent within a session while avoiding cross-run pollution: the shared
    analysis_cache.db may still hold notes distilled in previous test runs, and
    searching it would wrongly suppress a freshly distilled note as a duplicate.
    """
    notes_dir = output_dir / "notes"
    if not notes_dir.is_dir():
        return None

    best: Optional[Dict[str, Any]] = None
    best_score = 0.0
    for note_path in notes_dir.glob("*.md"):
        try:
            fm = _parse_frontmatter(note_path)
        except Exception:
            continue
        title = fm.get("title", "") or note_path.stem
        note_type = fm.get("type") or fm.get("note_type") or ""
        title_sim = _title_similarity(candidate_title, title)
        same_type = (note_type == candidate_type)
        # Use title similarity as the duplicate signal (0..1).
        score = title_sim
        is_dup = (
            score >= _DEDUP_THRESHOLD
            or (score >= _DEDUP_THRESHOLD * 0.8 and same_type)
            or (title_sim >= _TITLE_SIMILARITY_THRESHOLD and same_type)
        )
        if is_dup and score > best_score:
            rel = str(note_path.relative_to(output_dir))
            best = {
                "file": rel,
                "title": title,
                "note_type": note_type,
                "status": fm.get("status", "unknown"),
            }
            best_score = score
    return best


def _merge_source_into_note(
    existing_file: str,
    new_source_ref: str,
    output_dir: Path,
) -> None:
    """Append a source_conversation reference to an existing note (merge mode).

    Adds the raw conversation path to a YAML list frontmatter field
    ``source_conversations`` so repeated distillations accumulate provenance
    instead of creating duplicate drafts.
    """
    note_path = output_dir / existing_file
    try:
        text = note_path.read_text(encoding="utf-8")
    except OSError:
        return
    if not text.startswith("---"):
        return
    end = text.find("\n---", 3)
    if end == -1:
        return
    block = text[3:end]
    m = re.search(r"^source_conversations:\s*\[(.*)\]", block, re.MULTILINE)
    if m:
        items = [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
        if new_source_ref in items:
            return
        items.append(new_source_ref)
        new_list = "[" + ", ".join(f"'{x}'" for x in items) + "]"
        new_block = block[:m.start()] + "source_conversations: " + new_list + block[m.end():]
    else:
        new_block = block.rstrip() + f"\nsource_conversations: ['{new_source_ref}']\n"
    new_text = "---" + new_block + text[end:]
    try:
        note_path.write_text(new_text, encoding="utf-8")
    except OSError:
        pass


def _patch_note_origin(note_path: Path) -> None:
    """Add `origin: conversation` to a distilled draft note's frontmatter.

    This satisfies the T2 traceability requirement (every draft produced from a
    conversation must carry origin: conversation). The source_conversation
    reference is already stored via handle_ingest_note's source_ref field.
    """
    try:
        text = note_path.read_text(encoding="utf-8")
    except OSError:
        return
    if not text.startswith("---"):
        return
    end = text.find("\n---", 3)
    if end == -1:
        return
    block = text[3:end]
    if re.search(r"^origin:", block, re.MULTILINE):
        return  # already present
    new_block = block.rstrip() + "\norigin: conversation\n"
    new_text = "---" + new_block + text[end:]
    try:
        note_path.write_text(new_text, encoding="utf-8")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# LLM default builder (Mode B)
# --------------------------------------------------------------------------- #
def _default_llm_from_env() -> Callable[[str, str], Awaitable[str]]:
    """Build an async LLM callable from MAIN_MODEL / LLM_BASE_URL / LLM_API_KEY.

    Uses the project's pydantic-ai OpenAI-compatible client. Raises if the
    model cannot be constructed.
    """
    from codewiki.src.config import Config, MAIN_MODEL, LLM_BASE_URL, LLM_API_KEY
    from codewiki.src.be.llm_services import create_main_model
    import asyncio

    cfg = Config(
        repo_path=".",
        output_dir=".",
        dependency_graph_dir=".",
        docs_dir=".",
        max_depth=2,
        llm_base_url=LLM_BASE_URL,
        llm_api_key=LLM_API_KEY,
        main_model=MAIN_MODEL,
        cluster_model=MAIN_MODEL,
    )
    model = create_main_model(cfg)

    async def _call(prompt: str, system: str) -> str:
        # pydantic-ai run synchronous model call inside async via to_thread
        from pydantic_ai import Agent

        agent = Agent(model, system_prompt=system)
        result = await agent.run(prompt)
        return result.output

    return _call


# --------------------------------------------------------------------------- #
# Core distillation (stateless)
# --------------------------------------------------------------------------- #
def _parse_llm_notes(raw_llm_output: str) -> List[Dict[str, Any]]:
    """Parse the LLM JSON output into a list of note dicts; best-effort."""
    text = raw_llm_output.strip()
    # Strip possible markdown fences
    if text.startswith("```"):
        # remove first fence line and trailing fence
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to salvage a JSON object via brace matching
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return []
        else:
            return []
    notes = data.get("notes", []) if isinstance(data, dict) else []
    if not isinstance(notes, list):
        return []
    return notes


def _build_distill_input(raw_path: Path) -> Optional[Dict[str, Any]]:
    """Build the LLM input for one raw conversation file.

    Returns ``{"meta", "transcript", "prompt"}`` or ``None`` when the
    transcript body is empty (caller should skip the file). Shared by the
    LLM-injected modes (A/B) and the agent-driven mode (C, ``mode=prepare``).
    """
    meta = _parse_frontmatter(raw_path)
    text = raw_path.read_text(encoding="utf-8")
    transcript = _extract_turns(text)
    if not transcript:
        return None

    link_to = meta.get("link_to", "")
    prompt = (
        f"Conversation transcript (link_to={link_to or 'none'}):\n\n"
        f"{transcript}\n\n"
        f"{_NOTE_TYPE_HINT}\n"
        "Extract durable knowledge as JSON."
    )
    return {"meta": meta, "transcript": transcript, "prompt": prompt}


def _process_llm_output(
    raw_path: Path,
    llm_output: str,
    output_dir: Path,
    store: Any,
    note_type_override: Optional[str] = None,
    related_modules_override: Optional[List[str]] = None,
    dedup: str = "suppress",
) -> Dict[str, Any]:
    """Deterministic half of distillation.

    Takes the already-produced LLM JSON (from an injected LLM in modes A/B, or
    from the host agent itself in mode C ``submit``) and runs: parse → dedup
    against notes/ → ingest draft notes → mark/delete the raw file → rebuild
    the search index.
    """
    from codewiki.mcp.tools.knowledge_loop import handle_ingest_note

    meta = _parse_frontmatter(raw_path)
    link_to = meta.get("link_to", "")

    notes = _parse_llm_notes(llm_output)
    produced: List[Dict[str, Any]] = []
    # Traceability: source_conversation points at the raw file (relative to repowiki)
    raw_rel = str(raw_path.relative_to(output_dir)) if _safe_rel(raw_path, output_dir) else str(raw_path)
    for note in notes:
        note_type = note.get("note_type") or note_type_override or "general"
        if note_type not in _VALID_NOTE_TYPES:
            # Map unknown -> general to stay safe
            note_type = "general"
        title = note.get("title") or "Untitled conversation note"
        content = note.get("content") or ""
        related = note.get("related_modules") or related_modules_override or []
        if link_to and link_to not in related:
            related = related + [link_to]

        # --- T3: de-duplicate against existing notes/ before creating a draft ---
        existing = _find_existing_note(title, note_type, output_dir, store)
        if existing is not None:
            existing_file = existing.get("file", "")
            if dedup == "merge":
                _merge_source_into_note(existing_file, raw_rel, output_dir)
                produced.append({
                    "title": title,
                    "note_type": note_type,
                    "merged_into": existing_file,
                    "status": "merged",
                })
            else:  # suppress (default): drop the duplicate draft
                produced.append({
                    "title": title,
                    "note_type": note_type,
                    "duplicate_of": existing_file,
                    "status": "suppressed",
                })
            continue

        result = json.loads(handle_ingest_note({
            "output_dir": str(output_dir),
            "title": title,
            "note_type": note_type,
            "content": content,
            "related_modules": related,
            "tags": note.get("tags", []),
            "status": "draft",
            "source_ref": raw_rel,  # traceability: source_conversation
        }, store))
        note_file = result.get("note_path") or result.get("note_file")
        # Add origin: conversation to the draft note frontmatter (traceability)
        if note_file:
            _patch_note_origin(Path(note_file))
        produced.append({
            "title": title,
            "note_type": note_type,
            "note_file": note_file,
            "status": result.get("status", "unknown"),
        })

    # Mark raw as distilled and conditionally delete
    keep_raw = str(meta.get("keep_raw", "false")).lower() == "true"
    _mark_distilled(raw_path)
    deleted = False
    if not keep_raw and produced:
        try:
            raw_path.unlink()
            deleted = True
        except OSError:
            pass

    # Rebuild the BM25 search index so the freshly distilled notes become
    # immediately queryable via query_wiki. The index is cached on disk and
    # would otherwise miss the new notes until the next full rebuild.
    if produced:
        try:
            from codewiki.mcp.tools.wiki_search import build_full_index
            build_full_index(output_dir)
        except Exception as _e:  # indexing is best-effort; never block distillation
            logger.warning("search index rebuild failed after distill: %s", _e)

    return {
        "raw_path": str(raw_path),
        "status": "completed" if produced else "no_knowledge",
        "notes_created": len(produced),
        "notes": produced,
        "distilled": produced,
        "deleted_raw": deleted,
        "keep_raw": keep_raw,
    }


async def _distill_one(
    raw_path: Path,
    llm: Callable[[str, str], Awaitable[str]],
    output_dir: Path,
    store: Any,
    note_type_override: Optional[str] = None,
    related_modules_override: Optional[List[str]] = None,
    dedup: str = "suppress",
) -> Dict[str, Any]:
    """Distill a single raw conversation file into draft note(s) (modes A/B)."""
    built = _build_distill_input(raw_path)
    if built is None:
        return {"raw_path": str(raw_path), "status": "skipped", "reason": "empty transcript"}

    try:
        llm_output = await llm(built["prompt"], _DISTILL_SYSTEM)
    except Exception as e:  # LLM failure must not crash caller
        logger.exception("distill_conversation LLM call failed for %s", raw_path)
        return {"raw_path": str(raw_path), "status": "llm_error", "error": str(e)}

    return _process_llm_output(
        raw_path, llm_output, output_dir, store,
        note_type_override, related_modules_override, dedup,
    )


def _mark_distilled(raw_path: Path) -> None:
    try:
        text = raw_path.read_text(encoding="utf-8")
        new_text = re.sub(
            r"^status:\s*\w+", "status: distilled", text, count=1, flags=re.MULTILINE
        )
        if new_text == text and "status:" not in text:
            new_text = text.replace("---", "---\nstatus: distilled", 1)
        raw_path.write_text(new_text, encoding="utf-8")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Background job status file (Mode B)
# --------------------------------------------------------------------------- #
def _job_status_path(output_dir: Path) -> Path:
    return output_dir / "distill-jobs.json"


def _write_job_status(output_dir: Path, job_id: str, state: Dict[str, Any]) -> None:
    path = _job_status_path(output_dir)
    jobs: Dict[str, Any] = {}
    if path.exists():
        try:
            jobs = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            jobs = {}
    jobs[job_id] = state
    try:
        path.write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _background_run(
    raw_paths: List[Path],
    output_dir: Path,
    store: Any,
    job_id: str,
    note_type_override: Optional[str],
    related_modules_override: Optional[List[str]],
) -> None:
    import asyncio

    try:
        llm = _default_llm_from_env()
    except Exception as e:
        _write_job_status(output_dir, job_id, {
            "status": "error",
            "error": f"Failed to build LLM from env: {e}",
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        return

    async def _run() -> List[Dict[str, Any]]:
        results = []
        for p in raw_paths:
            _write_job_status(output_dir, job_id, {
                "status": "processing",
                "current": p.name,
                "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            res = await _distill_one(
                p, llm, output_dir, store, note_type_override, related_modules_override
            )
            results.append(res)
        return results

    try:
        results = asyncio.run(_run())
        _write_job_status(output_dir, job_id, {
            "status": "completed",
            "results": results,
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    except Exception as e:
        logger.exception("distill_conversation background job %s failed", job_id)
        _write_job_status(output_dir, job_id, {
            "status": "error",
            "error": str(e),
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })


# --------------------------------------------------------------------------- #
# Tool handler
# --------------------------------------------------------------------------- #
def handle_distill_conversation(
    arguments: Dict[str, Any],
    store: Any,
) -> str:
    """Distill one or more raw conversations into draft wiki notes.

    Arguments:
      - session_id / output_dir / repo_path: repowiki resolution.
      - raw_path / conversation_id (optional): target a single raw file; if
        omitted, all pending raw/conv-*.md files are distilled (batch).
      - llm (optional, Mode A): async callable ``llm(prompt, system) -> str``.
        Calling in this mode runs distillation inline (still in a thread per the
        server's mode="thread" dispatch) and returns the result JSON.
      - run_in_background (optional, Mode B): spawn a daemon thread that builds
        the LLM from MAIN_MODEL/LLM_BASE_URL/LLM_API_KEY and writes progress to
        repowiki/distill-jobs.json. Returns a job_id immediately.
      - note_type / related_modules (optional): force type/module for all notes.

    The tool is stateless: it never retains an LLM. Either ``llm`` or
    ``run_in_background`` must be supplied; neither means an error.
    """
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    if session is None and session_id:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    try:
        output_dir = _resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    note_type_ov = arguments.get("note_type")
    if note_type_ov and note_type_ov not in _VALID_NOTE_TYPES:
        return json.dumps({"error": f"Invalid note_type '{note_type_ov}'. {_NOTE_TYPE_HINT}"})
    related_ov = arguments.get("related_modules") or []

    # Resolve target raw files
    single = _resolve_raw_path(arguments, output_dir)
    from codewiki.src.config import RAW_DIR
    raw_dir = output_dir / RAW_DIR
    targets = [single] if single else _iter_raw_files(raw_dir)

    if not targets:
        return json.dumps({
            "status": "noop",
            "message": "No pending raw conversations to distill.",
            "distilled": [],
        })

    # Mode C (agent-driven): the host agent IS the LLM. Over MCP JSON the
    # caller cannot inject a callable (Mode A) and usually has no MAIN_MODEL
    # env (Mode B), so prepare hands out transcripts + system prompt and
    # submit runs the deterministic half on the agent's extraction results.
    mode = str(arguments.get("mode") or "auto").lower()
    if mode not in ("auto", "prepare", "submit"):
        return json.dumps({"error": f"Invalid mode '{mode}'. Expected one of: auto, prepare, submit."})

    if mode == "prepare":
        captures: List[Dict[str, Any]] = []
        for p in targets:
            built = _build_distill_input(p)
            if built is None:
                continue
            meta = built["meta"]
            captures.append({
                "conversation_id": p.stem,
                "path": str(p.relative_to(output_dir)) if _safe_rel(p, output_dir) else str(p),
                "captured_at": meta.get("captured_at", ""),
                "turn_count": meta.get("turn_count", ""),
                "link_to": meta.get("link_to", ""),
                "transcript": built["transcript"],
            })
        if not captures:
            return json.dumps({
                "status": "noop",
                "message": "No readable pending conversations.",
                "captures": [],
            })
        return json.dumps({
            "status": "prepared",
            "mode": "prepare",
            "system_prompt": _DISTILL_SYSTEM,
            "captures": captures,
            "next": (
                "Act as the LLM: apply system_prompt to each capture's transcript and "
                'produce one JSON object shaped {"notes": [{title, note_type, '
                "related_modules, tags, content}]} per capture. Then call "
                "distill_conversation again with mode='submit' and distilled="
                "{conversation_id: <that JSON>}."
            ),
        }, indent=2, ensure_ascii=False)

    if mode == "submit":
        distilled_map = arguments.get("distilled")
        if not isinstance(distilled_map, dict) or not distilled_map:
            return json.dumps({
                "error": (
                    "mode='submit' requires 'distilled': a mapping of conversation_id "
                    '(e.g. "conv-20260808T113515Z") to the extraction JSON shaped '
                    '{"notes": [...]}.'
                ),
            })
        results: List[Dict[str, Any]] = []
        for p in targets:
            key = p.stem  # e.g. "conv-20260808T113515Z"
            bare = key[len("conv-"):] if key.startswith("conv-") else key
            llm_output = distilled_map.get(key)
            if llm_output is None:
                llm_output = distilled_map.get(bare)
            if llm_output is None:
                # No extraction result for this capture: leave the raw file untouched.
                results.append({"raw_path": str(p), "conversation_id": key, "status": "missing_result"})
                continue
            if not isinstance(llm_output, str):
                llm_output = json.dumps(llm_output, ensure_ascii=False)
            res = _process_llm_output(p, llm_output, output_dir, store, note_type_ov, related_ov)
            res["conversation_id"] = key
            results.append(res)
        n_notes = sum(len(r.get("notes", [])) for r in results)
        return json.dumps({
            "status": "completed",
            "mode": "submit",
            "distilled": results,
            "raw_processed": len(results),
            "notes_created": n_notes,
        }, indent=2, ensure_ascii=False)

    # Mode B: background
    if arguments.get("run_in_background") and not arguments.get("llm"):
        job_id = "distill-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        _write_job_status(output_dir, job_id, {
            "status": "queued",
            "targets": [p.name for p in targets],
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        t = threading.Thread(
            target=_background_run,
            args=(targets, output_dir, store, job_id, note_type_ov, related_ov),
            daemon=True,
        )
        t.start()
        return json.dumps({
            "status": "queued",
            "job_id": job_id,
            "targets": len(targets),
            "poll": "Read repowiki/distill-jobs.json for progress, then confirm_note each draft.",
        }, indent=2, ensure_ascii=False)

    # Mode A: direct (llm injected)
    llm = arguments.get("llm")
    if not callable(llm):
        return json.dumps({
            "error": (
                "distill_conversation is stateless and requires an LLM. "
                "Pass 'llm' (async callable) for direct mode, or "
                "'run_in_background=true' to build one from MAIN_MODEL env."
            )
        })

    import asyncio

    async def _run_all() -> List[Dict[str, Any]]:
        results = []
        for p in targets:
            res = await _distill_one(p, llm, output_dir, store, note_type_ov, related_ov)
            results.append(res)
        return results

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    # If we're already inside a running loop (unlikely in thread dispatch), run via thread
    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(1) as ex:
            results = ex.submit(lambda: asyncio.run(_run_all())).result()
    else:
        results = loop.run_until_complete(_run_all())

    n_notes = sum(len(r.get("notes", [])) for r in results)
    return json.dumps({
        "status": "completed",
        "distilled": results,
        "raw_processed": len(results),
        "notes_created": n_notes,
    }, indent=2, ensure_ascii=False)
