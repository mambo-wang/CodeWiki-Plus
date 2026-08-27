"""Unit tests for the transcript noise filters.

Two gate functions were added together with the team-memory L0/L1 design:

- ``capture_conversation._should_capture_l0`` -- lenient gate applied at
  capture time; drops only framework-level structural noise.
- ``distill_conversation._should_extract_l1`` / ``_filter_transcript_lines`` --
  strict gate applied before the LLM call; drops pure-symbol/question rows.
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codewiki.mcp.tools.capture_conversation import _should_capture_l0  # noqa: E402
from codewiki.mcp.tools.distill_conversation import (  # noqa: E402
    _filter_transcript_lines,
    _should_extract_l1,
)


# --------------------------------------------------------------------------- #
# L0 (capture side): lenient gate
# --------------------------------------------------------------------------- #
def test_l0_keeps_normal_dialogue():
    assert _should_capture_l0("hello world")
    assert _should_capture_l0("帮我 review 一下代码")
    assert _should_capture_l0("user: <user_query>继续</user_query>")


def test_l0_drops_empty_and_whitespace():
    assert not _should_capture_l0("")
    assert not _should_capture_l0("   ")
    assert not _should_capture_l0("\n\t")


def test_l0_drops_framework_noise():
    assert not _should_capture_l0("(session bootstrap)")
    assert not _should_capture_l0("NO_REPLY")
    assert not _should_capture_l0("A new session was started via foo")
    assert not _should_capture_l0("Pre-compaction memory flush ...")


def test_l0_prefix_match_does_not_eat_real_content():
    # Prefix list only drops known placeholders, never arbitrary text.
    assert _should_capture_l0("A new feature was started via discussion")


# --------------------------------------------------------------------------- #
# L1 (distill side): strict gate
# --------------------------------------------------------------------------- #
def test_l1_drops_pure_symbols():
    assert not _should_extract_l1("????")
    assert not _should_extract_l1("！！！")
    assert not _should_extract_l1("。。")
    assert not _should_extract_l1("!@#$%")


def test_l1_drops_pure_question_marks_any_length():
    assert not _should_extract_l1("?")
    assert not _should_extract_l1("？？")
    assert not _should_extract_l1("??????")  # 6+ 个问号，超出 {1,5} 兜底


def test_l1_keeps_real_content():
    assert _should_extract_l1("中文内容")
    assert _should_extract_l1("hello world")
    assert _should_extract_l1("123")
    assert _should_extract_l1("a+b=c")
    # 含字母/数字的符号混合行不是纯符号，保留
    assert _should_extract_l1("好的！")


def test_l1_drops_empty():
    assert not _should_extract_l1("")
    assert not _should_extract_l1("  ")


# --------------------------------------------------------------------------- #
# _filter_transcript_lines: role-prefix aware line filtering
# --------------------------------------------------------------------------- #
def test_filter_keeps_dialogue_and_drops_noise_lines():
    transcript = "user: ???\nassistant: 好的，这就改\nuser: \n"
    out = _filter_transcript_lines(transcript)
    assert out == "assistant: 好的，这就改"


def test_filter_does_not_mis_split_content_with_colon_space():
    # content 含 ": "（中文冒号场景），前缀匹配不应误切 role 段
    transcript = "user: 注意：这是重点\nassistant: 明白\n"
    out = _filter_transcript_lines(transcript)
    assert "注意：这是重点" in out
    assert "明白" in out


def test_filter_handles_bare_content_lines():
    transcript = "第一行\n？？？\n第三行"
    out = _filter_transcript_lines(transcript)
    assert out == "第一行\n第三行"


def test_filter_empty_input():
    assert _filter_transcript_lines("") == ""
    assert _filter_transcript_lines("\n\n") == ""
