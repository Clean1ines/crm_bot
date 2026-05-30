from __future__ import annotations

from src.infrastructure.db.repositories.knowledge_search_queries import (
    RUNTIME_HYBRID_SEARCH_SQL,
    RUNTIME_VECTOR_SEARCH_SQL,
)


def test_production_runtime_search_sql_filters_only_published_runtime_surfaces() -> (
    None
):
    for sql in (RUNTIME_HYBRID_SEARCH_SQL, RUNTIME_VECTOR_SEARCH_SQL):
        assert "FROM knowledge_retrieval_surface AS rs" in sql
        assert "rs.status = 'published'" in sql
        assert "rs.visibility = 'runtime'" in sql
        assert "AND (d.status = 'processed' OR d.status IS NULL)" in sql
