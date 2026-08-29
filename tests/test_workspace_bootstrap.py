"""Tests for workspace_bootstrap: init_workspace / add_workspace_repo /
remove_workspace_repo MCP tools.

Direct handler invocation style (no MCP server round-trip), tmp_path based.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from codewiki.mcp.tools import workspace_bootstrap as wb
from codewiki.mcp.tools.agents_md import (
    _BEGIN_MARKER,
    _END_MARKER,
    _WORKSPACE_BEGIN_MARKER,
)

URL_A = "https://example.com/a.git"  # derived name: a
URL_B = "https://example.com/b.git"  # derived name: b
URL_C = "https://example.com/repo-c.git"  # derived name: repo-c


def _init(tmp_path, **extra):
    args = {"workspace_path": str(tmp_path)}
    args.update(extra)
    return json.loads(wb.handle_init_workspace(args))


def _add(tmp_path, url, clone=False, **extra):
    args = {"workspace_path": str(tmp_path), "url": url, "clone": clone}
    args.update(extra)
    return json.loads(wb.handle_add_workspace_repo(args))


def _remove(tmp_path, name):
    return json.loads(
        wb.handle_remove_workspace_repo(
            {"workspace_path": str(tmp_path), "name": name}
        )
    )


def _read(path):
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Name derivation from URL
# ---------------------------------------------------------------------------
class TestDeriveName:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://github.com/org/Repo-Name.git", "Repo-Name"),
            ("https://github.com/org/repo/", "repo"),
            ("git@github.com:org/repo.git", "repo"),
            ("ssh://git@host:2222/org/repo.git", "repo"),
            ("file:///path/to/local-repo", "local-repo"),
            ("D:/path/to/local-repo", "local-repo"),
        ],
    )
    def test_derives(self, url, expected):
        assert wb._derive_repo_name(url) == expected

    def test_invalid_derivations(self):
        assert wb._derive_repo_name("") == ""
        assert wb._derive_repo_name("https://example.com/.git") == ""


# ---------------------------------------------------------------------------
# 1. Fresh init
# ---------------------------------------------------------------------------
class TestFreshInit:
    def test_all_artifacts_created(self, tmp_path):
        res = _init(tmp_path)
        assert res["status"] == "ok"
        assert res["bootstrap_scripts"] == "created"
        assert res["name"] == tmp_path.name

        sh = _read(tmp_path / "bootstrap.sh")
        ps1 = _read(tmp_path / "bootstrap.ps1")
        assert "declare -A repos=(" in sh  # empty table still valid structure
        assert "$repos = [ordered]@{" in ps1

        gi = _read(tmp_path / ".gitignore")
        assert "/workspace-wiki/" not in gi  # analysis artifacts live in committed repowiki

        repo_map = _read(tmp_path / "repowiki" / "wiki" / "repo-map.md")
        assert "| 业务仓 |" in repo_map  # header only, no rows yet
        assert "用 add_workspace_repo(url=<克隆URL>) 添加" in repo_map

        agents = _read(tmp_path / "AGENTS.md")
        assert _WORKSPACE_BEGIN_MARKER in agents
        assert _BEGIN_MARKER in agents
        assert agents.index(_WORKSPACE_BEGIN_MARKER) < agents.index(_BEGIN_MARKER)

        assert (tmp_path / "repowiki" / "schema.yaml").exists()
        assert (tmp_path / "repowiki" / "wiki" / "modules").is_dir()
        assert (tmp_path / "README.md").exists()


# ---------------------------------------------------------------------------
# 2/3. Idempotency and refresh semantics
# ---------------------------------------------------------------------------
class TestIdempotency:
    def test_rerun_refreshes_conventions_block(self, tmp_path):
        _init(tmp_path)
        agents_path = tmp_path / "AGENTS.md"
        customized = (
            _read(agents_path).replace("## 分支策略", "## 分支策略（团队定制版）")
            + "\n用户自己追加的尾部内容\n"
        )
        agents_path.write_text(customized, encoding="utf-8")

        res = _init(tmp_path)
        assert res["status"] == "ok"
        assert res["agents_md_conventions"] == "refreshed"
        new_text = _read(agents_path)
        assert "团队定制版" not in new_text  # in-block edits clobbered
        assert "用户自己追加的尾部内容" in new_text  # outside block kept

    def test_rerun_preserves_other_artifacts(self, tmp_path):
        _init(tmp_path)

        schema_path = tmp_path / "repowiki" / "schema.yaml"
        schema_path.write_text("purpose: customized\n", encoding="utf-8")
        sh_before = (tmp_path / "bootstrap.sh").read_bytes()

        res = _init(tmp_path)
        assert res["status"] == "ok"
        assert _read(schema_path) == "purpose: customized\n"
        assert (tmp_path / "bootstrap.sh").read_bytes() == sh_before


# ---------------------------------------------------------------------------
# 4. Invalid workspace_path
# ---------------------------------------------------------------------------
class TestInvalidWorkspace:
    def test_nonexistent_path(self, tmp_path):
        res = json.loads(wb.handle_init_workspace({"workspace_path": str(tmp_path / "nope")}))
        assert "error" in res
        assert not (tmp_path / "nope").exists()

    def test_path_is_file(self, tmp_path):
        f = tmp_path / "afile"
        f.write_text("x", encoding="utf-8")
        res = json.loads(wb.handle_init_workspace({"workspace_path": str(f)}))
        assert "error" in res

    def test_workspace_path_defaults_to_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        res = json.loads(wb.handle_init_workspace({}))
        assert res["status"] == "ok"
        assert res["workspace_path"] == str(tmp_path)
        assert (tmp_path / "bootstrap.sh").exists()
        assert (tmp_path / "AGENTS.md").exists()


# ---------------------------------------------------------------------------
# 5/6/7. add_workspace_repo flows
# ---------------------------------------------------------------------------
class TestAddRepo:
    def test_full_flow(self, tmp_path):
        _init(tmp_path)
        gi_path = tmp_path / ".gitignore"
        gi_path.write_text(_read(gi_path) + "\n# 用户自定义规则\n*.secret\n", encoding="utf-8")

        res = _add(tmp_path, URL_C)
        assert res["status"] == "ok"
        assert res["name"] == "repo-c"
        assert res["bootstrap_sh"] == "registered"
        assert res["bootstrap_ps1"] == "registered"

        assert '["repo-c"]="https://example.com/repo-c.git"' in _read(tmp_path / "bootstrap.sh")
        assert '"repo-c" = "https://example.com/repo-c.git"' in _read(tmp_path / "bootstrap.ps1")

        gi = _read(gi_path)
        assert "/repo-c/" in gi
        assert "*.secret" in gi  # user rules preserved

        repo_map = _read(tmp_path / "repowiki" / "wiki" / "repo-map.md")
        assert "| repo-c | `repo-c/`" in repo_map
        assert "## repo-c（`repo-c/`）" in repo_map

    def test_duplicate_same_url_is_noop(self, tmp_path):
        _init(tmp_path)
        first = _add(tmp_path, URL_A)
        assert first["bootstrap_sh"] == "registered"

        sh_before = (tmp_path / "bootstrap.sh").read_bytes()
        ps_before = (tmp_path / "bootstrap.ps1").read_bytes()
        gi_before = (tmp_path / ".gitignore").read_bytes()
        map_before = (tmp_path / "repowiki" / "wiki" / "repo-map.md").read_bytes()

        res = _add(tmp_path, URL_A)
        assert res["status"] == "ok"
        assert res["bootstrap_sh"] == "already_registered"
        assert res["bootstrap_ps1"] == "already_registered"
        assert (tmp_path / "bootstrap.sh").read_bytes() == sh_before
        assert (tmp_path / "bootstrap.ps1").read_bytes() == ps_before
        assert (tmp_path / ".gitignore").read_bytes() == gi_before
        assert (tmp_path / "repowiki" / "wiki" / "repo-map.md").read_bytes() == map_before

    def test_conflicting_url_writes_nothing(self, tmp_path):
        _init(tmp_path)
        _add(tmp_path, URL_A)  # registers name "a"
        snapshots = {
            p: p.read_bytes()
            for p in (
                tmp_path / "bootstrap.sh",
                tmp_path / "bootstrap.ps1",
                tmp_path / ".gitignore",
                tmp_path / "repowiki" / "wiki" / "repo-map.md",
            )
        }
        # same derived name "a" but a different URL -> hard error, no writes
        res = _add(tmp_path, "https://evil.example/a.git")
        assert "error" in res
        for p, before in snapshots.items():
            assert p.read_bytes() == before

    def test_uninitialized_workspace(self, tmp_path):
        res = _add(tmp_path, URL_C)
        assert "error" in res
        assert "init_workspace" in res["error"]

    def test_broken_sh_table(self, tmp_path):
        _init(tmp_path)
        sh_path = tmp_path / "bootstrap.sh"
        sh_path.write_text(
            _read(sh_path).replace("declare -A repos=(", "repos=("), encoding="utf-8"
        )
        res = _add(tmp_path, URL_C)
        assert "error" in res
        assert "bootstrap.sh" in res["error"]

    def test_broken_ps_table(self, tmp_path):
        _init(tmp_path)
        ps_path = tmp_path / "bootstrap.ps1"
        ps_path.write_text(
            _read(ps_path).replace("$repos = [ordered]@{", "$repos = @{"),
            encoding="utf-8",
        )
        res = _add(tmp_path, URL_C)
        assert "error" in res
        assert "bootstrap.ps1" in res["error"]

    @pytest.mark.parametrize(
        "url",
        [
            "",  # empty url -> empty derived name
            'https://example.com/"x".git',  # quote in url
            "https://example.com/bad name.git",  # derived name contains a space
            "https://example.com/.git",  # derived name is empty
        ],
    )
    def test_invalid_inputs(self, tmp_path, url):
        _init(tmp_path)
        res = _add(tmp_path, url)
        assert "error" in res


# ---------------------------------------------------------------------------
# 8. remove_workspace_repo flows
# ---------------------------------------------------------------------------
class TestRemoveRepo:
    def test_remove_deletes_directory(self, tmp_path):
        _init(tmp_path)
        _add(tmp_path, URL_A)
        clone_dir = tmp_path / "a"
        clone_dir.mkdir()
        (clone_dir / "README.md").write_text("clone", encoding="utf-8")

        res = _remove(tmp_path, "a")
        assert res["status"] == "ok"
        assert res["bootstrap_sh"] == "removed"
        assert res["bootstrap_ps1"] == "removed"
        assert res["gitignore"]["status"] == "removed"
        assert res["repo_map"]["nav_row"] == "removed"
        assert res["repo_map"]["section"] == "removed"
        assert res["directory"] == "deleted"

        assert '["a"]="https://example.com/a.git"' not in _read(tmp_path / "bootstrap.sh")
        assert '"a" = "https://example.com/a.git"' not in _read(tmp_path / "bootstrap.ps1")
        assert "/a/" not in _read(tmp_path / ".gitignore")
        repo_map = _read(tmp_path / "repowiki" / "wiki" / "repo-map.md")
        assert "| a | `a/`" not in repo_map
        assert "## a（`a/`）" not in repo_map
        assert not clone_dir.exists()  # directory deleted

    def test_remove_absent_directory_ok(self, tmp_path):
        _init(tmp_path)
        _add(tmp_path, URL_A)
        # never cloned — removal must still succeed
        res = _remove(tmp_path, "a")
        assert res["status"] == "ok"
        assert res["directory"] == "not present"
        assert not (tmp_path / "a").exists()

    def test_remove_not_registered_is_safe_error(self, tmp_path):
        _init(tmp_path)
        res = _remove(tmp_path, "ghost")
        assert "error" in res
        assert "not registered" in res["error"]

    def test_remove_uninitialized(self, tmp_path):
        res = _remove(tmp_path, "ghost")
        assert "error" in res
        assert "init_workspace" in res["error"]

    def test_remove_keeps_other_repos(self, tmp_path):
        _init(tmp_path)
        _add(tmp_path, URL_A)
        _add(tmp_path, URL_B)

        res = _remove(tmp_path, "a")
        assert res["status"] == "ok"

        assert '["b"]="https://example.com/b.git"' in _read(tmp_path / "bootstrap.sh")
        assert '"b" = "https://example.com/b.git"' in _read(tmp_path / "bootstrap.ps1")
        assert "/b/" in _read(tmp_path / ".gitignore")
        repo_map = _read(tmp_path / "repowiki" / "wiki" / "repo-map.md")
        assert "## b（`b/`）" in repo_map
        assert "## a（`a/`）" not in repo_map

    def test_remove_broken_table(self, tmp_path):
        _init(tmp_path)
        _add(tmp_path, URL_A)
        sh_path = tmp_path / "bootstrap.sh"
        sh_path.write_text(
            _read(sh_path).replace("declare -A repos=(", "repos=("), encoding="utf-8"
        )
        res = _remove(tmp_path, "a")
        assert "error" in res
        assert "bootstrap.sh" in res["error"]


# ---------------------------------------------------------------------------
# 9. Clone behavior (monkeypatched subprocess)
# ---------------------------------------------------------------------------
class _FakeProc:
    def __init__(self, returncode, stderr=""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = ""


class TestClone:
    def test_clone_success(self, tmp_path, monkeypatch):
        _init(tmp_path)
        calls = []
        monkeypatch.setattr(
            wb.subprocess,
            "run",
            lambda cmd, **kw: (calls.append(cmd), _FakeProc(0))[1],
        )
        res = _add(tmp_path, URL_C, clone=True)
        assert res["clone"]["status"] == "ok"
        assert calls and calls[0][:2] == ["git", "clone"]

    def test_clone_failure_keeps_registration(self, tmp_path, monkeypatch):
        _init(tmp_path)
        monkeypatch.setattr(
            wb.subprocess, "run", lambda cmd, **kw: _FakeProc(128, "fatal: ssl error")
        )
        res = _add(tmp_path, URL_C, clone=True)
        assert res["status"] == "ok"
        assert res["clone"]["status"] == "error"
        assert "ssl error" in res["clone"]["detail"]
        assert res["warnings"]
        assert '["repo-c"]' in _read(tmp_path / "bootstrap.sh")  # registration kept

    def test_existing_git_dir_skipped(self, tmp_path, monkeypatch):
        _init(tmp_path)
        dest = tmp_path / "repo-c" / ".git"
        dest.mkdir(parents=True)

        def fail(cmd, **kw):
            raise AssertionError("subprocess.run must not be called")

        monkeypatch.setattr(wb.subprocess, "run", fail)
        res = _add(tmp_path, URL_C, clone=True)
        assert res["clone"]["status"] == "skipped"

    def test_non_git_dir_warns(self, tmp_path, monkeypatch):
        _init(tmp_path)
        (tmp_path / "repo-c").mkdir()
        monkeypatch.setattr(wb.subprocess, "run", lambda cmd, **kw: _FakeProc(0))
        res = _add(tmp_path, URL_C, clone=True)
        assert res["clone"]["status"] == "warn"


# ---------------------------------------------------------------------------
# 10. init_workspace re-sync auto-clone
# ---------------------------------------------------------------------------
class TestInitAutoClone:
    def test_rerun_clones_registered_repo(self, tmp_path, monkeypatch):
        _init(tmp_path)
        _add(tmp_path, URL_C, clone=False)  # registered, not cloned
        calls = []
        monkeypatch.setattr(
            wb.subprocess,
            "run",
            lambda cmd, **kw: (calls.append(cmd), _FakeProc(0))[1],
        )
        res = _init(tmp_path)  # re-run must auto-clone
        assert res["status"] == "ok"
        assert res["clones"]["repo-c"]["status"] == "ok"
        assert calls and calls[0][:2] == ["git", "clone"]
        assert calls[0][3] == str(tmp_path / "repo-c")

    def test_rerun_skips_already_cloned(self, tmp_path, monkeypatch):
        _init(tmp_path)
        _add(tmp_path, URL_C, clone=False)
        (tmp_path / "repo-c" / ".git").mkdir(parents=True)  # already cloned
        monkeypatch.setattr(
            wb.subprocess, "run", lambda cmd, **kw: _FakeProc(0)
        )
        res = _init(tmp_path)
        assert res["clones"]["repo-c"]["status"] == "skipped"

    def test_clone_failure_warns_not_errors(self, tmp_path, monkeypatch):
        _init(tmp_path)
        _add(tmp_path, URL_C, clone=False)
        monkeypatch.setattr(
            wb.subprocess, "run", lambda cmd, **kw: _FakeProc(128, "fatal: network")
        )
        res = _init(tmp_path)
        assert res["status"] == "ok"  # a failed clone never fails the init
        assert res["clones"]["repo-c"]["status"] == "error"
        assert any("repo-c" in w for w in res["warnings"])

    def test_empty_table_clones_nothing(self, tmp_path):
        res = _init(tmp_path)
        assert res["clones"] == {}

    def test_centralized_clone_strips_codewiki_block(self, tmp_path, monkeypatch):
        _init(tmp_path, layout="centralized")
        _add(tmp_path, URL_C, clone=False)

        def fake_clone(cmd, **kw):
            dest = Path(cmd[3])
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "AGENTS.md").write_text(
                f"own content\n{_BEGIN_MARKER}\nwiki usage\n{_END_MARKER}\ntail\n",
                encoding="utf-8",
            )
            return _FakeProc(0)

        monkeypatch.setattr(wb.subprocess, "run", fake_clone)
        res = _init(tmp_path)
        assert res["clones"]["repo-c"]["status"] == "ok"
        cloned_agents = _read(tmp_path / "repo-c" / "AGENTS.md")
        assert _BEGIN_MARKER not in cloned_agents  # block stripped
        assert "own content" in cloned_agents


# ---------------------------------------------------------------------------
# 11. Hand-built workspace adoption
# ---------------------------------------------------------------------------
class TestHandBuiltAdoption:
    def test_adopt_reference_style_scripts(self, tmp_path):
        # Replicate the hand-built harness style (no tool header comments)
        (tmp_path / "bootstrap.sh").write_text(
            '#!/usr/bin/env bash\nset -euo pipefail\nroot="$(cd "$(dirname "$0")" && pwd)"\n'
            'declare -A repos=(\n    ["old-repo"]="https://example.com/old.git"\n)\n'
            'for name in "${!repos[@]}"; do :; done\n',
            encoding="utf-8",
        )
        (tmp_path / "bootstrap.ps1").write_text(
            '$ErrorActionPreference = "Stop"\n$root = $PSScriptRoot\n'
            '$repos = [ordered]@{\n    "old-repo" = "https://example.com/old.git"\n}\n'
            "foreach ($name in $repos.Keys) { }\n",
            encoding="utf-8",
        )
        (tmp_path / ".gitignore").write_text("/old-repo/\n", encoding="utf-8")
        wiki_dir = tmp_path / "repowiki" / "wiki"
        wiki_dir.mkdir(parents=True)
        (wiki_dir / "repo-map.md").write_text(
            "# 仓库导航\n\n| 业务仓 | 目录 |\n|-------|------|\n| old-repo | `old-repo/` |\n",
            encoding="utf-8",
        )

        res = _add(tmp_path, "https://example.com/new-repo.git")
        assert res["status"] == "ok"
        assert res["name"] == "new-repo"
        sh = _read(tmp_path / "bootstrap.sh")
        assert '["old-repo"]="https://example.com/old.git"' in sh
        assert '["new-repo"]="https://example.com/new-repo.git"' in sh
        assert "/new-repo/" in _read(tmp_path / ".gitignore")
        assert "## new-repo（`new-repo/`）" in _read(wiki_dir / "repo-map.md")


# ---------------------------------------------------------------------------
# 11. Registry wiring smoke test
# ---------------------------------------------------------------------------
class TestRegistryWiring:
    def test_tools_registered(self):
        from codewiki.mcp import registry

        for tool_name in (
            "init_workspace",
            "add_workspace_repo",
            "remove_workspace_repo",
        ):
            assert tool_name in registry.REGISTRY
            tool_def = registry.REGISTRY[tool_name]
            assert tool_def.mode == "thread"
            assert tool_def.takes_store is False
            module_name, func_name = tool_def.handler_path.rsplit(":", 1)
            module = importlib.import_module(module_name)
            assert callable(getattr(module, func_name))

    def test_init_workspace_schema_is_minimal(self):
        from codewiki.mcp import registry

        tool_def = registry.REGISTRY["init_workspace"]
        props = tool_def.schema.inputSchema["properties"]
        assert tool_def.schema.inputSchema["required"] == []
        assert set(props) == {"output_dir"}
        assert "workspace_path" not in props
        assert "layout" not in props
        assert "with_readme" not in props
        assert "repos" not in props
        assert "name" not in props
        assert "clone_repos" not in props

    def test_add_and_remove_schemas(self):
        from codewiki.mcp import registry

        add_def = registry.REGISTRY["add_workspace_repo"]
        add_props = add_def.schema.inputSchema["properties"]
        assert add_def.schema.inputSchema["required"] == ["url"]
        assert "name" not in add_props

        rm_def = registry.REGISTRY["remove_workspace_repo"]
        rm_props = rm_def.schema.inputSchema["properties"]
        assert rm_def.schema.inputSchema["required"] == ["name"]
        assert "url" not in rm_props
        assert "delete_dir" not in rm_props
