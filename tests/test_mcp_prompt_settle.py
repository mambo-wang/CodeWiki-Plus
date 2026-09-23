"""票 06：MCP prompt 同步——team-memory-hook 的 capture / action=status。

依据 docs/接线档位选择设计方案.md §3.6 入口 2 与 ADR-0014：
  - capture=off → 返回采集开关说明（档位自动判定，无 mode 参数）
  - action=status → 含 `--status` 命令与能力缺口解读模板
  - 不传新参数 → 行为与今日一致（默认 hook 正文，向后兼容）
  - init-wiki enable_task_management 段含档位自动判定说明
  - 参数在 MCP 工具 schema/args 元组里登记
"""

from __future__ import annotations

import asyncio

from codewiki.mcp.prompts import (
    _PROMPT_REGISTRY,
    _prompt_init_wiki,
    _prompt_team_memory_hook,
    register,
)

_CAPTURE_NOTE_HEAD = "**采集开关（--capture off）**"


def _args(**kw):
    """默认带 repo_path；调用方可覆盖任意参数。"""
    base = {"repo_path": "."}
    base.update(kw)
    return base


class _FakeServer:
    """最小 MCP Server 桩：只捕获 list_prompts/get_prompt 注册的处理器。"""

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


def _get_prompt(name: str, arguments: dict) -> str:
    """走真实 get_prompt 分发路径，返回响应正文。"""
    srv = _FakeServer()
    register(srv)
    result = asyncio.run(srv._get(name, arguments))
    return result.messages[0].content.text


# ---------------------------------------------------------------------------
# 1. capture=off
# ---------------------------------------------------------------------------


def test_capture_off_via_get_prompt():
    # get_prompt 路径（非直接调私有函数），覆盖 args → 响应的完整接线
    text = _get_prompt(
        "team-memory-hook",
        {"action": "enable", "capture": "off"},
    )
    assert "--capture off" in text
    # 主动沉淀固定启用说明
    assert "主动沉淀" in text
    assert "CODEWIKI-ACTIVE-SETTLE" in text


def test_capture_on_renders_without_capture_note():
    text = _prompt_team_memory_hook(_args(action="enable"))
    assert "install-hooks" in text
    # 未关采集时不追加 `--capture off`，也不出现采集开关说明
    assert "--capture off" not in text
    assert _CAPTURE_NOTE_HEAD not in text


# ---------------------------------------------------------------------------
# 2. action=status
# ---------------------------------------------------------------------------


def test_status_action_has_command_and_gap_reading():
    text = _get_prompt("team-memory-hook", {"action": "status"})
    assert "codewiki install-hooks" in text
    assert "--status" in text
    # 缺口解读模板：gap 列 + 各家族缺口 + 决策模板
    assert "capability gap" in text
    assert "no auto-capture; agent-mediated" in text
    assert "no SessionEnd" in text
    assert "决策模板" in text
    # 逐列含义解释（不退化为一句空话）
    for col in ("agent", "family", "registry", "wiring", "capture", "wired-on-disk"):
        assert f"**{col}**" in text


def test_status_action_takes_priority():
    # status 是独立动作：即便同时传其他参数也返回状态诊断而非接线正文
    text = _prompt_team_memory_hook(_args(action="status", capture="off"))
    assert "--status" in text


# ---------------------------------------------------------------------------
# 3. 向后兼容：不传新参数 = 今日 hook 正文
# ---------------------------------------------------------------------------


def test_default_output_unchanged_without_new_params():
    enable = _prompt_team_memory_hook(_args(action="enable"))
    assert "对话自动采集 Hook" in enable
    assert "install-hooks" in enable
    assert "capture_session_end.py" in enable
    assert "settings.json" in enable
    assert "hooks.yaml" in enable
    # 未关采集时不出现采集开关说明（与今日一致）
    assert _CAPTURE_NOTE_HEAD not in enable


def test_mode_param_no_longer_registered():
    # --mode 已移除：args 元组不再登记 mode
    meta = next(m for m in _PROMPT_REGISTRY if m["name"] == "team-memory-hook")
    names = {n for n, _ in meta["args"]}
    assert "mode" not in names
    assert {"action", "repo_path", "capture"} <= names


# ---------------------------------------------------------------------------
# 4. init-wiki：enable_task_management 段
# ---------------------------------------------------------------------------


def test_init_wiki_auto_tier_note():
    text = _prompt_init_wiki(_args(enable_task_management="true"))
    assert "档位自动判定" in text
    assert "只写注入文件" in text
    # 原有守则未被破坏
    assert "绝不主动新建" in text


def test_init_wiki_task_management_default_on():
    # 默认启用（opt-out）：无参渲染接线步骤与档位说明
    text = _prompt_init_wiki(_args())
    assert "## 步骤 2: 启用任务管理" in text
    assert "档位自动判定" in text
    assert "install-hooks" in text


def test_init_wiki_task_management_explicit_off():
    # 仅显式 false/0/no/off 跳过；拼错值（如 ture）按默认启用处理
    for off in ("false", "0", "no", "off"):
        text = _prompt_init_wiki(_args(enable_task_management=off))
        assert "## 步骤 2: 启用任务管理" not in text
        assert "档位自动判定" not in text
    text = _prompt_init_wiki(_args(enable_task_management="ture"))
    assert "## 步骤 2: 启用任务管理" in text


# ---------------------------------------------------------------------------
# 5. schema / args 元组登记
# ---------------------------------------------------------------------------


def test_team_memory_hook_args_registered():
    meta = next(m for m in _PROMPT_REGISTRY if m["name"] == "team-memory-hook")
    names = {n for n, _ in meta["args"]}
    assert {"action", "repo_path", "capture"} <= names


def test_init_wiki_registers_capture():
    meta = next(m for m in _PROMPT_REGISTRY if m["name"] == "init-wiki")
    names = {n for n, _ in meta["args"]}
    assert {"enable_task_management", "capture"} <= names
