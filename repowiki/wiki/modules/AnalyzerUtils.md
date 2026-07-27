---
type: Module
title: Analyzer Utilities
description: Utility functions for the dependency analyzer including external symbol detection, path canonicalization, and entry point patterns
resource: codewiki/src/be/dependency_analyzer/utils/
tags: [utils, analyzer, symbols, patterns, security, logging]
---

# Analyzer Utilities

## Overview

Provides utility functions for the dependency analysis pipeline: external symbol filtering, path normalization, logging configuration, security checks, and heuristic patterns for entry point detection.

## Components

### External Symbols (external_symbols.py)
- **is_external_symbol**: Detects third-party/library symbols not in the analyzed repo
- **normalize_symbol**: Standardizes symbol names across languages
- **is_macro_name**: C/C++ macro name detection

### Path Canonicalizer (path_canonicalizer.py)
- **canonicalize_path**: Normalizes file paths for consistent comparison
- **make_route_key**: Creates canonical HTTP route keys for cross-service matching
- **make_mq_route_key**: Creates canonical MQ topic/queue keys

### Patterns (patterns.py)
Heuristic functions for identifying critical code elements:
- **is_entry_point_path/is_entry_point_file**: Detects application entry points (main.py, app.js, etc.)
- **find_fallback_entry_points**: Fallback detection when standard patterns fail
- **is_critical_function**: Identifies high-import functions (handlers, controllers)
- **has_high_connectivity_potential**: Finds functions likely to have many callers
- **get_function_patterns_for_language**: Language-specific function patterns

### Security (security.py)
- **assert_safe_path**: Prevents path traversal attacks
- **safe_open_text**: Safe file opening with path validation

### Logging (logging_config.py)
- **[ColoredFormatter](../../../codewiki/src/be/dependency_analyzer/utils/logging_config.py)**: Colored terminal output for analysis progress
- **setup_logging/setup_module_logging**: Module-level log configuration

## Cross References

- [AnalysisPipeline](AnalysisPipeline.md): Uses patterns and security utilities
- [[RouteExtractors]]: Uses path canonicalizer for route matching
- [CLI_Utils](CLI_Utils.md): Shares [ColoredFormatter](../../../codewiki/src/be/dependency_analyzer/utils/logging_config.py)


<!-- crosslinks (auto-generated) -->
## Related Modules
- Used by: [AnalysisPipeline](analysispipeline.md), [CLI_Adapter](cli_adapter.md), [LanguageAnalyzers](languageanalyzers.md), [RouteExtractors](routeextractors.md)
