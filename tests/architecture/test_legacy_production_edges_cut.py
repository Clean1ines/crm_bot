from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_old_knowledge_ingestion_facade_is_deleted() -> None:
    assert not Path("src/application/services/knowledge_ingestion_service.py").exists()
    assert not Path(
        "src/application/services/knowledge_ingestion_contracts.py"
    ).exists()
    assert not Path("src/application/ports/knowledge/structured_ingestion.py").exists()


def test_process_knowledge_upload_worker_files_are_deleted() -> None:
    assert not Path("src/infrastructure/queue/handlers/knowledge_upload.py").exists()
    assert not Path(
        "src/infrastructure/queue/handlers/knowledge_upload_recovery.py"
    ).exists()


def test_process_knowledge_upload_is_not_a_queue_runtime_path() -> None:
    queue_roots = (
        "src/infrastructure/queue/job_types.py",
        "src/infrastructure/queue/job_dispatcher.py",
        "src/infrastructure/queue/worker_loop.py",
    )
    forbidden = (
        "TASK_PROCESS_KNOWLEDGE_UPLOAD",
        "process_knowledge_upload",
        "handle_process_knowledge_upload",
        "mark_process_knowledge_upload_exhausted",
        "src.infrastructure.queue.handlers.knowledge_upload",
    )

    for raw_path in queue_roots:
        source = Path(raw_path).read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in source, f"{raw_path} still contains {marker}"


def test_retired_knowledge_service_processing_report_is_not_a_legacy_path() -> None:
    assert not Path("src/application/services/knowledge_service.py").exists()
    assert not Path(
        "src/application/services/knowledge_source_material_builder.py"
    ).exists()
    assert not Path("src/application/services/knowledge_ingestion_service.py").exists()

    source = _read("src/interfaces/http/knowledge.py")

    assert "KnowledgeService(" not in source
    assert "knowledge_source_material_builder" not in source
    assert "knowledge_ingestion_service" not in source


def test_processing_overview_backend_path_is_retired() -> None:
    assert not Path(
        "src/interfaces/composition/faq_workbench_processing_overview.py"
    ).exists()
    assert not Path(
        "src/application/workbench_observability/processing_overview.py"
    ).exists()

    knowledge_http = Path("src/interfaces/http/knowledge.py").read_text(
        encoding="utf-8"
    )
    repository = Path(
        "src/infrastructure/db/workbench_observability_repository.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        '"/processing-overview"',
        "fetch_workbench_processing_overview",
        "knowledge_processing_overview",
        "list_processing_overview_documents",
        "list_processing_overview_node_runs",
    )

    for marker in forbidden:
        assert marker not in knowledge_http
        assert marker not in repository
