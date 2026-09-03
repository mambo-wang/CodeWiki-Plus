# -*- coding: utf-8 -*-
"""Tests for the claude-mem borrowings (P0-1 / P0-2 / P1-4 / P0-3).

Covers docs/claude-mem借鉴详细设计方案.md (Rev.2) acceptance criteria:
  - P0-1 est_tokens: cost visibility across all three retrieval paths,
    expand content_tokens, response-level cost_hint, config switches
  - P0-2 by_file: file-scoped knowledge timeline (notes only, specificity
    sort, query hard-filter, path normalisation, no bodies)
  - P1-4 possibly_stale: git last-commit-time peer freshness (ADR-0003)
  - P0-3: workflow embedded in the query_wiki tool description
Signal discipline: by_file writes telemetry by_file events but NOT
usage-heat hits.
"""

from __future__ import annotations

import json
from pathlib import Path

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.injection_budget import (
    estimate_tokens,
    load_retrieval_cost,
)
from codewiki.mcp.tools.knowledge_loop import handle_query_wiki
from codewiki.mcp.tools.wiki_search import build_full_index

# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #

NOTE_STABLE = """---
type: decision
title: 检索必须走 BM25 索引
status: stable
metadata:
  date: 2020-01-01
  related_modules:
  - mcp
  - wiki_search
  related_components: []
---
正文：BM25 索引构建与查询路径的设计决策。
"""

NOTE_DRAFT = """---
type: lesson
title: 草稿教训：索引重建的坑
status: draft
metadata:
  date: 2020-02-02
  related_modules:
  - mcp
  related_components: []
---
正文：草稿状态的教训笔记。
"""

NOTE_COMPONENT = """---
type: pitfall
title: 组件级命中应排最前
status: stable
metadata:
  date: 2020-03-03
  related_modules:
  - mcp
  related_components:
  - wiki_search
---
正文：related_components 命中的笔记特异性更高。
"""

NOTE_DEPRECATED = """---
type: decision
title: 已废弃的旧决策
status: deprecated
metadata:
  date: 2020-01-01
  related_modules:
  - mcp
---
正文：deprecated 笔记不应出现在时间线。
"""

NOTE_NO_META = """---
type: lesson
title: 无 metadata 的笔记静默跳过
status: stable
---
正文：没有 related_modules 的笔记。
"""

DOC_PAGE = "---\ntype: Module\ntitle: 认证模块\n---\n\n认证模块负责登录鉴权。\n"


def _mk_wiki(tmp_path) -> Path:
    od = tmp_path / "repowiki"
    (od / "wiki" / "modules").mkdir(parents=True, exist_ok=True)
    (od / "notes").mkdir(exist_ok=True)
    (od / "wiki" / "modules" / "auth.md").write_text(DOC_PAGE, encoding="utf-8")
    for name, body in (
        ("n-stable.md", NOTE_STABLE),
        ("n-draft.md", NOTE_DRAFT),
        ("n-component.md", NOTE_COMPONENT),
        ("n-deprecated.md", NOTE_DEPRECATED),
        ("n-nometa.md", NOTE_NO_META),
    ):
        (od / "notes" / name).write_text(body, encoding="utf-8")
    build_full_index(od, session=None)
    return od


def _query(od: Path, **kw) -> dict:
    args = {"output_dir": str(od)}
    args.update(kw)
    return json.loads(handle_query_wiki(args, SessionStore()))


def _schema_with(od: Path, conv: dict) -> Path:
    """Write a schema.yaml with the given conventions block."""
    import yaml

    schema = {"conventions": conv}
    (od / "schema.yaml").write_text(
        yaml.safe_dump(schema, allow_unicode=True), encoding="utf-8"
    )
    return od


# --------------------------------------------------------------------------- #
# P0-1: estimate_tokens / load_retrieval_cost
# --------------------------------------------------------------------------- #


class TestEstimateTokens:
    def test_zero_and_negative(self):
        assert estimate_tokens(0) == 0
        assert estimate_tokens(-5) == 0

    def test_simple_division(self):
        assert estimate_tokens(1000) == 250

    def test_ceil_not_floor(self):
        assert estimate_tokens(1001) == 251
        assert estimate_tokens(5) == 2

    def test_custom_divisor(self):
        assert estimate_tokens(1000, chars_per_token=2) == 500

    def test_chinese_chars_not_bytes(self):
        # len() counts characters, not UTF-8 bytes (中文 3 bytes/char)
        text = "中文字符测试"  # 6 chars, 18 bytes
        assert estimate_tokens(len(text)) == estimate_tokens(6) == 2


