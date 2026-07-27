---
type: Module
title: Shared Configuration
description: Global configuration constants, dataclass, and utility functions shared across all modules
resource: codewiki/src/config.py
tags: [config, constants, shared, metadata, paths]
---

# Shared [Configuration](../../../codewiki/cli/models/config.py)

## Overview

Defines global configuration constants, the [Config](../../../codewiki/src/config.py) dataclass, and utility functions shared across the CLI, backend, and MCP layers. Central point for output paths, metadata conventions, and token budget settings.

## Components

### [Config](../../../codewiki/src/config.py) Dataclass
Main configuration container with fields:
- repo_path, output_dir: [Repository](../../../codewiki/src/be/dependency_analyzer/models/core.py) and output directories
- dependency_graph_dir, docs_dir: Subdirectory paths
- llm_base_url, llm_api_key: LLM API credentials
- main_model, cluster_model, fallback_model: Model selection
- provider: openai-compatible, anthropic, bedrock, azure-openai, claude-code, codex
- max_depth: Decomposition depth limit (default 3)
- max_tokens, max_token_per_module, max_token_per_leaf_module: Token budgets
- agent_instructions: Dict with doc_type, patterns, custom instructions

### Constants
- **META_DIR**: `.meta/` directory for metadata
- **WIKI_DIR**: `wiki/` for structured knowledge
- **PAGE_TYPE_DIRS**: Maps page types to subdirectories
- **SCHEMA_FILENAME**: `schema.yaml`
- Token defaults: 32K max tokens, 36K per module, 16K per leaf

### Utility Functions
- **meta_join/meta_resolve**: Path helpers for `.meta/` files with backward compatibility
- **set_cli_context/is_cli_context**: Distinguishes CLI vs web app execution

### [FileManager](../../../codewiki/src/utils.py) (src/utils.py)
- File I/O utility class for safe read/write operations

## Cross References

- [CLI_Config](CLI_Config.md): CLI [Configuration](../../../codewiki/cli/models/config.py) model references these constants
- [LLM_Backend](LLM_Backend.md): Uses [Config](../../../codewiki/src/config.py) for LLM settings
- [MCP_Tools_Analysis](MCP_Tools_Analysis.md): Uses [Config](../../../codewiki/src/config.py) for analysis parameters
- [MCP_Tools_DocWriter](MCP_Tools_DocWriter.md): References META_DIR and PAGE_TYPE_DIRS


<!-- crosslinks (auto-generated) -->
## Related Modules
- Used by: [CLI_Adapter](cli_adapter.md), [CLI_Commands](cli_commands.md), [CLI_Config](cli_config.md), [DocVisualizer](docvisualizer.md), [LLM_Backend](llm_backend.md), [MCP_Core](mcp_core.md), [MCP_Tools_Analysis](mcp_tools_analysis.md), [MCP_Tools_DocWriter](mcp_tools_docwriter.md), [MCP_Tools_Knowledge](mcp_tools_knowledge.md), [MCP_Tools_Quality](mcp_tools_quality.md), [WebApp](webapp.md)
