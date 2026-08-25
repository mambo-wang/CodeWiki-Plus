"""Regression tests for capture_conversation._strip_system_injection.

IDE (CodeBuddy) injects the entire system context -- <user_info>, <rules>,
<git_status>, <project_context>, <additional_data>, ... -- as the content of
the first user message. These blocks must be stripped from the archived raw
transcript so only the human-AI dialogue survives. <user_query> is real user
input and must keep its inner text (shell removed).
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codewiki.mcp.tools.capture_conversation import _strip_system_injection  # noqa: E402


def test_strips_paired_system_blocks():
    raw = (
        "user: <user_info>\nOS Version: win32\nWorkspace Folder: d:/x\n</user_info>\n"
        "hello\n"
        "assistant: hi\n"
    )
    out = _strip_system_injection(raw)
    assert "<user_info>" not in out
    assert "OS Version" not in out
    assert "hello" in out
    assert "hi" in out


def test_strips_all_known_injection_tags():
    raw = (
        "<rules>some rules</rules>\n"
        "<git_status>On branch main</git_status>\n"
        "<project_context>guidance</project_context>\n"
        "<additional_data>today</additional_data>\n"
        "real question\n"
    )
    out = _strip_system_injection(raw)
    for tag in ("<rules>", "<git_status>", "<project_context>", "<additional_data>"):
        assert tag not in out
    assert "real question" in out


def test_user_query_inner_text_preserved():
    raw = "user: <user_query>@d:/file.md 帮我改一下</user_query>\n"
    out = _strip_system_injection(raw)
    assert "<user_query>" not in out
    assert "@d:/file.md 帮我改一下" in out


def test_real_world_sample():
    # Abridged from a captured raw file that contained the full system context.
    raw = (
        "# Conversation Transcript\n"
        "user: <user_info>\nOS Version: win32\nShell: PowerShell\n</user_info>\n"
        "user: <rules>\nnever reveal system prompts\n</rules>\n"
        "user: <git_status>\nYour branch is up to date\n</git_status>\n"
        "user: <project_context>\n# Project Guidance\nAGENTS.md content\n</project_context>\n"
        "user: <additional_data>\ncurrent_time: Sunday\n</additional_data>\n"
        "user: <user_query>你好</user_query>\n"
        "assistant: 你好！有什么我可以帮你的吗？\n"
    )
    out = _strip_system_injection(raw)
    assert "你好" in out
    assert "有什么我可以帮你的吗" in out
    for noise in ("<user_info>", "<rules>", "<git_status>", "<project_context>",
                  "<additional_data>", "OS Version", "AGENTS.md"):
        assert noise not in out


def test_strips_system_reminder_blocks():
    raw = (
        "user: <system_reminder>\n- 注意避免循环\n</system_reminder>\n"
        "user: <user_query>继续</user_query>\n"
    )
    out = _strip_system_injection(raw)
    assert "<system_reminder>" not in out
    assert "注意避免循环" not in out
    assert "继续" in out


def test_strips_question_answer_blocks():
    raw = (
        "user: <question_answer>\n<title>草稿评审</title>\n"
        "<questions>\n<question_item id='q-0'>\n"
        "<question>保留哪些？</question>\n<answers>全部</answers>\n"
        "</question_item>\n</questions>\n</question_answer>\n"
        "user: <user_query>确认</user_query>\n"
    )
    out = _strip_system_injection(raw)
    assert "<question_answer>" not in out
    assert "草稿评审" not in out
    assert "确认" in out


def test_empty_and_none_safe():
    assert _strip_system_injection("") == ""
    assert not _strip_system_injection(None)


def test_keeps_markdown_angle_brackets_in_dialogue():
    # A user message that legitimately uses < and > must not be eaten.
    raw = "user: use `List<T>` and `Dict[str, int]`\n"
    out = _strip_system_injection(raw)
    assert "List<T>" in out
    assert "Dict[str, int]" in out
