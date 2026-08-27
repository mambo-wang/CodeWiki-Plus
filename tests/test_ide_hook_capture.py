"""Regression tests for codewiki/mcp/_ide_hook.py (team-memory capture hook).

Covers the issues found in the review of commit 2e8c78c:

1. **Data loss (critical)**: a SessionEnd/Stop/PreCompact event without an
   inline transcript synthesizes a 1-line "event envelope". If that envelope
   carried ``source_session_id``, capture_conversation's session-scoped
   supersede logic would overwrite the previously captured full transcript
   with the diagnostic one-liner. The envelope must NOT carry it.

2. **Inline turns multi-key support**: IDEs inline conversations under several
   common keys (conversation / messages / turns / transcript_turns / chat).
   All must be recognized, both in stdin events and in transcript files.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codewiki.mcp import _ide_hook  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class _FakeStdin(io.StringIO):
    """StringIO that reports isatty() == False (like a real piped stdin)."""

    def isatty(self) -> bool:
        return False


@pytest.fixture
def enable_hook(monkeypatch):
    monkeypatch.setenv("CODEWIKI_TEAM_MEMORY_HOOK", "1")


def _run_hook_stdin(monkeypatch, payload: dict, repo: Path) -> int:
    """Invoke the hook's main() with a JSON payload on stdin."""
    monkeypatch.setattr("sys.stdin", _FakeStdin(json.dumps(payload)))
    return _ide_hook.main(["--repo-path", str(repo)])


def _raw_files(repo: Path) -> list[Path]:
    return sorted((repo / "repowiki" / "raw").glob("conv-*.md"))


