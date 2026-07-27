---
type: Module
title: MCP Prompt Templates
description: Workflow prompt templates for wiki generation, code analysis, knowledge extraction, and quality checks
resource: codewiki/mcp/server.py
tags: [mcp, prompts, templates, workflow, wiki-generation]
---

# MCP Prompt Templates

## Overview

Defines all MCP prompt templates that guide AI agents through multi-step workflows: wiki generation, code analysis, incremental updates, knowledge extraction, cross-service tracing, and quality auditing.

## Available Prompts

| Prompt | Purpose | Entry Point |
|--------|---------|-------------|
| generate-wiki | Full wiki generation pipeline | analyze_repo |
| extract-knowledge | Import external docs and extract entities | source_path |
| search-wiki | BM25 + graph search strategy | query |
| quality-check | Lint report for documentation health | output_dir |
| incremental-update | Detect changes and update affected modules | repo_path |
| workspace-analysis | Multi-repo analysis with cross-service topology | workspace_path |
| cross-service-trace | Cross-service call chain analysis | workspace_path + filter |
| code_analysis | Full code analysis workflow | repo_path |
| impact_review | Interpret analyze_impact results | impact data |
| architecture_review | Layer/hotspot/boundary analysis | dependency data |

## Internal Functions

- **_prompt_generate_wiki**: 6-step workflow (analyze → cluster → order → generate docs → overview → close)
- **_prompt_code_analysis**: Analysis-first workflow without doc generation
- **_prompt_impact_review**: Risk assessment for blast-radius analysis
- **_prompt_incremental_update**: Change detection and targeted module updates
- **_prompt_workspace_analysis**: Multi-git-repo scanning with cross-service matching
- **_prompt_cross_service_trace**: [RouteNode](../../../codewiki/src/be/dependency_analyzer/models/cross_service.py) tracing with CBM semantic analysis
- **_prompt_extract_knowledge**: External document import pipeline
- **_prompt_search_wiki**: Three-layer search strategy (BM25 → hop → deep read)
- **_prompt_quality_check**: 11-check lint report format
- **_prompt_architecture_review**: Architecture dimension analysis

## Cross References

- [MCP_Core](MCP_Core.md): Server dispatches prompt requests
- [[MCP_Tools_Analysis]]: Analysis tools referenced in prompts
- [[MCP_Tools_Knowledge]]: Knowledge extraction tools


<!-- crosslinks (auto-generated) -->
## Related Modules
- Depends on: [MCP_Core](mcp_core.md)
