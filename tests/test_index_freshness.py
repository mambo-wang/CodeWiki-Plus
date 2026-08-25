"""Tests for T1: index freshness self-healing + project.json relativisation.

Covers docs/团队知识库支持优化设计方案.md §3 acceptance criteria:
  - git-pull scenario: new note lands on disk → next search rebuilds and
    finds it (count/manifest tiers)
  - deleted note disappears from results after self-heal
  - content-only change (mtime tier): file count unchanged, mtimes newer
    than the build stamp → rebuild
  - 60s throttle: two consecutive calls scan only once
  - no index at all → caller's build-if-missing path (ensure_fresh passes)
  - project.json: relative paths written by analyze-side helper semantics;
    _resolve_db_path resolves relative cache_db against repo root; legacy
    absolute entries still honoured; missing absolute falls back to layout
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import index_freshness as fr
from codewiki.mcp.tools.knowledge_loop import handle_query_wiki
from codewiki.mcp.tools.wiki_search import (
    _resolve_db_path,
    build_full_index,
    search,
)


def _mk_wiki(tmp_path) -> Path:
    od = tmp_path / "repowiki"
    (od / "wiki" / "modules").mkdir(parents=True, exist_ok=True)
    (od / "notes").mkdir(exist_ok=True)
    (od / "wiki" / "modules" / "auth.md").write_text(
        "---\ntype: Module\ntitle: 认证模块\n---\n\n认证模块负责登录鉴权。\n",
        encoding="utf-8",
    )
    build_full_index(od, session=None)
    return od


def _reset_throttle():
    fr._last_check.clear()


class TestFreshnessSelfHeal:
    def test_new_note_found_after_pull(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _reset_throttle()
        # teammate's note arrives via (simulated) git pull
        (od / "notes" / "fresh-note.md").write_text(
            "---\ntype: pitfall\ntitle: 端口冲突排查\nstatus: stable\n---\n\n"
            "端口冲突用 lsof 排查。\n",
            encoding="utf-8",
        )
        res = search(od, "端口冲突", session=None)
        assert any(r["file"] == "notes/fresh-note.md" for r in res), \
            "pulled note must be findable after self-heal rebuild"

    def test_deleted_note_gone_after_heal(self, tmp_path):
        od = _mk_wiki(tmp_path)
        note = od / "notes" / "temp-note.md"
        note.write_text(
            "---\ntype: lesson\ntitle: 临时经验\n---\n\n临时内容 temporary lesson\n",
            encoding="utf-8",
        )
        _reset_throttle()
        search(od, "临时经验", session=None)  # indexed
        note.unlink()                          # (simulated) removed upstream
        _reset_throttle()
        res = search(od, "临时经验", session=None)
        assert not any(r["file"] == "notes/temp-note.md" for r in res)

    def test_content_only_change_rebuilds(self, tmp_path):
        od = _mk_wiki(tmp_path)
        note = od / "notes" / "confirmable.md"
        note.write_text(
            "---\ntype: pitfall\ntitle: 待确认笔记\nstatus: draft\n---\n\n"
            "正文提到特性关键字 featuremarker\n",
            encoding="utf-8",
        )
        _reset_throttle()
        search(od, "featuremarker", session=None)  # index the draft
        # teammate confirm: content changed, file count unchanged
        time.sleep(0.05)
        note.write_text(
            "---\ntype: pitfall\ntitle: 待确认笔记\nstatus: stable\n---\n\n"
            "正文提到特性关键字 featuremarker 且新增检索词 zonecheck\n",
            encoding="utf-8",
        )
        _reset_throttle()
        res = search(od, "zonecheck", session=None)
        assert any("confirmable" in r["file"] for r in res), \
            "content-only change must trigger rebuild via mtime sampling"

    def test_fresh_index_no_rebuild(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _reset_throttle()
        idx_path = od / ".meta" / "search_index.json"
        before = idx_path.read_text(encoding="utf-8")
        assert fr.ensure_fresh(od) is True
        assert idx_path.read_text(encoding="utf-8") == before  # untouched

    def test_throttle_single_scan_per_minute(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _reset_throttle()
        calls = []
        orig = fr.scan_disk_inventory
        def counting(od_):
            calls.append(1)
            return orig(od_)
        fr.scan_disk_inventory = counting
        try:
            fr.ensure_fresh(od)
            fr.ensure_fresh(od)
            fr.ensure_fresh(od)
        finally:
            fr.scan_disk_inventory = orig
        assert len(calls) == 1, "fresh verdicts must be throttled to one scan"

    def test_missing_index_passes(self, tmp_path):
        od = tmp_path / "repowiki"
        od.mkdir()
        _reset_throttle()
        assert fr.ensure_fresh(od) is True  # nothing to validate

    def test_handle_query_wiki_end_to_end_pull(self, tmp_path):
        od = _mk_wiki(tmp_path)
        _reset_throttle()
        (od / "wiki" / "modules" / "newmod.md").write_text(
            "---\ntype: Module\ntitle: 新模块文档\n---\n\n"
            "新模块处理供应链供应链追溯。\n",
            encoding="utf-8",
        )
        out = json.loads(handle_query_wiki(
            {"output_dir": str(od), "query": "供应链追溯"}, SessionStore()))
        assert any("newmod" in r["file"] for r in out["results"])


class TestProjectJsonRelative:
    def test_relative_cache_db_resolves(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / "repowiki" / ".meta").mkdir(parents=True)
        (repo / ".codewiki").mkdir()
        (repo / ".codewiki" / "analysis_cache.db").write_text("x", encoding="utf-8")
        (repo / "repowiki" / ".meta" / "project.json").write_text(
            json.dumps({"repo_name": "repo", "output_dir": "repowiki",
                        "cache_db": ".codewiki/analysis_cache.db"}),
            encoding="utf-8",
        )
        assert _resolve_db_path(repo / "repowiki") == \
            (repo / ".codewiki" / "analysis_cache.db").resolve()

    def test_legacy_absolute_still_works(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / "repowiki" / ".meta").mkdir(parents=True)
        db = tmp_path / "elsewhere" / "analysis_cache.db"
        db.parent.mkdir()
        db.write_text("x", encoding="utf-8")
        (repo / "repowiki" / ".meta" / "project.json").write_text(
            json.dumps({"cache_db": str(db)}), encoding="utf-8")
        assert _resolve_db_path(repo / "repowiki") == db.resolve()

    def test_missing_absolute_falls_back(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / "repowiki" / ".meta").mkdir(parents=True)
        (repo / ".codewiki").mkdir()
        fallback = repo / ".codewiki" / "analysis_cache.db"
        fallback.write_text("x", encoding="utf-8")
        (repo / "repowiki" / ".meta" / "project.json").write_text(
            json.dumps({"cache_db": "D:\\gone\\machine\\analysis_cache.db"}),
            encoding="utf-8")
        assert _resolve_db_path(repo / "repowiki") == fallback.resolve()

    def test_json_index_stores_built_at(self, tmp_path):
        od = _mk_wiki(tmp_path)
        data = json.loads(
            (od / ".meta" / "search_index.json").read_text(encoding="utf-8"))
        assert float(data.get("built_at") or 0) > 0


class TestT3IndexMdHealing:
    def test_index_md_rebuilt_on_stale(self, tmp_path):
        """T3: wiki/index.md is rebuilt alongside the search index when stale."""
        od = _mk_wiki(tmp_path)
        _reset_throttle()
        idx_md = od / "wiki" / "index.md"
        if idx_md.exists():
            idx_md.unlink()          # simulate a lost/corrupted catalog
        (od / "notes" / "another.md").write_text(   # trigger staleness
            "---\ntype: pitfall\ntitle: 另一踩坑\n---\n\n内容正文 bodytext\n",
            encoding="utf-8",
        )
        search(od, "bodytext", session=None)
        assert idx_md.exists(), "index.md must be rebuilt during self-heal"

    def test_gitignore_excludes_search_index(self):
        """T3: search_index.json stays out of version control."""
        import subprocess
        out = subprocess.run(
            ["git", "check-ignore", "repowiki/.meta/search_index.json"],
            cwd=str(Path(__file__).resolve().parents[1]),
            capture_output=True, text=True,
        )
        assert out.returncode == 0, "search_index.json must be gitignored"
