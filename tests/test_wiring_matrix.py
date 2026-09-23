"""{宿主 × 采集开关} 接线矩阵——产物快照、幂等、零回归锚点。

依据 docs/接线档位选择设计方案.md §3.2（档位定义）、§3.5（注册表单源）、
§3.6（选择入口校验表）、§3.11（注入文件适配）、§3.12（决策树）与 ADR-0014：

  - 宿主：codebuddy / trae / qwenwork / qoder / cursor（注册表 family、verified
    见 codewiki/hooks.yaml）。
  - 档位：由注册表自动判定（支持 SessionStart 的宿主走 hook 档，不支持的
    qwenwork 走 prompt 档），无手动覆盖（--mode 已移除）。
  - 采集开关：on / off（默认 on）。
  - 主动沉淀固定启用（ADR-0014）：所有宿主恒渲染 CODEWIKI-ACTIVE-SETTLE 块。
  - 合法组合产物快照：hook 档含 settings 注册 + 脚本；prompt 档只动注入文件；
    capture off 移除 SessionEnd（trae 为 Stop）采集注册。
  - 幂等：每个合法组合连跑两次，产物逐字节不变。
  - 零回归锚点：codebuddy × capture on 与今日产物逐字节一致。

注：cursor 是注册表里的「理论支持」条目（family=cursor），但尚未进入
``IDE_SPECS``（cursor 家族的 hooks.json/camelCase 适配未实现），因此安装器
按未支持宿主拒绝——本测试如实覆盖该现状，不臆造接线能力。
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from codewiki.cli.commands.install_hooks import install_hooks
from codewiki.cli.utils.ide_config import (
    AGENT_FILE,
    HOOK_FILES,
    IDE_SPECS,
    PROMPT_HOOK_CMD,
    IdeWiringError,
    install_for_ide,
)
from codewiki.mcp.prompts import (
    _ACTIVE_SETTLE_START,
    _TASK_MEMORY_AGENTS_START,
)
from codewiki.mcp.tools.hook_registry import (
    inject_file_of,
    load_registry,
    support_matrix_markdown,
    wiring_of,
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

# 要覆盖的宿主（工单要求至少这 5 个）。
HOSTS = ("codebuddy", "trae", "qwenwork", "qoder", "cursor")
# 可由 install_for_ide 实际接线的宿主（cursor 未进 IDE_SPECS，见模块 docstring）。
INSTALLABLE = ("codebuddy", "trae", "qwenwork", "qoder")
# hook 档宿主（家族有 shell hook 机制）。
HOOK_HOSTS = ("codebuddy", "trae", "qoder")
# prompt 家族宿主。
PROMPT_FAMILY = ("qwenwork",)
CAPTURES = (None, True, False)

# 今日 codebuddy（claude 家族）hook 档 settings.json 的已知契约——零回归锚点。
EXPECTED_CODEBUDDY_SETTINGS = {
    "hooks": {
        "SessionStart": [
            {
                "matcher": "startup",
                "hooks": [
                    {
                        "type": "command",
                        "command": 'python ".codebuddy/hooks/task_session_start.py"',
                        "timeout": 15,
                    }
                ],
            }
        ],
        "SessionEnd": [
            {
                "matcher": "other",
                "hooks": [
                    {
                        "type": "command",
                        "command": 'python ".codebuddy/hooks/capture_session_end.py"',
                        "timeout": 30,
                    }
                ],
            }
        ],
        "UserPromptSubmit": [
            {
                "matcher": "",
                "hooks": [{"type": "command", "command": PROMPT_HOOK_CMD, "timeout": 10}],
            }
        ],
    }
}


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
    """递归快照目录内容（相对路径 → 字节），用于产物快照与幂等比对。"""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_commands(data: dict) -> list[str]:
    out: list[str] = []
    for entries in (data.get("hooks") or {}).values():
        for entry in entries:
            for h in entry.get("hooks") or []:
                if isinstance(h, dict) and isinstance(h.get("command"), str):
                    out.append(h["command"])
    return out


def _spec_dir(ide: str):
    return (IDE_SPECS.get(ide) or {}).get("dir")


def _install(repo: Path, ide: str, capture):
    kwargs = {}
    if capture is not None:
        kwargs["capture"] = capture
    return install_for_ide(str(repo), ide, **kwargs)


# ---------------------------------------------------------------------------
# 注册表矩阵解析（口径 = 注册表单源）
# ---------------------------------------------------------------------------


def test_registry_matrix_resolution():
    """5 宿主的家族 / 支持等级 / 默认档位与注册表口径一致（主动沉淀固定启用）。"""
    expected = {
        # id: (family, verified, wiring)
        "codebuddy": ("claude", True, "hook"),
        "qoder": ("claude", True, "hook"),
        "trae": ("trae", True, "hook"),
        "qwenwork": ("prompt", True, "prompt"),
        "cursor": ("cursor", False, "hook"),
    }
    for aid, (fam, verified, wiring) in expected.items():
        agent = next(a for a in load_registry()["agents"] if a["id"] == aid)
        assert agent["family"] == fam
        assert bool(agent["verified"]) is verified
        assert wiring_of(aid) == wiring
        assert inject_file_of(aid) == "AGENTS.md"
        # ADR-0014：注册表不再有 active_settle 字段
        assert "active_settle" not in agent


def test_readme_support_matrix_matches_registry():
    """G3：README 宿主验证表 = 注册表生成的矩阵（单一来源，无第二处双源漂移）。"""
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    assert support_matrix_markdown() in readme


# ---------------------------------------------------------------------------
# 合法组合产物快照：{宿主 × 采集开关}（档位自动判定）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ide", HOOK_HOSTS)
@pytest.mark.parametrize("capture", CAPTURES, ids=lambda c: f"capture={c}")
def test_hook_host_products(tmp_path, fake_pkg, ide, capture):
    """hook 档宿主：settings 注册 + 脚本 + subagent 就位；主动沉淀块恒渲染。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    result = _install(repo, ide, capture)

    spec = IDE_SPECS[ide]
    settings_path = repo / spec["dir"] / spec["settings"]
    hooks_dir = repo / spec["dir"] / "hooks"
    agents_dir = repo / spec["dir"] / spec["agents_dir"]

    assert result["wiring"] == "hook"
    assert result["capture"] is (True if capture is None else bool(capture))
    assert result["settings_written"] is True
    # 脚本与 distill-worker 就位（capture off 也照常拷贝——存量积压仍需补蒸馏）
    for name in HOOK_FILES:
        assert (hooks_dir / name).is_file()
    assert (agents_dir / AGENT_FILE).is_file()
    # settings 注册我们的命令（start 脚本 + python -m 入口）
    data = _read_json(settings_path)
    commands = _all_commands(data)
    assert any("task_session_start.py" in c for c in commands)
    assert PROMPT_HOOK_CMD in commands
    capture_on = True if capture is None else bool(capture)
    if ide == "trae":
        # trae 家族：hooks.json 顶层 version；采集注册在 Stop 事件（无 SessionEnd）
        assert data.get("version") == 1
        assert "SessionEnd" not in data["hooks"]
        if capture_on:
            assert "Stop" in data["hooks"]
        else:
            assert "Stop" not in data["hooks"]
    else:
        if capture_on:
            assert "SessionEnd" in data["hooks"]
        else:
            assert "SessionEnd" not in data["hooks"]
    # 注入文件：共享引导块恒在；主动沉淀块恒渲染（ADR-0014 固定启用）
    inject_text = (repo / inject_file_of(ide)).read_text(encoding="utf-8")
    assert _TASK_MEMORY_AGENTS_START in inject_text
    assert _ACTIVE_SETTLE_START in inject_text


