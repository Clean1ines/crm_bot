from __future__ import annotations

from pathlib import Path


def test_answer_candidate_queries_module_owns_candidate_read_sql() -> None:
    helper_source = Path(
        "src/infrastructure/db/repositories/knowledge_answer_candidate_queries.py"
    ).read_text(encoding="utf-8")

    assert "FROM knowledge_answer_candidates" in helper_source
    assert "metadata->>'stage' = 'stage_k_raw_extraction'" in helper_source
    assert "COUNT(*)::int AS total_count" in helper_source
    assert "jsonb_array_length(source_refs)" in helper_source
    assert "KnowledgeAnswerCandidateSummaryView" in helper_source
    assert "AnswerCandidateStatus" in helper_source


def test_repository_delegates_answer_candidate_read_sql() -> None:
    repository_source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")

    assert "await query_document_raw_answer_candidates(" in repository_source
    assert "await query_document_answer_candidate_summary(" in repository_source

    assert "FROM knowledge_answer_candidates" not in repository_source
    assert "metadata->>'stage' = 'stage_k_raw_extraction'" not in repository_source
    assert "COUNT(*)::int AS total_count" not in repository_source
    assert "jsonb_array_length(source_refs)" not in repository_source
