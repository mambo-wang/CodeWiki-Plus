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

# note_type values accepted by ingest_note (see agents_md.py routing table).
# V4: single source of truth is the note_types declaration table
# (codewiki/mcp/tools/note_types.py) — the registry inputSchema enum and
# knowledge_loop promotion routing derive from the same table.
from codewiki.src.frontmatter import parse_frontmatter
from codewiki.mcp.tools.note_types import valid_note_types as _nt_valid

logger = logging.getLogger(__name__)

_VALID_NOTE_TYPES = _nt_valid()

# System prompt: instruct the LLM to emit one JSON object with a list of notes,
# each following OKF note shape (## sections, title, note_type, related_modules).
# P1: five extraction disciplines (borrowed from TAM work-mode L1 prompt) and
# the optional priority / scene fields were added to raise distillation quality.
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
    "EXTRACTION DISCIPLINES (mandatory):\n"
    "1. Self-contained: every note MUST be understandable outside this "
    "conversation. Include clear subject, object, conclusion or method; never "
    "use context-dependent references like 'this', 'that', 'mentioned above'.\n"
    "2. Accurate attribution: a suggestion or concern raised by someone is NOT "
    "a project decision. Only write a definitive conclusion when it was "
    "explicitly confirmed/adopted/verified; otherwise phrase it as 'under "
    "discussion' or 'pending confirmation'.\n"
    "3. Merge, don't fragment: strongly related turns about one conclusion "
    "must be merged into a single note; different topics/modules/methods stay "
    "separate.\n"
    "4. AI outputs: an assistant-generated plan or analysis is extractable only "
    "when the user adopted/confirmed it or it was validated in practice.\n"
    "5. Drop low value: greetings, one-shot requests ('just fix this formatting "
    "for now'), and anything obvious from the code must NOT be extracted.\n\n"
    "Return ONLY a single JSON object (no markdown fences) shaped exactly as:\n"
    "{\n"
    '  "notes": [\n'
    "    {\n"
    '      "title": "Short imperative/declarative title",\n'
    '      "note_type": "decision | lesson | pitfall | architecture | workaround",\n'
    '      "related_modules": ["module_slug"],\n'
    '      "tags": ["optional", "keywords"],\n'
    '      "priority": 85,\n'
    '      "scene": "optional short scene label, e.g. the work context this knowledge belongs to",\n'
    '      "content": "Full OKF note body in Markdown. Use H2 (##) sections such as '
    "## Background, ## Decision/正确做法, ## Rationale, ## Root cause, ## Recovery. "
    'Reuse exact names, paths, and code snippets from the conversation."\n'
    "    }\n"
    "  ],\n"
    '  "memories": [\n'
    '    "string",\n'
    '    "string"\n'
    "  ]\n"
    "}\n"
    "The optional 'priority' field is an integer 0-100: use 90-100 for core "
    "decisions / long-term constraints / critical pitfalls, 70-89 for generally "
    "reusable knowledge. Notes with priority below 70 are dropped by the "
    "system — when in doubt about a note's durable value, do not emit it at "
    "all. The optional 'scene' field labels the work context (e.g. the module "
    "or topic the discussion revolves around) and helps later consolidation.\n"
    'The "memories" array captures task-scoped progress knowledge: what was '
    "accomplished this session, what remains, decisions reached, and next-step "
    "context relevant to the *task at hand* (not general reusable wiki knowledge, "
    "which belongs in notes). Each entry is a concise 1-3 sentence Markdown string "
    "suitable for appending to a task memory log. Return [] when there is no "
    "task-scoped progress to record.\n"
    'If the conversation contains no durable knowledge, return {"notes": [], "memories": []}.'
)

_NOTE_TYPE_HINT = "Allowed note_type values: " + ", ".join(sorted(_VALID_NOTE_TYPES)) + "."

# Mode C (prepare) 遵循 file-side-channel：不通过 MCP stdio 内联完整 transcript
# 正文（多条大对话会撑满宿主 Agent 上下文）。每条 capture 只回传 full_path +
# 元数据 + 短 preview（初筛用）；正文走磁盘文件，由宿主 Agent 用
# read_file(full_path, offset, limit) 逐条读取、逐条蒸馏、逐条 submit 落盘。
_DEFAULT_PREVIEW_CHARS = 1500

# --------------------------------------------------------------------------- #
# 严格门（对齐 TAM shouldExtractL1）：L0 采集门之外的确定性质量过滤。
# 在 transcript 喂给 LLM 之前按行拦截，避免纯符号/纯问号等噪声进入蒸馏。
# --------------------------------------------------------------------------- #
# 已知角色前缀（_filter_transcript_lines 只剥前缀做判断，避免 content 内
# 含 ": " 时误切 role，如中文 "注意：xxx"）。
_ROLE_PREFIXES = ("user: ", "assistant: ")


def _should_extract_l1(line: str) -> bool:
    """严格门：长度/纯符号/纯问号过滤。不做 prompt-injection 校验（按需裁剪）。"""
    t = line.strip()
    if not t:
        return False
    # 纯符号/标点（1-5 字符，无字母/数字/CJK）。注：Python3 的 \w 默认
    # Unicode-aware，已匹配中文等 CJK 字符，故无需显式列出 CJK 码位范围。
    if re.fullmatch(r"[^\w\s]{1,5}", t):
        return False
    # 兜底：6+ 个纯问号（含全角/半角）不在上面 {1,5} 覆盖范围内。
    if re.fullmatch(r"[?？]+", t):
        return False
    return True


def _filter_transcript_lines(transcript: str) -> str:
    """按行应用严格门。行格式为 ``role: content`` 或纯 content 片段。

    只剥离已知 role 前缀（``user: ``/``assistant: ``）后再判断内容段，
    避免 content 本身含 ``": "``（如 "注意：xxx"）时误切；保留原行原样。
    """
    kept: List[str] = []
    for line in transcript.splitlines():
        content = line
        for prefix in _ROLE_PREFIXES:
            if line.startswith(prefix):
                content = line[len(prefix) :]
                break
        if _should_extract_l1(content):
            kept.append(line)
    return "\n".join(kept)


# Relevance score at/above which an existing note/ in notes/ is treated as a
# near-duplicate of a candidate draft (suppressed or merged instead of created).
_DEDUP_THRESHOLD = 0.6

