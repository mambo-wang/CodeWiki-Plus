"""MCP tool: capture_conversation — store a raw conversation transcript.

capture_conversation is the *ingest* half of the team-memory fusion loop
(spec: SPEC-conversation-to-wiki.md, ticket T1). It accepts a structured
conversation object (turns with role/content), resolves the target
repowiki, and writes it as a markdown file into ``repowiki/raw/``.

Design constraints (must hold):
  - The raw/ staging area is NOT indexed by query_wiki; it is a transient
    holding pen for conversations awaiting async distillation by
    distill_conversation.
  - capture_conversation is synchronous and cheap: it only persists raw
    text. No LLM is involved here.
  - Deduplication is by content hash (sha256) of the transcript so the
    same conversation captured twice does not create two files.
  - link_to (optional) records what wiki object the conversation relates to.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from codewiki.mcp.session import SessionState, SessionStore
from codewiki.mcp.tools.friction import format_friction_signals, score_friction
from codewiki.src.store import _MAX_SLUG_LEN  # noqa: F401 (re-exported for tests)

logger = logging.getLogger(__name__)

# 顶层系统注入标签：IDE 会把整个系统上下文（user_info / rules / git_status /
# project_context / additional_data 等）作为 user message 的 content 传入。
# 这些块对知识蒸馏无价值，应在落盘前剥离。
_SYSTEM_INJECTION_TAGS = frozenset(
    {
        "user_info",
        "rules",
        "memories",
        "git_status",
        "project_context",
        "project_guidance",
        "project_layout",
        "additional_data",
        "content_policy",
        "communication",
        "tool_calling",
        "maximize_context_understanding",
        "maximize_parallel_tool_calls",
        "automations",
        "inline_line_numbers",
        "agent_skills",
        "response_language",
        # IDE 每次 user 消息注入的"避免循环"提醒块，纯系统提示，无知识价值
        "system_reminder",
        # AskUserQuestion 结构化问答序列化（应用 UI 交互记录，非用户知识）
        "question_answer",
        "questions",
        "question_item",
    }
)
# 形如 <tag> ... </tag> 的成对块（含可能跨行的多行内容）。
# 注意：不锚定行首——IDE 常把块包在 "user: <user_info> ... </user_info>"
# 之类的行内，行首并非 '<'。
_BLOCK_RE = re.compile(
    r"<(?P<name>[A-Za-z_][\w-]*)>(?P<inner>(?:(?!</(?P=name)>).)*)</(?P=name)>",
    re.DOTALL,
)
# 形如 <tag .../> 或 <tag ...> 的单行自闭合/起始标签（无配对闭合块时按行剥离）
_SELF_RE = re.compile(
    r"^[ \t]*<(?P<name>[A-Za-z_][\w-]*)(?:\s[^>\n]*)?/?>[ \t]*$",
    re.MULTILINE,
)
# 捕获块内部纯文本（去壳），用于 <user_query> 这类应保留的对话内容
_INNER_RE = re.compile(r"<(?P<name>[A-Za-z_][\w-]*)>(?P<inner>(?:(?!</(?P=name)>).)*)</(?P=name)>")


def _strip_system_injection(text: str) -> str:
    """剥离 IDE 注入到 user message 中的系统上下文噪声块。

    - 已知的系统注入标签（``<user_info>``、``<rules>``、``<git_status>``、
      ``<project_context>``、``<additional_data>`` 等）整体删除。
    - ``<user_query>`` 是真正的用户对话，去掉外壳标签、保留内部文本。
    - 多行残留的孤立起始/自闭合标签（无配对闭合块时）也按行清除。
    - 清理 ``user: `` 这类因块被删而留下的空角色前缀行。
    """
    if not text:
        return text

    def _remove_block(m: "re.Match[str]") -> str:
        name = m.group("name").lower()
        if name in _SYSTEM_INJECTION_TAGS:
            return ""
        if name == "user_query":
            # 保留真实用户文本，仅去壳
            return m.group("inner").strip()
        return m.group(0)

    cleaned = _BLOCK_RE.sub(_remove_block, text)

    def _remove_self(m: "re.Match[str]") -> str:
        return "" if m.group("name").lower() in _SYSTEM_INJECTION_TAGS else m.group(0)

    cleaned = _SELF_RE.sub(_remove_self, cleaned)

    # 删除 "user: " 后跟空白/换行的空角色行（块被删后残留）
    cleaned = re.sub(r"^\s*user:\s*$\n?", "", cleaned, flags=re.MULTILINE)
    # 压缩因剥离产生的连续空行（>1 个空行 → 1 个空行），并去除首尾空白
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# --------------------------------------------------------------------------- #
# Filename slug
# --------------------------------------------------------------------------- #
# Built from the first user message so archived files mirror the conversation
# title shown in the IDE. Delegates to the shared store implementation.
def _slugify(text: str) -> str:
    """Turn arbitrary text into a filesystem-safe, human-readable slug.

    Returns "" when nothing usable remains (caller then falls back to a
    timestamp-based name). Thin re-export of ``store.slugify`` — kept here for
    the modules (task_manager) that import it from this module.
    """
    from codewiki.src.store import slugify

    return slugify(text)


def _first_user_text(turns: List[Dict[str, str]]) -> str:
    """Extract the first user turn's text content for use as a filename."""
    for t in turns:
        if t.get("role") != "user":
            continue
        content = t.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            return " ".join(p for p in parts if p)
    return ""


