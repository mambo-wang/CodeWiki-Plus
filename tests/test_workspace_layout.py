"""Tests for ticket 02: workspace layout foundation.

Covers the workspace-resolution guardrails (single-repo zero impact,
unregistered-directory anti-hijack, tri-state fallback, caching) and the
init_workspace layout parameter (config write, idempotence, conflict,
conventions variant).

Handler invocation style follows test_workspace_bootstrap.py.
"""

from __future__ import annotations

import json

import pytest

from codewiki.mcp.tools import workspace_bootstrap as wb
from codewiki.mcp.tools import workspace_layout as wl

URL_A = "https://example.com/a.git"  # derived name: a


@pytest.fixture(autouse=True)
def _clear_layout_cache():
    wl.clear_cache()
    yield
    wl.clear_cache()


def _init(tmp_path, layout="colocated", **extra):
    # layout=None omits the argument entirely (decision-gate / adopt paths).
    args = {"workspace_path": str(tmp_path)}
    if layout is not None:
        args["layout"] = layout
    args.update(extra)
    return json.loads(wb.handle_init_workspace(args))


def _register(tmp_path, url=URL_A):
    return json.loads(
        wb.handle_add_workspace_repo({"workspace_path": str(tmp_path), "url": url, "clone": False})
    )


def _config_path(tmp_path):
    return tmp_path / "repowiki" / ".meta" / "workspace.json"


# ---------------------------------------------------------------------------
# Resolution guardrails
# ---------------------------------------------------------------------------
class TestResolutionGuardrails:
    def test_single_repo_no_workspace(self, tmp_path):
        """Single-repo scenario: no workspace.json anywhere → status quo."""
        repo = tmp_path / "myrepo"
        repo.mkdir()
        res = wl.resolve_workspace(repo)
        assert res.root is None
        assert res.layout == wl.LAYOUT_COLOCATED
        assert res.member is False
        assert res.centralized is False

    def test_centralized_registered_member(self, tmp_path):
        _init(tmp_path, layout="centralized")
        _register(tmp_path)
        repo = tmp_path / "a"
        repo.mkdir(exist_ok=True)
        res = wl.resolve_workspace(repo)
        assert res.root == tmp_path.resolve()
        assert res.layout == wl.LAYOUT_CENTRALIZED
        assert res.member is True
        assert res.centralized is True

    def test_unregistered_dir_not_hijacked(self, tmp_path):
        """A stray clone inside the workspace tree keeps status-quo paths."""
        _init(tmp_path, layout="centralized")
        _register(tmp_path)
        stray = tmp_path / "stray"
        stray.mkdir()
        res = wl.resolve_workspace(stray)
        assert res.root == tmp_path.resolve()
        assert res.member is False
        assert res.centralized is False

    def test_colocated_config_no_central_routing(self, tmp_path):
        _init(tmp_path)  # colocated config persisted by init
        _register(tmp_path)
        repo = tmp_path / "a"
        repo.mkdir(exist_ok=True)
        res = wl.resolve_workspace(repo)
        assert res.member is True
        assert res.layout == wl.LAYOUT_COLOCATED
        assert res.centralized is False

    def test_malformed_config_falls_back_to_colocated(self, tmp_path):
        _init(tmp_path, layout="centralized")
        _register(tmp_path)
        _config_path(tmp_path).write_text("{not json", encoding="utf-8")
        repo = tmp_path / "a"
        repo.mkdir(exist_ok=True)
        res = wl.resolve_workspace(repo)
        assert res.layout == wl.LAYOUT_COLOCATED
        assert res.centralized is False

    def test_nested_repo_path_resolves_via_first_component(self, tmp_path):
        _init(tmp_path, layout="centralized")
        _register(tmp_path)
        nested = tmp_path / "a" / "src" / "deep"
        nested.mkdir(parents=True)
        res = wl.resolve_workspace(nested)
        assert res.member is True
        assert res.centralized is True

    def test_registration_table_alone_is_not_a_workspace(self, tmp_path):
        """Guardrail 1: the bootstrap table is NOT a discovery signal."""
        # Simulate a legacy workspace: registration table present but the
        # layout config absent — discovery must not fire on the table.
        _init(tmp_path)
        _config_path(tmp_path).unlink()
        _register(tmp_path)
        repo = tmp_path / "a"
        repo.mkdir(exist_ok=True)
        res = wl.resolve_workspace(repo)
        assert res.root is None
        assert res.centralized is False

    def test_workspace_root_itself_is_not_a_member(self, tmp_path):
        _init(tmp_path, layout="centralized")
        res = wl.resolve_workspace(tmp_path)
        assert res.root == tmp_path.resolve()
        assert res.member is False
        assert res.centralized is False

    def test_cache_holds_until_cleared(self, tmp_path):
        _init(tmp_path, layout="centralized")
        _register(tmp_path)
        repo = tmp_path / "a"
        repo.mkdir(exist_ok=True)
        assert wl.resolve_workspace(repo).centralized is True
        # Delete the config behind the cache's back.
        _config_path(tmp_path).unlink()
        assert wl.resolve_workspace(repo).centralized is True  # cached
        wl.clear_cache()
        assert wl.resolve_workspace(repo).centralized is False  # re-resolved


