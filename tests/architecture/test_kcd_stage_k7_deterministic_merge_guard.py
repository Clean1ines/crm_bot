from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_kcd_stage_k7_runtime_does_not_call_full_entry_llm_merge() -> None:
    service_source = (
        ROOT / "src/application/services/knowledge_ingestion_service.py"
    ).read_text(encoding="utf-8")
    preprocessor_source = (
        ROOT / "src/infrastructure/llm/knowledge_preprocessor.py"
    ).read_text(encoding="utf-8")
    port_source = (ROOT / "src/application/ports/knowledge_port.py").read_text(
        encoding="utf-8"
    )

    assert ("merge" + "_answer_entry") not in service_source
    assert ("merge" + "_answer_entry") not in preprocessor_source
    assert ("merge" + "_answer_entry") not in port_source
    assert "merge_embedding_text" in service_source
    assert "merge_embedding_text" in preprocessor_source
    assert "merge_embedding_text" in port_source


def test_kcd_stage_k7_llm_merge_only_accepts_embedding_text_payload() -> None:
    domain_source = (
        ROOT / "src/domain/project_plane/knowledge_preprocessing.py"
    ).read_text(encoding="utf-8")
    preprocessor_source = (
        ROOT / "src/infrastructure/llm/knowledge_preprocessor.py"
    ).read_text(encoding="utf-8")

    prompt_block = preprocessor_source[
        preprocessor_source.index(
            "def _build_embedding_text_merge_prompt"
        ) : preprocessor_source.index("def _build_prompt")
    ]

    assert "parse_embedding_text_merge_payload" in domain_source
    assert "KnowledgeEmbeddingTextMergeExecutionResult" in domain_source
    assert "The only allowed key is embedding_text" in prompt_block
    assert "existing_entry" not in prompt_block
    assert "incoming_entry" not in prompt_block


def test_kcd_stage_k7_progress_metrics_expose_technical_and_semantic_counts() -> None:
    service_source = (
        ROOT / "src/application/services/knowledge_ingestion_service.py"
    ).read_text(encoding="utf-8")
    frontend_source = (
        ROOT / "frontend/src/pages/knowledge/KnowledgePage.tsx"
    ).read_text(encoding="utf-8")

    assert "technical_chunk_total_count" in service_source
    assert "technical_chunk_processed_count" in service_source
    assert "semantic_answer_count" in service_source
    assert "semantic_answer_merge_count" in service_source
    assert "elapsed_seconds" in service_source

    assert "Технические фрагменты" in frontend_source
    assert "Собрано смысловых ответов" in frontend_source
    assert "Времени прошло" in frontend_source
    assert "setInterval" in frontend_source