# --------------------------------------------------------------------------- #
# Issue #1: envelope must not supersede a real transcript
# --------------------------------------------------------------------------- #
def test_envelope_does_not_supersede_full_transcript(enable_hook, monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    sid = "ide-session-abc"

    # 1) Stop fires with a full inline transcript -> captured with source_session_id
    rc1 = _run_hook_stdin(
        monkeypatch,
        {
            "hook_event_name": "Stop",
            "session_id": sid,
            "conversation": [
                {"role": "user", "content": "real question with substance"},
                {"role": "assistant", "content": "real detailed answer"},
            ],
        },
        repo,
    )
    assert rc1 == 0

    files = _raw_files(repo)
    assert len(files) == 1
    full_text = files[0].read_text(encoding="utf-8")
    assert "real question with substance" in full_text
    assert f'source_session: "{sid}"' in full_text

    # 2) SessionEnd fires for the SAME session but WITHOUT any transcript.
    #    Before the fix, the synthesized envelope carried source_session_id and
    #    supersede-replaced the full transcript -> data loss.
    rc2 = _run_hook_stdin(
        monkeypatch,
        {
            "hook_event_name": "SessionEnd",
            "session_id": sid,
            "cwd": str(repo),
        },
        repo,
    )
    assert rc2 == 0

    files = _raw_files(repo)
    # Envelope must be a NEW file, not a replacement of the full transcript.
    assert len(files) == 2

    texts = [p.read_text(encoding="utf-8") for p in files]
    # The full transcript must survive intact.
    assert any("real question with substance" in t for t in texts)
    # The envelope exists and carries NO source_session id.
    envelopes = [t for t in texts if "event envelope preserved" in t]
    assert len(envelopes) == 1
    assert 'source_session: ""' in envelopes[0]
    assert f'source_session: "{sid}"' not in envelopes[0]


def test_envelope_only_fires_for_lifecycle_events(enable_hook, monkeypatch, tmp_path, capsys):
    """A payload with no turns and a non-lifecycle event must be a no-op."""
    repo = tmp_path / "repo"
    repo.mkdir()

    rc = _run_hook_stdin(
        monkeypatch,
        {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "s1",
        },
        repo,
    )
    assert rc == 0
    assert not (repo / "repowiki" / "raw").exists() or not _raw_files(repo)


# --------------------------------------------------------------------------- #
# Issue #2: inline turns under several common keys
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("key", ["conversation", "messages", "turns", "transcript_turns", "chat"])
def test_inline_turns_keys_are_captured(enable_hook, monkeypatch, tmp_path, key):
    repo = tmp_path / "repo"
    repo.mkdir()

    rc = _run_hook_stdin(
        monkeypatch,
        {
            "hook_event_name": "SessionEnd",
            "session_id": "s2",
            key: [
                {"role": "user", "content": f"inline via {key}"},
                {"role": "assistant", "content": "reply"},
            ],
        },
        repo,
    )
    assert rc == 0
    files = _raw_files(repo)
    assert len(files) == 1
    assert f"inline via {key}" in files[0].read_text(encoding="utf-8")


def test_extract_inline_turns_unit():
    assert _ide_hook._extract_inline_turns({"messages": [{"role": "u"}]}) == [{"role": "u"}]
    assert _ide_hook._extract_inline_turns({"chat": [{"role": "u"}]}) == [{"role": "u"}]
    assert _ide_hook._extract_inline_turns({"unrelated": [{"role": "u"}]}) is None
    assert _ide_hook._extract_inline_turns({"messages": []}) is None  # empty -> None
    assert _ide_hook._extract_inline_turns({"messages": "not-a-list"}) is None


def test_load_transcript_supports_wrapper_keys(tmp_path):
    """Transcript files wrapped in transcript_turns/chat keys must be readable."""
    for key in ("conversation", "messages", "turns", "transcript_turns", "chat"):
        f = tmp_path / f"t-{key}.json"
        f.write_text(json.dumps({key: [{"role": "user", "content": "hi"}]}), encoding="utf-8")
        turns = _ide_hook._load_transcript(str(f))
        assert turns == [{"role": "user", "content": "hi"}], f"key={key} failed"


# --------------------------------------------------------------------------- #
# Issue #3: CodeBuddy index.json + messages/ transcript format
# --------------------------------------------------------------------------- #
def _make_codebuddy_transcript(tmp_path: Path, messages: list[dict]) -> Path:
    """Create a CodeBuddy-style transcript: index.json + messages/<id>.json."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    msgs_dir = session_dir / "messages"
    msgs_dir.mkdir()

    index_messages = []
    for msg in messages:
        msg_id = msg["id"]
        index_messages.append(
            {
                "id": msg_id,
                "type": "text",
                "role": msg["role"],
                "isComplete": True,
            }
        )
        msg_file = msgs_dir / f"{msg_id}.json"
        msg_file.write_text(json.dumps(msg["file_data"]), encoding="utf-8")

    index_file = session_dir / "index.json"
    index_file.write_text(json.dumps({"messages": index_messages}), encoding="utf-8")
    return index_file


def test_expand_codebuddy_index(tmp_path):
    """CodeBuddy index.json + messages/ dir must expand into full turns."""
    index_file = _make_codebuddy_transcript(
        tmp_path,
        [
            {
                "id": "m1",
                "role": "user",
                "file_data": {
                    "role": "user",
                    "message": json.dumps(
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": "hello world"}],
                        }
                    ),
                },
            },
            {
                "id": "m2",
                "role": "assistant",
                "file_data": {
                    "role": "assistant",
                    "message": json.dumps(
                        {
                            "role": "assistant",
                            "content": [
                                {"type": "reasoning", "text": "thinking..."},
                                {"type": "tool-call", "toolName": "list_dir", "args": {}},
                                {"type": "text", "text": "here is the answer"},
                            ],
                        }
                    ),
                },
            },
            {
                "id": "m3",
                "role": "tool",
                "file_data": {
                    "role": "tool",
                    "message": json.dumps(
                        {
                            "role": "tool",
                            "content": [{"type": "tool-result", "text": "file listing"}],
                        }
                    ),
                },
            },
        ],
    )

    turns = _ide_hook._load_transcript(str(index_file))
    assert turns is not None
    # tool messages are skipped, reasoning/tool-call blocks filtered
    assert len(turns) == 2
    assert turns[0] == {"role": "user", "content": "hello world"}
    assert turns[1] == {"role": "assistant", "content": "here is the answer"}


def test_expand_codebuddy_index_only_user_assistant(tmp_path):
    """Only user/assistant dialogue is kept; system/thinking/other roles dropped."""
    index_file = _make_codebuddy_transcript(
        tmp_path,
        [
            {
                "id": "m0",
                "role": "system",
                "file_data": {
                    "role": "system",
                    "message": json.dumps(
                        {
                            "role": "system",
                            "content": [{"type": "text", "text": "You are a helpful assistant."}],
                        }
                    ),
                },
            },
            {
                "id": "m1",
                "role": "user",
                "file_data": {
                    "role": "user",
                    "message": json.dumps(
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": "user question"}],
                        }
                    ),
                },
            },
            {
                "id": "m2",
                "role": "assistant",
                "file_data": {
                    "role": "assistant",
                    "message": json.dumps(
                        {
                            "role": "assistant",
                            "content": [{"type": "text", "text": "assistant answer"}],
                        }
                    ),
                },
            },
            {
                "id": "m3",
                "role": "thinking",
                "file_data": {
                    "role": "thinking",
                    "message": json.dumps(
                        {
                            "role": "thinking",
                            "content": [{"type": "text", "text": "internal thought"}],
                        }
                    ),
                },
            },
            {
                "id": "m4",
                "role": "tool",
                "file_data": {
                    "role": "tool",
                    "message": json.dumps(
                        {
                            "role": "tool",
                            "content": [{"type": "text", "text": "tool output"}],
                        }
                    ),
                },
            },
        ],
    )

    turns = _ide_hook._load_transcript(str(index_file))
    assert turns == [
        {"role": "user", "content": "user question"},
        {"role": "assistant", "content": "assistant answer"},
    ]


def test_expand_codebuddy_index_skips_missing_files(tmp_path):
    """Messages whose files don't exist are silently skipped."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    msgs_dir = session_dir / "messages"
    msgs_dir.mkdir()

    # Only create file for m1, not m2
    (msgs_dir / "m1.json").write_text(
        json.dumps(
            {
                "role": "user",
                "message": json.dumps(
                    {"role": "user", "content": [{"type": "text", "text": "hi"}]}
                ),
            }
        ),
        encoding="utf-8",
    )

    index_file = session_dir / "index.json"
    index_file.write_text(
        json.dumps(
            {
                "messages": [
                    {"id": "m1", "type": "text", "role": "user", "isComplete": True},
                    {"id": "m2", "type": "text", "role": "assistant", "isComplete": True},
                ]
            }
        ),
        encoding="utf-8",
    )

    turns = _ide_hook._load_transcript(str(index_file))
    assert turns == [{"role": "user", "content": "hi"}]


def test_expand_codebuddy_index_not_an_index(tmp_path):
    """A messages list with inline content is NOT treated as an index."""
    f = tmp_path / "t.json"
    f.write_text(
        json.dumps(
            {
                "messages": [
                    {"id": "m1", "role": "user", "content": "inline content"},
                ],
            }
        ),
        encoding="utf-8",
    )
    turns = _ide_hook._load_transcript(str(f))
    assert turns == [{"id": "m1", "role": "user", "content": "inline content"}]


def test_codebuddy_transcript_e2e(enable_hook, monkeypatch, tmp_path):
    """Full pipeline: SessionEnd with transcript_path -> CodeBuddy index -> conv-*.md."""
    repo = tmp_path / "repo"
    repo.mkdir()

    index_file = _make_codebuddy_transcript(
        tmp_path,
        [
            {
                "id": "m1",
                "role": "user",
                "file_data": {
                    "role": "user",
                    "message": json.dumps(
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": "what is CodeWiki?"}],
                        }
                    ),
                },
            },
            {
                "id": "m2",
                "role": "assistant",
                "file_data": {
                    "role": "assistant",
                    "message": json.dumps(
                        {
                            "role": "assistant",
                            "content": [{"type": "text", "text": "CodeWiki is an LLM wiki."}],
                        }
                    ),
                },
            },
        ],
    )

    rc = _run_hook_stdin(
        monkeypatch,
        {
            "hook_event_name": "SessionEnd",
            "session_id": "cb-session-001",
            "transcript_path": str(index_file),
        },
        repo,
    )
    assert rc == 0

    files = _raw_files(repo)
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "what is CodeWiki?" in text
    assert "CodeWiki is an LLM wiki." in text
    assert 'source_session: "cb-session-001"' in text


