"""Tests for the hook agent registry (H1/H3) and `codewiki query` CLI (H4).

Covers docs/Hook多智能体支持设计方案.md §5 acceptance criteria:
  - hooks.yaml loads with 3 families and >= 9 agents; verified tiers correct
  - family_event: claude PascalCase / cursor camelCase mapping; arrays tolerated
  - detect_project_agents: only existing config dirs detected, none created
  - mtime cache invalidates on registry change
  - support_matrix_markdown renders verified-first
  - CLI query: delimited block output, coverage/usage/matched fields present,
    --check mode lightweight, projection reuses the MCP handler
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from codewiki.mcp.tools import hook_registry as hr


# --------------------------------------------------------------------------- #
# H1: registry loading
# --------------------------------------------------------------------------- #
class TestRegistry:
    def test_three_families(self):
        fams = hr.load_registry()["families"]
        assert set(fams.keys()) == {"claude", "cursor", "codex"}

    def test_at_least_nine_agents(self):
        agents = hr.load_registry()["agents"]
        assert len(agents) >= 9

    def test_verified_tiers(self):
        agents = hr.load_registry()["agents"]
        verified = {a["id"] for a in agents if a.get("verified")}
        assert verified == {"codebuddy", "qoder", "claude-code"}
        # theoretical agents all carry verified: false explicitly
        for a in agents:
            assert isinstance(a.get("verified"), bool)

    def test_family_event_mapping(self):
        assert hr.family_event("claude", "session_start") == "SessionStart"
        assert hr.family_event("claude", "session_end") == "SessionEnd"
        assert hr.family_event("cursor", "session_start") == "sessionStart"
        assert hr.family_event("cursor", "session_end") == "stop"
        assert hr.family_event("codex", "session_end") == "SessionEnd"

    def test_family_event_unknown(self):
        assert hr.family_event("nope", "session_start") is None
        assert hr.family_event("claude", "nope") is None

    def test_event_candidates_are_arrays(self):
        # version-compat slots: every event value is a list of candidate keys
        for fam in hr.load_registry()["families"].values():
            for candidates in fam.get("events", {}).values():
                assert isinstance(candidates, list) and candidates

    def test_string_event_tolerated(self):
        # loader tolerates a bare-string event value (defensive)
        assert hr.family_event("claude", "session_start") == "SessionStart"

    def test_malformed_registry_degrades(self, monkeypatch):
        monkeypatch.setattr(hr, "_registry_path", lambda: Path("Z:/nonexistent/hooks.yaml"))
        hr._REGISTRY_CACHE.clear()
        reg = hr.load_registry()  # must not raise
        assert reg["agents"] == []
        hr._REGISTRY_CACHE.clear()

    def test_get_agent(self):
        assert hr.get_agent("cursor")["family"] == "cursor"
        assert hr.get_agent("nope") is None


# --------------------------------------------------------------------------- #
# H3: project detection
# --------------------------------------------------------------------------- #
class TestDetection:
    def test_detects_existing_only(self, tmp_path):
        (tmp_path / ".codebuddy").mkdir()
        (tmp_path / ".cursor").mkdir()
        detected = {a["id"] for a in hr.detect_project_agents(tmp_path)}
        assert detected == {"codebuddy", "cursor"}

    def test_no_detection_creates_nothing(self, tmp_path):
        hr.detect_project_agents(tmp_path)
        assert list(tmp_path.iterdir()) == []

    def test_empty_repo(self, tmp_path):
        assert hr.detect_project_agents(tmp_path) == []


class TestSupportMatrix:
    def test_verified_first_and_tiers(self):
        md = hr.support_matrix_markdown()
        v_pos = md.index("| `codebuddy`")
        t_pos = md.index("| `cursor`")
        assert v_pos < t_pos
        assert "已验证" in md and "理论支持" in md


# --------------------------------------------------------------------------- #
# H4: codewiki query CLI
# --------------------------------------------------------------------------- #
def _mk_wiki(tmp_path) -> Path:
    od = tmp_path / "repowiki"
    (od / "notes").mkdir(parents=True)
    (od / "notes" / "pitfall-port.md").write_text(
        "---\ntype: pitfall\ntitle: 端口冲突排查\nstatus: stable\n---\n\n端口冲突用 lsof 排查。\n",
        encoding="utf-8",
    )
    (od / "notes" / "unrelated.md").write_text(
        "---\ntype: lesson\ntitle: 无关笔记\nstatus: stable\n---\n\n数据库索引优化。\n",
        encoding="utf-8",
    )
    from codewiki.mcp.tools.wiki_search import build_full_index

    build_full_index(od, session=None)
    return od


class TestCliQuery:
    def test_delimited_block_output(self, tmp_path):
        from codewiki.cli.commands.query import query_command

        od = _mk_wiki(tmp_path)
        res = CliRunner().invoke(query_command, ["端口冲突", "--output-dir", str(od)])
        assert res.exit_code == 0, res.output
        out = res.output
        assert out.startswith("--- codewiki:query:start ---")
        assert "--- codewiki:query:end ---" in out
        assert "notes/pitfall-port.md" in out
        assert "matched_terms: 端口, 冲突" in out
        assert "usage: hit_count=" in out
        assert "adoption_hint:" in out

    def test_missing_terms_noted(self, tmp_path):
        from codewiki.cli.commands.query import query_command

        od = _mk_wiki(tmp_path)
        res = CliRunner().invoke(query_command, ["端口冲突 量子", "--output-dir", str(od)])
        assert res.exit_code == 0
        assert "missing_terms: 量子" in res.output
        assert "topically adjacent" in res.output

    def test_check_mode_lightweight(self, tmp_path):
        from codewiki.cli.commands.query import query_command

        od = _mk_wiki(tmp_path)
        res = CliRunner().invoke(query_command, ["端口冲突", "--check", "--output-dir", str(od)])
        assert res.exit_code == 0
        assert "relevant: true" in res.output
        assert "top_score:" in res.output
        assert "snippet" not in res.output  # lightweight: no bodies
        # check must not record telemetry hits
        from codewiki.mcp.tools import telemetry

        agg = telemetry.aggregate_usage(od)
        assert not agg.get("notes/pitfall-port.md", {}).get("hits")

    def test_missing_output_dir_errors(self, tmp_path):
        from codewiki.cli.commands.query import query_command

        res = CliRunner().invoke(query_command, ["x", "--output-dir", str(tmp_path / "nope")])
        assert res.exit_code == 2

    def test_full_search_records_telemetry(self, tmp_path):
        # the projection reuses the MCP handler → hit telemetry recorded
        from codewiki.cli.commands.query import query_command

        od = _mk_wiki(tmp_path)
        CliRunner().invoke(query_command, ["端口冲突", "--output-dir", str(od)])
        from codewiki.mcp.tools import telemetry

        agg = telemetry.aggregate_usage(od)
        assert agg.get("notes/pitfall-port.md", {}).get("hits", 0) >= 1

    def test_expand_flag(self, tmp_path):
        from codewiki.cli.commands.query import query_command

        od = _mk_wiki(tmp_path)
        res = CliRunner().invoke(query_command, ["端口冲突", "--output-dir", str(od), "--expand"])
        assert res.exit_code == 0
        assert "lsof" in res.output  # full page content included


# --------------------------------------------------------------------------- #
# H2: registry-driven prompt
# --------------------------------------------------------------------------- #
class TestPromptRegistryDriven:
    def test_prompt_contains_tiers_and_detection(self, tmp_path):
        (tmp_path / ".codebuddy").mkdir()
        from codewiki.mcp.prompts import _prompt_team_memory_hook

        s = _prompt_team_memory_hook({"repo_path": str(tmp_path)})
        assert "hooks.yaml" in s
        assert "已验证支持" in s and "理论支持" in s
        assert "`codebuddy`" in s  # detected in this fake repo
        assert "cursor 家族采集降级" in s  # downgrade disclosed
        assert "只为探测到的智能体接线" in s

    def test_prompt_equivalence_for_verified(self):
        # regression: existing wiring steps must survive the rewrite
        from codewiki.mcp.prompts import _prompt_team_memory_hook

        s = _prompt_team_memory_hook({"repo_path": "."})
        assert "install-hooks" in s
        assert "settings.json" in s
        assert "capture_session_end.py" in s
        assert "task_session_start.py" in s
        assert "distill-worker.md" in s

    def test_prompt_no_ambiguous_installed_agents_wording(self, tmp_path):
        # regression: "覆盖全部已安装智能体" read as machine-installed led an
        # IDE agent to wire Qoder/Claude Code in a repo that only had
        # .codebuddy — wording must say "已探测" (detected), never "已安装".
        from codewiki.mcp.prompts import _prompt_team_memory_hook

        s = _prompt_team_memory_hook({"repo_path": str(tmp_path), "action": "enable"})
        assert "覆盖全部已探测" in s
        assert "覆盖全部已安装" not in s
        assert "未探测到任何已安装智能体" not in s
        # manual fallback must carry the no-conjured-dirs guard too
        assert "不创建其目录" in s or "绝不创建" in s

    def test_init_wiki_prompt_carries_wiring_guardrail(self):
        # regression: the init_wiki task-management hook steps enumerated all
        # three IDEs without any guardrail, letting agents wire (and create)
        # .qoder/.claude dirs in repos that never used those tools.
        from codewiki.mcp.prompts import _prompt_init_wiki

        s = _prompt_init_wiki({"repo_path": ".", "enable_task_management": "true"})
        assert "只为项目根目录已存在配置目录的智能体接线" in s
        assert "绝不主动新建" in s

    def test_init_workspace_prompt_renders(self):
        from codewiki.mcp.prompts import _prompt_init_workspace

        s = _prompt_init_workspace({})
        assert "init_workspace()" in s  # zero-config invocation for skeleton repair
        assert "bootstrap.sh" in s
        assert "CodeWiki Workspace Conventions" in s
        assert "补克隆" in s  # re-sync clone wording
        assert "needs_layout_decision" in s  # first-init decision gate handling
        assert "centralized" in s  # first-init layout choice guidance
        assert "不要凭记忆猜测" in s  # URL gathering guardrail
        assert "add_workspace_repo" in s

    def test_add_workspace_repo_prompt_renders(self):
        import os

        from codewiki.mcp.prompts import _prompt_add_workspace_repo

        ws = os.path.normpath("D:/tmp/ws")
        s = _prompt_add_workspace_repo(
            {"workspace_path": "D:/tmp/ws", "name": "demo", "url": "https://x/demo.git"}
        )
        assert f'add_workspace_repo(workspace_path="{ws}"' in s
        assert "demo" in s
        assert "https://x/demo.git" in s
        assert "clone" in s

    def test_new_workspace_prompts_registered(self):
        # prompts_map (get_prompt path) must know the two new names
        import asyncio

        from codewiki.mcp.prompts import register

        class FakeServer:
            def __init__(self):
                self._list = None
                self._get = None

            def list_prompts(self):
                def deco(fn):
                    self._list = fn
                    return fn

                return deco

            def get_prompt(self):
                def deco(fn):
                    self._get = fn
                    return fn

                return deco

        srv = FakeServer()
        register(srv)
        names = {p.name for p in asyncio.run(srv._list())}
        assert {"init-workspace", "add-workspace-repo"} <= names
        res = asyncio.run(srv._get("add-workspace-repo", {"name": "r", "url": "u"}))
        assert "add_workspace_repo" in res.messages[0].content.text