@pytest.mark.parametrize("capture", CAPTURES, ids=lambda c: f"capture={c}")
def test_prompt_family_only_touches_inject_file(tmp_path, fake_pkg, capture):
    """prompt 档宿主（qwenwork）：不建配置目录、不拷脚本、不写 settings。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    result = _install(repo, "qwenwork", capture)

    assert result["wiring"] == "prompt"
    assert result["settings_written"] is False
    # 唯一产物：注入文件（+ 恒渲染的协议块）
    assert set(_snapshot(repo)) == {inject_file_of("qwenwork")}
    inject_text = (repo / inject_file_of("qwenwork")).read_text(encoding="utf-8")
    assert _TASK_MEMORY_AGENTS_START in inject_text
    assert _ACTIVE_SETTLE_START in inject_text


@pytest.mark.parametrize("ide", INSTALLABLE)
@pytest.mark.parametrize("capture", CAPTURES, ids=lambda c: f"capture={c}")
def test_install_twice_is_byte_identical(tmp_path, fake_pkg, ide, capture):
    repo = tmp_path / "repo"
    repo.mkdir()
    _install(repo, ide, capture)
    first = _snapshot(repo)
    _install(repo, ide, capture)
    assert _snapshot(repo) == first


# ---------------------------------------------------------------------------
# capture off 往返：off → on 恢复采集注册
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ide", HOOK_HOSTS)
def test_capture_off_on_roundtrip(tmp_path, fake_pkg, ide):
    """capture off 移除采集注册；不带参数重跑恢复（默认 on，不持久化）。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    spec = IDE_SPECS[ide]
    settings_path = repo / spec["dir"] / spec["settings"]

    _install(repo, ide, False)
    data = _read_json(settings_path)
    commands = _all_commands(data)
    assert any("task_session_start.py" in c for c in commands)
    assert not any("capture_session_end.py" in c for c in commands)
    if ide == "trae":
        assert "Stop" not in data["hooks"]
    else:
        assert "SessionEnd" not in data["hooks"]

    # 重跑不带参数：默认恢复 on
    _install(repo, ide, None)
    data = _read_json(settings_path)
    commands = _all_commands(data)
    assert any("capture_session_end.py" in c for c in commands)
    if ide == "trae":
        assert "Stop" in data["hooks"]
    else:
        assert "SessionEnd" in data["hooks"]