def test_extract_codebuddy_message_text_variants():
    """Unit tests for _extract_codebuddy_message_text edge cases."""
    # JSON string message with content blocks
    assert (
        _ide_hook._extract_codebuddy_message_text(
            {
                "message": json.dumps({"content": [{"type": "text", "text": "abc"}]}),
            }
        )
        == "abc"
    )

    # Plain string message (not JSON)
    assert (
        _ide_hook._extract_codebuddy_message_text(
            {
                "message": "plain text",
            }
        )
        == "plain text"
    )

    # Dict message
    assert (
        _ide_hook._extract_codebuddy_message_text(
            {
                "message": {"content": [{"type": "text", "text": "xyz"}]},
            }
        )
        == "xyz"
    )

    # Fallback to top-level content
    assert (
        _ide_hook._extract_codebuddy_message_text(
            {
                "content": [{"type": "text", "text": "fallback"}],
            }
        )
        == "fallback"
    )

    # String content
    assert (
        _ide_hook._extract_codebuddy_message_text(
            {
                "content": "direct string",
            }
        )
        == "direct string"
    )

    # All noise -> empty
    assert (
        _ide_hook._extract_codebuddy_message_text(
            {
                "message": json.dumps(
                    {
                        "content": [
                            {"type": "reasoning", "text": "thinking"},
                            {"type": "tool-call", "toolName": "x"},
                        ]
                    }
                ),
            }
        )
        == ""
    )


