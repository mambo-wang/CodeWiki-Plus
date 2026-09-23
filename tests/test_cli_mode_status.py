"""票 03：CLI --capture / --status / --inject-file（档位自动判定）。

依据 docs/接线档位选择设计方案.md §3.6 与 ADR-0014：
  - 档位由注册表自动判定（--mode 已移除，传入即硬报错）
  - --capture on|off 独立控制 SessionEnd 采集注册（默认 on；主动沉淀固定启用）
  - --status → 只读状态表，含全部七列，退出码 0，不改任何文件
  - --inject-file 参数可达
  - 理论支持宿主（verified: false）接线成功 + 黄色警告
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from codewiki.cli.commands.install_hooks import install_hooks, _wired_on_disk
from codewiki.cli.utils.ide_config import AGENT_FILE, HOOK_FILES, install_for_ide
from codewiki.mcp.prompts import (
    _ACTIVE_SETTLE_START,
    _TASK_MEMORY_AGENTS_START,
)

HOOK_SOURCES = {
    "capture_session_end.py": "import json\n\nprint('ok')\n",
    "task_session_start.py": "import os\n\nprint('ok')\n",
}
AGENT_SOURCE = "---\nname: distill-worker\nmcpServers:\n  - codewiki\n---\nworker\n"
AGENT_SOURCE_CLAUDE = (
    "---\nname: distill-worker\n"
    "tools: Read, Write, mcp__codewiki__distill_conversation\n---\nworker\n"
)


@pytest.fixture
def fake_pkg(tmp_path, monkeypatch):
    """假包目录（与 test_install_hooks.fake_pkg 同构）：提供接线源副本。"""
    pkg = tmp_path / "pkg"
    (pkg / "hooks").mkdir(parents=True)
    (pkg / "agents").mkdir(parents=True)
    for name, content in HOOK_SOURCES.items():
        (pkg / "hooks" / name).write_text(content, encoding="utf-8")
    (pkg / "agents" / AGENT_FILE).write_text(AGENT_SOURCE, encoding="utf-8")
    (pkg / "agents" / "distill-worker.claude.md").write_text(AGENT_SOURCE_CLAUDE, encoding="utf-8")
    monkeypatch.setattr("codewiki.cli.utils.ide_config._resolve_pkg_sources", lambda: pkg)
    return pkg


def _snapshot(root: Path) -> dict[str, bytes]:
    """递归快照目录内容（相对路径 → 字节），用于零回归逐字节比对。"""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# ---------------------------------------------------------------------------
# 已移除参数：--mode / --active-settle 传入即硬报错（不静默忽略）
# ---------------------------------------------------------------------------


def test_mode_flag_removed_hard_error(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("# Project\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        install_hooks,
        ["--repo-path", str(repo), "--ide", "qwenwork", "--mode", "prompt"],
    )
    assert result.exit_code != 0
    assert "--mode has been removed" in result.output
    # 硬报错：注入文件原样，无任何写入
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == "# Project\n"


def test_active_settle_flag_removed_hard_error(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        install_hooks,
        ["--repo-path", str(repo), "--active-settle", "on"],
    )
    assert result.exit_code != 0
    assert "--capture" in result.output


# ---------------------------------------------------------------------------
# 档位自动判定（注册表单源）
# ---------------------------------------------------------------------------


def test_qwenwork_auto_prompt_wiring(tmp_path):
    # qwenwork（prompt 家族）自动走 prompt 档：只写注入文件，不建配置目录
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = CliRunner()
    result = runner.invoke(install_hooks, ["--repo-path", str(repo), "--ide", "qwenwork"])
    assert result.exit_code == 0, result.output
    assert "prompt wiring" in result.output
    text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert _ACTIVE_SETTLE_START in text
    assert _TASK_MEMORY_AGENTS_START in text
    assert not (repo / ".qoder").exists()


def test_verified_false_warns_but_wires(tmp_path, fake_pkg, monkeypatch):
    # 理论支持宿主（注册表 verified: false）：接线成功 + 黄色警告。
    # 现注册表里可接线宿主均已验证，故把 gemini-cli 临时翻成未验证。
    import copy

    from codewiki.mcp.tools import hook_registry as hr

    patched = copy.deepcopy(hr.load_registry())
    for a in patched["agents"]:
        if a["id"] == "gemini-cli":
            a["verified"] = False
    monkeypatch.setattr(hr, "load_registry", lambda: patched)

    (tmp_path / ".gemini").mkdir()
    runner = CliRunner()
    result = runner.invoke(
        install_hooks,
        ["--repo-path", str(tmp_path), "--ide", "gemini-cli"],
    )
    assert result.exit_code == 0, result.output
    assert "warning" in result.output and "verified=false" in result.output
    assert (tmp_path / ".gemini" / "settings.json").is_file()


def test_verified_host_has_no_warning(tmp_path, fake_pkg):
    (tmp_path / ".codebuddy").mkdir()
    runner = CliRunner()
    result = runner.invoke(
        install_hooks,
        ["--repo-path", str(tmp_path), "--ide", "codebuddy"],
    )
    assert result.exit_code == 0, result.output
    assert "warning" not in result.output


# ---------------------------------------------------------------------------
# --capture：独立采集开关（ADR-0014）
# ---------------------------------------------------------------------------


def test_capture_off_removes_session_end_registration(tmp_path, fake_pkg):
    (tmp_path / ".codebuddy").mkdir()
    runner = CliRunner()
    result = runner.invoke(
        install_hooks,
        ["--repo-path", str(tmp_path), "--ide", "codebuddy", "--capture", "off"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads((tmp_path / ".codebuddy" / "settings.json").read_text(encoding="utf-8"))
    assert "SessionStart" in data["hooks"]
    assert "SessionEnd" not in data["hooks"]
    # 脚本与 distill-worker 照常拷贝（存量积压仍需补蒸馏）
    for name in HOOK_FILES:
        assert (tmp_path / ".codebuddy" / "hooks" / name).is_file()


def test_capture_default_on_keeps_session_end(tmp_path, fake_pkg):
    r1 = install_for_ide(str(tmp_path), "codebuddy")
    assert r1["capture"] is True
    r2 = install_for_ide(str(tmp_path), "trae", capture=False)
    assert r2["capture"] is False  # 显式覆盖生效


# ---------------------------------------------------------------------------
# --status：只读状态表
# ---------------------------------------------------------------------------


def test_status_table_header_columns(tmp_path, fake_pkg):
    runner = CliRunner()
    result = runner.invoke(install_hooks, ["--repo-path", str(tmp_path), "--status"])
    assert result.exit_code == 0, result.output
    header = result.output.splitlines()[0]
    # 七列表头（工单验收至少三列：agent / registry / wiring 均在其中）
    for col in (
        "agent",
        "family",
        "registry",
        "wiring",
        "capture",
        "wired-on-disk",
        "capability gap",
    ):
        assert col in header, f"missing column: {col}"


def test_status_source_annotation_default_vs_cli(tmp_path):
    runner = CliRunner()
    default = runner.invoke(install_hooks, ["--repo-path", str(tmp_path), "--status"])
    assert default.exit_code == 0
    assert "(默认)" in default.output  # 默认来源标注
    override = runner.invoke(
        install_hooks,
        ["--repo-path", str(tmp_path), "--status", "--capture", "off"],
    )
    assert override.exit_code == 0
    assert "(CLI)" in override.output  # CLI 覆盖来源标注


def test_status_is_readonly_and_exit_0(tmp_path, fake_pkg):
    (tmp_path / ".codebuddy").mkdir()
    before = _snapshot(tmp_path)
    runner = CliRunner()
    result = runner.invoke(install_hooks, ["--repo-path", str(tmp_path), "--status"])
    assert result.exit_code == 0
    assert _snapshot(tmp_path) == before  # 不改任何文件
    assert "Hook wiring complete" not in result.output  # 未执行接线


def test_status_wired_on_disk_reflects_reality(tmp_path, fake_pkg):
    (tmp_path / ".codebuddy").mkdir()
    runner = CliRunner()
    before = runner.invoke(install_hooks, ["--repo-path", str(tmp_path), "--status"])
    assert "not wired" in before.output

    runner.invoke(install_hooks, ["--repo-path", str(tmp_path)])
    after = runner.invoke(install_hooks, ["--repo-path", str(tmp_path), "--status"])
    assert after.exit_code == 0
    # codebuddy 接线后应显示 hooks+settings
    cb_row = next(row for row in after.output.splitlines() if row.startswith("| codebuddy"))
    assert "hooks+settings" in cb_row
    # capture off 后应显示专用状态值（与 partial 区分）
    runner.invoke(
        install_hooks, ["--repo-path", str(tmp_path), "--ide", "codebuddy", "--capture", "off"]
    )
    off = runner.invoke(install_hooks, ["--repo-path", str(tmp_path), "--status"])
    cb_off_row = next(row for row in off.output.splitlines() if row.startswith("| codebuddy"))
    assert "capture off" in cb_off_row
    assert "partial" not in cb_off_row


def test_status_wired_on_disk_matches_legacy_backslash_entries(tmp_path):
    # 反匹配用 _relative_hook_suffix 口径：反斜杠历史条目也算已接线
    (tmp_path / ".qoder").mkdir()
    (tmp_path / ".qoder" / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "startup",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": 'python "D:\\repos\\proj\\.qoder\\hooks\\task_session_start.py"',
                                    "timeout": 15,
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    agent = {"id": "qoder", "family": "claude"}
    assert _wired_on_disk(tmp_path, agent) != "not wired"


def test_status_gap_column_has_family_gaps(tmp_path):
    runner = CliRunner()
    result = runner.invoke(install_hooks, ["--repo-path", str(tmp_path), "--status"])
    qw_row = next(row for row in result.output.splitlines() if row.startswith("| qwenwork"))
    assert "no auto-capture; agent-mediated" in qw_row
    tr_row = next(row for row in result.output.splitlines() if row.startswith("| trae"))
    assert "no SessionEnd" in tr_row


# ---------------------------------------------------------------------------
# --inject-file：参数可达，不破坏现状
# ---------------------------------------------------------------------------


def test_inject_file_override_writes_custom_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        install_hooks,
        [
            "--repo-path",
            str(repo),
            "--ide",
            "qwenwork",
            "--inject-file",
            "docs/AGENT_INSTRUCTIONS.md",
        ],
    )
    assert result.exit_code == 0, result.output
    custom = repo / "docs" / "AGENT_INSTRUCTIONS.md"
    assert custom.is_file()
    assert _TASK_MEMORY_AGENTS_START in custom.read_text(encoding="utf-8")
    assert not (repo / "AGENTS.md").exists()  # 默认注入文件未被创建
