"""Schema-level target-anchor guards (A+B+C).

Regression coverage for the "agents omit output_dir/repo_path" problem,
updated for the output_dir-retirement world:
- A: no registered tool advertises the retired output_dir; knowledge-base
     tools expose repo_path as the single anchor.
- B: dispatch injects repo_path=<server start CWD> when a call carries no
     explicit repo_path, so resolution succeeds instead of raising. Explicit
     repo_path is never overwritten (output_dir is NOT an anchor anymore).
- C: resolve_output_dir raises an actionable error and dispatch wraps it in a
     JSON payload with a "fix" field.
"""

import asyncio
import importlib as _il
import json

import pytest
from mcp.types import TextContent, Tool

from codewiki.mcp.registry import REGISTRY, ToolDef, dispatch
from codewiki.mcp.registry import _inject_repo_path_default
from codewiki.mcp.tools.store_bridge import resolve_output_dir


# --------------------------------------------------------------------------- #
# A: single-anchor schema invariant (output_dir retired)
# --------------------------------------------------------------------------- #


def test_no_tool_advertises_output_dir() -> None:
    """Exhaustive invariant: output_dir is retired — it must not appear in any
    registered tool schema. repo_path is the single target anchor."""
    for name, td in REGISTRY.items():
        props = td.schema.inputSchema.get("properties") or {}
        assert "output_dir" not in props, f"{name} still advertises output_dir"


def test_tool_already_requiring_anchor_is_untouched() -> None:
    # analyze_repo already requires repo_path — no anchor fallback needed.
    schema = REGISTRY["analyze_repo"].schema.inputSchema
    assert "repo_path" in schema["required"]


def test_query_wiki_schema_declares_repo_path() -> None:
    """query_wiki's handler derives output_dir from repo_path; the schema must
    expose repo_path so clients never hit a runtime anchor error."""
    props = REGISTRY["query_wiki"].schema.inputSchema["properties"]
    assert "repo_path" in props


def test_batch_ingest_schema_declares_repo_path() -> None:
    props = REGISTRY["batch_ingest"].schema.inputSchema["properties"]
    assert "repo_path" in props


# --------------------------------------------------------------------------- #
# B: server-CWD fallback injection
# --------------------------------------------------------------------------- #


def test_inject_fills_only_when_fully_absent(monkeypatch, tmp_path) -> None:
    cwd = str(tmp_path)
    monkeypatch.setattr("codewiki.mcp.registry._SERVER_START_CWD", cwd)

    a: dict = {}
    _inject_repo_path_default(a)
    assert a == {"repo_path": cwd}

    # A legacy output_dir arg is NOT an anchor in the retired world: the call
    # still needs repo_path and gets the CWD fallback. Explicit repo_path is
    # never overwritten.
    b = {"output_dir": "x"}
    _inject_repo_path_default(b)
    assert b == {"output_dir": "x", "repo_path": cwd}

    c = {"repo_path": "y"}
    _inject_repo_path_default(c)
    assert c == {"repo_path": "y"}


def test_inject_noop_when_start_cwd_unset(monkeypatch) -> None:
    monkeypatch.setattr("codewiki.mcp.registry._SERVER_START_CWD", None)
    a: dict = {}
    _inject_repo_path_default(a)
    assert a == {}


# --------------------------------------------------------------------------- #
# C: actionable errors
# --------------------------------------------------------------------------- #


def test_resolve_output_dir_error_is_actionable() -> None:
    with pytest.raises(ValueError, match=r"repo_path=<repo root>"):
        resolve_output_dir(None, {})


def _boom(arguments, store):
    raise ValueError("output_dir or repo_path is required (or pass an active session).")


def test_dispatch_anchor_error_carries_fix(monkeypatch) -> None:
    """dispatch must wrap anchor-resolution ValueErrors with a 'fix' field the
    calling LLM can act on (not just a bare error string)."""
    fake = ToolDef(
        schema=Tool(
            name="__anchor_boom",
            description="test-only",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        handler_path="fakemodule:_boom",
        mode="main_thread",
        takes_store=True,
    )
    monkeypatch.setitem(REGISTRY, "__anchor_boom", fake)
    monkeypatch.setattr(
        _il,
        "import_module",
        lambda _path: type("m", (), {"_boom": _boom}),
    )

    results = asyncio.run(dispatch("__anchor_boom", {}, None))
    assert isinstance(results, list) and isinstance(results[0], TextContent)
    payload = json.loads(results[0].text)
    assert payload["error"]
    assert "fix" in payload
    assert "repo_path" in payload["fix"]
    monkeypatch.delitem(REGISTRY, "__anchor_boom", raising=False)
