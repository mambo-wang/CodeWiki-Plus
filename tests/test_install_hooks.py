"""Tests for the multi-IDE hook wiring (codewiki/cli/utils/ide_config.py
+ codewiki/cli/commands/install_hooks.py).

Covered:
  - detect_ide_dirs: scans the repo root for .codebuddy/.qoder/.claude;
  - merge_settings_json: deep merge keeps unrelated config, dedups by command;
  - install_for_ide end-to-end: copies hook scripts + distill-worker.md,
    merges settings.json, upserts the AGENTS.md task-memory section;
  - CLI: default auto-detect mode vs. --ide explicit mode;
  - idempotency: running the wiring twice does not duplicate registrations.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from codewiki.cli.commands.install_hooks import install_hooks
from codewiki.cli.utils.ide_config import (
    AGENT_FILE,
    HOOK_FILES,
    detect_ide_dirs,
    install_for_ide,
    merge_settings_json,
)
from codewiki.mcp.prompts import (
    _QWENWORK_CAPTURE_END,
    _QWENWORK_CAPTURE_START,
    _TASK_MEMORY_AGENTS_END,
    _TASK_MEMORY_AGENTS_START,
)

HOOK_SOURCES = {
    "capture_session_end.py": "import json\n\nprint('ok')\n",
    "task_session_start.py": "import os\n\nprint('ok')\n",
}
AGENT_SOURCE = "---\nname: distill-worker\ntoolsMCP: codewiki\n---\nworker\n"
AGENT_SOURCE_CLAUDE = (
    "---\nname: distill-worker\n"
    "tools: Read, Write, mcp__codewiki__distill_conversation\n---\nworker\n"
)


@pytest.fixture
def fake_pkg(tmp_path, monkeypatch):
    """A fake codewiki package directory with hook/agent source copies."""
    pkg = tmp_path / "pkg"
    (pkg / "hooks").mkdir(parents=True)
    (pkg / "agents").mkdir(parents=True)
    for name, content in HOOK_SOURCES.items():
        (pkg / "hooks" / name).write_text(content, encoding="utf-8")
    (pkg / "agents" / AGENT_FILE).write_text(AGENT_SOURCE, encoding="utf-8")
    (pkg / "agents" / "distill-worker.claude.md").write_text(
        AGENT_SOURCE_CLAUDE, encoding="utf-8"
    )
    monkeypatch.setattr("codewiki.cli.utils.ide_config._resolve_pkg_sources", lambda: pkg)
    return pkg


def _write_settings(repo: Path, ide_dir: str, data: dict) -> None:
    (repo / ide_dir).mkdir(parents=True, exist_ok=True)
    (repo / ide_dir / "settings.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# detect_ide_dirs
# ---------------------------------------------------------------------------


def test_detect_finds_only_existing_dirs(tmp_path):
    (tmp_path / ".qoder").mkdir()
    assert detect_ide_dirs(str(tmp_path)) == ["qoder"]


def test_detect_finds_multiple_dirs(tmp_path):
    (tmp_path / ".codebuddy").mkdir()
    (tmp_path / ".claude").mkdir()
    assert detect_ide_dirs(str(tmp_path)) == ["codebuddy", "claude-code"]


def test_detect_finds_gemini_dir(tmp_path):
    (tmp_path / ".gemini").mkdir()
    assert detect_ide_dirs(str(tmp_path)) == ["gemini-cli"]


def test_detect_none(tmp_path):
    assert detect_ide_dirs(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# merge_settings_json
# ---------------------------------------------------------------------------


def test_merge_keeps_unrelated_config():
    existing = {
        "telemetry": {"enabled": True},
        "hooks": {"Stop": [{"matcher": "always", "hooks": []}]},
    }
    merged = merge_settings_json(existing, "start-cmd", "end-cmd")
    assert merged["telemetry"] == {"enabled": True}
    assert "Stop" in merged["hooks"]
    start = merged["hooks"]["SessionStart"]
    assert start[0]["matcher"] == "startup"
    assert start[0]["hooks"][0]["command"] == "start-cmd"
    assert start[0]["hooks"][0]["timeout"] == 15
    end = merged["hooks"]["SessionEnd"]
    assert end[0]["matcher"] == "other"
    assert end[0]["hooks"][0]["command"] == "end-cmd"
    assert end[0]["hooks"][0]["timeout"] == 30


def test_merge_none_existing():
    merged = merge_settings_json(None, "start-cmd", "end-cmd")
    assert set(merged["hooks"]) == {"SessionStart", "SessionEnd"}


def test_merge_is_idempotent():
    once = merge_settings_json(None, "start-cmd", "end-cmd")
    twice = merge_settings_json(once, "start-cmd", "end-cmd")
    assert once == twice
    # Re-running must not grow the registrations.
    assert len(twice["hooks"]["SessionStart"]) == 1
    assert len(twice["hooks"]["SessionEnd"]) == 1


def test_merge_dedups_same_command_with_different_timeout():
    existing = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup",
                    "hooks": [{"type": "command", "command": "start-cmd", "timeout": 99}],
                }
            ]
        }
    }
    merged = merge_settings_json(existing, "start-cmd", "end-cmd")
    assert len(merged["hooks"]["SessionStart"]) == 1
    # Existing timeout preserved; no duplicate entry added.
    assert merged["hooks"]["SessionStart"][0]["hooks"][0]["timeout"] == 99


# Legacy entries (absolute / backslash paths, or $*_PROJECT_DIR placeholders)
# must be migrated in place to the project-relative form instead of being
# duplicated when install-hooks is re-run after a path-format change.

NEW_START = 'python ".qoder/hooks/task_session_start.py"'
NEW_END = 'python ".qoder/hooks/capture_session_end.py"'


@pytest.mark.parametrize(
    "legacy_start",
    [
        'python "D:/repos/proj/.qoder/hooks/task_session_start.py"',
        'python "D:\\repos\\proj\\.qoder\\hooks\\task_session_start.py"',
        'python "$CODEBUDDY_PROJECT_DIR/.qoder/hooks/task_session_start.py"',
        'python "$CLAUDE_PROJECT_DIR/.qoder/hooks/task_session_start.py"',
    ],
)
def test_merge_migrates_legacy_start_command_in_place(legacy_start):
    existing = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup",
                    "hooks": [{"type": "command", "command": legacy_start, "timeout": 42}],
                }
            ]
        }
    }
    merged = merge_settings_json(existing, NEW_START, NEW_END)
    start = merged["hooks"]["SessionStart"]
    assert len(start) == 1
    assert len(start[0]["hooks"]) == 1
    assert start[0]["hooks"][0]["command"] == NEW_START
    assert start[0]["hooks"][0]["timeout"] == 42  # original timeout preserved


def test_merge_keeps_unrelated_commands_while_migrating():
    existing = {
        "hooks": {
            "SessionEnd": [
                {
                    "matcher": "other",
                    "hooks": [
                        {"type": "command", "command": "my-other-tool --on-exit", "timeout": 5},
                        {
                            "type": "command",
                            "command": 'python "D:/repos/proj/.qoder/hooks/capture_session_end.py"',
                            "timeout": 30,
                        },
                    ],
                }
            ]
        }
    }
    merged = merge_settings_json(existing, NEW_START, NEW_END)
    inner = merged["hooks"]["SessionEnd"][0]["hooks"]
    assert len(inner) == 2  # no duplicate appended
    commands = [h["command"] for h in inner]
    assert "my-other-tool --on-exit" in commands  # unrelated entry untouched
    assert NEW_END in commands


def test_install_migrates_existing_absolute_path_entries(tmp_path, fake_pkg):
    (tmp_path / ".qoder").mkdir()
    _write_settings(
        tmp_path,
        ".qoder",
        {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "startup",
                        "hooks": [
                            {
                                "type": "command",
                                "command": 'python "D:/repos/proj/.qoder/hooks/task_session_start.py"',
                                "timeout": 15,
                            }
                        ],
                    }
                ]
            }
        },
    )
    result = install_for_ide(str(tmp_path), "qoder")
    assert result["settings_changed"] is True
    settings = json.loads((tmp_path / ".qoder" / "settings.json").read_text(encoding="utf-8"))
    start = settings["hooks"]["SessionStart"][0]["hooks"]
    assert len(start) == 1
    assert start[0]["command"] == NEW_START
    # Re-running is idempotent on the migrated form.
    second = install_for_ide(str(tmp_path), "qoder")
    assert second["settings_changed"] is False


# ---------------------------------------------------------------------------
# install_for_ide (end-to-end)
# ---------------------------------------------------------------------------


def test_install_for_ide_copies_and_wires(tmp_path, fake_pkg):
    result = install_for_ide(str(tmp_path), "qoder")

    hooks_dir = tmp_path / ".qoder" / "hooks"
    for name in HOOK_FILES:
        assert (hooks_dir / name).is_file(), f"missing {name}"
    agents_file = tmp_path / ".qoder" / "agents" / AGENT_FILE
    assert agents_file.is_file()

    settings = json.loads((tmp_path / ".qoder" / "settings.json").read_text(encoding="utf-8"))
    start = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    end = settings["hooks"]["SessionEnd"][0]["hooks"][0]["command"]
    assert start == 'python ".qoder/hooks/task_session_start.py"'
    assert end == 'python ".qoder/hooks/capture_session_end.py"'

    agents_md = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert _TASK_MEMORY_AGENTS_START in agents_md
    assert _TASK_MEMORY_AGENTS_END in agents_md

    assert result["ide"] == "qoder"
    assert result["settings_written"] is True
    assert result["settings_changed"] is True
    assert result["agents_changed"] is True
    assert len(result["copied"]) == len(HOOK_FILES) + 1  # 2 hooks + distill-worker


def test_install_keeps_existing_settings_and_is_idempotent(tmp_path, fake_pkg):
    _write_settings(
        tmp_path,
        ".codebuddy",
        {"telemetry": {"enabled": True}, "hooks": {}},
    )
    first = install_for_ide(str(tmp_path), "codebuddy")
    assert first["settings_changed"] is True
    assert first["agents_changed"] is True

    second = install_for_ide(str(tmp_path), "codebuddy")
    assert second["settings_changed"] is False
    assert second["agents_changed"] is False

    settings = json.loads((tmp_path / ".codebuddy" / "settings.json").read_text(encoding="utf-8"))
    assert settings["telemetry"] == {"enabled": True}  # unrelated config kept
    assert len(settings["hooks"]["SessionStart"]) == 1
    assert len(settings["hooks"]["SessionEnd"]) == 1

    # AGENTS.md must contain exactly one task-memory section.
    agents_md = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert agents_md.count(_TASK_MEMORY_AGENTS_START) == 1


def test_install_updates_existing_agents_section(tmp_path, fake_pkg):
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text(
        "prefix\n\n"
        + _TASK_MEMORY_AGENTS_START
        + "\nstale block\n"
        + _TASK_MEMORY_AGENTS_END
        + "\n\nsuffix\n",
        encoding="utf-8",
    )
    install_for_ide(str(tmp_path), "claude-code")
    text = agents_md.read_text(encoding="utf-8")
    # Prefix/suffix untouched, stale block replaced.
    assert text.startswith("prefix\n\n")
    assert text.endswith("\n\nsuffix\n")
    assert "stale block" not in text
    assert text.count(_TASK_MEMORY_AGENTS_START) == 1


def test_unknown_ide_raises(tmp_path):
    with pytest.raises(Exception) as exc:
        install_for_ide(str(tmp_path), "cursor")
    assert "Unknown IDE" in str(exc.value)


# ---------------------------------------------------------------------------
# distill-worker 变体：宿主 subagent frontmatter schema 不同，claude 家族
# 拿到 CodeBuddy 专属格式会解析出空工具集、subagent 不可用——必须按 IDE 发变体。
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ide", ["qoder", "claude-code", "gemini-cli"])
def test_install_claude_family_gets_claude_agent_variant(tmp_path, fake_pkg, ide):
    install_for_ide(str(tmp_path), ide)
    spec_dir = {
        "qoder": ".qoder",
        "claude-code": ".claude",
        "gemini-cli": ".gemini",
    }[ide]
    installed = (tmp_path / spec_dir / "agents" / AGENT_FILE).read_text(encoding="utf-8")
    assert installed == AGENT_SOURCE_CLAUDE
    assert "toolsMCP" not in installed  # CodeBuddy-only field must not leak


def test_install_codebuddy_keeps_default_agent_variant(tmp_path, fake_pkg):
    install_for_ide(str(tmp_path), "codebuddy")
    installed = (tmp_path / ".codebuddy" / "agents" / AGENT_FILE).read_text(encoding="utf-8")
    assert installed == AGENT_SOURCE
    assert "toolsMCP: codewiki" in installed


def test_install_agent_variant_missing_falls_back_to_default(tmp_path, fake_pkg):
    (fake_pkg / "agents" / "distill-worker.claude.md").unlink()
    install_for_ide(str(tmp_path), "qoder")
    installed = (tmp_path / ".qoder" / "agents" / AGENT_FILE).read_text(encoding="utf-8")
    assert installed == AGENT_SOURCE  # degraded but still wired


# ---------------------------------------------------------------------------
# CLI (Click)
# ---------------------------------------------------------------------------


def test_cli_auto_detect_wires_found_ides(tmp_path, fake_pkg):
    (tmp_path / ".qoder").mkdir()
    (tmp_path / ".claude").mkdir()
    runner = CliRunner()
    result = runner.invoke(install_hooks, ["--repo-path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".qoder" / "settings.json").is_file()
    assert (tmp_path / ".claude" / "settings.json").is_file()
    assert "qoder" in result.output
    assert "claude-code" in result.output


def test_cli_ide_flag_wires_single_ide(tmp_path, fake_pkg):
    # Explicit --ide on an EXISTING dir wires only that IDE.
    (tmp_path / ".qoder").mkdir()
    runner = CliRunner()
    result = runner.invoke(install_hooks, ["--repo-path", str(tmp_path), "--ide", "qoder"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".qoder" / "settings.json").is_file()
    assert not (tmp_path / ".codebuddy" / "settings.json").exists()


# ---------------------------------------------------------------------------
# --ide safety gate: explicit wiring must not conjure new IDE config dirs.
# Regression for the bug where an IDE agent ran `install-hooks --ide qoder`
# (and `--ide claude-code`) in a repo that only had .codebuddy, silently
# creating .qoder/ and .claude/ with full hook wiring the user never asked
# for. Auto-detect never creates dirs; now explicit --ide must not either,
# unless the user passes --create-dir.
# ---------------------------------------------------------------------------


def test_cli_ide_flag_missing_dir_refuses_without_create_dir(tmp_path, fake_pkg):
    (tmp_path / ".codebuddy").mkdir()
    runner = CliRunner()
    result = runner.invoke(install_hooks, ["--repo-path", str(tmp_path), "--ide", "qoder"])
    assert result.exit_code != 0
    # Refusal must leave the filesystem untouched: no .qoder conjured.
    assert not (tmp_path / ".qoder").exists()
    assert "--create-dir" in result.output


def test_cli_ide_flag_create_dir_wires_missing_dir(tmp_path, fake_pkg):
    runner = CliRunner()
    result = runner.invoke(
        install_hooks,
        ["--repo-path", str(tmp_path), "--ide", "qoder", "--create-dir"],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".qoder" / "settings.json").is_file()
    assert (tmp_path / ".qoder" / "hooks" / "capture_session_end.py").is_file()
    assert (tmp_path / ".qoder" / "agents" / AGENT_FILE).is_file()


def test_cli_create_dir_requires_ide(tmp_path, fake_pkg):
    (tmp_path / ".codebuddy").mkdir()
    runner = CliRunner()
    result = runner.invoke(install_hooks, ["--repo-path", str(tmp_path), "--create-dir"])
    assert result.exit_code != 0
    assert "--ide" in result.output


def test_cli_no_ides_found_prints_hint(tmp_path):
    runner = CliRunner()
    result = runner.invoke(install_hooks, ["--repo-path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "No supported IDE config dir detected" in result.output
    assert "--ide" in result.output


def test_cli_repeat_run_idempotent(tmp_path, fake_pkg):
    (tmp_path / ".qoder").mkdir()
    runner = CliRunner()
    first = runner.invoke(install_hooks, ["--repo-path", str(tmp_path)])
    second = runner.invoke(install_hooks, ["--repo-path", str(tmp_path)])
    assert first.exit_code == 0
    assert second.exit_code == 0
    settings = json.loads((tmp_path / ".qoder" / "settings.json").read_text(encoding="utf-8"))
    assert len(settings["hooks"]["SessionStart"]) == 1
    assert len(settings["hooks"]["SessionEnd"]) == 1
    agents_md = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert agents_md.count(_TASK_MEMORY_AGENTS_START) == 1


# ---------------------------------------------------------------------------
# QwenWork prompt wiring (no shell hooks; AGENTS.md protocol section only)
# ---------------------------------------------------------------------------


def test_detect_never_auto_detects_qwenwork(tmp_path):
    # QwenWork has no repo marker dir; auto-detection must skip it even if
    # every other IDE dir exists.
    for d in (".codebuddy", ".qoder", ".claude"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    detected = detect_ide_dirs(str(tmp_path))
    assert "qwenwork" not in detected
    assert set(detected) == {"codebuddy", "qoder", "claude-code"}


def test_install_qwenwork_writes_protocol_without_dirs(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("# Project\n\nexisting content\n", encoding="utf-8")

    r = install_for_ide(str(repo), "qwenwork")
    assert r["wiring"] == "prompt"
    assert r["dir"] is None
    assert r["copied"] == []
    assert r["settings_written"] is False
    assert r["protocol_changed"] is True

    # No IDE dirs / scripts / settings created anywhere.
    assert not (repo / ".qwenwork").exists()
    assert not (repo / ".codebuddy").exists()

    text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert _QWENWORK_CAPTURE_START in text and _QWENWORK_CAPTURE_END in text
    assert 'source_session_id="qwenwork-' in text
    assert "capture_conversation" in text
    # Existing content and the shared task-memory section are both present.
    assert "existing content" in text
    assert _TASK_MEMORY_AGENTS_START in text


def test_install_qwenwork_idempotent(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("# Project\n", encoding="utf-8")

    r1 = install_for_ide(str(repo), "qwenwork")
    assert r1["protocol_changed"] is True
    text1 = (repo / "AGENTS.md").read_text(encoding="utf-8")

    r2 = install_for_ide(str(repo), "qwenwork")
    assert r2["protocol_changed"] is False
    assert r2["agents_changed"] is False
    text2 = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert text1 == text2  # no re-append, no duplication


def test_install_qwenwork_replaces_stale_protocol_without_touching_rest(tmp_path):
    from codewiki.mcp.prompts import _QWENWORK_CAPTURE_END, _QWENWORK_CAPTURE_START

    repo = tmp_path / "repo"
    repo.mkdir()
    stale = (
        "# Project\n\n"
        f"{_QWENWORK_CAPTURE_START}\nOLD PROTOCOL TEXT\n{_QWENWORK_CAPTURE_END}\n\n"
        "after-block content\n"
    )
    (repo / "AGENTS.md").write_text(stale, encoding="utf-8")

    r = install_for_ide(str(repo), "qwenwork")
    assert r["protocol_changed"] is True
    text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "OLD PROTOCOL TEXT" not in text
    assert "capture_conversation" in text
    assert "after-block content" in text  # block-external content untouched


def test_cli_ide_qwenwork_flag(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("# Project\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(install_hooks, ["--ide", "qwenwork", "--repo-path", str(repo)])
    assert result.exit_code == 0, result.output
    assert "prompt wiring" in result.output
    text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert _QWENWORK_CAPTURE_START in text


def test_cli_auto_detect_skips_qwenwork_hint(tmp_path):
    # Empty repo: auto-detect finds nothing; the hint mentions qwenwork is
    # explicit-only.
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = CliRunner()
    result = runner.invoke(install_hooks, ["--repo-path", str(repo)])
    assert result.exit_code == 0
    assert "--ide qwenwork" in result.output
