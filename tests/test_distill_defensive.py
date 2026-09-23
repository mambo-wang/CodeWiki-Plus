"""ADR-0011: distill LLM-output defensive validation + CJK title tokens.

Three guarantees under test:
1. Unparseable LLM output must NOT delete/archive the raw transcript — the raw
   stays pending with status=parse_failed and an explicit parse_error field.
2. Chinese titles get real token sets via the shared tokeniser, so
   near-duplicate CJK titles enter the weak-conflict (Jaccard) band.
3. Malformed note entries (missing title/content) are dropped with an explicit
   invalid_note record, never silently ingested.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codewiki.mcp.tools.distill_conversation import (  # noqa: E402
    _find_existing_note,
    _is_title_subset,
    _process_llm_output,
    _title_similarity,
    _title_tokens,
)


def _make_raw(tmp_path: Path, name: str = "conv-20260918T000000Z") -> Path:
    raw = tmp_path / "raw" / f"{name}.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(
        "---\n"
        "status: pending\n"
        "captured_at: 2026-09-18T00:00:00Z\n"
        "turn_count: 2\n"
        "---\n"
        "user: 我们决定用分层去重\n"
        "assistant: 好的，已记录\n",
        encoding="utf-8",
    )
    return raw


def test_parse_failure_keeps_raw_pending(tmp_path):
    raw = _make_raw(tmp_path)
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir(exist_ok=True)

    res = _process_llm_output(
        raw,
        "totally not json at all",
        tmp_path,
        store=None,
    )
    data = json.loads(json.dumps(res))
    assert data["status"] == "parse_failed", data
    assert data["parse_error"], "parse_error must be explicit"
    assert data["deleted_raw"] is False
    assert data["archived_raw"] is None
    # raw file must still exist and remain pending (not marked distilled)
    assert raw.is_file(), "raw transcript must survive a parse failure"
    assert "status: distilled" not in raw.read_text(encoding="utf-8")


def test_valid_empty_notes_is_not_parse_failure(tmp_path):
    raw = _make_raw(tmp_path, "conv-20260918T000001Z")
    (tmp_path / "notes").mkdir(exist_ok=True)
    res = _process_llm_output(
        raw,
        json.dumps({"notes": []}),
        tmp_path,
        store=None,
    )
    assert res["status"] == "no_knowledge", res
    assert "parse_error" not in res or res.get("parse_error") is None


def test_malformed_note_entries_dropped_explicitly(tmp_path):
    raw = _make_raw(tmp_path, "conv-20260918T000002Z")
    (tmp_path / "notes").mkdir(exist_ok=True)
    payload = json.dumps(
        {
            "notes": [
                {"note_type": "decision", "content": "no title here"},  # missing title
                {"title": "有标题没正文", "note_type": "decision"},  # missing content
            ]
        }
    )
    res = _process_llm_output(raw, payload, tmp_path, store=None)
    statuses = [n.get("status") for n in res["notes"]]
    assert statuses == ["invalid_note", "invalid_note"], res["notes"]
    reasons = {n.get("reason") for n in res["notes"]}
    assert "missing or empty title" in reasons
    assert "missing or empty content" in reasons
    # nothing was ingested
    assert not list((tmp_path / "notes").glob("*.md"))


def test_cjk_title_tokens_are_segmented():
    tokens = _title_tokens("发版本流程")
    assert isinstance(tokens, set)
    assert len(tokens) >= 2, f"CJK title must be segmented, got {tokens}"


def test_cjk_near_duplicate_titles_enter_weak_band():
    # Before ADR-0011 these were single tokens -> Jaccard 0.0 (never a conflict).
    sim = _title_similarity("发版本", "发版本流程")
    assert sim >= 0.35, f"near-duplicate CJK titles must reach the weak band, got {sim}"


def test_english_title_similarity_unchanged():
    sim = _title_similarity("Use status draft", "Use status=draft")
    assert sim > 0.0
    # identical titles still 1.0
    assert _title_similarity("same title", "same title") == 1.0


# --- ADR-0011 Round 2: subset-title downgrade + parse_error stamping --- #


def test_subset_titles_detected():
    assert _is_title_subset("发版本", "发版本流程")
    assert _is_title_subset("任务记忆压缩设计方案", "任务记忆压缩")
    # near-identical paraphrase (sim 0.857) is NOT an ambiguous subset
    assert not _is_title_subset(
        "缓存失效策略：写入后删除 cache key", "缓存失效策略：写入后删除 key"
    )
    # identical token sets are NOT subsets (fast path preserved)
    assert not _is_title_subset("same title", "same title")
    # disjoint titles are not subsets
    assert not _is_title_subset("统一知识存储层", "多仓工作区")


def test_subset_title_not_auto_suppressed(tmp_path):
    """Q5(c): "任务记忆压缩" vs "任务记忆压缩设计方案" scores 0.75 (strong band)
    but is a strict subset — must NOT auto-suppress, must go to agent hold."""
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "existing.md").write_text(
        '---\ntitle: "任务记忆压缩设计方案"\ntype: decision\nstatus: stable\n---\n正文\n',
        encoding="utf-8",
    )
    hit = _find_existing_note("任务记忆压缩", "decision", tmp_path, store=None)
    assert hit is None, f"subset title must not auto-suppress, got {hit}"


def test_identical_title_still_auto_suppressed(tmp_path):
    """Fast path preserved: identical titles still auto-suppress."""
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "existing.md").write_text(
        '---\ntitle: "任务记忆压缩设计方案"\ntype: decision\nstatus: stable\n---\n正文\n',
        encoding="utf-8",
    )
    hit = _find_existing_note("任务记忆压缩设计方案", "decision", tmp_path, store=None)
    assert hit is not None, "identical title must still take the fast path"


def test_parse_failure_stamps_raw_frontmatter(tmp_path):
    """Q6(b): parse failure writes parse_error into the raw frontmatter so the
    next worker sees the failure reason without re-reading the transcript."""
    raw = _make_raw(tmp_path, "conv-20260918T000003Z")
    (tmp_path / "notes").mkdir(exist_ok=True)
    res = _process_llm_output(raw, "garbage not json", tmp_path, store=None)
    assert res["status"] == "parse_failed"
    text = raw.read_text(encoding="utf-8")
    assert "parse_error:" in text, f"frontmatter must carry parse_error, got:\n{text}"
    assert "status: pending" in text, "raw must stay pending for retry"
