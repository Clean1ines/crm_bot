from src.application.dto.knowledge_dto import (
    KnowledgePreviewRequestDto,
    KnowledgePreviewResponseDto,
)
from src.domain.project_plane.knowledge_views import KnowledgeSearchResultView


def test_preview_request_normalizes_question_and_limit() -> None:
    request = KnowledgePreviewRequestDto(question="  Где мой заказ?  ", limit=50)

    assert request.normalized_question() == "Где мой заказ?"
    assert request.normalized_limit() == 10


def test_preview_response_serializes_best_and_top_results() -> None:
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
    )

    payload = response.to_dict()

    assert payload["query"] == "возврат"
    assert payload["is_empty"] is False
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
    }