# ---------------------------------------------------------------------------
# 已移除参数：--mode / --active-settle 传入即硬报错（不静默忽略）
# ---------------------------------------------------------------------------


def test_legacy_mode_flag_rejected(tmp_path):
    """--mode 已移除（档位由注册表自动判定），传入即硬报错。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        install_hooks,
        ["--repo-path", str(repo), "--mode", "prompt"],
    )
    assert result.exit_code != 0
    assert "--mode has been removed" in result.output


def test_legacy_active_settle_flag_rejected(tmp_path):
    """ADR-0014：--active-settle 已移除，传入即硬报错（不静默忽略）。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        install_hooks,
        ["--repo-path", str(repo), "--active-settle", "on"],
    )
    assert result.exit_code != 0
    assert "--capture" in result.output


def test_cursor_not_installable_but_present_in_registry(tmp_path):
    """cursor 是注册表「理论支持」条目，但尚未进入 IDE_SPECS：安装器拒绝。

    诚实覆盖现状：不臆造 cursor 家族的 hooks.json/camelCase 适配能力。
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(IdeWiringError) as exc:
        install_for_ide(str(repo), "cursor")
    assert "Unknown IDE" in str(exc.value)
    assert _snapshot(repo) == {}

    # CLI 的 --ide 取自 IDE_SPECS，cursor 不在其中 → 参数校验失败（非 0 退出）
    runner = CliRunner()
    result = runner.invoke(install_hooks, ["--repo-path", str(repo), "--ide", "cursor"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 零回归锚点：codebuddy × capture on 与今日产物逐字节一致
# ---------------------------------------------------------------------------


def test_zero_regression_codebuddy_capture_on(tmp_path, fake_pkg):
    """不传新参数（今日默认）与显式 capture on 逐字节一致，settings = 今日契约。"""
    repo_today = tmp_path / "today"
    repo_explicit = tmp_path / "explicit"
    repo_today.mkdir()
    repo_explicit.mkdir()

    # 今日行为 = 不传 capture
    install_for_ide(str(repo_today), "codebuddy")
    install_for_ide(str(repo_explicit), "codebuddy", capture=True)

    assert _snapshot(repo_today) == _snapshot(repo_explicit)
    # settings.json 结构等于今日已知契约（零回归锚点，非仅自比较）
    assert _read_json(repo_today / ".codebuddy" / "settings.json") == (EXPECTED_CODEBUDDY_SETTINGS)
    # 主动沉淀块恒渲染（ADR-0014）；共享引导块恒在
    text = (repo_today / "AGENTS.md").read_text(encoding="utf-8")
    assert _TASK_MEMORY_AGENTS_START in text
    assert _ACTIVE_SETTLE_START in text
