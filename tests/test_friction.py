"""Tests for the K-line friction-signal trigger (摩擦信号触发机制).

Covers the four sub-tasks:
  K1  friction.score_friction — full scoring matrix (correction / interrupt /
      repeat / scale bonus / hard gate / verdict / config overrides);
  K2  capture_conversation — friction keys in the raw frontmatter + the
      returned JSON, and score refresh on session supersede;
  K3  distill_conversation prepare listing ordered by friction score DESC
      (plus friction_hint), and get_task_context pending_raws entries
      carrying friction_score;
  K4  task_session_start hook — stdlib-only line scan of the newest pending
      raw capture, one-line hint when friction_score >= 20.

Design reference: docs/知识飞轮增强设计方案-P0三项.md §2.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import capture_conversation as capture
from codewiki.mcp.tools import distill_conversation as distill
from codewiki.mcp.tools import task_manager as tm
from codewiki.mcp.tools.friction import format_friction_signals, score_friction

REPO_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# K1: score_friction pure-function matrix
# --------------------------------------------------------------------------- #

def _u(content: str) -> dict:
    return {"role": "user", "content": content}


def _a(content: str = "ok, done") -> dict:
    return {"role": "assistant", "content": content}


def test_two_corrections_trigger_suggest_distill():
    turns = [
        _u("帮我看看这个函数"), _a(),
        _u("不对，这个逻辑有问题"), _a(),
        _u("应该是先校验再处理"), _a(),
        _u("现在对了，谢谢"), _a(),
    ]
    r = score_friction(turns)
    assert r["signals"]["correction"] == 2
    assert r["signals"]["user_turns"] == 4
    assert r["score"] >= 40
    assert r["verdict"] == "suggest_distill"


def test_short_session_always_zero():
    # Even with blatant corrections AND an interrupt, <4 user turns → 0.
    turns = [
        _u("不对，你搞错了"),
        _a(),
        _u("[Request interrupted by user for tool use]"),
        _a(),
    ]
    r = score_friction(turns)
    assert r["signals"]["correction"] == 1
    assert r["signals"]["interrupt"] == 1
    assert r["score"] == 0
    assert r["verdict"] == ""


def test_smooth_long_session_below_threshold():
    # 20 turns, 10 user turns, zero friction: only the scale bonus (5+5) applies.
    turns = []
    for i in range(10):
        turns.append(_u(f"第 {i} 个问题，请解释模块 {i} 的职责"))
        turns.append(_a(f"模块 {i} 负责……"))
    r = score_friction(turns)
    assert r["signals"]["user_turns"] == 10
    assert r["signals"]["total_turns"] == 20
    assert all(r["signals"][k] == 0 for k in ("correction", "interrupt", "repeat"))
    assert r["score"] == 10
    assert r["score"] < 20
    assert r["verdict"] == ""


def test_scale_bonus_capped_at_10():
    # user_turns >= 8 AND total >= 20 → both bonuses fire, total scale == 10
    # (the cap: a long-but-smooth session can never reach the 20 threshold).
    turns = []
    for i in range(10):
        turns.append(_u(f"问题 {i}"))
        turns.append(_a(f"回答 {i}"))
    assert score_friction(turns)["score"] == 10
    # With one repeat (15) the score is 15 + 10 = 25 — scale stays at 10.
    turns[0] = _u("重试一下")
    turns[2] = _u("重试一下")  # adjacent user turns, identical after normalize
    r = score_friction(turns)
    assert r["signals"]["repeat"] == 1
    assert r["score"] == 25


def test_repeat_detection_normalized():
    # Whitespace-insensitive + case-insensitive comparison; a run of >2
    # identical adjacent user turns counts as ONE group.
    turns = [
        _u("请重试 Scan"), _a(), _u("请重试scan"), _a(), _u(" 请 重 试  scan "),
        _a(), _u("换个话题"), _a(),
    ]
    r = score_friction(turns)
    assert r["signals"]["repeat"] == 1
    assert r["signals"]["user_turns"] == 4
    assert r["score"] == 15
    assert r["verdict"] == ""


def test_repeat_non_adjacent_not_counted():
    turns = [
        _u("再来一次"), _a(), _u("别的请求"), _a(), _u("再来一次"), _a(),
        _u("结尾"), _a(),
    ]
    r = score_friction(turns)
    assert r["signals"]["repeat"] == 0


def test_interrupt_marker_counts():
    turns = [
        _u("继续"), _a(), _u("[Request interrupted by user for tool use]"), _a(),
        _u("[Request interrupted"), _a(), _u("好了"), _a(),
    ]
    r = score_friction(turns)
    assert r["signals"]["interrupt"] == 2
    assert r["signals"]["correction"] == 0
    assert r["score"] == 40
    assert r["verdict"] == "suggest_distill"


def test_correction_counted_once_per_turn():
    # Multiple keywords in one user turn → still a single correction.
    turns = [
        _u("不对，你搞错了，不是这样的"), _a(), _u("应该是这样"), _a(),
        _u("嗯"), _a(), _u("好"), _a(),
    ]
    r = score_friction(turns)
    assert r["signals"]["correction"] == 2


def test_config_override_threshold():
    turns = [
        _u("不对"), _a(), _u("错了"), _a(), _u("继续"), _a(), _u("完成"), _a(),
    ]
    base = score_friction(turns)
    assert base["score"] == 40
    # Raising the threshold above the score silences the verdict.
    r = score_friction(turns, {"threshold": 100})
    assert r["score"] == 40
    assert r["verdict"] == ""


def test_config_override_min_user_turns():
    turns = [_u("不对"), _a(), _u("错了"), _a()]
    # Default gate (4) forces 0.
    assert score_friction(turns)["score"] == 0
    # Lowering the gate lets the friction through.
    r = score_friction(turns, {"min_user_turns": 2})
    assert r["score"] == 40
    assert r["verdict"] == "suggest_distill"


def test_config_override_keywords_and_markers():
    # "重来" is a DEFAULT correction keyword; use a phrase outside the default
    # vocabulary so custom-config behaviour can be observed in isolation.
    turns = [
        _u("再跑一次那个命令"), _a(), _u("xxx"), _a(), _u("yyy"), _a(), _u("zzz"), _a(),
    ]
    # Default vocabulary: neither a correction nor an interrupt.
    base = score_friction(turns)
    assert base["signals"]["correction"] == 0
    assert base["signals"]["interrupt"] == 0
    # Custom vocabulary replaces (not extends) the default one.
    r = score_friction(turns, {"correction_keywords": ["再跑一次"]})
    assert r["signals"]["correction"] == 1
    # Custom interrupt markers likewise replace the defaults.
    r2 = score_friction(turns, {"interrupt_markers": ["再跑一次"]})
    assert r2["signals"]["interrupt"] == 1
    assert r2["signals"]["correction"] == 0


def test_format_friction_signals_line():
    s = format_friction_signals({"correction": 2, "interrupt": 0, "repeat": 1,
                                 "user_turns": 9})
    assert s == "correction=2,interrupt=0,repeat=1,user_turns=9"
    # No YAML-special characters (survives naive line scanners).
    assert ":" not in s


# --------------------------------------------------------------------------- #
# K2: capture_conversation integration
# --------------------------------------------------------------------------- #

def _capture(repo: Path, conversation, **kwargs) -> dict:
    args = {"output_dir": str(repo / "repowiki"), "conversation": conversation}
    args.update(kwargs)
    return json.loads(capture.handle_capture_conversation(args, SessionStore()))


def _correction_conversation(n_user: int = 5) -> list:
    """A ≥4-user-turn conversation with two correction turns."""
    conv = [_u("帮我实现摩擦评分"), _a("好的，方案是……")]
    conv.append(_u("不对，评分权重应该反过来"))
    conv.append(_a("明白了，调整后……"))
    conv.append(_u("应该是 correction 也计 20 分"))
    conv.append(_a("已更新。"))
    for i in range(n_user - 4):
        conv.append(_u(f"补充问题 {i}"))
        conv.append(_a(f"补充回答 {i}"))
    return conv


def test_capture_writes_friction_frontmatter_and_returns_friction(tmp_path):
    result = _capture(tmp_path, _correction_conversation())
    assert result["status"] == "captured"

    # Returned JSON carries the friction readout.
    fr = result["friction"]
    assert fr["score"] >= 40
    assert fr["verdict"] == "suggest_distill"
    assert fr["signals"]["correction"] == 2

    # Raw file frontmatter carries the two top-level single-line keys.
    raw_file = tmp_path / "repowiki" / "raw" / Path(result["stored_at"]).name
    text = raw_file.read_text(encoding="utf-8")
    fm_block = text.split("---")[1] if text.startswith("---") else text
    score_lines = [ln for ln in fm_block.splitlines()
                   if ln.startswith("friction_score:")]
    signal_lines = [ln for ln in fm_block.splitlines()
                    if ln.startswith("friction_signals:")]
    assert len(score_lines) == 1
    assert len(signal_lines) == 1
    assert score_lines[0] == f"friction_score: {fr['score']}"
    assert "correction=2" in signal_lines[0]
    assert "user_turns=" in signal_lines[0]


def test_capture_writes_zero_score_too(tmp_path):
    # A calm, short conversation: score 0 is information and must be written.
    conv = [_u("你好"), _a("你好！"), _u("再见"), _a("再见！")]
    result = _capture(tmp_path, conv)
    assert result["status"] == "captured"
    assert result["friction"]["score"] == 0
    assert result["friction"]["verdict"] == ""

    raw_file = tmp_path / "repowiki" / "raw" / Path(result["stored_at"]).name
    text = raw_file.read_text(encoding="utf-8")
    assert "friction_score: 0" in text


def test_supersede_refreshes_friction_score(tmp_path):
    # First capture: calm conversation, low score.
    calm = [_u("开始任务"), _a("好的"), _u("继续"), _a("继续中"),
            _u("还有一步"), _a("完成")]
    first = _capture(tmp_path, calm, source_session_id="sess-1")
    assert first["friction"]["score"] == 0

    # Same IDE session re-captured with a growing, friction-heavy transcript.
    heated = calm + [
        _u("不对，这里逻辑反了"), _a("抱歉，我改一下"),
        _u("应该是先做校验"), _a("已修复。"),
    ]
    second = _capture(tmp_path, heated, source_session_id="sess-1")
    assert second["status"] == "captured"
    assert second["superseded"] is True
    assert second["friction"]["score"] >= 40
    assert second["friction"]["verdict"] == "suggest_distill"

    # The raw file (same path — superseded in place) reflects the NEW score.
    raw_file = tmp_path / "repowiki" / "raw" / Path(second["stored_at"]).name
    assert Path(first["stored_at"]).name == Path(second["stored_at"]).name
    text = raw_file.read_text(encoding="utf-8")
    assert f"friction_score: {second['friction']['score']}" in text
    assert "friction_score: 0" not in text
    # Only one raw file exists (no incremental copies).
    assert len(list((tmp_path / "repowiki" / "raw").glob("conv-*.md"))) == 1


# --------------------------------------------------------------------------- #
# K3: distill prepare ordering + get_task_context friction payload
# --------------------------------------------------------------------------- #

def _write_raw_with_friction(repo: Path, name: str, score: int, task_id: str = "") -> Path:
    raw_dir = repo / "repowiki" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    p = raw_dir / name
    extra = f"task_id: \"{task_id}\"\n" if task_id else ""
    p.write_text(
        "---\n"
        "type: conversation\n"
        "status: pending\n"
        f"friction_score: {score}\n"
        f"friction_signals: correction=0,interrupt=0,repeat=0,user_turns=5\n"
        f"{extra}"
        "---\n\nuser: hello\nassistant: hi there\n",
        encoding="utf-8",
    )
    return p


def test_prepare_lists_captures_by_friction_desc(tmp_path):
    _write_raw_with_friction(tmp_path, "conv-low.md", 0)
    _write_raw_with_friction(tmp_path, "conv-high.md", 45)
    _write_raw_with_friction(tmp_path, "conv-mid.md", 20)
    _write_raw_with_friction(tmp_path, "conv-legacy.md", 0)  # pre-K-line: no key

    out = json.loads(distill.handle_distill_conversation({
        "output_dir": str(tmp_path / "repowiki"),
        "mode": "prepare",
    }, SessionStore()))

    assert out["status"] == "prepared"
    scores = [c["friction_score"] for c in out["captures"]]
    assert scores == sorted(scores, reverse=True)
    ids = [c["conversation_id"] for c in out["captures"]]
    assert ids[0] == "conv-high"
    assert ids[1] == "conv-mid"
    # Additive hint key present (at least one capture >= 20) without touching
    # any pre-existing key.
    assert "friction_hint" in out
    assert "摩擦" in out["friction_hint"]
    assert all(k in out for k in ("status", "mode", "system_prompt", "captures", "next"))


def test_prepare_no_hint_when_all_calm(tmp_path):
    _write_raw_with_friction(tmp_path, "conv-calm.md", 5)
    out = json.loads(distill.handle_distill_conversation({
        "output_dir": str(tmp_path / "repowiki"),
        "mode": "prepare",
    }, SessionStore()))
    assert out["status"] == "prepared"
    assert "friction_hint" not in out
    assert out["captures"][0]["friction_score"] == 5


def test_get_task_context_pending_raws_carry_friction(tmp_path):
    repo = tmp_path
    od = str(repo / "repowiki")
    store = SessionStore()

    r = json.loads(tm.handle_create_task(
        {"output_dir": od, "title": "摩擦信号机制"}, store))
    assert r["ok"] is True
    task_id = r["task"]["id"]

    # Capture two conversations bound to the task: one calm, one friction-heavy.
    calm = [_u("第一步"), _a("ok"), _u("第二步"), _a("ok"), _u("第三步"), _a("ok")]
    _capture(repo, calm, task_id=task_id)
    _capture(repo, _correction_conversation(), task_id=task_id)

    ctx = json.loads(tm.handle_get_task_context(
        {"output_dir": od, "task_id": task_id}, store))
    assert ctx["ok"] is True
    assert ctx["pending_raw_count"] == 2
    entries = ctx["pending_raws"]
    assert len(entries) == 2
    assert all("friction_score" in e for e in entries)
    scores = {e["relpath"]: e["friction_score"] for e in entries}
    assert any(s >= 40 for s in scores.values())
    assert any(s == 0 for s in scores.values())


# --------------------------------------------------------------------------- #
# K4: session-start hook (stdlib-only line scan)
# --------------------------------------------------------------------------- #

HOOK_PATH = REPO_ROOT / ".codebuddy" / "hooks" / "task_session_start.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("friction_hook_under_test", HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_hook_source_is_stdlib_only():
    src = HOOK_PATH.read_text(encoding="utf-8")
    assert "import codewiki" not in src
    assert "from codewiki" not in src


def test_hook_friction_hint_for_high_score(tmp_path):
    hook = _load_hook()
    raw_dir = tmp_path / "repowiki" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "conv-a.md").write_text(
        "---\n"
        "status: pending\n"
        "task_id: \"task-x\"\n"
        "friction_score: 35\n"
        "friction_signals: correction=2,interrupt=0,repeat=0,user_turns=9\n"
        "---\n\nuser: hi",
        encoding="utf-8",
    )
    hint = hook._latest_friction_hint(str(tmp_path))
    assert "[codewiki]" in hint
    assert "摩擦分 35" in hint
    assert "纠正 2 次" in hint
    assert "distill_conversation" in hint or "蒸馏 worker" in hint


def test_hook_no_hint_for_low_or_missing_score(tmp_path):
    hook = _load_hook()
    raw_dir = tmp_path / "repowiki" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "conv-a.md").write_text(
        "---\nstatus: pending\nfriction_score: 5\n---\n\nuser: hi",
        encoding="utf-8",
    )
    assert hook._latest_friction_hint(str(tmp_path)) == ""

    # Pre-K-line file without the key: silent.
    (raw_dir / "conv-b.md").write_text(
        "---\nstatus: pending\n---\n\nuser: hi", encoding="utf-8")
    assert hook._latest_friction_hint(str(tmp_path)) == ""


def test_hook_skips_distilled_and_empty_dirs(tmp_path):
    hook = _load_hook()
    raw_dir = tmp_path / "repowiki" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    # Distilled file with a high score must not trigger the hint.
    (raw_dir / "conv-a.md").write_text(
        "---\nstatus: distilled\nfriction_score: 80\n---\n\nuser: hi",
        encoding="utf-8",
    )
    assert hook._latest_friction_hint(str(tmp_path)) == ""

    # No raw dir at all → empty hint, no exception.
    assert hook._latest_friction_hint(str(tmp_path / "nowhere")) == ""


def test_hook_message_embeds_friction_hint(tmp_path):
    """End-to-end: the friction hint rides along in additionalContext."""
    import subprocess
    import os

    raw_dir = tmp_path / "repowiki" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "conv-a.md").write_text(
        "---\nstatus: pending\nfriction_score: 35\n"
        "friction_signals: correction=2,interrupt=0,repeat=0,user_turns=9\n"
        "---\n\nuser: hi",
        encoding="utf-8",
    )
    event = json.dumps({"session_id": "s", "cwd": str(tmp_path),
                        "hook_event_name": "SessionStart", "source": "startup"})
    env = dict(os.environ)
    env["CODEBUDDY_PROJECT_DIR"] = str(tmp_path)
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(
        [sys.executable, str(HOOK_PATH)], input=event, capture_output=True,
        text=True, encoding="utf-8", env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "上次会话摩擦分 35" in ctx
    # The pre-existing line-scan behaviour is untouched.
    assert "ask_followup_question" in ctx
