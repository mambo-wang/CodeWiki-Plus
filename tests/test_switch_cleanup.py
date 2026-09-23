"""票 05：换采集开关清理——幂等可逆，只删自己的条目。

依据 docs/接线档位选择设计方案.md §3.10 与 ADR-0014：

  - capture on → off → on：移除/恢复 SessionEnd（trae 为 Stop）采集注册，
    SessionStart/UserPromptSubmit 与脚本、distill-worker 不受影响。
  - 历史换档残留清理：prompt 档宿主接线时自动摘除此前 hook 档写入的注册
    条目（command 命中相对脚本后缀的才删，复用 ``_relative_hook_suffix``，
    兼容正/反斜杠历史条目）；他人条目与 settings 其他键原样保留。
  - 往返等价 + 两次 install 幂等（产物逐字节不变）。
"""

import json
from pathlib import Path

import pytest

from codewiki.cli.utils.ide_config import (
    AGENT_FILE,
    install_for_ide,
    unwire_hook_registration,
)
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


# 他人（非 CodeWiki）hook 条目：往返全程必须零改动。
FOREIGN_END_ENTRY = {
    "matcher": "other",
    "hooks": [{"type": "command", "command": "my-other-tool --on-exit", "timeout": 5}],
}
FOREIGN_UP_ENTRY = {
    "matcher": "startup",
    "hooks": [{"type": "command", "command": "my-own-hook", "timeout": 5}],
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


def _snapshot(root: Path) -> dict[str, bytes]:
    """递归快照目录内容（相对路径 → 字节），用于幂等逐字节比对。"""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# ---------------------------------------------------------------------------
# 历史换档残留清理（prompt 档宿主接线时自动摘除 hook 档注册）
# ---------------------------------------------------------------------------


def test_unwire_keeps_foreign_entries_and_other_keys(tmp_path):
    (tmp_path / ".codebuddy").mkdir()
    settings_path = tmp_path / ".codebuddy" / "settings.json"
    settings_path.write_text(
        json.dumps(
            {"telemetry": {"enabled": True}, "hooks": {"SessionEnd": [FOREIGN_END_ENTRY]}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # 模拟历史 hook 档注册（codebuddy 现为 hook 档宿主，这里直接铺注册条目）
    from codewiki.cli.utils.ide_config import (
        END_HOOK_CMD,
        START_HOOK_CMD,
        merge_settings_json,
    )

    merged = merge_settings_json(
        _read_json(settings_path),
        START_HOOK_CMD.format(ide_dir=".codebuddy"),
        END_HOOK_CMD.format(ide_dir=".codebuddy"),
    )
    settings_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # 摘除：只摘我们的条目。
    assert unwire_hook_registration(str(tmp_path), "codebuddy") is True
    unwired = _read_json(settings_path)
    # settings 其他键原样保留。
    assert unwired["telemetry"] == {"enabled": True}
    # 他人条目零改动（强断言：整条 dict 相等）。
    assert unwired["hooks"]["SessionEnd"] == [FOREIGN_END_ENTRY]
    # 我们的条目全部消失（脚本后缀 + 常量 python -m 入口）。
    commands = _all_commands(unwired)
    assert not any("task_session_start.py" in c for c in commands)
    assert not any("capture_session_end.py" in c for c in commands)
    assert not any("_ide_hook" in c for c in commands)

    # 幂等：第二次无我们的条目 → 无操作。
    assert unwire_hook_registration(str(tmp_path), "codebuddy") is False


def test_unwire_keeps_foreign_user_prompt_submit(tmp_path):
    (tmp_path / ".codebuddy").mkdir()
    settings_path = tmp_path / ".codebuddy" / "settings.json"
    settings_path.write_text(
        json.dumps({"hooks": {"UserPromptSubmit": [FOREIGN_UP_ENTRY]}}, ensure_ascii=False),
        encoding="utf-8",
    )

    from codewiki.cli.utils.ide_config import (
        END_HOOK_CMD,
        START_HOOK_CMD,
        merge_settings_json,
    )

    merged = merge_settings_json(
        _read_json(settings_path),
        START_HOOK_CMD.format(ide_dir=".codebuddy"),
        END_HOOK_CMD.format(ide_dir=".codebuddy"),
    )
    settings_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    assert unwire_hook_registration(str(tmp_path), "codebuddy") is True
    data = _read_json(settings_path)
    # 他人的 UserPromptSubmit 规则原样保留，只有我们的常量命令被摘除。
    assert data["hooks"]["UserPromptSubmit"] == [FOREIGN_UP_ENTRY]


@pytest.mark.parametrize(
    "legacy_start",
    [
        'python "D:/repos/proj/.qoder/hooks/task_session_start.py"',
        'python "D:\\repos\\proj\\.qoder\\hooks\\task_session_start.py"',
        'python "$CLAUDE_PROJECT_DIR/.qoder/hooks/task_session_start.py"',
    ],
)
def test_unwire_matches_legacy_entries_and_is_idempotent(tmp_path, legacy_start):
    (tmp_path / ".qoder").mkdir()
    settings_path = tmp_path / ".qoder" / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "startup",
                            "hooks": [{"type": "command", "command": legacy_start, "timeout": 15}],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    assert unwire_hook_registration(str(tmp_path), "qoder") is True
    data = _read_json(settings_path)
    # 该 event 原本只有我们的历史条目 → 条目删空后 hooks 键一并还原。
    assert "hooks" not in data
    # 幂等：第二次无我们的条目 → 无操作、不产生写入。
    assert unwire_hook_registration(str(tmp_path), "qoder") is False


def test_unwire_never_clears_hooks_key_when_foreign_remain(tmp_path):
    # 铁律：绝不整段清空 hooks 键；只摘除我们的条目。
    (tmp_path / ".qoder").mkdir()
    settings_path = tmp_path / ".qoder" / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionEnd": [FOREIGN_END_ENTRY],
                    "SessionStart": [
                        {
                            "matcher": "startup",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": 'python ".qoder/hooks/task_session_start.py"',
                                    "timeout": 15,
                                }
                            ],
                        }
                    ],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert unwire_hook_registration(str(tmp_path), "qoder") is True
    data = _read_json(settings_path)
    assert data["hooks"]["SessionEnd"] == [FOREIGN_END_ENTRY]
    assert "SessionStart" not in data["hooks"]  # 只有我们的 event 被移除


# ---------------------------------------------------------------------------
# 换采集开关：capture on → off → on 往返等价（ADR-0014）
# ---------------------------------------------------------------------------


def test_capture_on_off_on_roundtrip_settings(tmp_path, fake_pkg):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".codebuddy").mkdir()
    settings = repo / ".codebuddy" / "settings.json"

    # on（默认）：SessionEnd 注册存在。
    install_for_ide(str(repo), "codebuddy")
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "SessionEnd" in data["hooks"]

    # off：移除采集注册，SessionStart 保留。
    install_for_ide(str(repo), "codebuddy", capture=False)
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "SessionEnd" not in data["hooks"]
    assert "SessionStart" in data["hooks"]

    # on again：恢复注册（往返闭合）。
    install_for_ide(str(repo), "codebuddy", capture=True)
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "SessionEnd" in data["hooks"]


def test_capture_off_keeps_protocol_block_on_hook_host(tmp_path, fake_pkg):
    # 主动沉淀固定启用（ADR-0014）：capture off 只动注册，协议块恒渲染。
    (tmp_path / ".codebuddy").mkdir()
    install_for_ide(str(tmp_path), "codebuddy", capture=False)
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert _ACTIVE_SETTLE_START in text
    assert _TASK_MEMORY_AGENTS_START in text  # 共享引导块保留


# ---------------------------------------------------------------------------
# 幂等：连跑两次 = 跑一次（产物 diff 为空）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("capture", [None, True, False])
def test_install_twice_is_byte_identical(tmp_path, fake_pkg, capture):
    repo = tmp_path / "repo"
    (repo / ".qoder").mkdir(parents=True)
    kwargs = {}
    if capture is not None:
        kwargs["capture"] = capture

    install_for_ide(str(repo), "qoder", **kwargs)
    first = _snapshot(repo)
    install_for_ide(str(repo), "qoder", **kwargs)
    second = _snapshot(repo)
    assert second == first  # 产物逐字节不变
