"""Tests for OpenViking 借鉴落地（V2/V3/V4/V6/V7'）.

- V4 note_types: authoritative table, single-source wiring, freshness derivation
- V3 note_merge: field-level pre-merge (replace/append/union), reversibility
- V2 injection_budget: snippet degradation + module-line cap; doc_description
- V6 distill: merge action field strategies, related_notes in prepare
- V7' doc_update_notify: related_modules intersection reminder
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── V4: note_types ──────────────────────────────────────────────────────────

def test_v4_table_single_source():
    from codewiki.mcp.tools.note_types import (
        DEFAULT_NOTE_TYPES, valid_note_types, promotion_targets,
        freshness_windows, merge_fields_for, validate_note_types,
    )
    from codewiki.mcp.tools.distill_conversation import _VALID_NOTE_TYPES
    import codewiki.mcp.tools.knowledge_loop as kl

    assert _VALID_NOTE_TYPES == set(DEFAULT_NOTE_TYPES)
    assert kl._PROMOTION_PAGE_TYPES["pitfall"] == "query"
    assert kl._PROMOTION_PAGE_TYPES["lesson"] == "concept"
    assert kl._PROMOTION_PAGE_TYPES["general"] == ""
    assert freshness_windows(None)["workaround"] == 45
    assert freshness_windows(None)["decision"] == 365
    assert promotion_targets(None)["bug_fix"] == "query"
    assert merge_fields_for("pitfall")["body"] == "append"
    assert merge_fields_for("unknown-type-x") == merge_fields_for("general")
    assert validate_note_types() == []


def test_v4_schema_overrides():
    from codewiki.mcp.tools.note_types import load_note_types, freshness_windows
    schema = {"conventions": {"note_types": {
        "workaround": {"freshness_days": 20},
        "custom_type": {"freshness_days": 90, "promote_to": "concept"},
    }}}
    table = load_note_types(schema)
    assert table["workaround"]["freshness_days"] == 20
    assert table["workaround"]["promote_to"] == "query"  # unlisted sub-keys inherit
    assert table["custom_type"]["promote_to"] == "concept"
    assert freshness_windows(schema)["custom_type"] == 90


def test_v4_load_freshness_config_precedence():
    import codewiki.mcp.tools.knowledge_loop as kl
    # legacy schema without note_types: custom by_type preserved (no override)
    legacy = {"conventions": {"freshness": {"by_type": {"workaround": 30}}}}
    assert kl.load_freshness_config(legacy)["by_type"] == {"workaround": 30}
    # schema WITH note_types: derived windows win; defaults fill the rest
    mod = {"conventions": {
        "note_types": {"workaround": {"freshness_days": 20}},
        "freshness": {"by_type": {"workaround": 45}},
    }}
    cfg = kl.load_freshness_config(mod)
    assert cfg["by_type"]["workaround"] == 20
    assert cfg["by_type"]["pitfall"] == 180


def test_v4_registry_enum_from_table():
    import codewiki.mcp.registry as reg
    from codewiki.mcp.tools.note_types import DEFAULT_NOTE_TYPES
    # ingest_note 的 note_type 枚举是 note_type 域，从权威表生成
    ing = reg.REGISTRY["ingest_note"]
    ing_blob = json.dumps(ing.schema.inputSchema, ensure_ascii=False)
    for t in DEFAULT_NOTE_TYPES:
        assert f'"{t}"' in ing_blob, f"ingest enum missing {t}"
    # query_wiki 的 type_filter 是 page_type 域（doc/note/module/...），
    # 不属于 note_types 表管辖——只确认域未受本次改动影响。
    q = reg.REGISTRY["query_wiki"]
    tf = q.schema.inputSchema.get("properties", {}).get("type_filter", {})
    assert set(tf.get("enum", [])) >= {"doc", "note", "module", "entity", "concept"}


# ── V3: note_merge ──────────────────────────────────────────────────────────

def _mk_note(tmp_path, name, title, body, *, date, related, note_type="pitfall"):
    notes = tmp_path / "notes"
    notes.mkdir(exist_ok=True)
    related_line = "related_modules: [" + ", ".join(f'"{r}"' for r in related) + "]"
    (notes / name).write_text(
        f"---\ntitle: \"{title}\"\ntype: {note_type}\nstatus: draft\n"
        f"date: {date}\n{related_line}\ntags: [\"{note_type}\", \"alpha\"]\n"
        f"metadata:\n  date: {date}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return f"notes/{name}"


def test_v3_merge_notes_field_strategies(tmp_path):
    from codewiki.mcp.tools.note_merge import merge_notes
    a = _mk_note(tmp_path, "a.md", "旧标题", "旧结论正文",
                 date="2026-01-01", related=["mod_a"])
    b = _mk_note(tmp_path, "b.md", "新标题", "新结论正文",
                 date="2026-06-01", related=["mod_b"])
    res = merge_notes(tmp_path, [a, b])
    assert "error" not in res
    # oldest first (chronological story), newest title/type (replace)
    assert res["title"] == "新标题"
    assert res["note_type"] == "pitfall"
    assert res["content"].index("旧结论正文") < res["content"].index("新结论正文")
    assert "> 合并自 `notes/a.md`" in res["content"]
    assert "> 合并自 `notes/b.md`" in res["content"]
    # replace: related_modules from newest only
    assert '"mod_b"' in res["content"] and '"mod_a"' not in res["content"]
    # merged draft, never stable
    assert "status: draft" in res["content"]
    assert "merged_from" in res["content"]
    # sources untouched (copy semantics — reversibility)
    assert "旧结论正文" in (tmp_path / "notes/a.md").read_text(encoding="utf-8")


def test_v3_merge_union_strategy_override(tmp_path):
    from codewiki.mcp.tools.note_merge import merge_notes
    a = _mk_note(tmp_path, "a.md", "A", "正文A", date="2026-01-01", related=["m1"])
    b = _mk_note(tmp_path, "b.md", "B", "正文B", date="2026-06-01", related=["m2"])
    schema = {"conventions": {"note_types": {
        "pitfall": {"merge_fields": {"related_modules": "union"}},
    }}}
    res = merge_notes(tmp_path, [a, b], schema)
    assert '"m1"' in res["content"] and '"m2"' in res["content"]


def test_v3_merge_write_and_idempotence_guards(tmp_path):
    from codewiki.mcp.tools.note_merge import merge_notes
    a = _mk_note(tmp_path, "a.md", "A", "x", date="2026-01-01", related=[])
    b = _mk_note(tmp_path, "b.md", "B", "y", date="2026-06-01", related=[])
    res = merge_notes(tmp_path, [a, b], write=True)
    assert res.get("written", "").startswith("notes/")
    assert (tmp_path / res["written"]).is_file()
    # one source → error; missing source → error
    assert "error" in merge_notes(tmp_path, [a])
    assert "error" in merge_notes(tmp_path, [a, "notes/nope.md"])


# ── V2: injection_budget + doc_description ─────────────────────────────────

def test_v2_budget_config_and_defaults():
    from codewiki.mcp.tools.injection_budget import load_budget
    assert load_budget(None)["search_result_chars"] == 1200
    off = {"conventions": {"injection_budget": {"search_result_chars": 0}}}
    assert load_budget(off)["search_result_chars"] == 0
    custom = {"conventions": {"injection_budget": {"search_result_chars": 50,
                                                   "agents_md_module_lines": 2}}}
    cfg = load_budget(custom)
    assert cfg["search_result_chars"] == 50 and cfg["agents_md_module_lines"] == 2


def test_v2_snippet_degradation(tmp_path):
    from codewiki.mcp.tools.injection_budget import apply_snippet_budget
    results = [{"file": "wiki/modules/A.md", "snippet": "x" * 400,
                "relevance_score": 1.5},
               {"file": "wiki/modules/B.md", "snippet": "y" * 400,
                "relevance_score": 1.2}]
    # budget 500: first entry consumes it, second degrades
    schema = {"conventions": {"injection_budget": {"search_result_chars": 500}}}
    n = apply_snippet_budget(results, tmp_path, schema)
    assert n == 1
    assert results[0]["snippet"].startswith("x")
    assert "degraded" not in results[0]
    assert results[1]["degraded"] is True
    assert "score 1.2" in results[1]["snippet"]
    # 0 = off → untouched
    r2 = [{"file": "a.md", "snippet": "z" * 900, "relevance_score": 1}]
    assert apply_snippet_budget(r2, tmp_path, {"conventions": {}}) == 0
    r3 = [{"file": "a.md", "snippet": "z" * 900, "relevance_score": 1}]
    assert apply_snippet_budget(
        r3, tmp_path, {"conventions": {"injection_budget": {"search_result_chars": 0}}}
    ) == 0


def test_v2_degraded_line_uses_description(tmp_path):
    from codewiki.mcp.tools.injection_budget import apply_snippet_budget
    doc = tmp_path / "wiki/modules/A.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        '---\ntitle: A\ndescription: "认证模块，负责 JWT 签发与校验"\n---\n\n正文\n',
        encoding="utf-8",
    )
    results = [{"file": "wiki/modules/A.md", "snippet": "s" * 2000,
                "relevance_score": 2.0}]
    schema = {"conventions": {"injection_budget": {"search_result_chars": 100}}}
    apply_snippet_budget(results, tmp_path, schema)
    assert "认证模块" in results[0]["snippet"]


def test_v2_cap_module_lines(tmp_path):
    from codewiki.mcp.tools.injection_budget import cap_module_lines
    mods = [f"Mod{i}" for i in range(10)]
    schema = {"conventions": {"injection_budget": {"agents_md_module_lines": 3}}}
    res = cap_module_lines(mods, tmp_path, schema)
    assert len(res["lines"]) == 3 and res["hidden_count"] == 7
    # off
    res2 = cap_module_lines(mods, tmp_path, {"conventions": {}})
    assert len(res2["lines"]) == 10 and res2["hidden_count"] == 0


def test_v2_doc_description_extract_and_backfill(tmp_path):
    from codewiki.mcp.tools.doc_description import extract_lede, ensure_description, backfill_dir
    body = "\n\n这是第一句话。这是第二句话！这是第三句会被截掉。\n\n## 架构\n\n后文。\n"
    lede = extract_lede(body)
    assert lede.startswith("这是第一句话") and "第三句" not in lede
    assert len(lede) <= 160
    assert extract_lede("\n\n## 只有标题没有正文\n") == ""

    doc = tmp_path / "wiki/modules/A.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("---\ntitle: A\n---\n\n首段摘要句一。句二。\n\n## X\n\nb\n",
                   encoding="utf-8")
    assert ensure_description(doc) is True
    text = doc.read_text(encoding="utf-8")
    assert 'description: "首段摘要句一。句二。"' in text
    # idempotent
    assert ensure_description(doc) is False
    # non-frontmatter files untouched
    plain = tmp_path / "plain.md"
    plain.write_text("no frontmatter\n", encoding="utf-8")
    assert ensure_description(plain) is False
    stats = backfill_dir(tmp_path)
    assert stats["written"] == 0  # already backfilled / non-OKF


def test_v2_crlf_preserved_on_backfill(tmp_path):
    from codewiki.mcp.tools.doc_description import ensure_description
    doc = tmp_path / "crlf.md"
    raw = b"---\r\ntitle: T\r\n---\r\n\r\nCRLF first para.\r\n\r\n## H\r\n"
    doc.write_bytes(raw)
    assert ensure_description(doc) is True
    out = doc.read_bytes()
    assert b"description: \"CRLF first para.\"" in out
    assert out.count(b"\r\n") >= 4  # original CRLFs intact (byte-level rewrite)


# ── V7': doc_update_notify ──────────────────────────────────────────────────

def test_v7_affected_notes_and_payload(tmp_path):
    from codewiki.mcp.tools.doc_update_notify import affected_notes, reminder_payload
    notes = tmp_path / "notes"
    notes.mkdir(parents=True)
    (notes / "n1.md").write_text(
        "---\ntitle: N1\ntype: pitfall\nstatus: stable\n"
        "related_modules: [\"AnalysisPipeline\", \"CLI\"]\n---\n\nbody\n",
        encoding="utf-8",
    )
    (notes / "n2.md").write_text(
        "---\ntitle: N2\ntype: lesson\nstatus: draft\n"
        "related_modules: [\"cache\"]\n---\n\nbody\n",
        encoding="utf-8",
    )
    hits = affected_notes(tmp_path, ["analysis_pipeline"])  # norm: _/-/case
    assert len(hits) == 1 and hits[0]["file"].endswith("n1.md")
    assert hits[0]["matched_module"] == "AnalysisPipeline"
    pay = reminder_payload(tmp_path, ["AnalysisPipeline"])
    assert pay and len(pay["notes"]) == 1 and "review" in pay["message"]
    assert reminder_payload(tmp_path, ["nope"]) is None
    assert affected_notes(tmp_path, []) == []


# ── V6: distill merge strategies + union helper ─────────────────────────────

def test_v6_union_fm_list():
    from codewiki.mcp.tools.distill_conversation import _union_fm_list
    head = "---\ntitle: T\nrelated_modules: [\"a\", \"b\"]\ntags: [\"x\"]\n---\n"
    out = _union_fm_list(head, "related_modules", from_text="see `c` and `a`")
    assert '"a", "b", "c"' in out
    # no extras → unchanged (same object value)
    assert _union_fm_list(head, "tags") == head
    # missing key → unchanged
    assert _union_fm_list(head, "aliases") == head


def test_v6_merge_action_applies_field_strategies(tmp_path):
    from codewiki.mcp.tools.distill_conversation import _apply_dedup_action
    note = tmp_path / "notes" / "target.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\ntitle: 目标笔记\ntype: pitfall\nstatus: draft\n"
        "related_modules: [\"m1\"]\n---\n\n原有正文。\n",
        encoding="utf-8",
    )
    res = _apply_dedup_action(
        "merge", "notes/target.md", "新知识标题",
        "补充内容，涉及模块 `m2`。", "", tmp_path,
    )
    assert res["status"] == "merged"
    text = note.read_text(encoding="utf-8")
    assert "## 新知识标题" in text
    assert "合并自蒸馏候选：新知识标题" in text          # provenance marker (V6)
    assert '"m1", "m2"' in text or '"m1","m2"' in text   # related union (V6)
    assert "原有正文。" in text                            # append keeps old body


def test_v6_update_action_unchanged(tmp_path):
    from codewiki.mcp.tools.distill_conversation import _apply_dedup_action
    note = tmp_path / "notes" / "t2.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\ntitle: T2\ntype: lesson\nstatus: draft\n---\n\n旧正文\n",
        encoding="utf-8",
    )
    res = _apply_dedup_action("update", "notes/t2.md", "X", "全新正文", "", tmp_path)
    assert res["status"] == "updated"
    text = note.read_text(encoding="utf-8")
    assert "全新正文" in text and "旧正文" not in text
    assert "合并自蒸馏候选" not in text  # update path untouched by V6
