from __future__ import annotations

import inspect
from pathlib import Path

from src.application.ports import knowledge_port
from src.application.services import knowledge_ingestion_service
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository


def test_stage_e_migration_persists_compiler_trace() -> None:
    migration = Path("migrations/060_create_knowledge_compiler_trace.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS knowledge_compiler_runs" in migration
    assert "CREATE TABLE IF NOT EXISTS knowledge_compilation_metrics" in migration
    assert "CREATE TABLE IF NOT EXISTS knowledge_answer_candidates" in migration
    assert "CREATE TABLE IF NOT EXISTS knowledge_candidate_clusters" in migration
    assert "CREATE TABLE IF NOT EXISTS knowledge_candidate_cluster_members" in migration
    assert "expected_chunk_ids" not in migration
    assert "retrieved_chunk_ids" not in migration


def test_knowledge_port_exposes_stage_e_trace_methods() -> None:
    source = inspect.getsource(knowledge_port.KnowledgeRepositoryPort)

    assert "create_compiler_run" in source
    assert "complete_compiler_run" in source
    assert "fail_compiler_run" in source
    assert "add_answer_candidates" in source
    assert "add_candidate_clusters" in source


def test_repository_persists_stage_e_trace_tables() -> None:
    source = inspect.getsource(KnowledgeRepository)

    assert "INSERT INTO knowledge_compiler_runs" in source
    assert "INSERT INTO knowledge_compilation_metrics" in source
    assert "INSERT INTO knowledge_answer_candidates" in source
    assert "INSERT INTO knowledge_candidate_clusters" in source
    assert "INSERT INTO knowledge_candidate_cluster_members" in source
    assert "DELETE FROM knowledge_compiler_runs WHERE document_id = $1" in source


def test_ingestion_creates_compiler_run_before_outputs() -> None:
    source = inspect.getsource(knowledge_ingestion_service.KnowledgeIngestionService)

    assert "repo.create_compiler_run" in source
    assert "_persist_stage_e_compiler_outputs" in Path(
        "src/application/services/knowledge_ingestion_service.py"
    ).read_text(encoding="utf-8")
    assert "compiler_run_id=compiler_run_id" in Path(
        "src/application/services/knowledge_ingestion_service.py"
    ).read_text(encoding="utf-8")
