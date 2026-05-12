from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

INGESTION_SERVICE = ROOT / "src/application/services/knowledge_ingestion_service.py"
KNOWLEDGE_PORT = ROOT / "src/application/ports/knowledge_port.py"
KNOWLEDGE_PREPROCESSOR = ROOT / "src/infrastructure/llm/knowledge_preprocessor.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _function_source(path: Path, function_name: str) -> str:
    source = _source(path)
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            if node.name == function_name:
                if node.end_lineno is None:
                    raise AssertionError(f"{function_name} has no end_lineno")
                lines = source.splitlines()
                return "\n".join(lines[node.lineno - 1 : node.end_lineno])

    raise AssertionError(f"Function not found: {function_name}")


def test_stage_k_ingestion_does_not_use_preprocessing_result_to_chunks() -> None:
    source = _source(INGESTION_SERVICE)

    assert "result.to_chunks()" not in source
    assert ".to_chunks()" not in _function_source(
        INGESTION_SERVICE,
        "process_document",
    )


def test_stage_k_process_document_does_not_combine_raw_and_structured_runtime_rows() -> (
    None
):
    process_document_source = _function_source(
        INGESTION_SERVICE,
        "process_document",
    )

    assert "_combined_chunks_for_canonical_persistence(" not in process_document_source
    assert "_raw_chunks_for_structured_persistence(" not in process_document_source
    assert (
        "raw_source_chunks_not_persisted_as_runtime_entries" in process_document_source
    )


def test_stage_k_preprocessor_port_requires_carryover_and_one_meaning_merge() -> None:
    source = _source(KNOWLEDGE_PORT)

    assert "previous_entry_titles: Sequence[str] = ()" in source
    assert "async def merge_answer_entry(" in source
    assert "existing_entry: KnowledgePreprocessingEntry" in source
    assert "incoming_entry: KnowledgePreprocessingEntry" in source


def test_stage_k_groq_preprocessor_prompt_has_cross_chunk_carryover_contract() -> None:
    source = _source(KNOWLEDGE_PREPROCESSOR)

    assert '"previous_answer_titles": previous_titles' in source
    assert "CROSS-CHUNK COMPILER CONTEXT" in source
    assert "reuse the exact previous title" in source
    assert "Do not output standalone generated questions as entries" in source


def test_stage_k_groq_preprocessor_has_one_meaning_merge_contract() -> None:
    source = _source(KNOWLEDGE_PREPROCESSOR)

    assert "ONE-MEANING MERGE TASK" in source
    assert "Merge exactly these two grounded answer entries into one" in source
    assert "Return exactly one JSON entry" in source
    assert "Answer merge must return exactly one entry" in source


def test_stage_k_ingestion_records_compiler_loop_and_merge_metrics() -> None:
    source = _source(INGESTION_SERVICE)

    assert "technical_compiler_call_count" in source
    assert "previous_title_carryover" in source
    assert "one_meaning_at_a_time_merge" in source
    assert "llm_merge_call_count" in source
    assert "KCD_STAGE_K_COMPILER_VERSION" in source