# --------------------------------------------------------------------------- #
# Output directory resolution (mirrors source_ingest.py)
# --------------------------------------------------------------------------- #
def _resolve_output_dir(
    session: Optional[SessionState],
    arguments: Dict[str, Any],
) -> Path:
    """Resolve the repowiki output directory (see store_bridge.resolve_output_dir).

    Resolution order:
      1. An active session's ``output_dir`` (a fully-resolved repowiki path).
      2. An explicit ``output_dir`` argument.
      3. ``repo_path``/repowiki fallback.

    Thin re-export of the unified bridge — kept here for the modules
    (task_manager) and tests that import it from this module.
    """
    from codewiki.mcp.tools.store_bridge import resolve_output_dir

    return resolve_output_dir(session, arguments)


# --------------------------------------------------------------------------- #
# Transcript extraction
# --------------------------------------------------------------------------- #
# Only user/assistant turns are archived. Everything else (system prompts,
# tool_use/tool_result, thinking/reasoning blocks) is dropped so the raw file
# captures the human–AI dialogue only.
_KEEP_ROLES = {"user", "assistant"}

# 框架级结构噪声（宽松门 _should_capture_l0 用）：这些消息不携带对话内容，
# 只是 session/工具链自己产生的占位文本。落盘前滤掉，避免污染 raw 与 content_hash。
_FRAMEWORK_NOISE = frozenset(
    {
        "(session bootstrap)",
        "NO_REPLY",
    }
)
_FRAMEWORK_NOISE_PREFIXES = (
    "A new session was started via",
    "Pre-compaction memory flush",
)


def _should_capture_l0(content: str) -> bool:
    """宽松门：只滤结构噪声，保证据链完整。质量门（长度/符号）留给蒸馏侧。"""
    t = content.strip()
    if not t:
        return False
    if t in _FRAMEWORK_NOISE:
        return False
    if t.startswith(_FRAMEWORK_NOISE_PREFIXES):
        return False
    return True


# Content-block types that carry internal monologue / tool plumbing rather than
# user-facing assistant text. Skipped even when nested inside a content array.
_NOISE_BLOCK_TYPES = {
    "thinking",
    "reasoning",
    "thought",
    "tool_use",
    "tool_result",
    "tool_call",
    "function_call",
    "function_result",
    "system",
    "system_prompt",
    "context",
}


def _content_blocks_text(content: Any) -> Any:
    """If ``content`` is a list of content blocks (Claude/CodeBuddy format),
    flatten to the concatenated text of user/assistant-facing blocks only,
    dropping thinking/tool/system blocks. Otherwise return it unchanged.
    """
    if not isinstance(content, list):
        return content
    texts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            if isinstance(block, str):
                texts.append(block)
            continue
        btype = block.get("type")
        if btype in _NOISE_BLOCK_TYPES:
            continue
        if btype == "text":
            text = block.get("text")
            if isinstance(text, str):
                texts.append(text)
        elif btype is None:
            text = block.get("text") or block.get("content")
            if isinstance(text, str):
                texts.append(text)
    return "\n".join(t for t in texts if t).strip() or content


