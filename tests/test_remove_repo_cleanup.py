"""Tests for ticket 10: remove_workspace_repo centralized knowledge cleanup.

Deregistering a repo under centralized also cleans the workspace knowledge
base: the modules partition is deleted and shared-pool provenance is scrubbed
(multi-source pages lose just this repo; sole-source pages keep their content
but are untagged, becoming orphans that lint surfaces — knowledge is never
auto-deleted). Colocated removal is unchanged.
"""

from __future__ import annotations

import json

import pytest

from codewiki.mcp.tools import workspace_bootstrap as wb
from codewiki.mcp.tools import workspace_layout as wl
from codewiki.mcp.tools.wiki_lint import handle_lint_wiki

URL_A = "https://example.com/a.git"
URL_B = "https://example.com/b.git"


class _StubStore:
    def find_or_restore(self, repo_path):
        return None

    def get(self, session_id):
        return None


@pytest.fixture(autouse=True)
def _clear_layout_cache():
    wl.clear_cache()
    yield
    wl.clear_cache()


def _setup(tmp_path):
    json.loads(wb.handle_init_workspace({"workspace_path": str(tmp_path), "layout": "centralized"}))
    for url in (URL_A, URL_B):
        name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        (tmp_path / name).mkdir(exist_ok=True)
        json.loads(
            wb.handle_add_workspace_repo(
                {"workspace_path": str(tmp_path), "url": url, "clone": False}
            )
        )
    return tmp_path


def _remove(tmp_path, name):
    return json.loads(
        wb.handle_remove_workspace_repo(
            {"workspace_path": str(tmp_path), "name": name}
        )
    )


def _write_entity(tmp_path, name, prov_line):
    d = tmp_path / "repowiki" / "wiki" / "entities"
    d.mkdir(parents=True, exist_ok=True)
    fm = "---\ntype: Entity\ntitle: " + json.dumps(name) + "\n"
    if prov_line:
        fm += prov_line + "\n"
    fm += "---\n\n" + name + " body\n"
    (d / f"{name}.md").write_text(fm, encoding="utf-8")
    return d / f"{name}.md"