# ---------------------------------------------------------------------------
# init_workspace layout parameter
# ---------------------------------------------------------------------------
class TestInitLayout:
    def test_centralized_writes_config_and_skeleton(self, tmp_path):
        res = _init(tmp_path, layout="centralized")
        assert res["status"] == "ok"
        assert res["layout"] == "centralized"
        config = _config_path(tmp_path)
        assert json.loads(config.read_text(encoding="utf-8")) == {"wiki_layout": "centralized"}
        # Skeleton: modules partition root + shared pools + repo-map.
        assert (tmp_path / "repowiki" / "wiki" / "modules").is_dir()
        assert (tmp_path / "repowiki" / "wiki" / "entities").is_dir()
        assert (tmp_path / "repowiki" / "notes").is_dir()
        assert (tmp_path / "repowiki" / "wiki" / "repo-map.md").is_file()

    def test_centralized_init_idempotent(self, tmp_path):
        first = _init(tmp_path, layout="centralized")
        assert first["status"] == "ok"
        config_text = _config_path(tmp_path).read_text(encoding="utf-8")
        second = _init(tmp_path, layout="centralized")
        assert second["status"] == "ok"
        assert second["workspace_config"].startswith("kept")
        assert _config_path(tmp_path).read_text(encoding="utf-8") == config_text

    def test_colocated_init_writes_config(self, tmp_path):
        """Both layouts persist their decision to workspace.json."""
        res = _init(tmp_path)
        assert res["status"] == "ok"
        assert res["layout"] == wl.LAYOUT_COLOCATED
        config = _config_path(tmp_path)
        assert json.loads(config.read_text(encoding="utf-8")) == {"wiki_layout": "colocated"}
        assert res["workspace_config"].endswith("workspace.json")

    def test_rerun_adopts_persisted_layout(self, tmp_path):
        _init(tmp_path, layout="centralized")
        res = _init(tmp_path, layout=None)  # no-layout re-run: adopt, never fight
        assert res["status"] == "ok"
        assert res["layout"] == "centralized"
        assert res["workspace_config"].startswith("kept")

    def test_layout_conflict_is_an_error(self, tmp_path):
        _init(tmp_path, layout="centralized")
        res = _init(tmp_path, layout="colocated")  # explicit conflicting value
        assert "error" in res
        assert "refusing" in res["error"]

    def test_invalid_layout_value(self, tmp_path):
        res = _init(tmp_path, layout="hub")
        assert "error" in res
        assert "invalid layout" in res["error"]
        assert not _config_path(tmp_path).exists()

    def test_conventions_variant_centralized(self, tmp_path):
        _init(tmp_path, layout="centralized")
        agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "一跳" in agents
        assert "集中式知识布局" in agents

    def test_conventions_variant_colocated_default(self, tmp_path):
        _init(tmp_path)
        agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "两跳" in agents
        assert "集中式知识布局" not in agents

    def test_centralized_reinit_switches_variant(self, tmp_path):
        _init(tmp_path)  # colocated block written
        _init(tmp_path, layout="centralized")  # block always refreshed
        agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "一跳" in agents

    def test_centralized_rejects_custom_output_dir(self, tmp_path):
        """Discovery is anchored at <workspace>/repowiki — a custom output_dir
        would make the layout config invisible to routing."""
        res = _init(tmp_path, layout="centralized", output_dir="custom-wiki")
        assert "error" in res
        assert "output_dir" in res["error"]
        assert not (tmp_path / "custom-wiki" / ".meta" / "workspace.json").exists()


