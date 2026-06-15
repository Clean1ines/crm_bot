from __future__ import annotations

from pathlib import Path

from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
    PUBLISHED_ENTRIES_FOR_WORKBENCH_RAG_EVAL_SQL,
)


def test_repository_reads_published_workbench_runtime_entries_not_legacy_surfaces() -> (
    None
):
    sql = PUBLISHED_ENTRIES_FOR_WORKBENCH_RAG_EVAL_SQL

    assert "knowledge_workbench_runtime_retrieval_entries" in sql
    assert "knowledge_workbench_canonical_facts" in sql
    assert "knowledge_retrieval_surface" not in sql
    assert "knowledge_workbench_surfaces" not in sql
    assert "answer_text" not in sql
    assert "entry.visibility = 'published'" in sql
    assert "entry.status = 'active'" in sql


def test_repository_source_does_not_use_legacy_rag_eval_or_answer_text() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/rag_eval/infrastructure/postgres/"
        "postgres_workbench_rag_eval_repository.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        "answer_text",
        "knowledge_retrieval_surface",
        "knowledge_workbench_surfaces",
        "src.application.rag_eval",
        "RagEvalRunner",
    )
    for marker in forbidden:
        assert marker not in source