class TestLoadRetrievalCost:
    def test_defaults(self):
        cfg = load_retrieval_cost(None)
        assert cfg["enabled"] is True
        assert cfg["chars_per_token"] == 4
        assert cfg["expand_hint"] is True

    def test_overrides(self):
        cfg = load_retrieval_cost(
            {"conventions": {"retrieval_cost": {"enabled": False, "chars_per_token": 2}}}
        )
        assert cfg["enabled"] is False
        assert cfg["chars_per_token"] == 2

    def test_invalid_chars_per_token_kept_default(self):
        cfg = load_retrieval_cost(
            {"conventions": {"retrieval_cost": {"chars_per_token": "bogus"}}}
        )
        assert cfg["chars_per_token"] == 4


# --------------------------------------------------------------------------- #
# P0-1: est_tokens in retrieval results
# --------------------------------------------------------------------------- #


class TestEstTokensInResults:
    def test_default_search_carries_est_tokens(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, query="BM25")
        assert out["results"], "query must hit the corpus"
        for r in out["results"]:
            assert "est_tokens" in r
            assert r["est_tokens"] > 0

    def test_json_fallback_path_carries_est_tokens(self, tmp_path):
        # No SQLite cache on disk (fresh tmp wiki, no session): wiki_search
        # falls back to the JSON index path.
        from codewiki.mcp.tools.wiki_search import search

        od = _mk_wiki(tmp_path)
        results = search(od, "BM25", session=None)
        assert results
        for r in results:
            assert r.get("est_tokens", 0) > 0

    def test_sqlite_path_carries_est_tokens(self, tmp_path):
        from codewiki.mcp.cache import AnalysisCache

        od = _mk_wiki(tmp_path)
        cache = AnalysisCache(tmp_path, db_path=tmp_path / ".codewiki" / "analysis_cache.db")
        try:
            cache.build_search_index(od)
            results = cache.search("BM25", output_dir=od, chars_per_token=4)
            assert results
            for r in results:
                assert r.get("est_tokens", 0) > 0
        finally:
            cache.close()

    def test_hop_expansion_carries_est_tokens(self, tmp_path):
        from codewiki.mcp.cache import AnalysisCache

        od = _mk_wiki(tmp_path)
        cache = AnalysisCache(tmp_path, db_path=tmp_path / ".codewiki" / "analysis_cache.db")
        try:
            cache.build_search_index(od)
            results = cache.search("BM25", output_dir=od, hop=1, chars_per_token=4)
            # Whatever comes back (direct or hop), no KeyError and est present.
            for r in results:
                if "hop" in r:
                    assert "est_tokens" in r
                    assert r["est_tokens"] > 0
        finally:
            cache.close()

    def test_disabled_config_removes_field(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _schema_with(od, {"retrieval_cost": {"enabled": False}})
        out = _query(od, query="BM25")
        assert out["results"]
        for r in out["results"]:
            assert "est_tokens" not in r

    def test_chars_per_token_config_doubles_count(self, tmp_path):
        # Two fresh wikis (page_router caches schema.yaml per output_dir, so
        # the config must be in place before the first query touches it).
        od4 = _mk_wiki(tmp_path / "a")
        od2 = _mk_wiki(tmp_path / "b")
        _schema_with(od2, {"retrieval_cost": {"chars_per_token": 2}})
        out4 = _query(od4, query="BM25")
        out2 = _query(od2, query="BM25")
        assert out4["results"] and out2["results"]
        assert [r["file"] for r in out4["results"]] == [r["file"] for r in out2["results"]]
        for r4, r2 in zip(out4["results"], out2["results"]):
            assert r2["est_tokens"] == r4["est_tokens"] * 2


class TestExpandTokens:
    def test_expand_has_both_token_fields(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, query="BM25", expand=True, max_chars=500)
        assert out["results"]
        for r in out["results"]:
            if "content" in r:
                assert "est_tokens" in r
                assert "content_tokens" in r
                assert r["content_tokens"] <= r["est_tokens"]

    def test_truncated_content_costs_less_than_full(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, query="BM25", expand=True, max_chars=500)
        truncated = [r for r in out["results"] if r.get("content_truncated")]
        if truncated:  # depends on corpus sizes; notes here are small
            for r in truncated:
                assert r["content_tokens"] < r["est_tokens"]


class TestCostHint:
    def test_cost_hint_sums(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, query="BM25")
        assert "cost_hint" in out
        ch = out["cost_hint"]
        ests = [r["est_tokens"] for r in out["results"]]
        assert ch["expand_all_tokens"] == sum(ests)
        assert ch["top3_tokens"] == sum(ests[:3])
        assert ch["index_tokens"] > 0
        assert "hint" in ch

    def test_cost_hint_off_with_expand_hint_false(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _schema_with(od, {"retrieval_cost": {"expand_hint": False}})
        out = _query(od, query="BM25")
        assert "cost_hint" not in out
        # est_tokens still present (enabled untouched)
        for r in out["results"]:
            assert "est_tokens" in r

    def test_est_tokens_not_in_check_output(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, query="BM25", mode="check")
        for r in out["top_results"]:
            assert set(r.keys()) == {"file", "title", "relevance_score"}


# --------------------------------------------------------------------------- #
# P0-2: by_file
# --------------------------------------------------------------------------- #


class TestByFile:
    def test_by_file_hits_mcp_notes(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, by_file="codewiki/mcp/tools/wiki_search.py")
        assert out["by_file"] == "codewiki/mcp/tools/wiki_search.py"
        assert out["file_knowledge"]["total"] >= 2  # stable + draft (+component)
        files = {e["file"] for e in out["file_knowledge"]["timeline"]}
        assert all(f.startswith("notes/") for f in files)

    def test_no_knowledge_returns_empty_not_error(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, by_file="nowhere/unknown/thing.py")
        assert out["file_knowledge"]["total"] == 0
        assert out["file_knowledge"]["timeline"] == []
        assert "error" not in out

    def test_backslash_and_forward_slash_equivalent(self, tmp_path):
        od = _mk_wiki(tmp_path)
        a = _query(od, by_file="codewiki/mcp/tools/wiki_search.py")
        b = _query(od, by_file="codewiki\\mcp\\tools\\wiki_search.py")
        assert a["file_knowledge"]["total"] == b["file_knowledge"]["total"]
        assert [e["file"] for e in a["file_knowledge"]["timeline"]] == [
            e["file"] for e in b["file_knowledge"]["timeline"]
        ]

    def test_absolute_path_equivalent(self, tmp_path):
        od = _mk_wiki(tmp_path)
        rel = _query(od, by_file="codewiki/mcp/tools/wiki_search.py")
        repo_root = Path(od).resolve().parent
        abspath = (repo_root / "codewiki" / "mcp" / "tools" / "wiki_search.py").resolve()
        # The file need not exist on disk for path normalisation; use the
        # absolute form of the same logical path.
        absr = _query(od, by_file=str(abspath))
        assert absr["by_file"] == "codewiki/mcp/tools/wiki_search.py"
        assert absr["file_knowledge"]["total"] == rel["file_knowledge"]["total"]

    def test_component_hit_ranks_before_module_hit(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, by_file="codewiki/mcp/tools/wiki_search.py")
        timeline = out["file_knowledge"]["timeline"]
        specs = [e["specificity"] for e in timeline]
        assert specs == sorted(specs, reverse=True)
        comp = [e for e in timeline if e["specificity"] >= 2]
        mod = [e for e in timeline if e["specificity"] == 1]
        assert comp, "component-level note must match (related_components: wiki_search)"
        if comp and mod:
            assert timeline.index(comp[0]) < timeline.index(mod[0])

    def test_max_results_truncation(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _schema_with(od, {"file_knowledge": {"max_results": 1}})
        out = _query(od, by_file="codewiki/mcp/tools/wiki_search.py")
        assert out["file_knowledge"]["returned"] == 1
        assert len(out["file_knowledge"]["timeline"]) == 1

    def test_by_file_with_query_hard_filters(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, by_file="codewiki/mcp/tools/wiki_search.py", query="草稿")
        for e in out["file_knowledge"]["timeline"]:
            assert "草稿" in e["title"] or "草稿" in e["file"]

    def test_by_file_without_query_no_error(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, by_file="codewiki/mcp/tools/wiki_search.py")
        assert "error" not in out

    def test_missing_query_and_by_file_still_errors(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od)
        assert "error" in out
        assert "query is required" in out["error"]

    def test_files_field_exact_hit_scores_3(self, tmp_path):
        # v1.5 optional field (P1-2 forward compat): metadata.files exact match
        note = """---
type: decision
title: 精确文件级命中
status: stable
metadata:
  date: 2020-04-04
  related_modules: []
  related_components: []
  files:
  - codewiki/mcp/tools/wiki_search.py
---
正文：files 字段精确命中。
"""
        od = _mk_wiki(tmp_path)
        (od / "notes" / "n-files.md").write_text(note, encoding="utf-8")
        out = _query(od, by_file="codewiki/mcp/tools/wiki_search.py")
        hits = [e for e in out["file_knowledge"]["timeline"] if e["specificity"] == 3]
        assert hits and hits[0]["file"] == "notes/n-files.md"

    def test_note_without_related_modules_skipped(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, by_file="codewiki/mcp/tools/wiki_search.py")
        files = {e["file"] for e in out["file_knowledge"]["timeline"]}
        assert "notes/n-nometa.md" not in files

    def test_corrupt_frontmatter_skipped_others_survive(self, tmp_path):
        od = _mk_wiki(tmp_path)
        (od / "notes" / "n-corrupt.md").write_text(
            "没有 frontmatter 的裸正文", encoding="utf-8"
        )
        out = _query(od, by_file="codewiki/mcp/tools/wiki_search.py")
        assert out["file_knowledge"]["total"] >= 2  # others still matched

    def test_file_knowledge_disabled_returns_error(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _schema_with(od, {"file_knowledge": {"enabled": False}})
        out = _query(od, by_file="codewiki/mcp/tools/wiki_search.py")
        assert "error" in out

    def test_timeline_has_no_bodies(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, by_file="codewiki/mcp/tools/wiki_search.py")
        for e in out["file_knowledge"]["timeline"]:
            assert "content" not in e
            assert "snippet" not in e

    def test_deprecated_notes_excluded_draft_included(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, by_file="codewiki/mcp/tools/wiki_search.py")
        statuses = {e["file"]: e["status"] for e in out["file_knowledge"]["timeline"]}
        assert "notes/n-deprecated.md" not in statuses
        assert statuses.get("notes/n-draft.md") == "draft"

    def test_wiki_pages_not_in_timeline(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, by_file="codewiki/mcp/tools/wiki_search.py")
        # wiki/modules/auth.md exists and mentions 认证, but timeline is
        # notes-only by construction — assert every entry is a note.
        for e in out["file_knowledge"]["timeline"]:
            assert e["file"].startswith("notes/")


# --------------------------------------------------------------------------- #
# by_file signal discipline: telemetry yes, usage heat no
# --------------------------------------------------------------------------- #


class TestByFileSignalDiscipline:
    def test_by_file_does_not_write_usage_heat(self, tmp_path):
        od = _mk_wiki(tmp_path)
        from codewiki.mcp.tools import telemetry

        def _hit_counts(od):
            agg = telemetry.aggregate_usage(od) or {}
            return {fp: int(e.get("hits", 0) or 0) for fp, e in agg.items()}

        hits_before = _hit_counts(od)
        out = _query(od, by_file="codewiki/mcp/tools/wiki_search.py")
        hits_after = _hit_counts(od)
        # by_file events may create zero-hit entries in the aggregate (they
        # share the event stream), but the HIT COUNTS feeding usage heat must
        # not change: every doc stays at its previous hit count.
        for fp, n in hits_after.items():
            assert n == hits_before.get(fp, 0), f"usage-heat hit leaked via by_file: {fp}"
        returned = {e["file"] for e in out["file_knowledge"]["timeline"]}
        for fp in returned:
            assert hits_after.get(fp, 0) == 0, f"by_file wrote a usage hit: {fp}"

    def test_by_file_writes_telemetry_events(self, tmp_path):
        od = _mk_wiki(tmp_path)
        out = _query(od, by_file="codewiki/mcp/tools/wiki_search.py")
        # Read the raw event stream: by_file events must exist.
        from codewiki.mcp.tools import telemetry as tel

        user_file = tel._user_events_path(od, create=False)
        assert user_file.exists()
        events = []
        for line in user_file.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
        by_file_events = [e for e in events if e.get("t") == "by_file"]
        assert by_file_events, "by_file call must record telemetry events"
        recorded = {e["doc"] for e in by_file_events}
        returned = {e["file"] for e in out["file_knowledge"]["timeline"]}
        assert returned <= recorded


# --------------------------------------------------------------------------- #
# P1-4: possibly_stale (git last-commit time, ADR-0003)
# --------------------------------------------------------------------------- #


class TestPossiblyStale:
    def _mk_git_repo(self, tmp_path, commit_note_date: str, commit_after: bool):
        """Temp git repo with a tracked target file + a note dated around it."""
        import subprocess
        from datetime import datetime, timedelta

        repo = tmp_path / "repo"
        (repo / "codewiki" / "mcp" / "tools").mkdir(parents=True)
        target = repo / "codewiki" / "mcp" / "tools" / "wiki_search.py"
        target.write_text("def search(): pass\n", encoding="utf-8")
        od = repo / "repowiki"
        (od / "notes").mkdir(parents=True)

        def _git(*args, env_extra=None):
            env = {
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@t",
            }
            import os

            if env_extra:
                env.update(env_extra)
            subprocess.run(
                ["git", *args], cwd=str(repo), check=True, capture_output=True,
                env={**os.environ, **env},
            )

        _git("init", "-q")
        # Commit the target file at a controlled committer date.
        when = (
            "2021-06-15T12:00:00+00:00"
            if commit_after
            else "2019-06-15T12:00:00+00:00"
        )
        _git(
            "commit",
            "--allow-empty",
            "-m",
            "init",
        )
        _git("add", ".")
        _git(
            "-c",
            f"user.name=t",
            "commit",
            "-m",
            "target",
            "--date",
            when,
        )
        # Force the commit committer date via env for both author/committer.
        # (git commit --date only sets author date; set committer via env)
        # Re-commit with env to be safe:
        _git(
            "commit",
            "--amend",
            "--no-edit",
            "--date",
            when,
            env_extra={
                "GIT_COMMITTER_DATE": when,
                "GIT_AUTHOR_DATE": when,
            },
        )
        note_date = "2020-01-01"  # between 2019 and 2021
        (od / "notes" / "n.md").write_text(
            "---\ntype: decision\ntitle: git 时间判定测试\nstatus: stable\n"
            f"metadata:\n  date: {note_date}\n  related_modules:\n  - mcp\n---\n正文。\n",
            encoding="utf-8",
        )
        return od, "codewiki/mcp/tools/wiki_search.py"

    def test_commit_after_note_marks_stale(self, tmp_path):
        od, target = self._mk_git_repo(tmp_path, "2020-01-01", commit_after=True)
        out = _query(od, by_file=target)
        entries = out["file_knowledge"]["timeline"]
        assert entries
        assert entries[0]["possibly_stale"] is True

    def test_commit_before_note_marks_fresh(self, tmp_path):
        od, target = self._mk_git_repo(tmp_path, "2020-01-01", commit_after=False)
        out = _query(od, by_file=target)
        entries = out["file_knowledge"]["timeline"]
        assert entries
        assert entries[0]["possibly_stale"] is False

    def test_untracked_file_returns_null(self, tmp_path):
        od, target = self._mk_git_repo(tmp_path, "2020-01-01", commit_after=True)
        # Query a file that was never committed.
        out = _query(od, by_file="codewiki/mcp/tools/never_committed.py")
        # No notes match → empty timeline; staleness itself is untestable
        # through the timeline, so assert the helper directly.
        from codewiki.mcp.tools.knowledge_loop import _file_staleness

        repo_root = Path(od).resolve().parent
        assert (
            _file_staleness("2020-01-01", repo_root / "codewiki" / "mcp" / "tools" / "never_committed.py", repo_root)
            is None
        )

    def test_note_without_date_returns_null(self, tmp_path):
        from codewiki.mcp.tools.knowledge_loop import _file_staleness

        od = _mk_wiki(tmp_path)
        repo_root = Path(od).resolve().parent
        assert _file_staleness("", repo_root / "anything.py", repo_root) is None

    def test_staleness_disabled_config(self, tmp_path):
        od, target = self._mk_git_repo(tmp_path, "2020-01-01", commit_after=True)
        _schema_with(od, {"file_knowledge": {"stale_check": False}})
        out = _query(od, by_file=target)
        entries = out["file_knowledge"]["timeline"]
        assert entries
        assert "possibly_stale" not in entries[0]


# --------------------------------------------------------------------------- #
# P0-3: workflow embedded in the tool description
# --------------------------------------------------------------------------- #


class TestWorkflowDescription:
    def _get_tool(self):
        from codewiki.mcp.registry import get_all_tools

        return [t for t in get_all_tools() if t.name == "query_wiki"][0]

    def test_description_check_first(self):
        d = self._get_tool().description
        assert "RETRIEVAL STRATEGY" in d
        assert "mode=check" in d
        assert d.index("1) mode=check") < d.index("2) BM25")

    def test_description_expand_cost_warning(self):
        d = self._get_tool().description
        assert "est_tokens" in d
        assert "LAST RESORT" in d
        assert "by_file=<path>" in d

    def test_all_tool_schemas_serialize(self):
        import json as _json

        from codewiki.mcp.registry import get_all_tools

        for t in get_all_tools():
            _json.dumps(t.inputSchema)  # must not raise

    def test_query_no_longer_required_in_schema(self):
        tool = self._get_tool()
        assert tool.inputSchema.get("required") == []
        assert "by_file" in tool.inputSchema["properties"]
