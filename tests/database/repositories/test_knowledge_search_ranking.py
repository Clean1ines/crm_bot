from __future__ import annotations

from src.domain.project_plane.knowledge_retrieval_surface import (
    RUNTIME_ENTRY_KIND_VALUES,
)
from src.infrastructure.db.repositories.knowledge_search_ranking import (
    _optional_row_text,
    keyword_overlap,
    preview_score_and_trace,
    query_tokens,
)


def test_query_tokens_keeps_russian_and_english_words() -> None:
    assert query_tokens("Карта VISA, доставка!") == {"карта", "visa", "доставка"}


def test_keyword_overlap_scores_query_coverage() -> None:
    assert keyword_overlap("доставка карта", "карта visa") == 0.5


def test_optional_row_text_missing_key_is_none() -> None:
    assert _optional_row_text({}, "missing") is None


def test_preview_score_and_trace_marks_specific_title_question_match() -> None:
    runtime_entry_kind = next(iter(RUNTIME_ENTRY_KIND_VALUES))
    row = {
        "entry_kind": runtime_entry_kind,
        "title": "Доставка",
        "questions": ["Как работает доставка?"],
        "synonyms": ["привоз"],
        "tags": ["логистика"],
        "search_text": "Доставка бесплатная от 5000 рублей",
        "embedding_text": "Доставка бесплатная от 5000 рублей",
        "lexical_score": 0.12,
        "vector_score": 0.42,
        "exact_score": 0.0,
        "score": 0.0,
    }

    result = preview_score_and_trace(
        row,
        query="доставка",
        content="Доставка бесплатная от 5000 рублей",
    )

    assert result.score > 0
    assert result.trace.is_production_safe is True
    assert "title" in result.trace.matched_fields
    assert "questions" in result.trace.matched_fields


def test_search_score_and_trace_scores_runtime_row_and_trace() -> None:
    from src.domain.project_plane.knowledge_retrieval_surface import (
        RUNTIME_ENTRY_KIND_VALUES,
    )
    from src.infrastructure.db.repositories.knowledge_search_ranking import (
        search_score_and_trace,
    )

    row = {
        "content": "Доставка стоит 500 рублей по городу.",
        "search_text": "Доставка цена стоимость 500 рублей курьер",
        "embedding_text": "Вопрос: какая цена доставки? Ответ: 500 рублей.",
        "title": "Доставка",
        "questions": ["Какая цена доставки?"],
        "synonyms": ["стоимость доставки", "курьер"],
        "tags": ["доставка"],
        "entry_kind": next(iter(RUNTIME_ENTRY_KIND_VALUES)),
        "vector_score": 0.31,
        "lexical_score": 0.16,
        "exact_score": 0.0,
    }

    score_trace = search_score_and_trace(
        row,
        query="цена доставки",
        content=str(row["content"]),
    )

    assert score_trace.score > 0.5
    assert score_trace.method == "hybrid"
    assert score_trace.trace.final_score == score_trace.score
    assert score_trace.trace.is_production_safe is True
    assert score_trace.trace.retrieval_surface_role == "production_runtime"