def _extract_transcript(conversation: Any) -> List[Dict[str, str]]:
    """Normalize the conversation argument into a flat list of turns.

    Accepts either:
      - a list of {"role": ..., "content": ...} dicts, or
      - a dict with a "turns" key containing such a list.

    Returns a list of {"role": str, "content": str}. Missing/invalid items
    are skipped rather than raising, so a partial capture still persists.

    Only user/assistant dialogue is kept; system, tool and thinking/reasoning
    blocks are dropped so the archived raw file stays noise-free.
    """
    raw_turns: Any = conversation
    if isinstance(conversation, dict):
        raw_turns = conversation.get("turns", conversation.get("conversation", []))
    if not isinstance(raw_turns, list):
        return []

    turns: List[Dict[str, str]] = []
    for item in raw_turns:
        if not isinstance(item, dict):
            continue
        role = item.get("role") or item.get("speaker")
        if role not in _KEEP_ROLES:
            continue
        content = _content_blocks_text(
            item.get("content") or item.get("message") or item.get("text")
        )
        if content is None or content == "":
            continue
        content = str(content)
        # User turns may carry IDE-injected system context (<user_info>, <rules>,
        # <git_status>, <project_context>, <additional_data>, ...). Strip those
        # blocks so the archived transcript holds the human–AI dialogue only.
        if role == "user":
            content = _strip_system_injection(content)
        # 宽松门（对齐 TAM shouldCaptureL0）：统一处理空内容（剥离系统注入后
        # 可能变空）与框架级结构噪声，保证据链完整；更严格的质量过滤由
        # 蒸馏侧 should_extract_l1 承担。
        if not _should_capture_l0(content):
            continue
        turns.append({"role": str(role), "content": content})
    return turns


def pending_raws_by_task(output_dir: Path) -> Dict[str, List[Dict[str, str]]]:
    """Aggregate pending (not-yet-distilled) raw conversations by task_id.

    Shared read-only helper — the single source of truth for "which raw files
    still need distillation, grouped by task". Consumers:

    - ``distill_conversation``: task-scoped catch-up distillation (its
      ``task_id`` filter across prepare/submit/batch/Mode B).
    - ``task_manager.handle_get_task_context``: ``pending_raw_count`` — the
      deterministic trigger signal telling the agent that catch-up distillation
      is needed for the bound task.

    Resolution is **index-first**: ``raw/.index.json`` (maintained by
    ``handle_capture_conversation``) gives O(1) per-file task_id/status without
    opening the file. Files missing from the index (legacy captures or a failed
    index write) fall back to a frontmatter peek, mirroring
    ``distill_conversation._iter_raw_files`` semantics (``status != distilled``).

    Returns ``task_id -> [{"relpath", "task_id", "captured_at"}]``; entries
    without a task_id are grouped under the empty-string key. Never raises —
    any read failure degrades to "no pending raws" for that file.

    Thin re-export of ``KnowledgeStore.pending_raws_by_task`` — kept here for
    the modules (task_manager / distill_conversation) that import it from this
    module.
    """
    from codewiki.src.store import KnowledgeStore

    return KnowledgeStore(output_dir).pending_raws_by_task()


