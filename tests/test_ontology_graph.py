"""Tests for ontology activation (P0 + P1 + P2): extraction, consumption, lint, view.

NOTE: the modules under test (`codewiki.mcp.tools.extract_ontology`,
`codewiki.mcp.tools.ontology_view` and `wiki_lint._check_ontology_stale`) belong
to the planned ontology-activation feature (see
`docs/本体论应用-补充调研与完善方案.md`) which is not yet implemented in this
repo.  These tests are skipped until the feature lands; once the modules exist
they will run automatically.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytest.importorskip(
    "codewiki.mcp.tools.extract_ontology",
    reason="ontology activation (P0/P1/P2) not implemented yet",
)
from codewiki.mcp.tools.extract_ontology import extract_ontology, extract_and_write


# --- fixtures --------------------------------------------------------------

def _write_page(d: Path, rel: str, body: str) -> None:
    p = d / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


@pytest.fixture
def wiki_output(tmp_path: Path) -> Path:
    """Build a small wiki output dir with two entity pages + relations table."""
    od = tmp_path / "repowiki"
    od.mkdir()
    (od / "wiki").mkdir()
    # OrderService entity with a relations table
    _write_page(od, "wiki/entities/OrderService.md", textwrap.dedent("""
        ---
        title: OrderService
        page_type: entity
        aliases: [订单服务, OS]
        ---
        # OrderService

        ## 关系
        | 关系 | 目标 | 说明 |
        | depends_on | Account | 订单依赖账户 |
        | owns | OrderItem | 订单拥有订单项 |
        | calls | PaymentGateway | 调用支付 |

        Body text with [[Account]] wikilink.
    """).lstrip())
    # Account entity (no relations section)
    _write_page(od, "wiki/entities/Account.md", textwrap.dedent("""
        ---
        title: Account
        page_type: entity
        aliases: [账户]
        ---
        # Account
        Account body.
    """).lstrip())
    # A relation target that does NOT exist yet -> placeholder
    _write_page(od, "wiki/entities/PaymentGateway.md", textwrap.dedent("""
        ---
        title: PaymentGateway
        page_type: entity
        ---
        # PaymentGateway
        Exists.
    """).lstrip())
    return od


# --- P0.1 extraction -------------------------------------------------------

def test_extract_types_and_relations(wiki_output: Path):
    all_docs = {
        "wiki/entities/OrderService.md": "OrderService",
        "wiki/entities/Account.md": "Account",
        "wiki/entities/PaymentGateway.md": "PaymentGateway",
    }
    pages = [
        ("wiki/entities/OrderService.md", wiki_output / "wiki/entities/OrderService.md"),
        ("wiki/entities/Account.md", wiki_output / "wiki/entities/Account.md"),
        ("wiki/entities/PaymentGateway.md", wiki_output / "wiki/entities/PaymentGateway.md"),
    ]
    res = extract_ontology(wiki_output, all_docs, pages=pages)
    type_names = {t["name"] for t in res["types"]}
    assert "OrderService" in type_names
    assert "Account" in type_names
    rels = {(r["relation"], r["to"]) for r in res["relations"]}
    assert ("depends_on", "Account") in rels
    assert ("owns", "OrderItem") in rels  # placeholder (no page)
    # OrderItem is unresolved -> placeholder True
    order_item = [r for r in res["relations"] if r["to"] == "OrderItem"]
    assert order_item and order_item[0]["placeholder"] is True


def test_extract_and_write_merges_idempotently(wiki_output: Path):
    all_docs = {
        "wiki/entities/OrderService.md": "OrderService",
        "wiki/entities/Account.md": "Account",
        "wiki/entities/PaymentGateway.md": "PaymentGateway",
    }
    # Pre-seed ontology.yaml with a hand-authored relation (must be preserved)
    onto = wiki_output / "ontology.yaml"
    onto.write_text(textwrap.dedent("""
        types: []
        relations:
          - from: ManualService
            relation: depends_on
            to: Account
            note: hand-authored
    """).lstrip(), encoding="utf-8")

    info = extract_and_write(wiki_output, all_docs, ontology_path=onto, write_stubs=True)
    assert info["relations"] >= 4  # 3 extracted + 1 hand
    # hand-authored preserved
    import yaml
    data = yaml.safe_load(onto.read_text(encoding="utf-8"))
    hand = [r for r in data["relations"] if r.get("from") == "ManualService"]
    assert hand and hand[0].get("note") == "hand-authored"
    # placeholder stub created for OrderItem
    stub = wiki_output / "wiki" / "orderitem.md"
    assert stub.exists()


# --- P0.2 consumption via graph_expand ------------------------------------

def test_graph_expand_consumes_ontology_relations(wiki_output: Path):
    from codewiki.mcp.cache import AnalysisCache
    all_docs = {
        "wiki/entities/OrderService.md": "OrderService",
        "wiki/entities/Account.md": "Account",
        "wiki/entities/PaymentGateway.md": "PaymentGateway",
    }
    extract_and_write(wiki_output, all_docs, ontology_path=wiki_output / "ontology.yaml")

    cache = AnalysisCache(wiki_output)
    try:
        # index the pages so search_index exists for title resolution
        cache.build_search_index(wiki_output)
        # seed from Account, hop 1 should reach OrderService via ontology edge
        expanded = cache.graph_expand(
            [("wiki/entities/Account.md", 1.0)], hop=1, output_dir=wiki_output)
        files = {e["file"] for e in expanded}
        # OrderService depends_on Account -> edge Account->OrderService exists
        assert "wiki/entities/OrderService.md" in files
    finally:
        cache.close()


# --- P1 lint ---------------------------------------------------------------

def test_lint_ontology_stale_flags_broken_relation(wiki_output: Path):
    from codewiki.mcp.tools.wiki_lint import _check_ontology_stale
    all_docs = {
        "wiki/entities/OrderService.md": "OrderService",
        "wiki/entities/Account.md": "Account",
        "wiki/entities/PaymentGateway.md": "PaymentGateway",
    }
    extract_and_write(wiki_output, all_docs, ontology_path=wiki_output / "ontology.yaml",
                      write_stubs=False)
    issues = _check_ontology_stale(wiki_output)
    # OrderItem is referenced but has no page and no stub -> error
    error_msgs = [i["message"] for i in issues if i["severity"] == "error"]
    assert any("OrderItem" in m for m in error_msgs)


# --- P2 view ---------------------------------------------------------------

def test_generate_ontology_view_full(wiki_output: Path):
    from codewiki.mcp.tools.ontology_view import generate_ontology_view
    all_docs = {
        "wiki/entities/OrderService.md": "OrderService",
        "wiki/entities/Account.md": "Account",
        "wiki/entities/PaymentGateway.md": "PaymentGateway",
    }
    extract_and_write(wiki_output, all_docs, ontology_path=wiki_output / "ontology.yaml")

    res = generate_ontology_view(output_dir=str(wiki_output), view_type="full")
    assert res["file"].endswith("ontology_full.md")
    assert "mermaid" in res
    assert res["nodes"] >= 3
    out = Path(res["file"])
    assert out.exists()
    assert "graph" in out.read_text(encoding="utf-8")


def test_generate_ontology_view_impact_requires_root(wiki_output: Path):
    from codewiki.mcp.tools.ontology_view import generate_ontology_view
    res = generate_ontology_view(output_dir=str(wiki_output), view_type="impact")
    assert "error" in res
