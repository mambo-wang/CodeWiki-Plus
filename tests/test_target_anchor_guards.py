"""Schema-level target-anchor guards (A+B+C).

Regression coverage for the "agents omit output_dir/repo_path" problem:
- A: anyOf(output_dir | repo_path) is post-processed into every dual-anchor
     knowledge-base tool schema that requires neither path.
- B: dispatch injects repo_path=<server start CWD> when a call carries no
     explicit anchor (output_dir/repo_path), so resolution succeeds instead
     of raising. Explicit arguments are never overwritten.
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
# A: schema-level anyOf guard
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "tool_name",
    [
        "capture_conversation",
        "query_wiki",
        "ingest_note",
        "ingest_source",
        "distill_conversation",
        "lint_wiki",
        "confirm_note",
        "reject_note",
        "wiki_stats",
        "write_doc_file",
    ],
)
def test_dual_anchor_tools_gain_anyof(tool_name: str) -> None:
    """Tools exposing both output_dir and repo_path (neither required) must
    advertise anyOf so clients/LLMs treat one of them as required."""
    schema = REGISTRY[tool_name].schema.inputSchema
    assert schema.get("anyOf") == [
        {"required": ["output_dir"]},
        {"required": ["repo_path"]},
    ]


def test_tool_already_requiring_anchor_is_untouched() -> None:
    # analyze_repo already requires repo_path — an anyOf would be redundant.
    schema = REGISTRY["analyze_repo"].schema.inputSchema
    assert "repo_path" in schema["required"]
    assert "anyOf" not in schema


def test_query_wiki_schema_declares_repo_path() -> None:
    """query_wiki's handler derives output_dir from repo_path, but the schema
    used to omit the parameter — the main source of runtime "output_dir is
    required" errors. It must now expose repo_path."""
    props = REGISTRY["query_wiki"].schema.inputSchema["properties"]
    assert "repo_path" in props


def test_batch_ingest_schema_declares_repo_path() -> None:
    props = REGISTRY["batch_ingest"].schema.inputSchema["properties"]
    assert "repo_path" in props


def test_all_dual_anchor_tools_get_anyof() -> None:
    """Exhaustive invariant: every registered tool whose properties include
    both anchors — and requires neither — must carry the anyOf guard."""
    from codewiki.mcp.registry import _apply_target_anchor_anyof

    _apply_target_anchor_anyof()  # idempotent re-apply
    for name, td in REGISTRY.items():
        schema = td.schema.inputSchema
        props = schema.get("properties") or {}
        if "output_dir" not in props or "repo_path" not in props:
            continue
        required = set(schema.get("required") or [])
        if "output_dir" in required or "repo_path" in required:
            assert "anyOf" not in schema, f"{name} already requires an anchor"
            continue
        assert schema.get("anyOf"), f"{name} missing anyOf guard"


# --------------------------------------------------------------------------- #
# B: server-CWD fallback injection
# --------------------------------------------------------------------------- #


def test_inject_fills_only_when_fully_absent(monkeypatch, tmp_path) -> None:
    cwd = str(tmp_path)
    monkeypatch.setattr("codewiki.mcp.registry._SERVER_START_CWD", cwd)

    a: dict = {}
    _inject_repo_path_default(a)
    assert a == {"repo_path": cwd}

    # Explicit anchors are never overwritten.
    b = {"output_dir": "x"}
    _inject_repo_path_default(b)
    assert b == {"output_dir": "x"}

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