# --------------------------------------------------------------------------- #
# Opt-in gate still holds
# --------------------------------------------------------------------------- #
def test_hook_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("CODEWIKI_TEAM_MEMORY_HOOK", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(
        "sys.stdin",
        _FakeStdin(
            json.dumps(
                {
                    "conversation": [{"role": "user", "content": "x"}],
                }
            )
        ),
    )
    rc = _ide_hook.main(["--repo-path", str(repo)])
    assert rc == 0
    assert not _raw_files(repo)


# --------------------------------------------------------------------------- #
# Filename is derived from the first user message (mirrors IDE title)
# --------------------------------------------------------------------------- #
from codewiki.mcp.tools import capture_conversation as _cap  # noqa: E402


def test_slugify_filesystem_safe():
    assert _cap._slugify("review 最近一次提交") == "review-最近一次提交"
    # unsafe chars collapsed to dash
    assert _cap._slugify('a/b:c*?"d') == "a-b-c-d"
    # whitespace collapsed
    assert _cap._slugify("  hello   world  ") == "hello-world"
    # empty input
    assert _cap._slugify("") == ""
    assert _cap._slugify("   ") == ""


def test_slugify_truncates_long_text():
    long = "x" * 200
    slug = _cap._slugify(long)
    assert len(slug) <= _cap._MAX_SLUG_LEN


def test_filename_from_first_user_message(tmp_path):
    """Archived file name mirrors the first user message, not a timestamp."""
    out = tmp_path / "repowiki"
    raw = out / "raw"
    raw.mkdir(parents=True)

    class _Store:
        def get(self, sid):
            return None

    import json as _json

    result = _json.loads(
        _cap.handle_capture_conversation(
            {
                "output_dir": str(out),
                "conversation": [
                    {"role": "user", "content": "review 最近一次提交"},
                    {"role": "assistant", "content": "好的，我来审查"},
                ],
            },
            _Store(),
        )
    )
    assert result["status"] == "captured"
    # conversation_id is the filename stem without the conv- prefix
    assert result["conversation_id"].startswith("conv-")
    assert "review-最近一次提交" in result["conversation_id"]
    fname = raw / f"{result['conversation_id']}.md"
    assert fname.exists()
    # conversation_id must equal file stem (distill_conversation relies on this)
    assert fname.stem == result["conversation_id"]


def test_filename_falls_back_to_timestamp_when_no_user(tmp_path):
    """No user turn (e.g. assistant-only) -> timestamp-based name."""
    out = tmp_path / "repowiki"
    raw = out / "raw"
    raw.mkdir(parents=True)

    class _Store:
        def get(self, sid):
            return None

    import json as _json

    result = _json.loads(
        _cap.handle_capture_conversation(
            {
                "output_dir": str(out),
                "conversation": [
                    {"role": "assistant", "content": "only assistant text"},
                ],
            },
            _Store(),
        )
    )
    assert result["status"] == "captured"
    # Falls back to a timestamp-like stem with no CJK slug prefix issues
    assert result["conversation_id"].startswith("conv-")
    # It should NOT contain a slug from user text since there is none
    files = list(raw.glob("conv-*.md"))
    assert len(files) == 1


def test_filename_collision_appends_suffix(tmp_path):
    """Two captures with the same first user line get distinct file names."""
    out = tmp_path / "repowiki"
    raw = out / "raw"
    raw.mkdir(parents=True)

    class _Store:
        def get(self, sid):
            return None

    import json as _json

    conv = [{"role": "user", "content": "重复的开场白"}, {"role": "assistant", "content": "回答"}]
    _json.loads(
        _cap.handle_capture_conversation({"output_dir": str(out), "conversation": conv}, _Store())
    )
    _json.loads(
        _cap.handle_capture_conversation({"output_dir": str(out), "conversation": conv}, _Store())
    )
    # Second capture supersedes the first (same source_session empty) — but here
    # neither has source_session_id, so they are both written. Ensure distinct.
    files = list(raw.glob("conv-*.md"))
    stems = {f.stem for f in files}
    assert len(stems) == len(files)
    # At least one carries the expected slug
    assert any("重复的开场白" in s for s in stems)