# --------------------------------------------------------------------------- #
# Tool handler
# --------------------------------------------------------------------------- #
def handle_capture_conversation(
    arguments: Dict[str, Any],
    store: SessionStore,
) -> str:
    """Persist a raw conversation transcript into repowiki/raw/.

    Arguments:
      - session_id (optional): active session id.
      - output_dir / repo_path (optional): repowiki resolution fallback.
      - conversation (required): list of turns or {"turns": [...]} object.
      - link_to (optional): wiki object id/title this conversation relates to.
      - source_session_id (optional): the IDE-side session id (e.g. CodeBuddy's
        session_id carried by SessionEnd / PreCompact / Stop hook events).
        Distinct from session_id (the active MCP session). Re-capturing the
        same source session replaces its pending raw file instead of piling
        up incremental transcripts.
      - keep_raw (optional, bool, default False): hint for distill_conversation
        to retain the raw file after distillation. Stored as metadata only.
      - task_id (optional): id of the task this conversation is bound to. Stored
        as metadata and participates in dedup hashing so the same conversation
        under different tasks is preserved separately.

    Returns a JSON status object.
    """
    session_id = arguments.get("session_id")
    session = store.get(session_id) if session_id else None
    if session is None and session_id:
        return json.dumps({"error": f"Session {session_id} not found or expired."})

    try:
        output_dir = _resolve_output_dir(session, arguments)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    conversation = arguments.get("conversation")
    if not conversation:
        return json.dumps({"error": "conversation is required (list of turns or {turns: [...]})."})

    # Phase 4 second slice: session-start ff-only pull on the FIRST write
    # path this process touches (capture is the earliest knowledge write in
    # the hook-driven flow). Once per process; gated on D17; never raises.
    try:
        from codewiki.src.git_sync import session_ff_only

        _pull = session_ff_only(output_dir)
    except Exception as e:
        logger.debug("session_ff_only skipped: %s", e)
        _pull = None

    turns = _extract_transcript(conversation)
    if not turns:
        return json.dumps({"error": "conversation contained no usable turns."})

    link_to = str(arguments.get("link_to") or "")
    keep_raw = bool(arguments.get("keep_raw", False))
    source_session_id = str(arguments.get("source_session_id") or "")
    task_id = str(arguments.get("task_id") or "")

    # Friction scoring (K-line): pure-function signal detection on the already
    # filtered dialogue turns. The score only feeds frontmatter metadata + the
    # returned JSON; it never gates the capture itself.
    friction = score_friction(turns)

    from codewiki.src.store import KnowledgeStore

    result = KnowledgeStore(output_dir).capture_raw(
        turns,
        source_session_id=source_session_id,
        task_id=task_id,
        link_to=link_to,
        keep_raw=keep_raw,
        metadata={
            "friction_score": friction["score"],
            "friction_signals": format_friction_signals(friction["signals"]),
        },
        transcript_title=_first_user_text(turns),
    )

    kind = result["kind"]
    if kind == "error":
        return json.dumps({"error": result.get("error", "Failed to write conversation file.")})

    content_hash = result["content_hash"]

    if kind == "duplicate":
        return json.dumps(
            {
                "status": "duplicate",
                "content_hash": content_hash[:24] + "...",
                "stored_at": result["relpath"],
                "message": "Identical conversation already captured; skipped.",
            },
            indent=2,
            ensure_ascii=False,
        )

    superseded = kind == "superseded"

    # Adoption extraction (P1 A-line): parse ``codewiki:referenced-docs``
    # declarations from assistant turns and persist them into the per-user
    # telemetry event stream. Zero-IO fast path when nothing was declared.
    from codewiki.mcp.tools.adoption import (
        extract_adopted_docs,
        looks_like_search_happened,
        record_adoption_events,
    )

    adopted_docs = extract_adopted_docs(turns, existing=lambda rel: (output_dir / rel).exists())
    adoption_inserted = 0
    if adopted_docs:
        # capture_key (T2): namespaced by user_id so the same session id on
        # two machines never collides. Manual captures without an id fall back
        # to the content hash so an identical re-capture stays idempotent while
        # a changed transcript counts its new claims.
        from codewiki.src.config import user_id

        capture_key = f"{user_id()}/{source_session_id or f'hash-{content_hash[:24]}'}"
        adoption_inserted = record_adoption_events(
            output_dir,
            capture_key,
            adopted_docs,
            result["captured_at"][:10],
        )
    adoption_nudge = bool(not adopted_docs and looks_like_search_happened(turns))

    logger.info(
        "%s conversation at %s (%d turns)",
        "Superseded" if superseded else "Captured",
        result["relpath"],
        len(turns),
    )

    # Phase 4 second slice: capture is a batch boundary → auto-push when
    # enabled and gated (D17). Best-effort, never blocks the capture result.
    git_sync_info = None
    try:
        from codewiki.src.git_sync import auto_push

        git_sync_info = auto_push(output_dir, "capture_conversation")
    except Exception as e:
        logger.debug("auto_push skipped: %s", e)

    # session_ff_only outcome (from the entry hook above) rides the same
    # result key so the conversation sees both sync directions at once.
    if _pull:
        git_sync_info = _pull if not git_sync_info else f"{git_sync_info} {_pull}"

    return json.dumps(
        {
            "status": "captured",
            "conversation_id": result["conversation_id"],
            "stored_at": result["relpath"],
            "turn_count": result["turn_count"],
            "content_hash": content_hash[:24] + "...",
            "link_to": link_to,
            "source_session": source_session_id,
            "superseded": superseded,
            "keep_raw": keep_raw,
            "task_id": result["task_id"],
            "task_source": result["task_source"],
            # K-line friction readout (hook may print it to the IDE log).
            "friction": friction,
            # Phase 4: push outcome (present only when auto_push ran)
            **({"git_sync": git_sync_info} if git_sync_info else {}),
            # P1 A-line adoption readout: declared docs (persisted to
            # adoption_events) + a one-shot nudge when search traces exist but
            # nothing was declared.
            **({"adopted_docs": adopted_docs} if adopted_docs else {}),
            **({"adoption_inserted": adoption_inserted} if adopted_docs else {}),
            **({"adoption_nudge": True} if adoption_nudge else {}),
        },
        indent=2,
        ensure_ascii=False,
    )
