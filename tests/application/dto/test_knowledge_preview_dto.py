from src.application.dto.knowledge_dto import (
    KnowledgePreviewRequestDto,
    KnowledgePreviewResponseDto,
)
from src.domain.project_plane.knowledge_views import KnowledgeSearchResultView
from src.domain.project_plane.production_retrieval import ProductionRetrievalMode


def test_preview_request_normalizes_question_limit_and_default_retrieval_mode() -> None:
    request = KnowledgePreviewRequestDto(question="  Где мой заказ?  ", limit=50)

    assert request.normalized_question() == "Где мой заказ?"
    assert request.normalized_limit() == 10
    assert request.normalized_retrieval_mode_value() == "runtime_equivalent"
    assert (
        request.normalized_production_retrieval_mode()
        == ProductionRetrievalMode.RUNTIME_EQUIVALENT_PREVIEW
    )


def test_preview_request_supports_lexical_debug_mode() -> None:
    request = KnowledgePreviewRequestDto(
        question="debug",
        limit=5,
        retrieval_mode="lexical_debug",
    )

    assert request.normalized_retrieval_mode_value() == "lexical_debug"
    assert (
        request.normalized_production_retrieval_mode()
        == ProductionRetrievalMode.LEXICAL_DEBUG
    )


def test_preview_response_serializes_best_and_top_results_with_retrieval_metadata() -> (
    None
):
    response = KnowledgePreviewResponseDto.from_results(
        query="возврат",
        results=[
            KnowledgeSearchResultView(
                id="chunk-1",
                content="Возврат доступен в течение 14 дней.",
                score=0.91,
                method="hybrid",
                document_id="doc-1",
                source="faq.md",
                document_status="processed",
            )
        ],
        retrieval_mode="runtime_equivalent",
        method="production_runtime_search",
        trace={"runtime_equivalent": True},
    )

    payload = response.to_dict()

    assert payload["query"] == "возврат"
    assert payload["is_empty"] is False
    assert payload["retrieval_mode"] == "runtime_equivalent"
    assert payload["method"] == "production_runtime_search"
    assert payload["trace"] == {"runtime_equivalent": True}
    assert payload["best_result"] == {
        "id": "chunk-1",
        "content": "Возврат доступен в течение 14 дней.",
        "answer": "Возврат доступен в течение 14 дней.",
        "score": 0.91,
        "method": "hybrid",
        "source": "faq.md",
        "document_id": "doc-1",
        "document_status": "processed",
    }
    assert payload["top_results"] == [payload["best_result"]]


def test_preview_response_empty_is_safe() -> None:
    response = KnowledgePreviewResponseDto.empty(query="нет данных")

    assert response.to_dict() == {
        "query": "нет данных",
        "best_result": None,
        "top_results": [],
        "is_empty": True,
        "retrieval_mode": "runtime_equivalent",
        "method": "production_runtime_search",
        "trace": {},
    }
