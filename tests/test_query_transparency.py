"""Tests for the 检索透明化 (T-line) P0 enhancements.

Covers docs/知识飞轮增强设计方案-P0三项.md acceptance criteria:
  - mode=check: lightweight pre-check (relevant/top_score/top_results, no
    snippets, and NO retrieval-stats recording — a pre-check is not a
    consumption event)
  - max_chars content budget for expand=true (default 3000 unchanged,
    configurable up to 20000)
  - wiki_stats cold_candidates: once-hot-now-cold docs surfaced as a
    retrieval health signal (mirrors usage_ranking cold definition)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.knowledge_loop import (
    _cold_candidates,
    handle_query_wiki,
    handle_wiki_stats,
)
from codewiki.mcp.tools.wiki_search import build_full_index, query_coverage


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _mk_wiki(tmp_path) -> Path:
    od = tmp_path / "repowiki"
    (od / "wiki" / "modules").mkdir(parents=True, exist_ok=True)
    (od / "notes").mkdir(exist_ok=True)
    (od / "wiki" / "modules" / "auth.md").write_text(
        "---\ntype: Module\ntitle: 认证模块\n---\n\n认证模块负责登录鉴权与令牌签发。\n",
        encoding="utf-8",
    )
    (od / "notes" / "pitfall-port-conflict.md").write_text(
        "---\ntype: pitfall\ntitle: 端口冲突排查\nstatus: stable\n---\n\n"
        "开发时常见端口冲突，用 lsof -i :8080 排查。\n",
        encoding="utf-8",
    )
    build_full_index(od, session=None)
    return od


def _query(od: Path, **kw) -> dict:
    args = {"output_dir": str(od), "query": kw.pop("query", "认证")}
    args.update(kw)
    return json.loads(handle_query_wiki(args, SessionStore()))


def _stats_rows(od: Path) -> list:
    """All telemetry hit events as (doc, n) rows (T2 migration of the old
    retrieval_stats read — check-mode must record NOTHING, so any hit event
    present means stats leaked)."""
    from codewiki.mcp.tools import telemetry
    return [
        (doc, e["hits"])
        for doc, e in (telemetry.aggregate_usage(od) or {}).items()
        if e.get("hits")
    ]


def _seed_stats(od: Path, rows: list) -> None:
    """Seed telemetry hit events {rel_path: (hits, last_hit)} (T2 migration)."""
    from tests.telemetry_seed import seed_hits
    seed_hits(od, {fp: (hits, last_hit) for fp, hits, last_hit in rows})


# --------------------------------------------------------------------------- #
# T2: mode=check
# --------------------------------------------------------------------------- #
class TestCheckMode:
    def test_check_returns_verdict_without_snippets(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, query="端口冲突", mode="check")
        assert out["mode"] == "check"
        assert out["relevant"] is True
        assert out["top_score"] > 0
        assert 1 <= len(out["top_results"]) <= 3
        for r in out["top_results"]:
            assert set(r.keys()) == {"file", "title", "relevance_score"}
            assert "snippet" not in r
            assert "content" not in r

    def test_check_irrelevant_query(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, query="量子纠缠实验数据", mode="check")
        assert out["relevant"] is False
        assert out["top_score"] == 0
        assert out["top_results"] == []

    def test_check_records_no_stats(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _query(od, query="端口冲突", mode="check")
        assert _stats_rows(od) == [], "check mode must not record retrieval stats"

    def test_full_search_records_stats(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _query(od, query="端口冲突")
        rows = _stats_rows(od)
        assert rows, "normal search should record retrieval stats"


# --------------------------------------------------------------------------- #
# T3: max_chars content budget
# --------------------------------------------------------------------------- #
class TestMaxChars:
    def test_default_budget_unchanged(self, tmp_path):
        od = _mk_wiki(tmp_path)
        (od / "wiki" / "modules" / "big.md").write_text(
            "---\ntype: Module\ntitle: 大页面\n---\n\n" + "x" * 5000,
            encoding="utf-8",
        )
        build_full_index(od, session=None)
        out = _query(od, query="大页面", expand=True)
        entry = next(r for r in out["results"] if r["file"].endswith("big.md"))
        assert len(entry["content"]) <= 3000
        assert entry.get("content_truncated") is True

    def test_custom_budget(self, tmp_path):
        od = _mk_wiki(tmp_path)
        (od / "wiki" / "modules" / "big.md").write_text(
            "---\ntype: Module\ntitle: 大页面\n---\n\n" + "x" * 9000,
            encoding="utf-8",
        )
        build_full_index(od, session=None)
        out = _query(od, query="大页面", expand=True, max_chars=8000)
        entry = next(r for r in out["results"] if r["file"].endswith("big.md"))
        assert 7000 < len(entry["content"]) <= 8000
        assert entry.get("content_budget") == 8000

    def test_budget_clamped_to_max(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, query="认证", expand=True, max_chars=999999)
        # clamped server-side to 20000; must not raise
        assert "results" in out


# --------------------------------------------------------------------------- #
# U2 (knowledge_loop half): cold_candidates in wiki_stats
# --------------------------------------------------------------------------- #
class TestColdCandidates:
    def test_none_without_stats_db(self, tmp_path):
        od = _mk_wiki(tmp_path)
        assert _cold_candidates(od) is None

    def test_cold_detection(self, tmp_path):
        od = _mk_wiki(tmp_path)
        old = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")
        recent = datetime.now().strftime("%Y-%m-%d")
        _seed_stats(od, [
            ("wiki/modules/auth.md", 10, old),       # hot then cold -> listed
            ("notes/pitfall-port-conflict.md", 8, recent),  # hot, still warm
            ("wiki/modules/other.md", 1, old),       # never hot -> skipped
        ])
        cold = _cold_candidates(od)
        assert cold is not None
        assert [c["file_path"] for c in cold] == ["wiki/modules/auth.md"]
        assert cold[0]["hit_count"] == 10
        assert cold[0]["days_since_last_hit"] >= 200

    def test_wiki_stats_surfaces_cold(self, tmp_path):
        od = _mk_wiki(tmp_path)
        old = (datetime.now() - timedelta(days=220)).strftime("%Y-%m-%d")
        _seed_stats(od, [("wiki/modules/auth.md", 5, old)])
        out = json.loads(
            handle_wiki_stats({"output_dir": str(od)}, SessionStore())
        )
        assert "cold_candidates" in out
        assert out["cold_candidates"][0]["file_path"] == "wiki/modules/auth.md"

    def test_schema_overrides_thresholds(self, tmp_path):
        import yaml
        od = _mk_wiki(tmp_path)
        (od / "schema.yaml").write_text(
            yaml.safe_dump({"conventions": {"usage_ranking": {
                "cold_days": 30, "cold_min_hits": 2}}}),
            encoding="utf-8",
        )
        sixty = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        _seed_stats(od, [("wiki/modules/auth.md", 2, sixty)])
        cold = _cold_candidates(od)
        assert cold and cold[0]["file_path"] == "wiki/modules/auth.md"


# --------------------------------------------------------------------------- #
# T1: query_coverage + matched_tokens (word-level transparency)
# --------------------------------------------------------------------------- #
class TestQueryCoverage:
    def test_coverage_matched_and_missing(self, tmp_path):
        od = _mk_wiki(tmp_path)
        cov = query_coverage(od, "端口 冲突 量子")
        assert "端口" in cov["matched"]
        assert "冲突" in cov["matched"]
        assert "量子" in cov["missing"]

    def test_coverage_expanded_terms_annotated(self, tmp_path):
        od = _mk_wiki(tmp_path)
        # "鉴权" exists in auth.md body; "鉴定" does not
        cov = query_coverage(od, "认证", expand_terms=["鉴权", "鉴定"])
        assert any(t.endswith("(expanded)") and "鉴权" in t for t in cov["matched"])
        assert any(t.endswith("(expanded)") and "鉴定" in t for t in cov["missing"])

    def test_handle_query_wiki_returns_coverage(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, query="端口 冲突 量子")
        assert "query_coverage" in out
        assert "量子" in out["query_coverage"]["missing"]

    def test_matched_tokens_per_result(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, query="端口 冲突")
        entry = next(
            r for r in out["results"]
            if r["file"].endswith("pitfall-port-conflict.md")
        )
        assert "端口" in entry.get("matched_tokens", [])
        assert "冲突" in entry.get("matched_tokens", [])

    def test_usage_field_passthrough(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, query="端口冲突")
        for r in out["results"]:
            assert "usage" in r
            assert set(r["usage"].keys()) == {"hit_count", "last_hit", "adopted_count"}

    def test_check_mode_no_coverage_pollution(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, query="端口冲突", mode="check")
        # check mode stays lightweight: no query_coverage key required
        assert out["mode"] == "check"
