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

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from codewiki.mcp.session import SessionState, SessionStore
from codewiki.mcp.tools.friction import format_friction_signals, score_friction

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
# title shown in the IDE. Windows-reserved + generic filesystem-unsafe chars.
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Collapse runs of separators into a single dash.
_MULTI_DASH = re.compile(r"-{2,}")
# Max slug length (keeps filenames readable and well under OS limits).
_MAX_SLUG_LEN = 60


def _slugify(text: str) -> str:
    """Turn arbitrary text into a filesystem-safe, human-readable slug.

    Returns "" when nothing usable remains (caller then falls back to a
    timestamp-based name).
    """
    text = text.strip()
    if not text:
        return ""
    # Replace unsafe chars with a dash separator.
    slug = _UNSAFE_CHARS.sub("-", text)
    # Collapse whitespace runs into a single dash.
    slug = re.sub(r"\s+", "-", slug)
    slug = _MULTI_DASH.sub("-", slug).strip("-")
    if not slug:
        return ""
    # Truncate (Python str is unicode → slicing at char boundary is safe).
    if len(slug) > _MAX_SLUG_LEN:
        slug = slug[:_MAX_SLUG_LEN].rstrip("-")
    return slug


def _resolve_task_from_binding(output_dir: Path, source_session_id: str) -> str:
    """Read repowiki/.meta/task_bindings/<session>.json and return its task_id.

    路径约定必须与 task_manager._bindings_dir() 保持一致
    （output_dir / ".meta" / "task_bindings"）。此处不能 import task_manager，
    因为它反向 import 了本模块的 _resolve_output_dir / _slugify（循环依赖），
    所以目录名在这里有意重复一份。

    绑定文件缺失/损坏/无 task_id 时返回 ""（视为无任务对话）。
    """
    try:
        binding = output_dir / ".meta" / "task_bindings" / f"{source_session_id}.json"
        if not binding.exists():
            return ""
        data = json.loads(binding.read_text(encoding="utf-8"))
        return str(data.get("task_id") or "").strip()
    except (json.JSONDecodeError, OSError, TypeError):
        return ""


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
    """Resolve the repowiki output directory from session or arguments.

    Resolution order:
      1. An active session's ``output_dir`` (a fully-resolved repowiki path).
      2. An explicit ``output_dir`` argument.
      3. ``repo_path``/repowiki fallback.
    """
    if session:
        return Path(session.output_dir).expanduser().resolve()
    od = arguments.get("output_dir")
    if od:
        return Path(od).expanduser().resolve()
    rp = arguments.get("repo_path")
    if rp:
        # Layout-aware (ticket 07): centralized members capture into the
        # workspace-root shared area; everything else keeps <repo>/repowiki.
        from codewiki.mcp.tools.workspace_layout import default_output_dir

        return default_output_dir(Path(rp).expanduser().resolve())
    raise ValueError("output_dir or repo_path is required (or pass an active session).")


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


def _transcript_text(turns: List[Dict[str, str]]) -> str:
    """Render turns to a plain-text transcript for hashing and fallback body."""
    lines = []
    for t in turns:
        lines.append(f"{t['role']}: {t['content']}")
    return "\n".join(lines)


