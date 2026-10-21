"""Tests for the `setup` CLI command（三段式一键装机，2026-10-20 设计定案）。"""

import json
import os

import pytest
from click.testing import CliRunner

from codewiki.cli.commands.setup import setup
from codewiki.cli.commands.sync_skills import _STATIC_SKILL_NAMES
from codewiki.mcp import i18n
from codewiki.mcp.prompts import _PROMPT_REGISTRY

SKILL_COUNT = len(_PROMPT_REGISTRY) + len(_STATIC_SKILL_NAMES)

# README 手工配置口径的 server 配置块（_build_server_config 无 lang 形态；
# 解释器按平台快照，对齐 hooks 的 python/python3 平台口径）
EXPECTED_SERVER = {
    "command": "python" if os.name == "nt" else "python3",
    "args": ["-m", "codewiki.mcp.server"],
    "maxOutputLength": 500000,
    "timeout": 36000000,
    "disabled": False,
}


@pytest.fixture(autouse=True)
def _fix_lang(monkeypatch):
    """固定语言：屏蔽 init_lang 的环境重读，测试用显式参数控制。"""
    monkeypatch.setattr(i18n, "init_lang", lambda: None)
    yield
    i18n.set_lang("zh")


def _read_mcp_json(repo):
    return json.loads((repo / ".mcp.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 三段全跑（无 IDE 目录：hook 段 SKIP 不算失败）
# ---------------------------------------------------------------------------


def test_setup_fresh_repo_no_ide(tmp_path):
    result = CliRunner().invoke(setup, ["--repo-path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "SKIP: no IDE config dir detected" in result.output

    # .mcp.json 创建，无 env 块（未传 --lang）
    server = _read_mcp_json(tmp_path)["mcpServers"]["codewiki"]
    assert server == EXPECTED_SERVER

    # skill 段兜底写 .trae/skills/，含静态资产 codewiki-setup
    skills_dir = tmp_path / ".trae" / "skills"
    dirs = {d.name for d in skills_dir.iterdir() if d.is_dir()}
    assert len(dirs) == SKILL_COUNT
    assert "codewiki-setup" in dirs
    assert "codewiki-init-wiki" in dirs


def test_setup_nonexistent_repo_path_fails_fast(tmp_path):
    target = tmp_path / "typo-path"
    result = CliRunner().invoke(setup, ["--repo-path", str(target)])
    assert result.exit_code != 0
    assert "不存在" in result.output
    assert not target.exists()


def test_setup_lang_en_injects_env_and_english_skills(tmp_path):
    result = CliRunner().invoke(setup, ["--repo-path", str(tmp_path), "--lang", "en"])
    assert result.exit_code == 0, result.output

    server = _read_mcp_json(tmp_path)["mcpServers"]["codewiki"]
    assert server["env"] == {"CODEWIKI_LANG": "en"}

    content = (tmp_path / ".trae" / "skills" / "codewiki-setup" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "pip install --upgrade codewiki-plus" in content
    assert "一键" not in content


def test_setup_lang_zh_no_env_but_chinese_skills(tmp_path):
    """--lang 显式传 zh：env 注入 CODEWIKI_LANG=zh；不传才没有 env 块。"""
    result = CliRunner().invoke(setup, ["--repo-path", str(tmp_path), "--lang", "zh"])
    assert result.exit_code == 0, result.output
    server = _read_mcp_json(tmp_path)["mcpServers"]["codewiki"]
    assert server["env"] == {"CODEWIKI_LANG": "zh"}


# ---------------------------------------------------------------------------
# .mcp.json 合并语义
# ---------------------------------------------------------------------------


def test_setup_mcp_json_merge_preserves_others(tmp_path):
    existing = {
        "otherTopLevel": True,
        "mcpServers": {
            "other-server": {"command": "foo"},
            "codewiki": {"command": "stale", "args": ["old"]},
        },
    }
    (tmp_path / ".mcp.json").write_text(json.dumps(existing), encoding="utf-8")

    result = CliRunner().invoke(setup, ["--repo-path", str(tmp_path)])
    assert result.exit_code == 0, result.output

    data = _read_mcp_json(tmp_path)
    assert data["otherTopLevel"] is True
    assert data["mcpServers"]["other-server"] == {"command": "foo"}
    # codewiki 键覆盖（生成物快照语义）
    assert data["mcpServers"]["codewiki"] == EXPECTED_SERVER


def test_setup_mcp_json_invalid_json_hard_fails(tmp_path):
    (tmp_path / ".mcp.json").write_text("{ not json", encoding="utf-8")
    result = CliRunner().invoke(setup, ["--repo-path", str(tmp_path)])
    assert result.exit_code != 0
    assert "mcp" in result.output
    # 非法 JSON 不被改写
    assert (tmp_path / ".mcp.json").read_text(encoding="utf-8") == "{ not json"
    # skill 段不受 mcp 段失败影响，仍成功
    assert (tmp_path / ".trae" / "skills" / "codewiki-setup" / "SKILL.md").is_file()


# ---------------------------------------------------------------------------
# dry-run：.mcp.json 不写盘，hook/skill 段只打计划
# ---------------------------------------------------------------------------


def test_setup_dry_run_writes_nothing(tmp_path):
    result = CliRunner().invoke(setup, ["--repo-path", str(tmp_path), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "[plan] install-hooks" in result.output
    assert "preview" in result.output
    assert not (tmp_path / ".mcp.json").exists()
    assert not (tmp_path / ".trae").exists()


# ---------------------------------------------------------------------------
# --ide 显式指定
# ---------------------------------------------------------------------------


def test_setup_explicit_ide_wires_hooks_and_skills(tmp_path):
    (tmp_path / ".trae").mkdir()
    result = CliRunner().invoke(setup, ["--repo-path", str(tmp_path), "--ide", "trae"])
    assert result.exit_code == 0, result.output
    assert "[wired] trae" in result.output
    # hook 段真接线：hooks.json 落盘
    assert (tmp_path / ".trae" / "hooks.json").is_file()
    # skill 段只写 .trae
    assert (tmp_path / ".trae" / "skills" / "codewiki-setup" / "SKILL.md").is_file()


def test_setup_explicit_ide_missing_dir_fails_segment_but_others_succeed(tmp_path):
    result = CliRunner().invoke(setup, ["--repo-path", str(tmp_path), "--ide", "trae"])
    assert result.exit_code != 0
    assert "hooks" in result.output
    # 失败段不回滚其他段成果
    assert (tmp_path / ".mcp.json").is_file()
    assert (tmp_path / ".trae" / "skills" / "codewiki-setup" / "SKILL.md").is_file()


def test_setup_capture_off_passthrough(tmp_path):
    (tmp_path / ".trae").mkdir()
    result = CliRunner().invoke(
        setup, ["--repo-path", str(tmp_path), "--ide", "trae", "--capture", "off"]
    )
    assert result.exit_code == 0, result.output
    hooks_json = (tmp_path / ".trae" / "hooks.json").read_text(encoding="utf-8")
    assert "capture_session_end" not in hooks_json
