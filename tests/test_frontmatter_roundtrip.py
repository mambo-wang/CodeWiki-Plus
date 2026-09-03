"""Round-trip invariant for the frontmatter read/write pair.

parse(render(x)) == x is the contract that makes src/frontmatter.py the
single serialization point (architecture review 2026-09, candidate #3):
every value shape the wiki write paths produce must survive a write→read
cycle unchanged. A failure here means the write side emits something the
read side cannot faithfully recover — exactly the class of bug the five
hand-rolled parsers used to hide.
"""

from __future__ import annotations

from codewiki.src.frontmatter import (
    format_frontmatter_value,
    inject_okf_frontmatter,
    parse_frontmatter,
    render_frontmatter,
)


def _roundtrip(x: dict) -> None:
    text = render_frontmatter(x)
    y, body = parse_frontmatter(text)
    assert y == x, f"round-trip drift:\n  in : {x!r}\n  out: {y!r}\n  text:\n{text}"
    assert body == "", f"render leaked body content: {body!r}"


def test_scalars_roundtrip():
    _roundtrip(
        {
            "type": "pitfall",
            "title": "simple title",
            "status": "stable",
            "count": 42,
            "ratio": 1.5,
            "flag": True,
            "off": False,
            "nothing": None,
            "empty": "",
        }
    )


def test_tricky_strings_roundtrip():
    _roundtrip(
        {
            "colon": "value: with colon",
            "hash": "value # with hash",
            "quote": 'double " quote',
            "squote": "single ' quote",
            "newline": "line1\nline2",
            "leading_space": " padded",
            "yaml_reserved": "yes",  # must come back as the STRING "yes"
            "json_literal": "true",  # string, not bool
            "number_like": "42",  # string, not int
            "chinese": "中文标题（含全角标点）",
            "unicode": "emoji 🎉 ok",
        }
    )


def test_collections_roundtrip():
    _roundtrip(
        {
            "tags": ["a", "b"],
            "empty_list": [],
            "metadata": {
                "date": "2026-08-01",
                "related_modules": ["wiki_search", "cache"],
                "promoted_to": "",
                "nested_empty": {},
            },
            "verified": [{"by": "human:mambo", "at": "2026-08-14T12:00:00Z"}],
            "verified_multi": [
                {"by": "codewiki/1.0", "at": "2026-08-01T00:00:00Z"},
                {"by": "human:mambo", "at": "2026-08-14T12:00:00Z"},
            ],
        }
    )


def test_full_note_shape_roundtrip():
    """The exact shape ingest_note / doc_writer emit."""
    _roundtrip(
        {
            "type": "decision",
            "title": "检索 kernel 抽取决策",
            "aliases": ["retrieval kernel", "检索内核"],
            "status": "stable",
            "stale_after": "2026-12-02",
            "tags": ["retrieval", "kernel", "BM25"],
            "generated": {"by": "codewiki/5.5.1", "at": "2026-09-03T10:48:47Z"},
            "metadata": {
                "date": "2026-09-03",
                "related_modules": ["wiki_search", "cache"],
                "severity": "high",
            },
        }
    )


def test_parse_reads_inject_okf_output():
    """The historical write side (inject_okf_frontmatter) stays readable.

    render_frontmatter is the new canonical writer; inject_okf_frontmatter
    predates it and writes an inline ``generated: { by: x, at: y }`` flow
    mapping that parse must still tolerate (as an opaque string — never a
    crash, never a bogus key).
    """
    text = inject_okf_frontmatter(
        "body",
        type_="Module",
        title="Okf Round",
        aliases=["okf_round"],
        status="stable",
        okf_tags=["repo"],
        top_level_extra={"task_id": "abc-123"},
        metadata_extra={"category": "backend"},
        actor="codewiki/1.0",
        now_iso="2026-09-03T00:00:00Z",
    )
    fm, body = parse_frontmatter(text)
    assert fm["type"] == "Module"
    assert fm["title"] == "Okf Round"
    assert fm["status"] == "stable"
    assert fm["task_id"] == "abc-123"
    assert fm["metadata"]["category"] == "backend"
    assert body.lstrip().startswith("body")


def test_status_and_task_id_stay_top_level_single_line():
    """Permanent constraint (stdlib-only hook compatibility).

    .codebuddy/hooks/task_session_start.py line-scans status / task_id as
    top-level single-line keys and cannot import this module. render must
    never fold them into a block or nest them under metadata.
    """
    text = render_frontmatter(
        {"status": "draft", "task_id": "multi-仓工作区", "content_hash": "abc"}
    )
    lines = [l for l in text.splitlines() if l and not l.startswith("---")]
    top = [l for l in lines if not l.startswith((" ", "-"))]
    assert any(l.startswith("status:") for l in top)
    assert any(l.startswith("task_id:") for l in top)


def test_format_value_reserved_words():
    assert format_frontmatter_value("yes") == '"yes"'
    assert format_frontmatter_value("null") == '"null"'
    assert format_frontmatter_value("stable") == "stable"
    assert format_frontmatter_value(True) == "true"
    assert format_frontmatter_value(None) == "null"