class TestRemoveCentralizedCleanup:
    def test_full_cleanup(self, tmp_path):
        ws = _setup(tmp_path)
        # a's module partition with content
        part = ws / "repowiki" / "wiki" / "modules" / "a"
        part.mkdir(parents=True, exist_ok=True)
        (part / "mod.md").write_text("# mod\n", encoding="utf-8")
        # shared pages: multi-source, sole-source-a, and a global one
        multi = _write_entity(ws, "Multi", 'repos: ["a", "b"]')
        only_a = _write_entity(ws, "OnlyA", 'repo: "a"')
        glob = _write_entity(ws, "Glob", None)

        res = _remove(ws, "a")
        assert res["status"] == "ok"

        kc = res["knowledge_cleanup"]
        assert kc["modules_partition"] == "deleted"
        assert kc["pages_updated"] == 1  # Multi lost just "a"
        assert kc["pages_orphaned"] == 1  # OnlyA untagged

        # partition gone
        assert not part.exists()
        # Multi now sourced only by b
        assert wl.read_provenance(multi.read_text(encoding="utf-8")) == {"b"}
        # OnlyA keeps content, loses tag (orphan for a human to resolve)
        text = only_a.read_text(encoding="utf-8")
        assert wl.read_provenance(text) == set()
        assert "OnlyA body" in text
        # global page untouched
        assert "Glob body" in glob.read_text(encoding="utf-8")

        # registration gone from the four artifacts
        assert "a" not in wb.read_registration_table_names(ws)
        assert "/a/" not in (ws / ".gitignore").read_text(encoding="utf-8")
        repo_map = (ws / "repowiki" / "wiki" / "repo-map.md").read_text(encoding="utf-8")
        assert "## a" not in repo_map
        # clone dir deleted along with the registration
        assert not (ws / "a").exists()

    def test_orphan_surfaced_by_lint(self, tmp_path):
        ws = _setup(tmp_path)
        _write_entity(ws, "OnlyA", 'repo: "a"')
        _remove(ws, "a")
        res = json.loads(
            handle_lint_wiki(
                {"output_dir": str(ws / "repowiki"), "checks": ["layout_violations"]},
                _StubStore(),
            )
        )
        infos = [
            i
            for i in res.get("issues", [])
            if i.get("check") == "layout_violations" and i["severity"] == "info"
        ]
        assert any(i["file"].endswith("OnlyA.md") for i in infos)

    def test_repo_query_after_removal(self, tmp_path):
        """The removed repo's partition and tags no longer feed repo= queries."""
        from codewiki.mcp.tools.knowledge_loop import _repo_scope_match

        ws = _setup(tmp_path)
        part = ws / "repowiki" / "wiki" / "modules" / "a"
        part.mkdir(parents=True, exist_ok=True)
        (part / "mod.md").write_text("# mod\n", encoding="utf-8")
        only_a = _write_entity(ws, "OnlyA", 'repo: "a"')
        _remove(ws, "a")
        od = ws / "repowiki"
        # partition file physically gone → nothing to match
        assert not (part / "mod.md").exists()
        # the orphaned page now matches every repo scope (global), which is
        # exactly the "human decides" state — it no longer claims repo a only
        assert wl.read_provenance(only_a.read_text(encoding="utf-8")) == set()
        assert _repo_scope_match(od, "wiki/entities/OnlyA.md", "b") is True

    def test_colocated_removal_unchanged(self, tmp_path):
        json.loads(wb.handle_init_workspace({"workspace_path": str(tmp_path)}))
        (tmp_path / "a").mkdir(exist_ok=True)
        json.loads(
            wb.handle_add_workspace_repo(
                {"workspace_path": str(tmp_path), "url": URL_A, "clone": False}
            )
        )
        res = json.loads(
            wb.handle_remove_workspace_repo(
                {"workspace_path": str(tmp_path), "name": "a"}
            )
        )
        assert res["status"] == "ok"
        assert "knowledge_cleanup" not in res  # nothing to clean
        assert "a" not in wb.read_registration_table_names(tmp_path)

    def test_unregistered_name_safe_error(self, tmp_path):
        ws = _setup(tmp_path)
        res = json.loads(
            wb.handle_remove_workspace_repo(
                {"workspace_path": str(ws), "name": "ghost"}
            )
        )
        assert "error" in res
        # registered repos untouched
        assert wb.read_registration_table_names(ws) == {"a", "b"}


def _seed_analysis_artifacts(ws):
    """Seed analyze_workspace caches + a generated-style overview.md."""
    meta = ws / "repowiki" / ".meta"
    meta.mkdir(parents=True, exist_ok=True)
    routes = [
        {"route_key": "__route__GET__/a", "path": "/a", "repo_name": "a"},
        {"route_key": "__route__GET__/b", "path": "/b", "repo_name": "b"},
    ]
    links = [
        {"route_key": "__route__GET__/b", "client_repo": "a", "server_repo": "b"},
        {"route_key": "__route__GET__/a", "client_repo": "b", "server_repo": "a"},
        {"route_key": "__route__GET__/b2", "client_repo": "b", "server_repo": "b"},
    ]
    infra = {
        "svc-a": {
            "name": "svc-a",
            "ports": [8080],
            "source": "docker-compose",
            "source_path": "a/docker-compose.yml",
        },
        "svc-b": {
            "name": "svc-b",
            "ports": [9090],
            "source": "docker-compose",
            "source_path": "b/docker-compose.yml",
        },
        # pre-attribution cache entry: no source_path → must be kept
        "legacy-svc": {"name": "legacy-svc", "ports": [], "source": "docker-compose"},
    }
    (meta / "workspace_routes.json").write_text(json.dumps(routes), encoding="utf-8")
    (meta / "cross_service_links.json").write_text(json.dumps(links), encoding="utf-8")
    (meta / "infra_services.json").write_text(json.dumps(infra), encoding="utf-8")

    overview = "\n".join(
        [
            "# ws — Workspace Overview",
            "",
            "## Services",
            "",
            "| Service | Path | Languages | Components | Wiki |",
            "|---------|------|-----------|------------|------|",
            "| a | `a` | python | 10 | [wiki](../a/repowiki/wiki/) |",
            "| b | `b` | python | 20 | [wiki](../b/repowiki/wiki/) |",
            "",
            "## Infrastructure Services",
            "",
            "| Service | Type | Port(s) |",
            "|---------|------|---------|",
            "| svc-a | docker-compose | 8080 |",
            "| svc-b | docker-compose | 9090 |",
            "",
            "## Service Overviews",
            "",
            "- [a](../a/repowiki/wiki/overview.md) — `a`",
            "- [b](../b/repowiki/wiki/overview.md) — `b`",
        ]
    )
    (ws / "repowiki" / "overview.md").write_text(overview, encoding="utf-8")


