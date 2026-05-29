from __future__ import annotations

from src.application.services.knowledge_stage_k_shared_helpers import (
    _PLAIN_CHUNK_AUDIT_FIELDS,
    SEMANTIC_CHUNK_METADATA_FIELDS,
    _present_plain_chunk_value,
    _plain_chunk_field_counts,
    _log_plain_chunk_audit,
    _clean_optional_text,
    _text_tuple,
    _has_semantic_chunk_metadata,
    _role_from_entry_kind,
    _draft_from_json_chunk,
    _document_from_json_chunks,
    _raw_chunks_for_structured_persistence,
    _combined_chunks_for_canonical_persistence,
    _merged_preprocessing_result,
    _answer_titles_from_preprocessing_results,
    _canonical_entries_from_knowledge_chunks,
)

__all__ = [
    "_PLAIN_CHUNK_AUDIT_FIELDS",
    "SEMANTIC_CHUNK_METADATA_FIELDS",
    "_present_plain_chunk_value",
    "_plain_chunk_field_counts",
    "_log_plain_chunk_audit",
    "_clean_optional_text",
    "_text_tuple",
    "_has_semantic_chunk_metadata",
    "_role_from_entry_kind",
    "_draft_from_json_chunk",
    "_document_from_json_chunks",
    "_raw_chunks_for_structured_persistence",
    "_combined_chunks_for_canonical_persistence",
    "_merged_preprocessing_result",
    "_answer_titles_from_preprocessing_results",
    "_canonical_entries_from_knowledge_chunks",
]
