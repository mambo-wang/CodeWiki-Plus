"""主动沉淀协议块 + 共享引导段（ADR-0014 重构后的验收固化）。

依据 docs/接线档位选择设计方案.md §3.3/§3.8/§3.9 与 ADR-0014：
主动沉淀固定启用（不再有 per-agent 开关），本文件覆盖：

a. 混合档渲染唯一性：同一注入文件（AGENTS.md）下不出现两份引导段/两份协议块；
b. 四判据 + 收尾轮沉淀自查成文，且明确「不做字面每轮沉淀」及理由；
c. 旧 ``CODEWIKI-QWENWORK`` 块被整体迁移为新 ``CODEWIKI-ACTIVE-SETTLE`` 块；
d. 固定启用：所有宿主（含 codebuddy）默认渲染协议块；块正文不再含
   ``active_settle=true`` 保险采集段（ADR-0014 删除）。

另：固化 ``ingest_note(status="draft")`` 措辞（不暗示可跳过确认闸门）与「草稿
落盘即可被 ``get_task_context`` 的 related_notes 以 ``status: draft`` 展示」的
现状能力（工单第 5 条验收）。
"""

import json

import pytest

from codewiki.cli.utils.ide_config import (
    AGENT_FILE,
    install_for_ide,
    upsert_active_settle_protocol,
)
from codewiki.mcp.prompts import (
    _ACTIVE_SETTLE_END,
    _ACTIVE_SETTLE_START,
    _QWENWORK_CAPTURE_END,
    _QWENWORK_CAPTURE_START,
    _TASK_MEMORY_AGENTS_END,
    _TASK_MEMORY_AGENTS_START,
    _active_settle_section,
)
from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import note_ingest as ni
from codewiki.mcp.tools import task_manager as tm

# --------------------------------------------------------------------------- #
# Helpers / fixtures
# --------------------------------------------------------------------------- #

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
    """假包目录（与 test_cli_mode_status.fake_pkg 同构）：供 hook 档拷贝源。"""
    pkg = tmp_path / "pkg"
    (pkg / "hooks").mkdir(parents=True)
    (pkg / "agents").mkdir(parents=True)
    for name, content in HOOK_SOURCES.items():
        (pkg / "hooks" / name).write_text(content, encoding="utf-8")
    (pkg / "agents" / AGENT_FILE).write_text(AGENT_SOURCE, encoding="utf-8")
    (pkg / "agents" / "distill-worker.claude.md").write_text(AGENT_SOURCE_CLAUDE, encoding="utf-8")
    monkeypatch.setattr("codewiki.cli.utils.ide_config._resolve_pkg_sources", lambda: pkg)
    return pkg


def _call(fn, **kw) -> dict:
    return json.loads(fn(kw, SessionStore()))