class TestRemoveAnalysisArtifacts:
    def test_meta_and_overview_cleaned(self, tmp_path):
        ws = _setup(tmp_path)
        _seed_analysis_artifacts(ws)

        res = _remove(ws, "a")
        assert res["status"] == "ok"

        ac = res["analysis_cleanup"]
        assert ac["routes_removed"] == 1
        assert ac["links_removed"] == 2  # a→b and b→a; b→b stays
        assert ac["infra_removed"] == ["svc-a"]
        assert ac["overview"]["services_row"] == "removed"
        assert ac["overview"]["overviews_bullet"] == "removed"
        assert ac["overview"]["infra_rows"] == 1

        meta = ws / "repowiki" / ".meta"
        routes = json.loads((meta / "workspace_routes.json").read_text(encoding="utf-8"))
        assert [r["repo_name"] for r in routes] == ["b"]
        links = json.loads((meta / "cross_service_links.json").read_text(encoding="utf-8"))
        assert [(link["client_repo"], link["server_repo"]) for link in links] == [("b", "b")]
        infra = json.loads((meta / "infra_services.json").read_text(encoding="utf-8"))
        assert set(infra) == {"svc-b", "legacy-svc"}  # no attribution → kept

        overview = (ws / "repowiki" / "overview.md").read_text(encoding="utf-8")
        assert "| a |" not in overview
        assert "- [a](" not in overview
        assert "| svc-a |" not in overview
        assert "| b | `b` |" in overview
        assert "- [b](" in overview
        assert "| svc-b |" in overview

    def test_removal_without_artifacts_safe(self, tmp_path):
        ws = _setup(tmp_path)  # no analyze_workspace ever ran
        res = _remove(ws, "a")
        assert res["status"] == "ok"
        ac = res["analysis_cleanup"]
        assert ac["routes_removed"] == 0
        assert ac["links_removed"] == 0
        assert ac["infra_removed"] == []
        assert ac["overview"] == "skipped (overview.md not found)"

    def test_colocated_also_cleans_meta(self, tmp_path):
        json.loads(wb.handle_init_workspace({"workspace_path": str(tmp_path)}))
        (tmp_path / "a").mkdir(exist_ok=True)
        json.loads(
            wb.handle_add_workspace_repo(
                {"workspace_path": str(tmp_path), "url": URL_A, "clone": False}
            )
        )
        _seed_analysis_artifacts(tmp_path)
        res = json.loads(
            wb.handle_remove_workspace_repo(
                {"workspace_path": str(tmp_path), "name": "a"}
            )
        )
        assert res["status"] == "ok"
        assert "knowledge_cleanup" not in res  # colocated: no shared knowledge
        # but workspace-level analysis caches are still scrubbed
        assert res["analysis_cleanup"]["routes_removed"] == 1
        routes = json.loads(
            (tmp_path / "repowiki" / ".meta" / "workspace_routes.json").read_text(
                encoding="utf-8"
            )
        )
        assert [r["repo_name"] for r in routes] == ["b"]  # a's route gone, b stays

    def test_infra_source_path_attribution(self, tmp_path):
        from codewiki.src.be.dependency_analyzer.analysis.infra_scanner import InfraScanner

        sub = tmp_path / "repoA"
        sub.mkdir()
        (sub / "docker-compose.yml").write_text(
            "services:\n  web:\n    ports:\n      - '8080:80'\n", encoding="utf-8"
        )
        services = InfraScanner(str(tmp_path)).scan()
        assert services["web"].source_path == "repoA/docker-compose.yml"
        assert services["web"].to_dict()["source_path"] == "repoA/docker-compose.yml"
