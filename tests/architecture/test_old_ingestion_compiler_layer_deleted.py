from __future__ import annotations

import importlib
from pathlib import Path


DELETED_FILES = (
    "src/application/services/knowledge_ingestion_service.py",
    "src/application/services/knowledge_ingestion_contracts.py",
    "src/application/services/knowledge_answer_compiler_batching.py",
    "src/application/services/knowledge_source_material_builder.py",
    "src/application/ports/knowledge/structured_ingestion.py",
    "src/application/ports/knowledge/answer_candidates.py",
    "src/application/ports/knowledge/canonical_entries.py",
    "src/application/ports/knowledge/compilation_trace.py",
    "tests/application/services/test_knowledge_answer_compiler_batching.py",
)


def test_old_ingestion_compiler_layer_files_are_deleted() -> None:
    for rel_path in DELETED_FILES:
        assert not Path(rel_path).exists(), f"{rel_path} should be deleted"


def test_production_code_does_not_import_deleted_ingestion_compiler_layer() -> None:
    forbidden = (
        "knowledge_ingestion_service",
        "knowledge_ingestion_contracts",
        "knowledge_answer_compiler_batching",
        "knowledge_source_material_builder",
        "src.application.ports.knowledge." + "structured_ingestion",
        "src.application.ports.knowledge." + "answer_candidates",
        "src.application.ports.knowledge." + "canonical_entries",
        "src.application.ports.knowledge." + "compilation_trace",
        "KnowledgeStructuredIngestionRepositoryPort",
        "KnowledgeAnswerCandidatePort",
        "KnowledgeCanonicalEntryPort",
        "KnowledgeCompilationTracePort",
    )

    for path in Path("src").rglob("*.py"):
        source = path.read_text(encoding="utf-8", errors="replace")
        for marker in forbidden:
            assert marker not in source, f"{path} still contains {marker}"


def test_clean_runtime_roots_import_without_deleted_compiler_layer() -> None:
    modules = (
        "src.interfaces.http.knowledge",
        "src.interfaces.composition.fastapi_lifespan",
        "src.infrastructure.queue.job_dispatcher",
        "src.infrastructure.queue.worker_loop",
        "src.infrastructure.db.knowledge_workbench_repository",
        "src.infrastructure.db.workbench_runtime_retrieval_repository",
        "src.application.services.commercial_price_review_service",
    )

    for module in modules:
        importlib.import_module(module)
