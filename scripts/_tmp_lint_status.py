import sys, json
sys.path.insert(0, "d:/repos/CodeWiki-CN")
from pathlib import Path
from codewiki.mcp.tools import wiki_lint

output_dir = Path("d:/repos/CodeWiki-CN/repowiki")
module_tree = wiki_lint._load_module_tree(output_dir)
anchor_map = wiki_lint._build_anchor_map(output_dir)

checks = {
    "stale_refs": wiki_lint._check_stale_refs(output_dir, module_tree),
    "broken_links": wiki_lint._check_broken_links(output_dir),
    "orphan_pages": wiki_lint._check_orphan_pages(output_dir, anchor_map),
    "no_outlinks": wiki_lint._check_no_outlinks(output_dir, anchor_map),
    "missing_aliases": wiki_lint._check_missing_aliases(output_dir),
    "superseded_pages": wiki_lint._check_superseded_pages(output_dir),
    "stale_sources": wiki_lint._check_stale_sources(output_dir),
}
for name, issues in checks.items():
    sev = {}
    for i in issues:
        sev[i.get("severity", "?")] = sev.get(i.get("severity", "?"), 0) + 1
    print(name, "=>", len(issues), dict(sev))

print("--- missing_aliases detail ---")
for i in checks["missing_aliases"][:5]:
    print(json.dumps(i, ensure_ascii=False))
print("--- no_outlinks sample ---")
for i in checks["no_outlinks"][:3]:
    print(json.dumps(i, ensure_ascii=False))
