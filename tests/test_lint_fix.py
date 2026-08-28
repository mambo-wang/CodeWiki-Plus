"""Tests for lint_wiki's ``fix`` parameter (self-healing stale index)."""

import json
from pathlib import Path

from codewiki.mcp.tools.wiki_lint import (
    _check_stale_refs,
    _load_module_tree,
    handle_lint_wiki,
)


def _run_lint(output_dir: Path, **kwargs) -> dict:
    args = {"output_dir": str(output_dir), "checks": ["stale_refs"], **kwargs}
    out = handle_lint_wiki(args, None)
    return json.loads(out) if isinstance(out, str) else out


def _make_wiki(tmp_path: Path) -> Path:
    """Build a minimal wiki with a stale index.md referencing a removed note."""
    output_dir = tmp_path / "repowiki"
    wiki_dir = output_dir / "wiki"
    modules_dir = wiki_dir / "modules"
    modules_dir.mkdir(parents=True)

    (modules_dir / "Alpha.md").write_text(
        "---\ntype: Module\ntitle: Alpha\naliases: [Alpha]\n---\n\n# Alpha\n\nContent.\n",
        encoding="utf-8",
    )

    # index.md references a note file that does not exist on disk
    (wiki_dir / "index.md").write_text(
        "---\nokf_version: 0.2\ntype: Index\n---\n\n"
        "# Wiki Index\n\n"
        "- [Note A](../notes/2026-08-01-deleted-note.md)\n",
        encoding="utf-8",
    )

    # Non-empty module tree so stale_refs check runs
    meta_dir = output_dir / ".meta"
    meta_dir.mkdir(parents=True)
    (meta_dir / "module_tree.json").write_text(
        json.dumps({"alpha": {"components": []}}), encoding="utf-8"
    )
    return output_dir


def test_lint_reports_stale_index_ref(tmp_path):
    output_dir = _make_wiki(tmp_path)
    module_tree = _load_module_tree(output_dir)
    stale = _check_stale_refs(output_dir, module_tree)
    assert len(stale) == 1
    assert Path(stale[0]["file"]).as_posix().endswith("wiki/index.md")


def test_fix_true_rebuilds_index_and_clears_stale_refs(tmp_path):
    output_dir = _make_wiki(tmp_path)

    # Sanity: lint reports one stale ref before the fix
    result_before = _run_lint(output_dir)
    stale_before = [i for i in result_before["issues"] if i["check"] == "stale_refs"]
    assert len(stale_before) == 1

    # Apply the fix
    result = _run_lint(output_dir, fix=True)
    stale_after = [i for i in result["issues"] if i["check"] == "stale_refs"]
    assert stale_after == [], f"expected no stale refs after fix, got {stale_after}"

    # index.md was rebuilt and no longer references the removed note
    rebuilt = (output_dir / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "2026-08-01-deleted-note" not in rebuilt
    assert "Alpha" in rebuilt  # rebuilt index still lists live pages
    assert "Health Score" in rebuilt  # regenerated index carries score header


def test_fix_does_not_touch_content_files(tmp_path):
    output_dir = _make_wiki(tmp_path)
    module_path = output_dir / "wiki" / "modules" / "Alpha.md"
    before = module_path.read_text(encoding="utf-8")

    _run_lint(output_dir, fix=True)

    after = module_path.read_text(encoding="utf-8")
    assert after == before, "content file must not be modified by fix"


def test_fix_false_is_read_only(tmp_path):
    output_dir = _make_wiki(tmp_path)
    index_before = (output_dir / "wiki" / "index.md").read_text(encoding="utf-8")

    _run_lint(output_dir)

    index_after = (output_dir / "wiki" / "index.md").read_text(encoding="utf-8")
    assert index_after == index_before


def test_fix_noop_when_no_stale_refs(tmp_path):
    output_dir = _make_wiki(tmp_path)
    # Fresh index has nothing stale
    _run_lint(output_dir, fix=True)
    result = _run_lint(output_dir, fix=True)
    stale = [i for i in result["issues"] if i["check"] == "stale_refs"]
    assert stale == []


def test_fix_clears_broken_links_computed_on_old_index(tmp_path):
    """Regression: broken_links must not linger after fix=true rebuilds.

    The dead link in index.md is detected by BOTH stale_refs and
    broken_links when both checks run (the broken_links copy is normally
    deduped away by stale_refs).  In the old post-hoc fix order the rebuild
    dropped the stale_refs issues first, which disarmed the dedup and let
    the broken_links copies computed on the OLD index linger as errors.
    With fix=true the rebuild happens before the checks run, so neither
    check may report the removed note.
    """
    output_dir = _make_wiki(tmp_path)

    result_before = _run_lint(output_dir, checks=["stale_refs", "broken_links"])
    assert any(
        "2026-08-01-deleted-note" in str(i.get("message", "")) for i in result_before["issues"]
    )

    result = _run_lint(output_dir, fix=True, checks=["stale_refs", "broken_links"])
    assert [i for i in result["issues"] if i["check"] == "stale_refs"] == []
    assert [i for i in result["issues"] if i["check"] == "broken_links"] == []
    assert not any("2026-08-01-deleted-note" in str(i.get("message", "")) for i in result["issues"])
