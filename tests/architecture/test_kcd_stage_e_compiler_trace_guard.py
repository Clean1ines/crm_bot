from __future__ import annotations

import inspect
from pathlib import Path

from src.application.ports import knowledge_port
from src.application.services import knowledge_ingestion_service, knowledge_service
from src.interfaces.http import knowledge as knowledge_http
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

    batch_migration = Path(
        "migrations/061_create_knowledge_compiler_batches.sql"
    ).read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS knowledge_compiler_batches" in batch_migration
    assert (
        "compiler_run_id TEXT NOT NULL REFERENCES knowledge_compiler_runs"
        in batch_migration
    )
    assert (
        "status IN ('pending', 'processing', 'completed', 'failed', 'skipped', 'cancelled')"
        in batch_migration
    )
    assert "expected_chunk_ids" not in migration
    assert "retrieved_chunk_ids" not in migration


def test_knowledge_port_exposes_stage_e_trace_methods() -> None:
    source_material = inspect.getsource(knowledge_port.KnowledgeSourceMaterialPort)
    compilation_trace = inspect.getsource(knowledge_port.KnowledgeCompilationTracePort)
    answer_candidates = inspect.getsource(knowledge_port.KnowledgeAnswerCandidatePort)
    canonical_entries = inspect.getsource(knowledge_port.KnowledgeCanonicalEntryPort)

    for method_name in (
        "add_source_chunks",
        "list_document_source_chunks",
        "delete_document_chunks",
    ):
        assert method_name in source_material

    for method_name in (
        "create_compiler_run",
        "complete_compiler_run",
        "fail_compiler_run",
        "create_compiler_batches",
        "mark_compiler_batch_processing",
        "complete_compiler_batch",
        "fail_compiler_batch",
        "list_document_compiler_batches",
    ):
        assert method_name in compilation_trace

    for method_name in (
        "delete_raw_answer_candidates_for_batch",
        "add_answer_candidates",
        "add_candidate_clusters",
        "list_document_raw_answer_candidates",
        "get_document_answer_candidate_summary",
    ):
        assert method_name in answer_candidates

    assert "add_canonical_entries" in canonical_entries


def test_repository_persists_stage_e_trace_tables() -> None:
    source = inspect.getsource(KnowledgeRepository)
    compiler_persistence_source = Path(
        "src/infrastructure/db/repositories/knowledge_compiler_run_persistence.py"
    ).read_text(encoding="utf-8")
    candidate_persistence_source = Path(
        "src/infrastructure/db/repositories/knowledge_answer_candidate_persistence.py"
    ).read_text(encoding="utf-8")

    assert "create_compiler_run" in source
    assert "complete_compiler_run" in source
    assert "fail_compiler_run" in source
    assert "create_compiler_batches" in source
    assert "mark_compiler_batch_processing" in source
    assert "complete_compiler_batch" in source
    assert "fail_compiler_batch" in source
    assert "delete_raw_answer_candidates_for_batch" in source
    assert "add_answer_candidates" in source
    assert "add_candidate_clusters" in source

    assert "await upsert_compiler_run(" in source
    assert "await upsert_compiler_batch(" in source
    assert "await persist_mark_compiler_batch_processing(" in source
    assert "await persist_complete_compiler_batch(" in source
    assert "await persist_fail_compiler_batch(" in source
    assert "await persist_complete_compiler_run(" in source
    assert "await persist_fail_compiler_run(" in source
    assert "await persist_delete_raw_answer_candidates_for_batch(" in source
    assert "await upsert_answer_candidates(" in source
    assert "await upsert_candidate_clusters(" in source

    assert "INSERT INTO knowledge_compiler_runs" not in source
    assert "INSERT INTO knowledge_compilation_metrics" not in source
    assert "INSERT INTO knowledge_compiler_batches" not in source
    assert "UPDATE knowledge_compiler_batches" not in source
    assert "INSERT INTO knowledge_answer_candidates" not in source
    assert "INSERT INTO knowledge_candidate_clusters" not in source
    assert "INSERT INTO knowledge_candidate_cluster_members" not in source
    assert "DELETE FROM knowledge_candidate_cluster_members" not in source
    assert "DELETE FROM knowledge_answer_candidates" not in source

    assert "INSERT INTO knowledge_compiler_runs" in compiler_persistence_source
    assert "INSERT INTO knowledge_compilation_metrics" in compiler_persistence_source
    assert "INSERT INTO knowledge_compiler_batches" in compiler_persistence_source
    assert "UPDATE knowledge_compiler_batches" in compiler_persistence_source
    assert "INSERT INTO knowledge_answer_candidates" in candidate_persistence_source
    assert "INSERT INTO knowledge_candidate_clusters" in candidate_persistence_source
    assert (
        "INSERT INTO knowledge_candidate_cluster_members"
        in candidate_persistence_source
    )
    assert (
        "DELETE FROM knowledge_candidate_cluster_members"
        in candidate_persistence_source
    )
    assert "DELETE FROM knowledge_answer_candidates" in candidate_persistence_source

    assert "cleanup_document_artifacts(" in source
    assert "build_document_reset_cleanup_plan(" in source
    assert "DELETE FROM knowledge_compiler_runs WHERE document_id = $1" not in source


def test_ingestion_creates_compiler_run_before_outputs() -> None:
    source = inspect.getsource(knowledge_ingestion_service.KnowledgeIngestionService)

    assert "repo.create_compiler_run" in source
    assert "repo.create_compiler_batches" in source
    assert "repo.mark_compiler_batch_processing" in source
    assert "repo.complete_compiler_batch" in source
    assert "_persist_stage_e_compiler_outputs" in Path(
        "src/application/services/knowledge_ingestion_service.py"
    ).read_text(encoding="utf-8")
    assert "compiler_run_id=compiler_run_id" in Path(
        "src/application/services/knowledge_ingestion_service.py"
    ).read_text(encoding="utf-8")


def test_knowledge_progress_report_exposes_durable_batch_state() -> None:
    service_source = inspect.getsource(knowledge_service.KnowledgeService)
    http_source = inspect.getsource(knowledge_http)

    assert "processing_report" in service_source
    assert "answer_drafts" in service_source
    assert "list_document_compiler_batches" in service_source
    assert "get_document_answer_candidate_summary" in service_source
    assert "retry_document_failed_batches" in service_source
    assert "publish_document_ready_answers" in service_source
    assert '@router.get("/{document_id}/progress")' in http_source
    assert '@router.get("/{document_id}/fragments")' in http_source
    assert '@router.post("/{document_id}/publish-ready")' in http_source
    assert '@router.post("/{document_id}/retry-failed-batches")' in http_source
    assert "result.to_dict()" in http_source