# When the candidate title and an existing note title share this fraction of
# tokens (by Jaccard), it is a strong duplicate signal even at a slightly
# lower BM25 score.
_TITLE_SIMILARITY_THRESHOLD = 0.5

# --------------------------------------------------------------------------- #
# P1: priority gate + two-stage dedup constants.
# 设计见 docs/团队记忆融合-L2场景聚合与L3-Doctrine设计方案.md §4.1/§4.2：
#   - priority < _PRIORITY_MIN 的蒸馏笔记在 submit 时确定性丢弃（对齐 TAM
#     work 模式 "<70 直接丢弃" 分档）；
#   - 强重复信号（_find_existing_note 的 Jaccard 规则）沿用 dedup= 语义直接
#     判定，保持幂等；弱信号（标题相似度处于弱区间，或 BM25 召回命中）转为
#     conflict，交给宿主 agent 用 dedup_action 四操作（store/skip/update/merge）
#     裁决——agent 本身就是 LLM，精判零成本。
# --------------------------------------------------------------------------- #
_PRIORITY_MIN = 70  # below this value a distilled note is dropped
_PRIORITY_HIGH = 90  # >= maps to severity=high; 70-89 maps to medium
_CONFLICT_TITLE_FLOOR = 0.35  # weak-band lower bound for title Jaccard
_CONFLICT_BM25_FLOOR = 2.5  # BM25 recall score considered a conflict hint
_BM25_RECALL_TOPK = 3
_VALID_DEDUP_ACTIONS = ("store", "skip", "update", "merge")


# --------------------------------------------------------------------------- #
# Argument / path resolution
# --------------------------------------------------------------------------- #
def _resolve_output_dir(
    session: Optional[Any],
    arguments: Dict[str, Any],
) -> Path:
    from codewiki.mcp.tools.store_bridge import resolve_output_dir

    return resolve_output_dir(session, arguments)


