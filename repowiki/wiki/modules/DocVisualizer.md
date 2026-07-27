---
type: Module
title: Document Visualizer
description: Markdown-to-HTML rendering pipeline for browsing generated documentation
resource: codewiki/src/fe/visualise_docs.py
tags: [frontend, visualization, markdown, html, mermaid]
---

# Document Visualizer

## Overview

Renders generated Markdown documentation as browsable HTML with Mermaid diagram support, navigation tree, and template-based layout.

## Components

### visualise_docs.py
- **index**: Main page rendering with module tree navigation
- **serve_doc**: Individual doc rendering with markdown-to-HTML conversion
- **markdown_to_html**: Converts markdown with Mermaid diagram handling
- **replace_mermaid**: Replaces Mermaid code blocks with interactive diagrams
- **load_module_tree**: Loads module tree JSON for navigation structure

### template_utils.py
- **[StringTemplateLoader](../../../codewiki/src/fe/template_utils.py)**: In-memory template management
- **render_template**: Jinja2-compatible template rendering
- **render_navigation**: Generates sidebar navigation from module tree
- **render_job_list**: Formats generation job listings

## Cross References

- [[WebApp]]: Uses template_utils for page rendering
- [[MCP_Tools_DocWriter]]: Source of generated markdown files


<!-- crosslinks (auto-generated) -->
## Related Modules
- Depends on: [SharedConfig](sharedconfig.md)
- Used by: [CLI_Config](cli_config.md), [MCP_Cache](mcp_cache.md), [MCP_Tools_Knowledge](mcp_tools_knowledge.md), [MCP_Tools_Quality](mcp_tools_quality.md), [WebApp](webapp.md)
