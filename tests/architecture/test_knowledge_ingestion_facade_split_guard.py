from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INGESTION = ROOT / "src/application/services/knowledge_ingestion_service.py"

FORBIDDEN_HELPER_DEFS = {
    "_apply_answer_resolution_decisions",
    "_resolve_compiled_answer_cases",
    "_compiler_batches_from_technical_batches",
    "_raw_answer_candidates_from_preprocessing_entries",
    "_persist_stage_e_compiler_outputs",
    "_mechanically_cleanup_compiled_entries",
}

SERVICE_FILES = (
    ROOT / "src/application/services/knowledge_structured_ingestion_service.py",
    ROOT / "src/application/services/knowledge_failed_batch_retry_service.py",
    ROOT / "src/application/services/knowledge_ready_answer_publication_service.py",
    ROOT / "src/application/services/knowledge_retighten_service.py",
    ROOT / "src/application/services/knowledge_surface_ingestion_service.py",
)

QUEUE_HANDLER_FILES = (
    ROOT / "src/infrastructure/queue/handlers/knowledge_upload.py",
    ROOT / "src/infrastructure/queue/handlers/knowledge_publish_ready.py",
    ROOT / "src/infrastructure/queue/handlers/knowledge_failed_batches.py",
    ROOT / "src/infrastructure/queue/handlers/knowledge_retighten.py",
)


def _top_level_defined_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()

    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            result.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result.add(target.id)

    return result


def test_knowledge_ingestion_service_is_compatibility_facade_only() -> None:
    source = INGESTION.read_text(encoding="utf-8")
    defined_names = _top_level_defined_names(INGESTION)

    assert "class KnowledgeIngestionService" in source
    assert not (FORBIDDEN_HELPER_DEFS & defined_names)
    assert "knowledge_answer_resolution_service import" not in source
    assert "knowledge_canonical_publication_builder import" not in source
    assert "knowledge_source_material_builder import" not in source


def test_split_services_do_not_import_business_helpers_from_legacy_ingestion() -> None:
    for path in SERVICE_FILES:
        source = path.read_text(encoding="utf-8")

        assert (
            "from src.application.services.knowledge_ingestion_service import"
            not in source
        )
        assert "KnowledgeIngestionService" not in source


def test_queue_handlers_do_not_import_knowledge_ingestion_service() -> None:
    for path in QUEUE_HANDLER_FILES:
        source = path.read_text(encoding="utf-8")

        assert "KnowledgeIngestionService" not in source
        assert (
            "from src.application.services.knowledge_ingestion_service import"
            not in source
        )
