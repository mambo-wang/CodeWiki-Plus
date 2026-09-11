# -*- coding: utf-8 -*-
"""Tests for codewiki.src.secret_redact (2026-09-11 PyPI token incident)."""

from __future__ import annotations

from codewiki.src.secret_redact import redact_secrets
from codewiki.src.tool_digest import digest_blocks

PYPI = "REDACTED"
GITHUB = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"


def test_pypi_token_is_redacted():
    out = redact_secrets(f"$env:UV_PUBLISH_TOKEN='{PYPI}'")
    assert PYPI not in out
    assert "<redacted:" in out


def test_github_token_is_redacted():
    out = redact_secrets(f"git push https://x-access-token:{GITHUB}@github.com/o/r.git")
    assert GITHUB not in out


def test_env_assignment_keeps_name_drops_value():
    """The archived line must still read as 'a token was set here'."""
    out = redact_secrets("export SOME_API_KEY='abcdef123456'")
    assert "SOME_API_KEY" in out
    assert "abcdef123456" not in out


def test_powershell_env_assignment():
    out = redact_secrets("$env:UV_PUBLISH_TOKEN='abcdef123456'")
    assert "UV_PUBLISH_TOKEN" in out
    assert "abcdef123456" not in out


def test_operational_detail_survives():
    """Redaction must not eat the flags/paths skills are compiled from."""
    line = "uv publish --publish-url https://upload.pypi.org/legacy/ dist/foo-1.2.3.tar.gz"
    assert redact_secrets(line) == line


def test_non_string_and_empty_pass_through():
    assert redact_secrets("") == ""
    # Contract: never raises on odd input, returns it unchanged.
    assert redact_secrets(None) is None  # type: ignore[arg-type]


def test_digest_blocks_redacts_tool_commands():
    """The exact shape that leaked: a publish command inside a tool call."""
    blocks = [
        {
            "type": "tool-call",
            "name": "execute_command",
            "input": {"command": f"cd d:/repo; $env:UV_PUBLISH_TOKEN='{PYPI}'; uv publish"},
        }
    ]
    lines = digest_blocks(blocks)
    joined = "\n".join(lines)
    assert PYPI not in joined
    assert "<redacted:" in joined


def test_digest_blocks_keeps_command_skeleton():
    blocks = [
        {
            "type": "tool-call",
            "name": "execute_command",
            "input": {"command": f"cd d:/repo; $env:UV_PUBLISH_TOKEN='{PYPI}'; uv publish dist/x.tar.gz"},
        }
    ]
    joined = "\n".join(digest_blocks(blocks))
    # The procedure (publish step) must still be distillable.
    assert "uv publish" in joined
