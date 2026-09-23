"""Phase5 batch 1 (confidence skeleton): T1-T4.

T1 confidence_level lifecycle (confirm weak / evidence→strong / reject→shadow
/ ingest default / consolidation weak), T2 authority integration, T3
retrieval exposure + shadow gating, T4 wiki_stats distribution.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import note_lifecycle as nl
from codewiki.mcp.tools import note_ingest as ni
from codewiki.src.frontmatter import parse_frontmatter
from codewiki.src.retrieval import _doc_authority


class _Store(SessionStore):
    pass


def _call(fn, **kw) -> dict:
    return json.loads(fn(kw, _Store()))


def _ingest(repo: Path, title: str, content: str = "测试正文内容。", **extra) -> dict:
    args = {"repo_path": str(repo), "title": title, "content": content, "note_type": "general"}
    args.update(extra)
    return _call(ni.handle_ingest_note, **args)


def _note_name(r: dict) -> str:
    """Filename from an ingest_note result (note_path is absolute)."""
    return Path(r["note_path"]).name


def _fm_of(repo: Path, rel: str) -> dict:
    fm, body = parse_frontmatter((repo / "repowiki" / rel).read_text(encoding="utf-8"))
    return fm


def _confidence(fm: dict) -> str:
    meta = fm.get("metadata") or {}
    return str(fm.get("confidence_level") or meta.get("confidence_level") or "").strip().lower()


# --------------------------------------------------------------------------- #
# T1: lifecycle
# --------------------------------------------------------------------------- #


def test_ingest_default_confidence(tmp_path):
    r = _ingest(tmp_path, "默认置信流转", note_type="decision")
    assert r["status"] == "ingested"
    fm = _fm_of(tmp_path, f"notes/{_note_name(r)}")
    assert fm["status"] == "draft"
    # A draft stays visible ([unconfirmed] prefix) — weak, NOT shadow:
    # shadow is reserved for rejected/misrecalled assets.
    assert _confidence(fm) == "weak"

    r = _ingest(tmp_path, "预验证导入", status="stable", reason="ADR-0013 回归：预验证导入场景")
    fm = _fm_of(tmp_path, f"notes/{_note_name(r)}")
    assert _confidence(fm) == "weak"


def test_confirm_plain_writes_weak(tmp_path):
    r = _ingest(tmp_path, "普通确认笔记")
    note = _note_name(r)
    res = _call(nl.handle_confirm_note, repo_path=str(tmp_path), note_file=note)
    assert res["status"] == "stable"
    assert res["confidence_level"] == "weak"
    fm = _fm_of(tmp_path, f"notes/{note}")
    assert _confidence(fm) == "weak"
    assert "verification" not in (fm.get("metadata") or {})


def test_confirm_with_evidence_writes_strong(tmp_path):
    r = _ingest(tmp_path, "带证据确认笔记")
    note = _note_name(r)
    res = _call(
        nl.handle_confirm_note,
        repo_path=str(tmp_path),
        note_file=note,
        evidence={"test_ref": "tests/test_x.py::test_y", "reviewed_by": "human:mambo-wang"},
    )
    assert res["confidence_level"] == "strong"
    fm = _fm_of(tmp_path, f"notes/{note}")
    assert _confidence(fm) == "strong"
    verification = (fm.get("metadata") or {}).get("verification")
    assert verification["test_ref"] == "tests/test_x.py::test_y"
    assert verification["reviewed_by"] == "human:mambo-wang"


def test_confirm_evidence_validation(tmp_path):
    r = _ingest(tmp_path, "证据校验笔记")
    res = _call(
        nl.handle_confirm_note,
        repo_path=str(tmp_path),
        note_file=_note_name(r),
        evidence="just a string",
    )
    assert "error" in res
    # empty evidence object → treated as no evidence → weak
    res = _call(
        nl.handle_confirm_note,
        repo_path=str(tmp_path),
        note_file=_note_name(r),
        evidence={"test_ref": "  "},
    )
    assert res.get("confidence_level") == "weak"


def test_reject_writes_shadow(tmp_path):
    r = _ingest(tmp_path, "拒绝笔记")
    note = _note_name(r)
    _call(nl.handle_confirm_note, repo_path=str(tmp_path), note_file=note)
    res = _call(nl.handle_reject_note, repo_path=str(tmp_path), note_file=note, reason="内容有误")
    assert res["status"] == "deprecated"
    fm = _fm_of(tmp_path, f"notes/{note}")
    assert fm["status"] == "deprecated"
    assert _confidence(fm) == "shadow"


# --------------------------------------------------------------------------- #
# T1: migration script (idempotent)
# --------------------------------------------------------------------------- #


def test_migration_script_idempotent(tmp_path):
    od = tmp_path / "repowiki" / "notes"
    od.mkdir(parents=True)
    (od / "2026-01-01-stable.md").write_text(
        "---\ntype: decision\ntitle: t1\nstatus: stable\nmetadata:\n  date: 2026-01-01\n---\n\n正文。\n",
        encoding="utf-8",
    )
    (od / "2026-01-02-draft.md").write_text(
        "---\ntype: pitfall\ntitle: t2\nstatus: draft\nmetadata:\n  date: 2026-01-02\n---\n\n正文。\n",
        encoding="utf-8",
    )
    (od / "2026-01-03-dep.md").write_text(
        "---\ntype: lesson\ntitle: t3\nstatus: deprecated\nmetadata:\n  date: 2026-01-03\n---\n\n正文。\n",
        encoding="utf-8",
    )
    script = Path(__file__).resolve().parents[1] / "scripts" / "migrate_confidence.py"
    out = subprocess.run(
        [sys.executable, str(script), str(tmp_path)], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    assert "migrated=3" in out.stdout

    assert _confidence(_fm_of(tmp_path, "notes/2026-01-01-stable.md")) == "weak"
    assert _confidence(_fm_of(tmp_path, "notes/2026-01-02-draft.md")) == "weak"
    assert _confidence(_fm_of(tmp_path, "notes/2026-01-03-dep.md")) == "shadow"

    # Second run: everything skipped (idempotency).
    out2 = subprocess.run(
        [sys.executable, str(script), str(tmp_path)], capture_output=True, text=True
    )
    assert out2.returncode == 0
    assert "migrated=0" in out2.stdout


# --------------------------------------------------------------------------- #
# T2: authority integration
# --------------------------------------------------------------------------- #


def _note_fm_text(status: str, confidence: str) -> str:
    return (
        "---\n"
        "type: decision\n"
        "title: x\n"
        "status: %s\n"
        "metadata:\n  confidence_level: %s\n"
        "---\n\n正文。\n" % (status, confidence)
    )


def test_authority_confidence_offsets():
    base = _note_fm_text("stable", "weak")
    a_weak = _doc_authority("notes/a.md", "note", base)
    a_strong = _doc_authority("notes/a.md", "note", _note_fm_text("stable", "strong"))
    a_shadow = _doc_authority("notes/a.md", "note", _note_fm_text("stable", "shadow"))
    a_unstamped = _doc_authority("notes/a.md", "note", _note_fm_text("stable", ""))

    assert a_strong > a_weak > a_shadow
    assert a_unstamped == a_weak  # legacy unstamped behaves as weak (neutral)


def test_authority_clamp_still_binds():
    # decision +0.15, stable +0.05, strong +0.10 → 1.30 clamped at max
    a = _doc_authority("notes/a.md", "note", _note_fm_text("stable", "strong"))
    assert a == 1.3
    # deprecated -0.35 + shadow -0.30 → 0.35 clamped at min
    b = _doc_authority("notes/b.md", "note", _note_fm_text("deprecated", "shadow"))
    assert b == 0.7


def test_scenario_confidence_counts():
    text = "---\ntype: Scenario\ntitle: s\nstatus: stable\nmetadata:\n  confidence_level: shadow\n---\n\n正文。\n"
    a = _doc_authority("wiki/scenarios/s.md", "doc", text)
    b = _doc_authority("wiki/scenarios/s.md", "doc", text.replace("shadow", "weak"))
    assert b > a


# --------------------------------------------------------------------------- #
# T3: retrieval exposure + shadow gating
# --------------------------------------------------------------------------- #


def test_query_wiki_shadow_gating_and_exposure(tmp_path):
    from codewiki.mcp.tools.note_query import handle_query_wiki

    r1 = _ingest(
        tmp_path,
        "高置信知识：部署采用蓝绿发布",
        "蓝绿发布流程细节。",
        status="stable",
        reason="ADR-0013 回归：预验证知识导入",
    )
    _call(
        nl.handle_confirm_note,
        repo_path=str(tmp_path),
        note_file=_note_name(r1),
        evidence={"commit_ref": "abc123"},
    )
    # Shadow WITHOUT deprecated status: explicit shadow at ingest (the
    # misrecall-downgrade shape — a rejected note is status=deprecated which
    # the main path skips entirely, and a draft is weak/visible by design).
    r2 = _ingest(
        tmp_path, "影子知识：部署采用滚动发布", "滚动发布流程细节。", confidence_level="shadow"
    )

    args = {"repo_path": str(tmp_path), "query": "蓝绿 滚动 发布", "max_results": 10}
    payload = _call(handle_query_wiki, **args)
    files = [r.get("file", "") for r in payload["results"]]
    assert any(_note_name(r1) in f for f in files)
    assert not any(_note_name(r2) in f for f in files), "shadow must be gated by default"
    for r in payload["results"]:
        assert "confidence" in r
    strong = [r for r in payload["results"] if _note_name(r1) in r.get("file", "")]
    assert strong[0]["confidence"] == "strong"

    # Opt-in surfaces the shadow asset with its confidence label.
    payload = _call(handle_query_wiki, include_shadow=True, **args)
    shadow = [r for r in payload["results"] if _note_name(r2) in r.get("file", "")]
    assert shadow and shadow[0]["confidence"] == "shadow"


def test_get_task_context_excludes_shadow(tmp_path):
    from codewiki.mcp.tools import task_manager as tm

    r = _call(tm.handle_create_task, repo_path=str(tmp_path), title="置信任务")
    task_id = r["task"]["id"]
    good = _ingest(tmp_path, "任务相关好知识", "相关内容。", task_id=task_id)
    _call(nl.handle_confirm_note, repo_path=str(tmp_path), note_file=_note_name(good))
    bad = _ingest(tmp_path, "任务相关坏知识", "相关内容。", task_id=task_id)
    _call(nl.handle_reject_note, repo_path=str(tmp_path), note_file=_note_name(bad), reason="有误")

    ctx = _call(tm.handle_get_task_context, repo_path=str(tmp_path), task_id=task_id)
    rels = [n["relpath"] for n in ctx["related_notes"]]
    assert _note_name(good) in rels
    assert _note_name(bad) not in rels


# --------------------------------------------------------------------------- #
# T4: wiki_stats distribution
# --------------------------------------------------------------------------- #


def test_wiki_stats_confidence_distribution(tmp_path):
    from codewiki.mcp.tools.note_query import handle_query_wiki
    from codewiki.mcp.tools.wiki_stats import handle_wiki_stats

    # Distinctive per-note words (BM25 on a tiny corpus needs them to clear
    # the score threshold — shared words get df=n and near-zero idf).
    r1 = _ingest(
        tmp_path,
        "统计用强置信",
        "独占词阿尔法。",
        status="stable",
        reason="ADR-0013 回归：统计用例",
    )
    _call(
        nl.handle_confirm_note,
        repo_path=str(tmp_path),
        note_file=_note_name(r1),
        evidence={"test_ref": "t"},
    )
    r2 = _ingest(
        tmp_path,
        "统计用普通置信",
        "独占词贝塔。",
        status="stable",
        reason="ADR-0013 回归：统计用例",
    )
    _call(nl.handle_confirm_note, repo_path=str(tmp_path), note_file=_note_name(r2))
    _ingest(
        tmp_path, "统计用影子", "独占词伽马。", confidence_level="shadow"
    )  # explicit shadow (misrecall-downgrade shape)

    # Generate retrieval stats so wiki_stats has data (query the strong one).
    _call(handle_query_wiki, repo_path=str(tmp_path), query="阿尔法", max_results=10)

    stats = _call(handle_wiki_stats, repo_path=str(tmp_path), limit=50)
    conf = stats.get("confidence")
    assert conf is not None
    d = conf["distribution"]
    assert d["strong"] == 1 and d["weak"] == 1 and d["shadow"] == 1
    assert conf["strong_ratio"] == round(1 / 3, 4)
    assert "top_shadow_assets" in conf
