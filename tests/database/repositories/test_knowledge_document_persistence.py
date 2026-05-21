from __future__ import annotations

import inspect
from pathlib import Path

from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository


def _method_source(method_name: str, next_method_name: str) -> str:
    source = inspect.getsource(KnowledgeRepository)
    start = source.index(f"async def {method_name}(")
    end = source.index(f"async def {next_method_name}(", start)
    return source[start:end]


def test_document_persistence_module_owns_create_and_status_sql() -> None:
    helper_source = Path(
        "src/infrastructure/db/repositories/knowledge_document_persistence.py"
    ).read_text(encoding="utf-8")

    assert "INSERT INTO knowledge_documents" in helper_source
    assert "RETURNING id" in helper_source
    assert "UPDATE knowledge_documents" in helper_source
    assert "SET status = $1, error = $2, updated_at = NOW()" in helper_source
    assert "preprocessing_status = $2" in helper_source
    assert "preprocessing_metrics = COALESCE($6::jsonb, preprocessing_metrics)" in (
        helper_source
    )
    assert "async def mark_document_processing_cancelled(" in helper_source
    assert "status = 'error'" in helper_source
    assert "preprocessing_status = 'failed'" in helper_source
    assert "RETURNING id" in helper_source


def test_repository_delegates_create_and_status_document_sql() -> None:
    repository_source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")
    create_source = _method_source("create_document", "get_documents")
    status_source = _method_source("update_document_status", "_cancel_document_jobs")

    assert "await persist_create_document(" in create_source
    assert "await persist_update_document_status(" in status_source
    cancel_source = _method_source(
        "cancel_document_processing", "is_document_processing_cancelled"
    )

    assert "await persist_update_document_preprocessing_status(" in status_source
    assert "await mark_document_processing_cancelled(" in cancel_source

    assert "INSERT INTO knowledge_documents" not in create_source
    assert "RETURNING id" not in create_source
    assert "SET status = $1, error = $2, updated_at = NOW()" not in status_source
    assert "preprocessing_status = $2" not in status_source
    assert "preprocessing_metrics = COALESCE($6::jsonb, preprocessing_metrics)" not in (
        status_source
    )

    assert "status = 'error'" not in cancel_source
    assert "preprocessing_status = 'failed'" not in cancel_source

    # Other document curation/delete lifecycle SQL still belongs to later slices.
    assert "FROM knowledge_documents" in repository_source
    assert "DELETE FROM knowledge_documents" in repository_source


def test_repository_delegates_answer_resolution_metrics_update() -> None:
    helper_source = Path(
        "src/infrastructure/db/repositories/knowledge_document_persistence.py"
    ).read_text(encoding="utf-8")
    retightening_source = _method_source(
        "apply_document_answer_resolution_retightening", "search"
    )

    assert "async def merge_document_preprocessing_metrics(" in helper_source
    assert (
        "SET preprocessing_metrics = COALESCE(preprocessing_metrics, '{}'::jsonb)"
        in (helper_source)
    )
    assert "|| $3::jsonb" in helper_source

    assert "await merge_document_preprocessing_metrics(" in retightening_source
    assert "UPDATE knowledge_documents" not in retightening_source
    assert "SET preprocessing_metrics = COALESCE(preprocessing_metrics" not in (
        retightening_source
    )
