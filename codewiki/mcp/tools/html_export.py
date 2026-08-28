"""Internal utility: self-contained HTML wiki export.

Called automatically by close_session — not exposed as an MCP tool.
Generates a single HTML file embedding all wiki pages with sidebar
navigation, client-side search, and Mermaid diagram rendering (CDN).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Minimal markdown→HTML (headings, code blocks, links, bold, lists)
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_MD_FENCE_RE = re.compile(r"^```(\w*)\n(.*?)^```", re.MULTILINE | re.DOTALL)
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MD_UL_RE = re.compile(r"^[-*]\s+(.+)$", re.MULTILINE)


def _md_to_html(md: str) -> str:
    """Convert markdown to basic HTML (no external deps)."""
    code_blocks: List[str] = []

    def _save_code(m: re.Match) -> str:
        lang = m.group(1) or ""
        code = m.group(2).rstrip()
        if lang == "mermaid":
            code_blocks.append(f'<div class="mermaid">\n{code}\n</div>')
        else:
            escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            code_blocks.append(f'<pre><code class="language-{lang}">{escaped}</code></pre>')
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    html = _MD_FENCE_RE.sub(_save_code, md)
    html = _MD_HEADING_RE.sub(
        lambda m: f"<h{len(m.group(1))}>{m.group(2)}</h{len(m.group(1))}>", html
    )
    html = _MD_BOLD_RE.sub(r"<strong>\1</strong>", html)
    html = _MD_LINK_RE.sub(r'<a href="\2">\1</a>', html)
    html = _MD_UL_RE.sub(r"<li>\1</li>", html)
    html = re.sub(r"\n\n+", "\n<br>\n", html)

    for i, block in enumerate(code_blocks):
        html = html.replace(f"\x00CODEBLOCK{i}\x00", block)

    return html


def _collect_wiki_pages(output_dir: Path) -> List[Dict[str, str]]:
    """Collect all markdown pages from the wiki directory."""
    pages: List[Dict[str, str]] = []
    wiki_dir = output_dir / "wiki"
    search_dirs = [wiki_dir] if wiki_dir.exists() else [output_dir]

    for search_dir in search_dirs:
        for md_file in sorted(search_dir.rglob("*.md")):
            rel = md_file.relative_to(output_dir)
            title = md_file.stem.replace("_", " ").replace("-", " ").title()
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
                first_h = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                if first_h:
                    title = first_h.group(1)
            except Exception:
                content = ""
            pages.append(
                {
                    "id": str(rel).replace("\\", "/"),
                    "title": title,
                    "content": content,
                }
            )

    return pages


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.0/mermaid.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; display: flex; height: 100vh; }}
#sidebar {{ width: 280px; background: #1a1a2e; color: #eee; overflow-y: auto; padding: 16px 0; flex-shrink: 0; }}
#sidebar h2 {{ padding: 8px 20px 16px; font-size: 14px; color: #8892b0; text-transform: uppercase; letter-spacing: 1px; }}
#sidebar a {{ display: block; padding: 8px 20px; color: #ccd6f6; text-decoration: none; font-size: 14px; border-left: 3px solid transparent; }}
#sidebar a:hover, #sidebar a.active {{ background: #16213e; border-left-color: #64ffda; color: #64ffda; }}
#sidebar .search-box {{ padding: 8px 16px; }}
#sidebar input {{ width: 100%; padding: 8px 12px; border: 1px solid #333; border-radius: 4px; background: #16213e; color: #eee; font-size: 13px; }}
#content {{ flex: 1; overflow-y: auto; padding: 40px 60px; max-width: 900px; }}
#content h1 {{ font-size: 2em; margin-bottom: 16px; color: #1a1a2e; }}
#content h2 {{ font-size: 1.5em; margin: 24px 0 12px; color: #2d3748; }}
#content h3 {{ font-size: 1.2em; margin: 16px 0 8px; }}
#content p, #content li {{ line-height: 1.7; margin-bottom: 8px; color: #4a5568; }}
#content pre {{ background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; overflow-x: auto; margin: 12px 0; }}
#content code {{ font-family: 'Fira Code', monospace; font-size: 13px; }}
#content a {{ color: #3182ce; }}
#content .mermaid {{ margin: 16px 0; text-align: center; }}
#content table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
#content th, #content td {{ border: 1px solid #e2e8f0; padding: 8px 12px; text-align: left; font-size: 14px; }}
#content th {{ background: #f7fafc; }}
.page {{ display: none; }} .page.active {{ display: block; }}
@media (max-width: 768px) {{ #sidebar {{ width: 200px; }} #content {{ padding: 20px; }} }}
</style>
</head>
<body>
<div id="sidebar">
<h2>{title}</h2>
<div class="search-box"><input type="text" id="search" placeholder="搜索页面..." oninput="filterPages(this.value)"></div>
<nav id="nav">{nav_links}</nav>
</div>
<div id="content">{pages_html}</div>
<script>
mermaid.initialize({{ startOnLoad: true, theme: 'neutral' }});
function showPage(id) {{
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('#nav a').forEach(a => a.classList.remove('active'));
  const page = document.getElementById('page-' + id);
  const link = document.querySelector('#nav a[data-id="' + id + '"]');
  if (page) page.classList.add('active');
  if (link) link.classList.add('active');
  mermaid.run({{ nodes: page ? page.querySelectorAll('.mermaid') : [] }});
}}
function filterPages(q) {{
  q = q.toLowerCase();
  document.querySelectorAll('#nav a').forEach(a => {{
    a.style.display = a.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}}
showPage('{first_page_id}');
</script>
</body>
</html>"""


def generate_html_export(
    output_dir: str,
    *,
    title: Optional[str] = None,
) -> Optional[str]:
    """Generate wiki-export.html from all wiki markdown pages.

    Args:
        output_dir: Wiki output directory (contains wiki/ with .md files).
        title: HTML page title. Defaults to "<parent-dir-name> Wiki".

    Returns:
        Path to the generated HTML file, or None if generation failed.
    """
    try:
        out_path = Path(output_dir)
        if not out_path.exists():
            return None

        pages = _collect_wiki_pages(out_path)
        if not pages:
            return None

        if not title:
            title = f"{out_path.parent.name} Wiki"

        nav_parts: List[str] = []
        pages_parts: List[str] = []
        for i, page in enumerate(pages):
            page_id = page["id"].replace("/", "-").replace(".md", "").replace(".", "-")
            nav_parts.append(
                f'<a href="#" data-id="{page_id}" onclick="showPage(\'{page_id}\');return false;">'
                f"{page['title']}</a>"
            )
            active = " active" if i == 0 else ""
            html_content = _md_to_html(page["content"])
            pages_parts.append(
                f'<div class="page{active}" id="page-{page_id}">{html_content}</div>'
            )

        first_page_id = pages[0]["id"].replace("/", "-").replace(".md", "").replace(".", "-")

        html = _HTML_TEMPLATE.format(
            title=title,
            nav_links="\n".join(nav_parts),
            pages_html="\n".join(pages_parts),
            first_page_id=first_page_id,
        )

        export_path = out_path / "wiki-export.html"
        export_path.write_text(html, encoding="utf-8")
        logger.info(
            "Generated HTML export: %s (%d pages, %.1f KB)",
            export_path,
            len(pages),
            export_path.stat().st_size / 1024,
        )
        return str(export_path)

    except Exception as e:
        logger.warning("Failed to generate HTML export: %s", e)
        return None
