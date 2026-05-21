"""Tests for extracted knowledge search SQL constants."""

from src.infrastructure.db.repositories.knowledge_search_queries import (
    RUNTIME_HYBRID_SEARCH_SQL,
    RUNTIME_PREVIEW_SEARCH_SQL,
    RUNTIME_VECTOR_SEARCH_SQL,
)


def test_runtime_search_sql_constants_keep_production_surface_filters() -> None:
    for sql in (
        RUNTIME_VECTOR_SEARCH_SQL,
        RUNTIME_HYBRID_SEARCH_SQL,
        RUNTIME_PREVIEW_SEARCH_SQL,
    ):
        assert "knowledge_retrieval_surface AS rs" in sql
        assert "rs.entry_kind = ANY" in sql
        assert "rs.status = 'published'" in sql
        assert "rs.visibility = 'runtime'" in sql


def test_hybrid_runtime_search_sql_keeps_vector_and_lexical_candidate_paths() -> None:
    assert "vector_candidates AS" in RUNTIME_HYBRID_SEARCH_SQL
    assert "lexical_candidates AS" in RUNTIME_HYBRID_SEARCH_SQL
    assert "websearch_to_tsquery" in RUNTIME_HYBRID_SEARCH_SQL
    assert "to_tsvector" in RUNTIME_HYBRID_SEARCH_SQL


def test_preview_runtime_search_sql_stays_embedding_free() -> None:
    assert "::vector" not in RUNTIME_PREVIEW_SEARCH_SQL
    assert "websearch_to_tsquery" in RUNTIME_PREVIEW_SEARCH_SQL
    assert "regexp_split_to_table" in RUNTIME_PREVIEW_SEARCH_SQL
