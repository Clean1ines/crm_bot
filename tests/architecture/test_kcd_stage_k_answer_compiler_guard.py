from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

INGESTION_SERVICE = ROOT / "src/application/services/knowledge_ingestion_service.py"
KNOWLEDGE_PORT = ROOT / "src/application/ports/knowledge_port.py"
KNOWLEDGE_PREPROCESSOR = ROOT / "src/infrastructure/llm/knowledge_preprocessor.py"
FAQ_COMPILER_PROMPT = ROOT / "src/agent/prompts/knowledge_answer_compiler_faq.txt"


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


def test_stage_k_preprocessor_port_has_no_legacy_known_answer_path() -> None:
    source = _source(KNOWLEDGE_PORT)

    assert "previous_entry_titles" not in source
    assert "async def merge_known" + "_answer(" not in source
    assert "KnowledgeAnswerMerge" + "ExecutionResult" not in source
    assert "tighten_semantic_merges" in source


def test_stage_k_groq_preprocessor_prompt_has_question_first_contract() -> None:
    preprocessor_source = _source(KNOWLEDGE_PREPROCESSOR)
    build_prompt_source = _function_source(KNOWLEDGE_PREPROCESSOR, "_build_prompt")
    prompt_source = _source(FAQ_COMPILER_PROMPT)

    assert '"previous_answer_titles"' not in preprocessor_source
    assert "PREPROCESSING_SHARED_CONTRACT_PROMPT_FILE" not in preprocessor_source
    assert "knowledge_preprocess_shared_contract.txt" not in preprocessor_source
    assert "knowledge_answer_compiler_faq.txt" in preprocessor_source
    assert "NOW PROCESS THIS SOURCE JSON" not in build_prompt_source

    assert "known_question_intents" not in prompt_source
    assert "Не сравнивай текущий текст с предыдущими ответами" in prompt_source
    assert "Не объединяй результат с предыдущими ответами" in prompt_source
    assert "Не возвращай match, kind, known_intent_id" in prompt_source


def test_stage_k_groq_preprocessor_has_answer_only_resolution_contract() -> None:
    source = _source(KNOWLEDGE_PREPROCESSOR)

    assert "ANSWER_MERGE_PROMPT_FILE" not in source
    assert "merge_known" + "_answer" not in source
    assert "parse_answer" + "_merge_payload" not in source
    assert '"cases"' in source
    assert '"canonical_answer"' in source
    assert "full canonical entries" not in source


def test_answer_resolution_parser_does_not_read_candidate_ids_from_payload() -> None:
    parser_source = _function_source(
        ROOT / "src/domain/project_plane/knowledge_preprocessing.py",
        "_parse_semantic_merge_decision",
    )

    assert '.get("candidate_ids")' not in parser_source
    assert "_string_list(payload.get" not in parser_source
    assert "candidate_ids=()" in parser_source


def test_stage_k_ingestion_records_online_merge_compiler_metrics() -> None:
    source = _source(INGESTION_SERVICE)

    assert "technical_compiler_call_count" in source
    assert "previous_title_carryover" in source
    assert "False" in source
    assert "one_meaning_at_a_time_merge" in source
    assert "extractor_only_compiler_loop" not in source
    assert "answer_resolution_enabled" in source
    assert "semantic_merge_tightening" in source
    assert "semantic_merge_fallback_used" in source
    assert "llm_answer_resolution_call_count" in source
    assert "KCD_STAGE_K_COMPILER_VERSION" in source
    assert "Knowledge answer compiler technical batch completed" in source
    assert "technical_compiler_total_count" in source
    assert "compiled_entry_count" in source
    assert "status_message" in source
    assert "model" in source


def test_runtime_prompts_preserve_user_language() -> None:
    prompts_dir = FAQ_COMPILER_PROMPT.parent
    response_prompt = _source(prompts_dir / "response_prompt.txt")
    intent_prompt = _source(prompts_dir / "intent_prompt.txt")
    interpretation_prompt = _source(prompts_dir / "interpretation_block.txt")

    assert "Если клиент пишет по-русски, отвечай по-русски" in response_prompt
    assert "Не переходи на английский" in response_prompt
    assert "Верни только JSON" in intent_prompt
    assert "Значения enum оставляй строго на английском" in intent_prompt
    assert "ПРАВИЛА ИНТЕРПРЕТАЦИИ ПАМЯТИ" in interpretation_prompt
