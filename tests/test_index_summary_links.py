"""Tests for index.md summary link re-basing.

A page's frontmatter ``description`` carries links authored relative to that
page's own directory (``wiki/modules/``).  Index bullets live one level up in
``wiki/index.md``, so those links must gain the page's directory prefix or
``lint_wiki`` reports them as broken (stale_refs).
"""

from __future__ import annotations

from codewiki.mcp.tools.wiki_index import _relocate_summary_links, rebuild_index


def test_rebases_bare_relative_links():
    out = _relocate_summary_links("负责把 [A](A.md) 与 [B](B.md)", "modules/X.md")
    assert out == "负责把 [A](modules/A.md) 与 [B](modules/B.md)"


def test_leaves_urls_anchors_absolute_and_qualified_paths():
    summary = (
        "[url](https://example.com/a) [anchor](#sec) "
        "[abs](/a/b) [qualified](modules/A.md) [mail](mailto:a@b.c)"
    )
    assert _relocate_summary_links(summary, "modules/X.md") == summary


def test_root_level_page_is_untouched():
    """Root pages have no directory prefix, so their links already resolve."""
    assert _relocate_summary_links("根页面 [A](A.md)", "README.md") == "根页面 [A](A.md)"


def test_rebuild_index_writes_rebased_links(tmp_path):
    od = tmp_path / "repowiki"
    (od / "wiki" / "modules").mkdir(parents=True)
    (od / "notes").mkdir()
    (od / "wiki" / "modules" / "auth.md").write_text(
        "---\ntype: Module\ntitle: 认证模块\ndescription: '依赖 [会话](会话.md) 模块'\n---\n\n"
        "# 认证模块\n\n正文。\n",
        encoding="utf-8",
    )

    rebuild_index(od)

    text = (od / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "modules/auth.md" in text
    assert "(modules/会话.md)" in text
    assert "](会话.md)" not in text