def _load_distilled_file(arguments: Dict[str, Any], output_dir: Path) -> Optional[Dict[str, Any]]:
    """Load a distilled extraction mapping from a JSON file on disk (Mode C submit).

    File-side-channel counterpart of the prepare path: instead of inlining a
    large extracted JSON in the MCP ``distilled`` argument (which may exceed the
    transport limit for multi-note payloads), the host agent writes the JSON
    with ``write_to_file`` and passes only the small file path via
    ``distilled_file``. Accepted shapes:
      - mapping ``{conversation_id: {"notes": [...], "memories": [...]}}``;
      - a bare ``{"notes": [...], "memories": [...]}`` bound to the
        ``conversation_id`` argument (single-target submit).
    The staging file is deleted after a successful parse (one-shot
    consumption). Returns None when the file is absent/invalid (caller falls
    back to the inline ``distilled`` argument).
    """
    raw = str(arguments.get("distilled_file") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        cand = output_dir / p
        if cand.is_file():
            p = cand
        else:
            cand2 = Path.cwd() / p
            if cand2.is_file():
                p = cand2
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data:
        return None
    # One-shot consumption: the file is a staging artifact written by the host
    # agent; delete it once parsed so it never leaks into _iter_raw_files or
    # the search index. Matches the task_bindings one-shot-credential convention.
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass
    if "notes" in data or "memories" in data:
        # Bare extraction object — requires a single target conversation.
        cid = str(arguments.get("conversation_id") or "").strip()
        if not cid:
            return None
        key = cid if cid.startswith("conv-") else f"conv-{cid}"
        return {key: data}
    return data


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


def _friction_score_of(text: str) -> int:
    """Read the top-level ``friction_score:`` frontmatter value (0 when absent).

    Rides the same line-scan convention as ``status:``/``task_id:`` — capture
    writes the key via ``json.dumps`` so an int renders bare (no quotes).
    """
    m = re.search(r"^friction_score:\s*(-?\d+)", text, re.MULTILINE)
    if not m:
        return 0
    try:
        return int(m.group(1))
    except ValueError:
        return 0


def _iter_raw_files(raw_dir: Path) -> List[Path]:
    if not raw_dir.exists():
        return []
    files = [p for p in raw_dir.glob("conv-*.md")]
    # Only not-yet-distilled files, ordered by friction score DESC (K-line):
    # conversations with visible friction (corrections/interrupts/repeats) are
    # the most likely to yield valuable lesson notes, so they surface first in
    # the prepare listing. Missing friction_score (pre-K-line captures) → 0.
    scored = []
    for p in sorted(files):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        m = re.search(r"^status:\s*(\w+)", text, re.MULTILINE)
        if m and m.group(1) == "distilled":
            continue
        scored.append((_friction_score_of(text), p))
    scored.sort(key=lambda item: -item[0])
    return [p for _score, p in scored]


# --------------------------------------------------------------------------- #
# Frontmatter parsing helpers
# --------------------------------------------------------------------------- #
def _parse_frontmatter(path: Path) -> Dict[str, str]:
    """Read a page's frontmatter as a flat str->str mapping.

    Thin delegation to the frontmatter module's reader (architecture review
    2026-09, candidate #3): values are properly decoded there (json-encoded
    scalars lose their quotes, so ``task_id: "foo"`` never leaks a literal
    quote into routing keys — the bug ``_unquote_fm`` used to patch around).
    Non-string values (lists, dicts) are stringified for this flat view;
    callers that need structure should use ``parse_frontmatter`` directly.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    fm, _ = parse_frontmatter(text)
    return {
        k: v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        for k, v in fm.items()
    }


def _unquote_fm(value: str) -> str:
    """Kept for compatibility: values from ``_parse_frontmatter`` are already
    unquoted (json-decoded in the reader). Strips only stray wrapping quotes
    from values that predate the unified parser."""
    v = (value or "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return v
    return v


def _extract_turns(text: str) -> str:
    """Pull the transcript body after the frontmatter for LLM input."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            body = text[end + 4 :]
        else:
            body = text
    else:
        body = text
    body = body.strip()
    # Drop a leading "# Conversation Transcript" heading line if present
    if body.startswith("# Conversation Transcript"):
        body = body.split("\n", 1)[1].strip() if "\n" in body else ""
    # Defensive: strip any residual IDE-injected system context blocks
    # (<user_info>, <rules>, <git_status>, ...) so the LLM only sees the
    # human–AI dialogue. (capture_conversation should already have removed
    # these on ingest; this is a second safety net for older raw files.)
    from .capture_conversation import _strip_system_injection

    body = _strip_system_injection(body)
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
        # ingest_note writes the title JSON-quoted; unquote so Jaccard tokens
        # are not polluted by the surrounding quotes.
        title = _unquote_fm(fm.get("title", "")) or note_path.stem
        note_type = fm.get("type") or fm.get("note_type") or ""
        title_sim = _title_similarity(candidate_title, title)
        same_type = note_type == candidate_type
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

    # Team-layout Phase 2: read + merge + write all under the sidecar lock
    # (locked_rmw) — a read outside the lock could lose a concurrent
    # distillation's source_conversations entry.
    from codewiki.src.store import locked_rmw
    from codewiki.src.frontmatter import parse_frontmatter

    def _merge(text: str):
        if not text.startswith("---"):
            return None
        end = text.find("\n---", 3)
        if end == -1:
            return None
        block = text[3:end]
        m = re.search(r"^source_conversations:\s*\[(.*)\]", block, re.MULTILINE)
        if m:
            items = [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
            if new_source_ref in items:
                return None
            items.append(new_source_ref)
            new_list = "[" + ", ".join(f"'{x}'" for x in items) + "]"
            new_block = block[: m.start()] + "source_conversations: " + new_list + block[m.end() :]
        else:
            new_block = block.rstrip() + f"\nsource_conversations: ['{new_source_ref}']\n"
        return "---" + new_block + text[end:]

    try:
        locked_rmw(note_path, _merge)
    except OSError:
        pass


def _patch_note_origin(note_path: Path) -> None:
    """Add `origin: conversation` to a distilled draft note's frontmatter.

    This satisfies the T2 traceability requirement (every draft produced from a
    conversation must carry origin: conversation). The source_conversation
    reference is already stored via handle_ingest_note's source_ref field.
    """
    from codewiki.src.store import locked_rmw

    def _patch(text: str):
        if not text.startswith("---"):
            return None
        end = text.find("\n---", 3)
        if end == -1:
            return None
        block = text[3:end]
        if re.search(r"^origin:", block, re.MULTILINE):
            return None  # already present
        new_block = block.rstrip() + "\norigin: conversation\n"
        return "---" + new_block + text[end:]

    try:
        locked_rmw(note_path, _patch)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# P1 helpers: priority gate + two-stage dedup (recall stage & adjudication)
# --------------------------------------------------------------------------- #
def _parse_priority(value: Any) -> Optional[int]:
    """Clamp the optional distilled-note priority to an int in [0, 100].

    Returns None for missing/invalid values (treated as "unspecified": the
    note passes the gate without a severity mapping).
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        p = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(100, p))


def _bm25_recall_candidates(
    title: str,
    content: str,
    output_dir: Path,
) -> List[Dict[str, Any]]:
    """Two-stage dedup, recall stage: BM25 top-K similar existing notes.

    Reuses the existing zero-dependency wiki_search index (scope=notes) — no
    embeddings, per the project constraint. Best-effort: a missing index or a
    failed search yields [] so the draft falls back to title-similarity-only
    dedup instead of being blocked.
    """
    first_line = (content or "").strip().split("\n", 1)[0][:200]
    query = f"{title} {first_line}".strip()
    if not query:
        return []
    try:
        from codewiki.mcp.tools.wiki_search import search as _search

        hits = _search(
            output_dir,
            query,
            scope="notes",
            include_notes=True,
            max_results=_BM25_RECALL_TOPK,
            score_threshold=0.1,
            # Dedup is a similarity judgment, not a ranking one: exempt from
            # authority weighting so draft candidates can't sink below the
            # conflict floor just because they are unreviewed.
            apply_authority=False,
            # U1: retrieval popularity must not distort similarity either —
            # a hot note is not a more likely duplicate of this draft.
            apply_usage=False,
        )
    except Exception:  # index absent / search failure must never block distill
        return []
    out: List[Dict[str, Any]] = []
    for h in hits or []:
        score = float(h.get("relevance_score") or 0.0)
        if score < _CONFLICT_BM25_FLOOR:
            continue
        out.append(
            {
                "file": h.get("file", ""),
                "title": h.get("title", ""),
                "score": round(score, 3),
                "signal": "bm25",
            }
        )
    return out


def _find_weak_conflicts(
    candidate_title: str,
    candidate_content: str,
    candidate_type: str,
    output_dir: Path,
) -> List[Dict[str, Any]]:
    """Detect WEAK duplicate signals that warrant agent adjudication.

    Strong duplicates are already handled by ``_find_existing_note`` (and keep
    the legacy dedup= semantics for idempotent re-distillation). This function
    only returns the weak band: title similarity in
    [_CONFLICT_TITLE_FLOOR, strong-threshold) plus BM25 recall hits. An empty
    list means "no conflict — ingest directly".
    """
    candidates: List[Dict[str, Any]] = []
    notes_dir = output_dir / "notes"
    if notes_dir.is_dir():
        for note_path in notes_dir.glob("*.md"):
            try:
                fm = _parse_frontmatter(note_path)
            except Exception:
                continue
            title = _unquote_fm(fm.get("title", "")) or note_path.stem
            note_type = fm.get("type") or fm.get("note_type") or ""
            sim = _title_similarity(candidate_title, title)
            if sim < _CONFLICT_TITLE_FLOOR:
                continue
            same_type = note_type == candidate_type
            is_strong = (
                sim >= _DEDUP_THRESHOLD
                or (sim >= _DEDUP_THRESHOLD * 0.8 and same_type)
                or (sim >= _TITLE_SIMILARITY_THRESHOLD and same_type)
            )
            if is_strong:
                continue  # handled by _find_existing_note, not a "conflict"
            rel = str(note_path.relative_to(output_dir))
            candidates.append(
                {
                    "file": rel,
                    "title": title,
                    "score": round(sim, 3),
                    "signal": "title_sim",
                }
            )
    for hit in _bm25_recall_candidates(candidate_title, candidate_content, output_dir):
        if hit.get("file") and not any(c["file"] == hit["file"] for c in candidates):
            candidates.append(hit)
    return candidates[:5]


def _union_fm_list(
    head: str,
    key: str,
    from_text: str = "",
) -> str:
    """V6: union a frontmatter inline-list field with extra values.

    ``tags`` pulls nothing extra (caller-managed); ``related_modules`` unions
    module-ish tokens found in *from_text* (the merged draft's content) so the
    merged note keeps both sides' scope. Values already present are not
    duplicated; missing field ⇒ nothing to union ⇒ head returned unchanged.
    Inline ``key: [a, b]`` format is preserved.
    """
    m = re.search(rf"^[ 	]*{key}:\s*\[(.*?)\]\s*$", head, re.MULTILINE)
    if not m:
        return head
    existing = [v.strip().strip("'\"") for v in m.group(1).split(",") if v.strip()]
    extras: List[str] = []
    if key == "related_modules" and from_text:
        # module-ish tokens: backticked names or [[wikilinks]] in the draft
        for tok in re.findall(r"`([\w\-\.]+)`", from_text):
            if tok not in extras:
                extras.append(tok)
    merged: List[str] = list(existing)
    for e in extras:
        if e not in merged:
            merged.append(e)
    if merged == existing:
        return head
    line = f"{key}: [" + ", ".join(f'"{v}"' for v in merged) + "]"
    return head[: m.start()] + line + head[m.end() :]


def _apply_dedup_action(
    action: str,
    target: str,
    title: str,
    content: str,
    raw_rel: str,
    output_dir: Path,
) -> Dict[str, Any]:
    """Execute an agent-adjudicated update/merge action on the target note.

    - update: the draft supersedes the target — replace the body, keep the
      frontmatter (bumps generated.at), append provenance.
    - merge: complementary knowledge — append the draft as a new H2 section at
      the end of the target body, accumulate source_conversations.
    Returns {"status": ..., "target": rel-or-None}.
    """
    if action not in ("update", "merge"):
        return {"status": "invalid_action", "target": None}
    if not target:
        return {"status": "target_required", "target": None}
    note_path = (output_dir / target) if not Path(target).is_absolute() else Path(target)
    if not note_path.is_file():
        return {"status": "target_not_found", "target": target}

    # Team-layout Phase 2: read + adjudicated rewrite under the sidecar lock
    # (locked_rmw) — the dedup adjudication must not race another writer.
    from codewiki.src.store import locked_rmw

    def _rewrite(text: str):
        head, body = "", text
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                head, body = text[: end + 4], text[end + 4 :]

        if action == "update":
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            new_head = re.sub(
                r"(generated:\s*\{[^}]*at:\s*)\d{4}-\d{2}-\d{2}T[\d:]+Z",
                lambda m: m.group(1) + now,
                head,
                count=1,
            )
            return new_head + "\n\n" + content.strip() + "\n"
        # merge: V6 (note_merge 字段策略) — merge 不再是裸 H2 追加：frontmatter
        # 的 tags / related_modules 按策略并集（union），正文追加段带来源标记。
        # 策略从 note_types 权威表读（默认 union/append），借的是 OpenViking
        # merge_op 的字段粒度，闸门语义不变（合并结果仍是既有笔记的更新）。
        try:
            from codewiki.mcp.tools.note_types import merge_fields_for

            _fm_type = re.search(r"^(?:type|note_type):\s*(\S+)", head, re.MULTILINE)
            strategies = merge_fields_for(_fm_type.group(1) if _fm_type else "general")
        except Exception:
            strategies = {
                "body": "append",
                "tags": "union",
                "related_modules": "union",
                "title": "replace",
            }
        # tags union 在此场景无增量来源（draft 无 frontmatter，tags 在落盘
        # 时才生成）。related_modules 恒取 union：merge-into-target 是互补
        # 知识合并，双方 scope 都要保留——表的 replace 策略只属于
        # note_merge 多条对等 draft 的合并场景，语义不同。
        head = _union_fm_list(head, "related_modules", from_text=content)
        body_md = body.strip()
        marker = f"> 合并自蒸馏候选：{title}\n\n" if strategies.get("body") == "append" else ""
        section = f"\n\n## {title}\n\n{marker}{content.strip()}\n"
        return head + ("\n\n" + body_md if body_md else "") + section

    try:
        result_text = locked_rmw(note_path, _rewrite)
        if result_text is None:
            return {"status": "write_failed", "target": target}
    except OSError:
        return {"status": "write_failed", "target": target}
    # Provenance: accumulate the raw conversation that fed this change.
    if raw_rel:
        _merge_source_into_note(target, raw_rel, output_dir)
    # Refresh the BM25 index entry for the modified note.
    try:
        from codewiki.mcp.tools.wiki_search import update_file

        update_file(output_dir, note_path, session=None)
    except Exception as e:  # indexing is best-effort; never block distillation
        logger.warning("search index refresh failed after %s: %s", action, e)
    rel = str(note_path.relative_to(output_dir)) if _safe_rel(note_path, output_dir) else target
    return {"status": "updated" if action == "update" else "merged", "target": rel}


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
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return []
        else:
            return []
    notes = data.get("notes", []) if isinstance(data, dict) else []
    if not isinstance(notes, list):
        return []
    return notes


def _parse_llm_memories(raw_llm_output: str) -> List[str]:
    """Parse the LLM JSON output into a list of task-memory strings; best-effort."""
    text = raw_llm_output.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return []
        else:
            return []
    memories = data.get("memories", []) if isinstance(data, dict) else []
    if not isinstance(memories, list):
        return []
    return [str(m).strip() for m in memories if str(m).strip()]


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
    # 严格门：喂 LLM 前滤掉纯符号/纯问号噪声行，提升蒸馏信噪比
    # （对齐 TAM shouldExtractL1 —— 门控做在 LLM 调用之前）。
    filtered = _filter_transcript_lines(transcript)
    if not filtered:
        return None
    transcript = filtered

    link_to = _unquote_fm(meta.get("link_to", ""))
    task_id = _unquote_fm(meta.get("task_id", ""))
    prompt = (
        f"Conversation transcript (link_to={link_to or 'none'}, task_id={task_id or 'none'}):\n\n"
        f"{transcript}\n\n"
        f"{_NOTE_TYPE_HINT}\n"
        "Extract durable knowledge as JSON (notes + memories)."
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
    conflict_policy: str = "auto_suppress",
    drop_raw: bool = False,
) -> Dict[str, Any]:
    """Deterministic half of distillation.

    Takes the already-produced LLM JSON (from an injected LLM in modes A/B, or
    from the host agent itself in mode C ``submit``) and runs: parse →
    priority gate (P1: drop <70) → dedup against notes/ → ingest draft notes
    → mark/delete the raw file → rebuild the search index.

    P1 two-stage dedup: STRONG duplicates (title Jaccard band) keep the legacy
    ``dedup=`` semantics so re-distillation stays idempotent. WEAK conflicts
    (title similarity in the weak band, or BM25 recall hits) are held for agent
    adjudication when ``conflict_policy="hold"`` (Mode C): the note is not
    ingested, candidates are reported, and the raw file stays pending until the
    agent re-submits with a per-note ``dedup_action``
    (store/skip/update/merge). With ``conflict_policy="auto_suppress"``
    (modes A/B, no agent to interact with) weak conflicts fall back to the
    legacy suppress behaviour.
    """
    from codewiki.mcp.tools.knowledge_loop import handle_ingest_note

    meta = _parse_frontmatter(raw_path)
    link_to = _unquote_fm(meta.get("link_to", ""))
    task_id = _unquote_fm(meta.get("task_id", ""))

    notes = _parse_llm_notes(llm_output)
    produced: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []
    unresolved_conflicts = 0
    # Traceability: source_conversation points at the raw file (relative to repowiki)
    raw_rel = (
        str(raw_path.relative_to(output_dir)) if _safe_rel(raw_path, output_dir) else str(raw_path)
    )
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

        # --- P1: priority gate — low-value notes are deterministically dropped
        # (对齐 TAM work 模式 "<70 直接丢弃" 分档；LLM 侧已在 prompt 中要求
        # 宁缺毋滥，这里是确定性兜底)。
        priority = _parse_priority(note.get("priority"))
        if priority is not None and priority < _PRIORITY_MIN:
            produced.append(
                {
                    "title": title,
                    "note_type": note_type,
                    "priority": priority,
                    "status": "low_priority",
                }
            )
            continue

        # --- P1: two-stage dedup, second submit — agent adjudication actions.
        action = str(note.get("dedup_action") or "").strip().lower()
        if action not in _VALID_DEDUP_ACTIONS:
            action = ""
        if action == "skip":
            produced.append(
                {
                    "title": title,
                    "note_type": note_type,
                    "status": "skipped",
                }
            )
            continue
        if action in ("update", "merge"):
            applied = _apply_dedup_action(
                action,
                str(note.get("target") or ""),
                title,
                content,
                raw_rel,
                output_dir,
            )
            produced.append(
                {
                    "title": title,
                    "note_type": note_type,
                    "target": applied.get("target"),
                    "status": applied["status"],
                }
            )
            continue

        # --- T3/P1 de-duplicate against existing notes/ before creating a draft.
        # action == "store" skips dedup entirely (agent forced creation).
        if action != "store":
            existing = _find_existing_note(title, note_type, output_dir, store)
            if existing is not None:
                # STRONG duplicate: keep the legacy dedup= semantics (suppress
                # by default, provenance-only merge when dedup="merge") so
                # repeated distillation stays idempotent.
                existing_file = existing.get("file", "")
                if dedup == "merge":
                    _merge_source_into_note(existing_file, raw_rel, output_dir)
                    produced.append(
                        {
                            "title": title,
                            "note_type": note_type,
                            "merged_into": existing_file,
                            "status": "merged",
                        }
                    )
                else:  # suppress (default): drop the duplicate draft
                    produced.append(
                        {
                            "title": title,
                            "note_type": note_type,
                            "duplicate_of": existing_file,
                            "status": "suppressed",
                        }
                    )
                continue
            weak = _find_weak_conflicts(title, content, note_type, output_dir)
            if weak:
                if conflict_policy == "hold":
                    # WEAK conflict (Mode C): do NOT ingest yet — report the
                    # candidates and wait for a re-submit carrying dedup_action.
                    entry = {
                        "title": title,
                        "note_type": note_type,
                        "status": "conflict",
                        "candidates": weak,
                    }
                    produced.append(entry)
                    conflicts.append(entry)
                    unresolved_conflicts += 1
                    continue
                # Modes A/B: no agent to adjudicate — fall back to suppress
                # (legacy behaviour), but surface the candidates for auditing.
                produced.append(
                    {
                        "title": title,
                        "note_type": note_type,
                        "status": "suppressed",
                        "fallback": "auto_suppress",
                        "candidates": weak,
                    }
                )
                continue

        ingest_args = {
            "output_dir": str(output_dir),
            "title": title,
            "note_type": note_type,
            "content": content,
            "related_modules": related,
            "tags": note.get("tags", []),
            "status": "draft",
            "source_ref": raw_rel,  # traceability: source_conversation
        }
        # P1: priority → severity mapping (severity already carries a 2x BM25
        # boost in the search index, so high-value notes surface more readily).
        if priority is not None:
            ingest_args["severity"] = "high" if priority >= _PRIORITY_HIGH else "medium"
        # P1: scene label → metadata.scene (grouping hint for future L2
        # consolidation).
        scene = str(note.get("scene") or "").strip()
        if scene:
            ingest_args["scene"] = scene
        # Route the note to its task so get_task_context / query_wiki(task_id=...)
        # can surface task-scoped knowledge. Omitted for taskless conversations.
        if task_id:
            ingest_args["task_id"] = task_id
        result = json.loads(handle_ingest_note(ingest_args, store))
        note_file = result.get("note_path") or result.get("note_file")
        # Add origin: conversation to the draft note frontmatter (traceability)
        if note_file:
            _patch_note_origin(Path(note_file))
        produced.append(
            {
                "title": title,
                "note_type": note_type,
                "note_file": note_file,
                "status": result.get("status", "unknown"),
            }
        )

    # Task-memory dual track: route the LLM's task-scoped "memories" DIRECTLY
    # into the task's memories.md (timestamp-headed entries, atomic append) —
    # no confirm gate (ADR-0002: task-scoped progress knowledge carries
    # bounded noise cost; the gate stays for notes, which enter the shared,
    # retrieval-indexed knowledge base). Only meaningful when the raw file
    # carries a task_id. Ghost task_id (task deleted after capture) is
    # tolerated — the writer skips silently.
    memories = _parse_llm_memories(llm_output) if task_id else []
    memories_written = 0
    if task_id and memories:
        from codewiki.mcp.tools.task_manager import append_task_memories_direct

        memories_written = append_task_memories_direct(output_dir, task_id, memories)

    # Mark raw as distilled, then apply the retention policy (L0 archive):
    #   drop_raw (argument or frontmatter) -> delete (explicit privacy opt-out)
    #   produced knowledge OR keep_raw     -> archive into conversations/ and
    #                                         repoint note source_ref links
    #   no_knowledge without keep_raw      -> delete (noise; the staging area
    #                                         is not a warehouse)
    # Weak conflicts still pending keep the raw in raw/ untouched so the second
    # submit can re-read it.
    from codewiki.src.config import RAW_DIR

    raw_dir = output_dir / RAW_DIR
    keep_raw = str(meta.get("keep_raw", "false")).lower() == "true"
    if not drop_raw:
        drop_raw = str(meta.get("drop_raw", "false")).lower() == "true"
    deleted = False
    archived_to: Optional[str] = None
    if unresolved_conflicts == 0:
        _mark_distilled(raw_path)
        produced_knowledge = bool(produced) or bool(memories_written)
        if drop_raw:
            try:
                raw_path.unlink()
                deleted = True
            except OSError:
                pass
        elif produced_knowledge or keep_raw:
            # L0 archive: retained for provenance. Link-only layer — never
            # indexed; reached via note source_ref (设计方案 §9 链接优先)。
            archived_to = _archive_raw(raw_path, output_dir)
            if archived_to:
                _rewrite_source_refs_after_archive(output_dir, raw_path.name, archived_to)
        else:
            # no_knowledge noise: clean up so it doesn't linger.
            try:
                raw_path.unlink()
                deleted = True
            except OSError:
                pass
        # Keep the raw-dir index (used by capture_conversation) in sync: the
        # entry leaves raw/ both when deleted and when archived.
        try:
            _sync_raw_index_on_distill(raw_dir, raw_path, deleted or bool(archived_to))
        except Exception:  # best-effort; never block distillation
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

    if unresolved_conflicts:
        file_status = "conflicts_pending"
    else:
        file_status = "completed" if (produced or memories_written) else "no_knowledge"
    ret: Dict[str, Any] = {
        "raw_path": str(raw_path),
        "status": file_status,
        "notes_created": len(produced),
        "notes": produced,
        "distilled": produced,
        "memories_written": memories_written,
        "task_id": task_id or None,
        "deleted_raw": deleted,
        "archived_raw": archived_to,
        "keep_raw": keep_raw,
    }
    if conflicts:
        ret["conflicts"] = conflicts
        ret["conflict_next"] = (
            "Weak duplicate candidates were found for the note(s) listed in "
            "'conflicts'. Read each candidate note, then re-submit the SAME "
            "conversation with a per-note 'dedup_action': "
            "'store' (genuinely new knowledge, force create) | "
            "'skip' (the existing note is better, drop this draft) | "
            "'update' (same fact, newer version wins: set 'target' to the "
            "candidate file, its body will be replaced) | "
            "'merge' (complementary: appended as a new section into 'target'). "
            "Notes already ingested in the first pass need not be included again."
        )
    return ret


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
        raw_path,
        llm_output,
        output_dir,
        store,
        note_type_override,
        related_modules_override,
        dedup,
    )


def _mark_distilled(raw_path: Path) -> None:
    # Team-layout Phase 2: regex status flip under the sidecar lock
    from codewiki.src.store import locked_rmw

    def _flip(text: str):
        new_text = re.sub(r"^status:\s*\w+", "status: distilled", text, count=1, flags=re.MULTILINE)
        if new_text == text and "status:" not in text:
            new_text = text.replace("---", "---\nstatus: distilled", 1)
        return new_text

    try:
        locked_rmw(raw_path, _flip)
    except OSError:
        pass


def _sync_raw_index_on_distill(raw_dir: Path, raw_path: Path, deleted: bool) -> None:
    """Keep repowiki/raw/.index.json consistent after distillation.

    Delegates to ``KnowledgeStore.sync_raw_index`` — the store owns the index
    format + atomic write; this wrapper only adapts the distill call shape
    (raw_dir + raw_path + deleted flag) to it. Best-effort: a failed index
    update must never block or fail distillation.
    """
    from codewiki.src.store import KnowledgeStore

    KnowledgeStore(raw_dir.parent).sync_raw_index(raw_path.name, removed=deleted)


# --------------------------------------------------------------------------- #
# L0 archive (team-memory fusion): distilled conversations are retained for
# provenance instead of deleted. Design decision (链接优先、零索引):
#   - archive lives in repowiki/conversations/ (flat, permanent);
#   - it is NOT indexed for BM25 search — discovery is link-only, agents reach
#     a conversation by following the distilled note's source_ref;
#   - raw/ stays the pending staging queue (capture scans never see archives).
# --------------------------------------------------------------------------- #
def _archive_raw(raw_path: Path, output_dir: Path) -> Optional[str]:
    """Move a distilled raw transcript into conversations/ (L0 archive).

    Returns the archive path relative to output_dir (forward slashes), or None
    when the move failed (the file then stays in raw/ marked distilled —
    graceful degradation, provenance simply keeps pointing at raw/).
    """
    import shutil
    from codewiki.src.config import CONVERSATIONS_DIR

    arch_dir = Path(output_dir) / CONVERSATIONS_DIR
    try:
        arch_dir.mkdir(parents=True, exist_ok=True)
        dest = arch_dir / raw_path.name
        if dest.exists():
            # Defensive: same name already archived (e.g. re-captured slug).
            import hashlib

            digest = hashlib.sha1(
                (raw_path.name + str(raw_path.stat().st_size)).encode()
            ).hexdigest()[:6]
            dest = arch_dir / f"{raw_path.stem}-{digest}.md"
        shutil.move(str(raw_path), str(dest))
        return f"{CONVERSATIONS_DIR}/{dest.name}".replace("\\", "/")
    except OSError as e:
        logger.warning("L0 archive failed for %s: %s", raw_path, e)
        return None


def _rewrite_source_refs_after_archive(output_dir: Path, raw_name: str, archive_rel: str) -> int:
    """Repoint note source_ref from raw/<name> to the archived location.

    Scans notes/ (bounded) rather than only this run's produced files, so
    multi-round conflict submits converge: notes produced in an earlier round
    (before the raw was finally archived) get repointed too.
    """
    from codewiki.src.config import NOTES_DIR

    notes_dir = Path(output_dir) / NOTES_DIR
    if not notes_dir.is_dir():
        return 0
    # Frontmatter stores the ref JSON-escaped, so the separator may appear as
    # '/' or one/two backslashes in the raw file text.
    pattern = re.compile(r"raw[/\\]+" + re.escape(raw_name))
    target = archive_rel.replace("\\", "/")
    updated = 0
    for p in notes_dir.glob("*.md"):
        # Team-layout Phase 2: read + repoint under the sidecar lock
        from codewiki.src.store import locked_rmw

        def _repoint(text: str):
            if raw_name not in text:
                return None
            new_text = pattern.sub(target, text)
            return new_text if new_text != text else None

        try:
            if locked_rmw(p, _repoint) is not None:
                updated += 1
        except OSError:
            continue
    return updated


# --------------------------------------------------------------------------- #
# Background job status file (Mode B)
# --------------------------------------------------------------------------- #
def _job_status_path(output_dir: Path) -> Path:
    return output_dir / "distill-jobs.json"


def _write_job_status(output_dir: Path, job_id: str, state: Dict[str, Any]) -> None:
    path = _job_status_path(output_dir)

    # Team-layout Phase 2: Mode B background jobs from multiple processes
    # must not lose each other's state entries — the JSON read-modify-write
    # (read + merge + write) runs entirely under the sidecar lock.
    from codewiki.src.store import locked_rmw

    def _merge_state(text: str):
        try:
            jobs = json.loads(text)
            if not isinstance(jobs, dict):
                raise ValueError("not a mapping")
        except (json.JSONDecodeError, ValueError):
            jobs = {}
        jobs[job_id] = state
        return json.dumps(jobs, indent=2, ensure_ascii=False)

    try:
        locked_rmw(path, _merge_state)
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
        _write_job_status(
            output_dir,
            job_id,
            {
                "status": "error",
                "error": f"Failed to build LLM from env: {e}",
                "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        return

    async def _run() -> List[Dict[str, Any]]:
        results = []
        for p in raw_paths:
            _write_job_status(
                output_dir,
                job_id,
                {
                    "status": "processing",
                    "current": p.name,
                    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
            res = await _distill_one(
                p, llm, output_dir, store, note_type_override, related_modules_override
            )
            results.append(res)
        return results

    try:
        results = asyncio.run(_run())
        _write_job_status(
            output_dir,
            job_id,
            {
                "status": "completed",
                "results": results,
                "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
    except Exception as e:
        logger.exception("distill_conversation background job %s failed", job_id)
        _write_job_status(
            output_dir,
            job_id,
            {
                "status": "error",
                "error": str(e),
                "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )


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
      - task_id (optional): only distill pending raws bound to this task
        (sessionStart catch-up path). Applies to prepare/submit/batch/Mode B.
        If nothing pending belongs to the task, returns status="noop".
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

    # Optional task scope: only distill raws bound to the given task. This is
    # the sessionStart catch-up path — after binding a task, the agent calls
    # distill_conversation(mode="prepare", task_id=<bound task>) to clear only
    # that task's backlog. The filter sits on `targets`, so it applies
    # uniformly to prepare/submit/batch/Mode B. Task membership comes from
    # pending_raws_by_task (index-first, frontmatter fallback) — the same
    # source of truth get_task_context uses for pending_raw_count.
    task_filter = str(arguments.get("task_id") or "").strip()
    if task_filter:
        from codewiki.mcp.tools.capture_conversation import pending_raws_by_task

        allowed = {
            str((raw_dir / e["relpath"]).resolve())
            for e in pending_raws_by_task(output_dir).get(task_filter, [])
        }
        targets = [t for t in targets if str(t.resolve()) in allowed]
        if not targets:
            return json.dumps(
                {
                    "status": "noop",
                    "task_id": task_filter,
                    "message": (
                        f"No pending (un-distilled) conversations bound to task "
                        f"'{task_filter}'. Nothing to distill."
                    ),
                    "distilled": [],
                },
                ensure_ascii=False,
            )

    if not targets:
        return json.dumps(
            {
                "status": "noop",
                "message": "No pending raw conversations to distill.",
                "distilled": [],
            }
        )

    # Mode C (agent-driven): the host agent IS the LLM. Over MCP JSON the
    # caller cannot inject a callable (Mode A) and usually has no MAIN_MODEL
    # env (Mode B), so prepare hands out transcripts + system prompt and
    # submit runs the deterministic half on the agent's extraction results.
    mode = str(arguments.get("mode") or "auto").lower()
    if mode not in ("auto", "prepare", "submit"):
        return json.dumps(
            {"error": f"Invalid mode '{mode}'. Expected one of: auto, prepare, submit."}
        )

    if mode == "prepare":
        preview_chars = int(arguments.get("preview_chars") or _DEFAULT_PREVIEW_CHARS)
        captures: List[Dict[str, Any]] = []
        for p in targets:
            built = _build_distill_input(p)
            if built is None:
                continue
            meta = built["meta"]
            try:
                friction_score = int(str(meta.get("friction_score", "")).strip() or 0)
            except (TypeError, ValueError):
                friction_score = 0
            # V6: 库内相关笔记预给——对 capture 预览跑一次 BM25（authority/
            # usage 豁免，相似度导向），提取时即可参照已有笔记，减少 submit
            # 后的冲突往返（new vs 引用已有，agent 提前判断）。
            related_notes: List[Dict[str, Any]] = []
            try:
                related_notes = [
                    {
                        "file": h.get("file", ""),
                        "title": h.get("title", ""),
                        "score": h.get("score", 0),
                    }
                    for h in _bm25_recall_candidates(
                        p.stem, built["transcript"][:2000], output_dir
                    )[:3]
                ]
            except Exception as e:  # neighbour recall must never block prepare
                logger.debug("related_notes recall skipped: %s", e)
            captures.append(
                {
                    "conversation_id": p.stem,
                    "path": str(p.relative_to(output_dir)) if _safe_rel(p, output_dir) else str(p),
                    # file-side-channel：正文走磁盘，这里只给绝对路径。
                    "full_path": str(p.resolve()),
                    "transcript_chars": len(built["transcript"]),
                    "captured_at": meta.get("captured_at", ""),
                    "turn_count": meta.get("turn_count", ""),
                    "link_to": _unquote_fm(meta.get("link_to", "")),
                    "task_id": _unquote_fm(meta.get("task_id", "")),
                    # K-line: friction score for distillation prioritisation. The
                    # listing itself is already friction-DESC via _iter_raw_files.
                    "friction_score": friction_score,
                    # V6: 提取前即可见的库内近邻（无则空列表）。
                    **({"related_notes": related_notes} if related_notes else {}),
                    # 短预览仅用于初筛（这条对话有没有可蒸馏的知识），不是完整正文。
                    "preview": built["transcript"][:preview_chars],
                }
            )
        if not captures:
            return json.dumps(
                {
                    "status": "noop",
                    "message": "No readable pending conversations.",
                    "captures": [],
                }
            )
        ret: Dict[str, Any] = {
            "status": "prepared",
            "mode": "prepare",
            "system_prompt": _DISTILL_SYSTEM,
            "captures": captures,
            "next": (
                "Process captures ONE AT A TIME — do NOT read all transcripts at once "
                "(that would overflow your host context). For each capture: "
                "(1) read the FULL transcript with read_file(filePath=full_path), in "
                "offset/limit chunks if large (transcript_chars is the total size; "
                "preview is only a taster for deciding whether to skip); "
                "(2) apply system_prompt to it and produce ONE JSON object shaped "
                '{"notes": [{title, note_type, related_modules, tags, content, '
                'priority?, scene?}], "memories": [string]} — priority is 0-100 '
                "(notes below 70 are dropped by the tool, so only emit notes worth "
                "keeping); scene is a short work-context label; "
                "(3) immediately persist it with mode='submit' and distilled="
                "{conversation_id: <that JSON>} so it lands on disk; "
                "(4) if the submit response reports conflicts_pending, read the "
                "listed candidate notes and re-submit the same conversation with a "
                "per-note dedup_action (store|skip|update|merge, see conflict_next); "
                "(5) only then move to the next capture, dropping the previous "
                "transcript from working memory. Note: captures may carry "
                "related_notes (V6) — existing notes the transcript touches; "
                "prefer extending/referencing them over emitting a near-duplicate."
            ),
        }
        # K-line hint (additive key — existing consumers unaffected). Only
        # surfaced when at least one pending conversation shows friction.
        if any(c.get("friction_score", 0) >= 20 for c in captures):
            ret["friction_hint"] = (
                "提示：friction_score ≥ 20 的会话含明显摩擦信号（纠正/打断/重复），"
                "优先蒸馏更可能产出有价值的经验笔记（清单已按 friction_score 降序排列）。"
            )
        return json.dumps(ret, indent=2, ensure_ascii=False)

    if mode == "submit":
        # Mode C submit 双通道：大载荷走 distilled_file（file-side-channel，
        # 与 prepare 的 full_path 对称），小载荷仍可直接内联 distilled。
        # 两者可同时提供（file 为基座、内联覆盖同 key）；显式内联优先。
        distilled_map = arguments.get("distilled")
        file_map = _load_distilled_file(arguments, output_dir)
        if file_map is not None:
            if not isinstance(distilled_map, dict):
                distilled_map = {}
            distilled_map = {**file_map, **(distilled_map or {})}
        if not isinstance(distilled_map, dict) or not distilled_map:
            return json.dumps(
                {
                    "error": (
                        "mode='submit' requires 'distilled' or 'distilled_file': a "
                        'mapping of conversation_id (e.g. "conv-20260808T113515Z") to '
                        'the extraction JSON shaped {"notes": [...]}. For large '
                        "payloads, write the extraction JSON to a file first (write_to_file) "
                        "and pass only the path via 'distilled_file'."
                    ),
                }
            )
        results: List[Dict[str, Any]] = []
        for p in targets:
            key = p.stem  # e.g. "conv-20260808T113515Z"
            bare = key[len("conv-") :] if key.startswith("conv-") else key
            llm_output = distilled_map.get(key)
            if llm_output is None:
                llm_output = distilled_map.get(bare)
            if llm_output is None:
                # No extraction result for this capture: leave the raw file untouched.
                results.append(
                    {"raw_path": str(p), "conversation_id": key, "status": "missing_result"}
                )
                continue
            if not isinstance(llm_output, str):
                llm_output = json.dumps(llm_output, ensure_ascii=False)
            # P1: Mode C 启用两段式去重——弱冲突笔记挂起等待 agent 用
            # dedup_action 裁决（agent 即 LLM，精判零成本）；raw 文件在全部
            # 裁决完成前保留，不标记 distilled。
            res = _process_llm_output(
                p,
                llm_output,
                output_dir,
                store,
                note_type_ov,
                related_ov,
                conflict_policy="hold",
                drop_raw=bool(arguments.get("drop_raw", False)),
            )
            res["conversation_id"] = key
            results.append(res)
        n_notes = sum(len(r.get("notes", [])) for r in results)
        n_conflicts = sum(len(r.get("conflicts", [])) for r in results)
        ret: Dict[str, Any] = {
            "status": "completed",
            "mode": "submit",
            "distilled": results,
            "raw_processed": len(results),
            "notes_created": n_notes,
            "conflicts_pending": n_conflicts,
        }
        # Phase 4 second slice: submit is a batch boundary → auto-push when
        # enabled and gated (D17). Best-effort, never blocks the result.
        try:
            from codewiki.src.git_sync import auto_push

            _push = auto_push(output_dir, "distill_submit")
            if _push:
                ret["git_sync"] = _push
        except Exception as e:
            logger.debug("auto_push skipped: %s", e)
        return json.dumps(ret, indent=2, ensure_ascii=False)

    # Mode B: background
    if arguments.get("run_in_background") and not arguments.get("llm"):
        job_id = "distill-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        _write_job_status(
            output_dir,
            job_id,
            {
                "status": "queued",
                "targets": [p.name for p in targets],
                "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        t = threading.Thread(
            target=_background_run,
            args=(targets, output_dir, store, job_id, note_type_ov, related_ov),
            daemon=True,
        )
        t.start()
        return json.dumps(
            {
                "status": "queued",
                "job_id": job_id,
                "targets": len(targets),
                "poll": "Read repowiki/distill-jobs.json for progress, then confirm_note each draft.",
            },
            indent=2,
            ensure_ascii=False,
        )

    # Mode A: direct (llm injected)
    llm = arguments.get("llm")
    if not callable(llm):
        return json.dumps(
            {
                "error": (
                    "distill_conversation is stateless and requires an LLM. "
                    "Pass 'llm' (async callable) for direct mode, or "
                    "'run_in_background=true' to build one from MAIN_MODEL env."
                )
            }
        )

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
    return json.dumps(
        {
            "status": "completed",
            "distilled": results,
            "raw_processed": len(results),
            "notes_created": n_notes,
        },
        indent=2,
        ensure_ascii=False,
    )
