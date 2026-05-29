from __future__ import annotations

import ast
from pathlib import Path


INGESTION = Path("src/application/services/knowledge_ingestion_service.py")
STRUCTURED = Path("src/application/services/knowledge_structured_ingestion_service.py")


def _class_method_source(path: Path, class_name: str, method_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.AsyncFunctionDef) and item.name == method_name:
                    if item.end_lineno is None:
                        raise AssertionError(f"{method_name} has no end_lineno")
                    lines = source.splitlines()
                    return "\n".join(lines[item.lineno - 1 : item.end_lineno])

    raise AssertionError(f"{class_name}.{method_name} not found")


def test_structured_ingestion_service_contains_non_faq_processing_flow() -> None:
    source = STRUCTURED.read_text(encoding="utf-8")

    assert "class KnowledgeStructuredIngestionService" in source
    assert "async def process_document(" in source
    assert "await repo.cleanup_document_artifacts(" in source
    assert "CommercialPriceIngestionService" in source
    assert "await repo.create_compiler_run(" in source
    assert "_technical_chunk_batches_for_answer_compiler" in source
    assert "_raw_answer_candidates_from_preprocessing_entries" in source
    assert "KnowledgeAnswerResolutionService().resolve_compiled_answer_cases" in source
    assert "_canonical_entries_from_preprocessing_result" in source
    assert "_persist_stage_e_compiler_outputs" in source
    assert "PREPROCESSING_STATUS_COMPLETED" in source
    assert "PREPROCESSING_STATUS_FAILED" in source


def test_structured_ingestion_service_uses_extracted_builders_not_internals() -> None:
    source = STRUCTURED.read_text(encoding="utf-8")

    assert "knowledge_source_material_builder" in source
    assert "knowledge_answer_compiler_batching" in source
    assert "knowledge_generated_entry_repair" in source
    assert "knowledge_canonical_publication_builder" in source
    assert "knowledge_answer_resolution_service" in source

    forbidden_definitions = (
        "def _technical_chunk_batches_for_answer_compiler",
        "def repair_generated_entry",
        "def canonical_entries_from_preprocessing_result",
        "async def _resolve_compiled_answer_cases",
        "async def retighten_processed_document",
        "async def retry_failed_batches",
        "async def publish_ready_answers",
    )
    for marker in forbidden_definitions:
        assert marker not in source


def test_ingestion_process_document_is_wrapper_around_structured_service() -> None:
    method_source = _class_method_source(
        INGESTION,
        "KnowledgeIngestionService",
        "process_document",
    )
    compact_method_source = "".join(method_source.split())

    assert "KnowledgeStructuredIngestionService" in method_source
    assert (
        "returnawaitKnowledgeStructuredIngestionService(self.pool).process_document"
        in compact_method_source
    )
    assert "if mode == MODE_FAQ:" in method_source

    forbidden_markers = (
        "process_compiler_batch",
        "_technical_chunk_batches_for_answer_compiler",
        "KnowledgeAnswerResolutionService().resolve_compiled_answer_cases",
        "_canonical_entries_from_preprocessing_result",
        "_persist_stage_e_compiler_outputs",
        "CommercialPriceIngestionService",
    )
    for marker in forbidden_markers:
        assert marker not in method_source
