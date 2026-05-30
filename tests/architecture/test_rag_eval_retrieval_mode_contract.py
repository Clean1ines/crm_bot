from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_rag_service_retriever_no_longer_uses_object_getattr() -> None:
    source = read("src/infrastructure/rag_eval/adapters.py")
    class_block = source[
        source.index("class RagServiceRagEvalRetriever:") : source.index(
            "class VectorOnlyRagEvalRetriever:"
        )
    ]

    assert "rag_service: object" not in class_block
    assert "getattr(" not in class_block
    assert "RagEvalSearchWithExpansionPort" in source


def test_queue_payload_and_progress_include_retrieval_mode_metadata() -> None:
    http = read("src/interfaces/http/rag_eval.py")
    handler = read("src/infrastructure/queue/handlers/rag_eval.py")

    assert '"retrieval_mode": retrieval_mode.value' in http
    assert 'normalize_rag_eval_retrieval_mode(payload.get("retrieval_mode"))' in handler
    assert "**retrieval_metadata" in handler
    assert "VectorOnlyRagEvalRetriever" in handler


def test_frontend_rag_eval_request_and_preview_contract_include_retrieval_mode() -> (
    None
):
    rag_api = read("frontend/src/shared/api/modules/ragEval.ts")
    knowledge_api = read("frontend/src/shared/api/modules/knowledge.ts")
    page = read("frontend/src/pages/rag-eval/RagEvalPage.tsx")

    assert "export type RagEvalRetrievalMode" in rag_api
    assert (
        "retrieval_mode: options.retrieval_mode ?? 'production_equivalent'" in rag_api
    )
    assert "KnowledgePreviewRetrievalMode" in knowledge_api
    assert "retrieval_mode: retrievalMode" in knowledge_api
    assert "useState<RagEvalRetrievalMode>('production_equivalent')" in page
    assert "ragEval.retrievalMode.vectorDebug.label" in page