def _read(path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# a. 混合档渲染唯一性
# --------------------------------------------------------------------------- #


def test_mixed_tiers_render_single_sections(tmp_path, fake_pkg):
    """prompt 档（qwenwork）+ hook 档（codebuddy）同仓混跑。

    共享注入文件只允许一份引导段、一份协议块；主动沉淀固定启用（ADR-0014），
    两个宿主都渲染协议块且互不叠加。
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("# Project\n", encoding="utf-8")

    r_prompt = install_for_ide(str(repo), "qwenwork")
    r_hook = install_for_ide(str(repo), "codebuddy")
    assert r_prompt["wiring"] == "prompt"
    assert r_hook["wiring"] == "hook"

    text = _read(repo / "AGENTS.md")
    assert text.count(_TASK_MEMORY_AGENTS_START) == 1
    assert text.count(_TASK_MEMORY_AGENTS_END) == 1
    assert text.count(_ACTIVE_SETTLE_START) == 1
    assert text.count(_ACTIVE_SETTLE_END) == 1

    # 反向顺序再跑一遍：仍唯一（幂等，不叠加）
    install_for_ide(str(repo), "codebuddy")
    install_for_ide(str(repo), "qwenwork")
    text2 = _read(repo / "AGENTS.md")
    assert text2.count(_TASK_MEMORY_AGENTS_START) == 1
    assert text2.count(_TASK_MEMORY_AGENTS_END) == 1
    assert text2.count(_ACTIVE_SETTLE_START) == 1
    assert text2.count(_ACTIVE_SETTLE_END) == 1


# --------------------------------------------------------------------------- #
# b. 四判据 + 收尾轮沉淀自查成文（含每轮禁令、draft 措辞）
# --------------------------------------------------------------------------- #


def test_rendered_block_documents_criteria_and_fallback(tmp_path):
    """渲染出的块正文须同时含四类判据 + 收尾轮自查 + 每轮禁令 + draft 措辞。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("# Project\n", encoding="utf-8")
    install_for_ide(str(repo), "qwenwork")
    text = _read(repo / "AGENTS.md")

    # 四判据（里程碑 / 决策 / 话题转向 / 收尾轮）在成文正文中同时出现
    for phrase in ("里程碑达成", "决策落定", "明显转向", "收尾轮"):
        assert phrase in text
    # 收尾轮为强制兜底（必做）
    assert "强制兜底" in text
    # 明确「不做字面每轮沉淀」并给出理由（记忆压缩阈值）
    assert "不做字面每轮沉淀" in text
    assert "压缩阈值" in text
    # 两条写入路径：任务记忆直写 + 草稿笔记（确认闸门保留）
    assert "add_task_memory" in text
    assert 'ingest_note(status="draft"' in text
    assert "确认闸门保留" in text
    assert "confirm_note" in text
    assert "不得跳过确认" in text
    # ADR-0014：保险采集段已删除，块正文不再含 active_settle=true 标记
    assert "active_settle=true" not in text
    # 宿主专属小节由注册表 protocol 触发（qwenwork → 会话历史 API 拉取）
    assert "qw_query" in text


def test_section_generator_matches_rendered_block(tmp_path):
    """块正文生成器与落盘渲染一致（无宿主前置参数时为纯正文）。"""
    line = _active_settle_section()
    assert line.startswith(_ACTIVE_SETTLE_START)
    assert line.endswith(_ACTIVE_SETTLE_END)
    assert "不做字面每轮沉淀" in line


# --------------------------------------------------------------------------- #
# c. 旧 CODEWIKI-QWENWORK 块一次性迁移
# --------------------------------------------------------------------------- #


def test_legacy_qwenwork_block_migrated_to_active_settle(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    stale = (
        "# Project\n\n"
        f"{_QWENWORK_CAPTURE_START}\nOLD QWENWORK PROTOCOL\n{_QWENWORK_CAPTURE_END}\n\n"
        "tail content\n"
    )
    (repo / "AGENTS.md").write_text(stale, encoding="utf-8")

    r = install_for_ide(str(repo), "qwenwork")
    assert r["protocol_changed"] is True

    text = _read(repo / "AGENTS.md")
    # 旧标记与旧正文整块消失
    assert _QWENWORK_CAPTURE_START not in text
    assert _QWENWORK_CAPTURE_END not in text
    assert "OLD QWENWORK PROTOCOL" not in text
    # 新块出现且唯一
    assert text.count(_ACTIVE_SETTLE_START) == 1
    assert text.count(_ACTIVE_SETTLE_END) == 1
    # 块外内容原样保留
    assert "tail content" in text


# --------------------------------------------------------------------------- #
# d. 固定启用（ADR-0014）：所有宿主默认渲染协议块
# --------------------------------------------------------------------------- #


def test_always_on_renders_block_for_all_hosts(tmp_path, fake_pkg):
    """主动沉淀固定启用：codebuddy（原默认 off）也渲染协议块。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("# Project\n", encoding="utf-8")

    r = install_for_ide(str(repo), "codebuddy")
    assert r["protocol_changed"] is True
    text = _read(repo / "AGENTS.md")
    assert _ACTIVE_SETTLE_START in text
    assert _TASK_MEMORY_AGENTS_START in text


def test_upsert_protocol_is_idempotent(tmp_path):
    """upsert 幂等：重复调用不叠加块，返回 False（无变更）。"""
    f = tmp_path / "AGENTS.md"
    f.write_text("# Project\n", encoding="utf-8")
    assert upsert_active_settle_protocol(f, "codebuddy") is True
    assert upsert_active_settle_protocol(f, "codebuddy") is False
    text = _read(f)
    assert text.count(_ACTIVE_SETTLE_START) == 1


# --------------------------------------------------------------------------- #
# 第 5 条验收：draft 落盘即可被 get_task_context 以 status: draft 展示
# --------------------------------------------------------------------------- #


def test_draft_note_surfaces_in_task_context(tmp_path):
    repo = str(tmp_path)
    r = _call(tm.handle_create_task, repo_path=repo, title="沉淀任务")
    task_id = r["task"]["id"]

    _call(
        ni.handle_ingest_note,
        repo_path=repo,
        title="草稿经验",
        content="## 背景\n\nx\n\n## 结论\n\ny",
        note_type="general",
        status="draft",
        task_id=task_id,
    )

    ctx = _call(tm.handle_get_task_context, repo_path=repo, task_id=task_id)
    drafts = [n for n in ctx["related_notes"] if n["status"] == "draft"]
    assert drafts, ctx["related_notes"]