def _content_hash(turns: List[Dict[str, str]], linked: str, task_id: str = "") -> str:
    # task_id participates in the hash so the *same* conversation captured under
    # two different tasks is NOT deduplicated away — the task binding is part of
    # what makes a capture distinct.
    payload = json.dumps(
        {"turns": turns, "link_to": linked, "task_id": task_id},
        ensure_ascii=False,
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Raw-dir index (avoids scanning every conv-*.md on every capture)
# --------------------------------------------------------------------------- #
# repowiki/raw/ can accumulate many pending files when the hook is enabled but
# distillation is never run. The previous dedup/supersede logic read EVERY
# conv-*.md (full file text) on each capture, so capture time grew linearly
# with the backlog. We instead keep a small sidecar index of metadata so
# capture stays O(1) regardless of backlog size. The index is a best-effort
# cache: if it is missing or stale we fall back to scanning (and rebuild it).
_INDEX_NAME = ".index.json"


def _read_index(raw_dir: Path) -> Optional[Dict[str, Any]]:
    """Load the raw-dir index, or None if absent/corrupt."""
    idx = raw_dir / _INDEX_NAME
    if not idx.is_file():
        return None
    try:
        return json.loads(idx.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_index(raw_dir: Path, index: Dict[str, Any]) -> None:
    """Atomically rewrite the index (temp file + rename) so a crash mid-write
    cannot leave a truncated index behind."""
    idx = raw_dir / _INDEX_NAME
    tmp = raw_dir / (".index.tmp." + str(os.getpid()))
    try:
        tmp.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, idx)
    except OSError:
        # Best-effort: a failed index update must never break the capture.
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _rebuild_index(raw_dir: Path) -> Dict[str, Any]:
    """Scan existing conv-*.md files and rebuild the index from their frontmatter.
    Used when the index is missing (e.g. raw files created before this feature)
    or when a lookup misses and we suspect it is stale."""
    files: List[Dict[str, str]] = []
    for existing in sorted(raw_dir.glob("conv-*.md")):
        try:
            text = existing.read_text(encoding="utf-8")
        except OSError:
            continue
        ch = _unq(_peek_frontmatter(text, "content_hash"))
        ss = _unq(_peek_frontmatter(text, "source_session"))
        st = _unq(_peek_frontmatter(text, "status") or "pending")
        tk = _unq(_peek_frontmatter(text, "task_id"))
        ca = _unq(_peek_frontmatter(text, "captured_at"))
        if not ch:
            continue
        files.append(
            {
                "relpath": existing.name,
                "content_hash": ch,
                "source_session": ss,
                "status": st,
                "task_id": tk,
                "captured_at": ca,
            }
        )
    return {"files": files}


def _peek_frontmatter(text: str, key: str) -> str:
    """Extract a `key: value` line from a markdown frontmatter block (cheap,
    single-pass, no regex over the whole body)."""
    marker = f"{key}:"
    for line in text.splitlines():
        if line.startswith(marker):
            return line[len(marker) :].strip()
    return ""


def _unq(v: str) -> str:
    """Strip surrounding single/double quotes from a frontmatter value."""
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'" else v


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
    """
    from codewiki.src.config import RAW_DIR

    raw_dir = output_dir / RAW_DIR
    if not raw_dir.is_dir():
        return {}

    index = _read_index(raw_dir)
    indexed: Dict[str, dict] = {}
    if isinstance(index, dict):
        for e in index.get("files", []):
            if isinstance(e, dict) and e.get("relpath"):
                indexed[str(e["relpath"])] = e

    by_task: Dict[str, List[Dict[str, str]]] = {}
    try:
        candidates = sorted(raw_dir.glob("conv-*.md"))
    except OSError:
        return {}
    for p in candidates:
        if not p.is_file():
            continue
        entry = indexed.get(p.name)
        if entry is not None:
            if _unq(str(entry.get("status") or "pending")) == "distilled":
                continue
            task_id = _unq(str(entry.get("task_id") or ""))
            captured_at = _unq(str(entry.get("captured_at") or ""))
        else:
            # Not indexed — peek frontmatter directly.
            try:
                text = p.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            if _unq(_peek_frontmatter(text, "status") or "pending") == "distilled":
                continue
            task_id = _unq(_peek_frontmatter(text, "task_id"))
            captured_at = _unq(_peek_frontmatter(text, "captured_at"))
        by_task.setdefault(task_id, []).append(
            {
                "relpath": p.name,
                "task_id": task_id,
                "captured_at": captured_at,
            }
        )
    return by_task


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

    turns = _extract_transcript(conversation)
    if not turns:
        return json.dumps({"error": "conversation contained no usable turns."})

    link_to = arguments.get("link_to", "")
    if link_to is None:
        link_to = ""
    link_to = str(link_to)

    keep_raw = bool(arguments.get("keep_raw", False))

    source_session_id = str(arguments.get("source_session_id") or "")

    task_id = str(arguments.get("task_id") or "")
    task_source = "argument" if task_id else ""
    # 回退：未显式传入 task_id 时，按 source_session_id 反查会话绑定文件，
    # 让 set_session_task 建立的绑定真正生效。此前绑定文件从不被消费，
    # 导致「绑定成功但 raw 仍无 task_id」的断链。显式 task_id 永远优先。
    if not task_id and source_session_id:
        task_id = _resolve_task_from_binding(output_dir, source_session_id)
        if task_id:
            task_source = "binding"

    content_hash = _content_hash(turns, link_to, task_id)

    # Ensure repowiki/raw/ exists
    from codewiki.src.config import RAW_DIR

    raw_dir = output_dir / RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Deduplicate / session-supersede using the raw-dir index (O(1) lookup)
    # instead of scanning and reading every conv-*.md. Falls back to a full
    # scan + index rebuild if the index is missing or a lookup misses (keeps
    # behaviour correct for raw files created before this feature existed).
    index = _read_index(raw_dir)
    if index is None:
        # Backwards-compat: existing raw dir without an index → rebuild once.
        index = _rebuild_index(raw_dir)

    def _find_in_index(find_hash: str, find_session: str):
        """Return (duplicate_relpath, supersede_relpath) from the index."""
        dup = None
        sup = None
        for entry in index.get("files", []):
            if entry.get("content_hash") == find_hash:
                dup = entry.get("relpath")
                break
            if (
                find_session
                and entry.get("source_session") == find_session
                and entry.get("status") == "pending"
            ):
                sup = entry.get("relpath")
        return dup, sup

    dup_rel, sup_rel = _find_in_index(content_hash, source_session_id)
    # If the index missed a content_hash match we *know* should exist (e.g. it
    # is stale), rebuild from disk and re-check once before giving up.
    if dup_rel is None and sup_rel is None:
        rebuilt = _rebuild_index(raw_dir)
        if len(rebuilt.get("files", [])) != len(index.get("files", [])):
            index = rebuilt
            dup_rel, sup_rel = _find_in_index(content_hash, source_session_id)

    if dup_rel is not None:
        existing = raw_dir / dup_rel
        return json.dumps(
            {
                "status": "duplicate",
                "content_hash": content_hash[:24] + "...",
                "stored_at": str(existing.relative_to(output_dir)),
                "message": "Identical conversation already captured; skipped.",
            },
            indent=2,
            ensure_ascii=False,
        )

    # Session-scoped supersede: Stop fires every turn and PreCompact can fire
    # mid-session, so the same IDE session is captured repeatedly with a
    # growing transcript. Each capture is a superset of the previous one —
    # replace that session's still-pending raw file instead of accumulating
    # incremental copies. Distilled / keep_raw files are left untouched.
    superseded = False
    dest_path: Optional[Path] = None
    if sup_rel is not None:
        dest_path = raw_dir / sup_rel
        superseded = True
        # 绑定文件在首次成功捕获后即被删除（一次性消费凭证）。若同一会话
        # 再次捕获（supersede）时已解析不到 task_id，从被替换的旧 entry
        # 继承 task_id，避免覆盖后归属丢失。task_id 参与 content_hash，
        # 继承后需重算，保证索引与去重一致。
        if not task_id:
            for _entry in index.get("files", []):
                if _entry.get("relpath") == sup_rel:
                    inherited = str(_entry.get("task_id") or "").strip()
                    if inherited:
                        task_id = inherited
                        task_source = "binding-inherited"
                        content_hash = _content_hash(turns, link_to, task_id)
                    break

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    if dest_path is None:
        # Filename is derived from the first user message so archived files
        # read like the conversation title shown in the IDE (e.g.
        # ``conv-review最近一次提交.md``). Falls back to the timestamp when no
        # usable user text is present.
        slug = _slugify(_first_user_text(turns))
        if slug:
            base = f"conv-{slug}"
            dest_path = raw_dir / f"{base}.md"
            # Collision guard: same opening sentence captured twice or a slug
            # clashing with an existing file → append an index suffix.
            n = 2
            while dest_path.exists():
                dest_path = raw_dir / f"{base}-{n}.md"
                n += 1
        else:
            safe_link = "".join(c if c.isalnum() else "-" for c in link_to)[:40]
            fname = f"conv-{stamp}{('-' + safe_link) if safe_link else ''}.md"
            dest_path = raw_dir / fname
            if dest_path.exists():
                dest_path = raw_dir / f"conv-{stamp}-{int(now.timestamp() * 1000) % 100000}.md"

    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        from codewiki.src.config import actor_id

        actor = actor_id()
    except Exception:
        actor = "codewiki"

    body = _transcript_text(turns)
    # Friction scoring (K-line): pure-function signal detection on the already
    # filtered dialogue turns. Default config on purpose — capture must stay
    # lightweight (no schema.yaml reads here). The score only feeds frontmatter
    # metadata + the returned JSON; it never gates the capture itself.
    friction = score_friction(turns)
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
        # two machines never collides. Manual captures without an id fall
        # back to the content hash so an identical re-capture stays
        # idempotent while a changed transcript counts its new claims.
        from codewiki.src.config import user_id

        capture_key = f"{user_id()}/{source_session_id or f'hash-{content_hash[:24]}'}"
        adoption_inserted = record_adoption_events(
            output_dir,
            capture_key,
            adopted_docs,
            now.strftime("%Y-%m-%d"),
        )
    adoption_nudge = bool(not adopted_docs and looks_like_search_happened(turns))
    meta = {
        "captured_at": now_iso,
        "content_hash": content_hash,
        "turn_count": len(turns),
        "link_to": link_to,
        "source_session": source_session_id,
        "keep_raw": keep_raw,
        # K-line friction signals: top-level single-line keys so the stdlib-only
        # line scanners (distill_conversation / session-start hook) can read
        # them back. A 0 score is written too — "no friction" is information.
        # Values use the comma+equals format, YAML-special-char free.
        "friction_score": friction["score"],
        "friction_signals": format_friction_signals(friction["signals"]),
    }
    # task_id must stay top-level (like source_session) so distill_conversation's
    # simple line parser can read it back; only add when present to avoid an
    # empty ``task_id: `` line on taskless captures.
    if task_id:
        meta["task_id"] = task_id
    from codewiki.src.frontmatter import inject_okf_frontmatter

    content = inject_okf_frontmatter(
        "# Conversation Transcript\n\n" + body + "\n",
        type_="Conversation",
        title="conversation " + stamp,
        output_dir=output_dir,
        status="pending",
        stale_days=90,  # raw/ 暂存文件 90 天足够长，蒸馏必然在此之前消费
        # 蒸馏流程用简单行解析读取这些字段（_parse_frontmatter / ^status:），
        # 必须保持顶层，折叠进 metadata 会破坏蒸馏。
        top_level_extra=meta,
        actor=actor,
        now_iso=now_iso,
    )

    try:
        dest_path.write_text(content, encoding="utf-8")
    except OSError as e:
        return json.dumps({"error": f"Failed to write conversation file: {e}"})

    # Maintain the raw-dir index so future captures stay O(1). On a supersede
    # we update the existing entry (same relpath) rather than appending.
    entries = list(index.get("files", []))
    new_entry = {
        "relpath": dest_path.name,
        "content_hash": content_hash,
        "source_session": source_session_id,
        "status": "pending",
        "task_id": task_id,
        # captured_at is consumed by pending_raws_by_task() → get_task_context
        # so the backlog listing can show when each capture happened without
        # opening the raw file.
        "captured_at": now_iso,
    }
    if superseded:
        for i, e in enumerate(entries):
            if e.get("relpath") == dest_path.name:
                entries[i] = new_entry
                break
    else:
        entries.append(new_entry)
    _write_index(raw_dir, {"files": entries})

    # One-shot binding consumption: a session binding (repowiki/.meta/
    # task_bindings/<source_session_id>.json) exists only to route this
    # session's captures to a task. Once the raw file has been written
    # successfully, the binding has served its purpose — delete it so
    # task_bindings/ does not accumulate stale records for ended sessions.
    # Only delete when the task_id actually came from the binding file
    # (task_source == "binding"); explicit task_id arguments and inherited
    # supersede ids must not touch it. Missing/undelettable files are fine:
    # a failed cleanup must never block the capture itself.
    if task_source == "binding" and source_session_id:
        _binding_path = output_dir / ".meta" / "task_bindings" / f"{source_session_id}.json"
        try:
            _binding_path.unlink(missing_ok=True)
        except OSError:
            pass  # non-fatal: stale binding files are cosmetic only

    # NOTE: deliberately no append_log() here. Raw capture is transient (the
    # file is deleted after distillation), and the hook fires on every session
    # end — logging each capture would leave permanent log.md entries pointing
    # at files that no longer exist. Note creation is logged by ingest_note
    # during distillation instead.

    logger.info(
        "%s conversation at %s (%d turns)",
        "Superseded" if superseded else "Captured",
        dest_path,
        len(turns),
    )

    return json.dumps(
        {
            "status": "captured",
            "conversation_id": dest_path.stem,
            "stored_at": str(dest_path.relative_to(output_dir)),
            "turn_count": len(turns),
            "content_hash": content_hash[:24] + "...",
            "link_to": link_to,
            "source_session": source_session_id,
            "superseded": superseded,
            "keep_raw": keep_raw,
            "task_id": task_id,
            "task_source": task_source,
            # K-line friction readout (hook may print it to the IDE log).
            "friction": friction,
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
