"""Compat facade for the split knowledge loop modules (2026-09 #1).

This module previously held six tool families in one 2,947-line file. They
now live in their own modules (locality: one tool family, one file):

- note_ingest    — handle_ingest_note and note-creation helpers
- note_lifecycle — handle_confirm_note / handle_reject_note / handle_batch_set_status
- note_query     — handle_query_wiki, five query modes, legacy keyword fallback
- wiki_stats     — handle_wiki_stats, cold + promotion candidates
- note_freshness — evaluate_note_freshness and the freshness engine
- note_writer    — NoteWriter: slug, locked status rewrite, index refresh

Everything that used to be importable from here still is (tests and sibling
tools rely on it); the re-exports below are the compat surface.
"""

from codewiki.mcp.tools.note_writer import (  # noqa: F401
    _STATUS_LEGACY_MAP,
    _norm_status,
    _note_source_ref,
    _okf_actor,
    _slugify,
    _apply_status_to_file,
    _update_note_status,
    refresh_note_indexes,
)
from codewiki.mcp.tools.note_freshness import (  # noqa: F401
    load_freshness_config,
    freshness_window_days,
    _parse_day,
    evaluate_note_freshness,
    _freshness_distribution,
    _note_age_days,
)
from codewiki.mcp.tools.note_ingest import (  # noqa: F401
    _auto_match_modules,
    _extract_tags,
    _load_symbol_map,
    _inject_symbol_links,
    handle_ingest_note,
)
from codewiki.mcp.tools.note_lifecycle import (  # noqa: F401
    _resolve_within,
    _maybe_attach_aggregation_hint,
    handle_confirm_note,
    handle_reject_note,
    _iter_wiki_docs,
    _iter_note_docs,
    _read_doc_status,
    handle_batch_set_status,
)
from codewiki.mcp.tools.note_query import (  # noqa: F401
    _trust_tier,
    _extract_keywords,
    _score_document,
    _get_module_doc_name,
    _extract_frontmatter_block,
    _extract_section,
    _query_mode_overview,
    _query_mode_directory,
    _query_mode_detail,
    _query_mode_check,
    _load_file_knowledge_config,
    _last_commit_time,
    _file_staleness,
    _by_file_specificity,
    _query_mode_by_file,
    _repo_scope_match,
    handle_query_wiki,
    _record_retrieval_stats,
    _legacy_keyword_search,
    _extract_frontmatter,
    _get_module_components,
)
from codewiki.mcp.tools.wiki_stats import (  # noqa: F401
    _PROMOTION_PAGE_TYPES,
    handle_wiki_stats,
    _cold_candidates,
    _promotion_candidates,
)