# ---------------------------------------------------------------------------
# Ticket 03: add_workspace_repo under centralized layout
# ---------------------------------------------------------------------------
_CODEWIKI_BLOCK = (
    "<!-- CodeWiki LLM Wiki -->\n\n## CodeWiki LLM Wiki\n\nblock body\n\n"
    "<!-- /CodeWiki LLM Wiki -->"
)


class TestAddRepoLayout:
    def test_add_centralized_creates_partition_and_strips_block(self, tmp_path):
        _init(tmp_path, layout="centralized")
        repo = tmp_path / "a"
        repo.mkdir()
        # Business repo carries its own conventions + a CodeWiki usage block.
        (repo / "AGENTS.md").write_text(
            f"# Repo conventions\n\nkeep me\n\n{_CODEWIKI_BLOCK}\n\ntail\n",
            encoding="utf-8",
        )

        res = _register(tmp_path)
        assert res["status"] == "ok"
        assert res["layout"] == "centralized"

        # Partition skeleton in the workspace repowiki, none inside the repo.
        partition = tmp_path / "repowiki" / "wiki" / "modules" / "a"
        assert (partition / ".gitkeep").is_file()
        assert not (repo / "repowiki").exists()
        assert "modules_partition" in res

        # Dead CodeWiki block removed; the repo's own content preserved.
        agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
        assert "CodeWiki LLM Wiki" not in agents
        assert "keep me" in agents
        assert "tail" in agents
        assert res["agents_md_codewiki_block"] == "removed"

        # repo-map carries the centralized variant.
        repo_map = (tmp_path / "repowiki" / "wiki" / "repo-map.md").read_text(encoding="utf-8")
        assert "repowiki/wiki/modules/a/" in repo_map
        assert 'repo="a"' in repo_map

    def test_add_colocated_behaviour_unchanged(self, tmp_path):
        _init(tmp_path)  # colocated default
        repo = tmp_path / "a"
        repo.mkdir()
        (repo / "AGENTS.md").write_text(f"x\n\n{_CODEWIKI_BLOCK}\n", encoding="utf-8")

        res = _register(tmp_path)
        assert res["layout"] == "colocated"
        assert "modules_partition" not in res
        assert not (tmp_path / "repowiki" / "wiki" / "modules" / "a").exists()

        # Block kept; repo-map uses the two-hop variant.
        assert "CodeWiki LLM Wiki" in (repo / "AGENTS.md").read_text(encoding="utf-8")
        repo_map = (tmp_path / "repowiki" / "wiki" / "repo-map.md").read_text(encoding="utf-8")
        assert "a/repowiki" in repo_map

    def test_add_centralized_repo_dir_absent(self, tmp_path):
        _init(tmp_path, layout="centralized")
        # clone=False and no pre-created directory (clone failed / pending).
        res = _register(tmp_path)
        assert res["status"] == "ok"
        assert res["agents_md_codewiki_block"] == "skipped (repo directory not present)"

    def test_add_centralized_partition_idempotent(self, tmp_path):
        _init(tmp_path, layout="centralized")
        (tmp_path / "a").mkdir()
        _register(tmp_path)
        res = _register(tmp_path)  # same name+URL: registration no-op
        assert res["modules_partition"].startswith("kept")
