from src.domain.runtime.knowledge_search import (
    KnowledgeSearchContext,
    KnowledgeSearchResult,
)
from src.domain.runtime.knowledge_query import KnowledgeQuerySource


def test_knowledge_search_context_hashes_query():
    context = KnowledgeSearchContext.from_state(
        {"project_id": "project-1", "user_input": "hello"}
    )

    assert context.project_id == "project-1"
    assert context.query == "hello"
    assert len(context.query_hash) == 32


def test_knowledge_search_context_uses_resolved_query_only_for_continuation_cta():
    context = KnowledgeSearchContext.from_state(
        {
            "project_id": "project-1",
            "user_input": "Да",
            "knowledge_query": "подробнее как работает продукт и его возможности",
            "knowledge_query_source": "model_contextual",
            "turn_relation": "continuation",
            "cta": "continue_explanation",
            "should_search_kb": True,
        }
    )

    assert context.query == "подробнее как работает продукт и его возможности"
    assert context.original_user_input == "Да"
    assert context.query_source is KnowledgeQuerySource.MODEL_CONTEXTUAL
    assert context.resolved_query_used is True


def test_knowledge_search_context_ignores_stale_resolved_query_on_new_topic():
    context = KnowledgeSearchContext.from_state(
        {
            "project_id": "project-1",
            "user_input": "Сколько это стоит?",
            "knowledge_query": "подробнее как работает продукт и его возможности",
            "knowledge_query_source": "model_contextual",
            "turn_relation": "new_topic",
            "cta": "none",
            "should_search_kb": True,
        }
    )

    assert context.query == "Сколько это стоит?"
    assert context.query_source is KnowledgeQuerySource.NONE
    assert context.resolved_query_used is False


def test_knowledge_search_context_uses_canonical_continue_explanation_source():
    context = KnowledgeSearchContext.from_state(
        {
            "project_id": "project-1",
            "user_input": "да",
            "knowledge_query": "подробнее как работает продукт и его возможности",
            "knowledge_query_source": "canonical_continue_explanation",
            "turn_relation": "continuation",
            "cta": "continue_explanation",
            "should_search_kb": True,
        }
    )

    assert context.query == "подробнее как работает продукт и его возможности"
    assert context.original_user_input == "да"
    assert context.query_source is KnowledgeQuerySource.CANONICAL_CONTINUE_EXPLANATION
    assert context.resolved_query_used is True
    assert context.resolved_query_hash == context.query_hash
    assert context.resolved_query_len == len(context.query)


def test_knowledge_search_context_normalizes_unknown_query_source_to_none():
    context = KnowledgeSearchContext.from_state(
        {
            "project_id": "project-1",
            "user_input": "А роли?",
            "knowledge_query": "какие роли есть",
            "knowledge_query_source": "unknown_source",
            "turn_relation": "continuation",
            "cta": "none",
            "should_search_kb": True,
        }
    )

    assert context.query == "какие роли есть"
    assert context.query_source is KnowledgeQuerySource.NONE
    assert context.resolved_query_used is True


def _context_for_should_search(value: object = None, *, include: bool = True):
    state = {
        "project_id": "project-1",
        "user_input": "Да",
        "knowledge_query": "подробнее как работает продукт",
        "knowledge_query_source": "model_contextual",
        "turn_relation": "continuation",
        "cta": "none",
    }
    if include:
        state["should_search_kb"] = value
    return KnowledgeSearchContext.from_state(state)


def test_knowledge_search_context_requires_should_search_kb_identity_true():
    assert _context_for_should_search(True).resolved_query_used is True

    for value in (False, None, 0, "", "true"):
        context = _context_for_should_search(value)
        assert context.query == "Да"
        assert context.query_source is KnowledgeQuerySource.NONE
        assert context.resolved_query_used is False

    missing = _context_for_should_search(include=False)
    assert missing.query == "Да"
    assert missing.resolved_query_used is False


def test_knowledge_search_context_rejects_negative_cta_reply():
    context = KnowledgeSearchContext.from_state(
        {
            "project_id": "project-1",
            "user_input": "нет",
            "knowledge_query": "подробнее как работает продукт",
            "knowledge_query_source": "model_contextual",
            "turn_relation": "continuation",
            "cta": "continue_explanation",
            "resolved_cta_reply": "negative",
            "should_search_kb": True,
        }
    )

    assert context.query == "нет"
    assert context.query_source is KnowledgeQuerySource.NONE
    assert context.resolved_query_used is False


def test_knowledge_search_context_allows_reopening_contextual_query():
    context = KnowledgeSearchContext.from_state(
        {
            "project_id": "project-1",
            "user_input": "а по ролям?",
            "knowledge_query": "какие роли есть",
            "knowledge_query_source": "model_contextual",
            "turn_relation": "reopening",
            "cta": "none",
            "should_search_kb": True,
        }
    )

    assert context.query == "какие роли есть"
    assert context.query_source is KnowledgeQuerySource.MODEL_CONTEXTUAL
    assert context.resolved_query_used is True


def test_knowledge_search_result_normalizes_tool_payload():
    result = KnowledgeSearchResult.from_tool_payload(
        {
            "results": [
                {"id": "chunk-1", "score": 0.9, "content": "abc"},
                {"score": 0.5, "content": "xyz"},
            ]
        }
    )

    assert result.ids() == ["chunk-1", "no-id-1"]
    assert result.scores() == [0.9, 0.5]
    assert result.to_state_patch() == {
        "knowledge_chunks": [
            {"id": "chunk-1", "score": 0.9, "content": "abc"},
            {"id": "no-id-1", "score": 0.5, "content": "xyz"},
        ],
        "knowledge_retrieval_status": "retrieved",
        "knowledge_retrieval_error_type": None,
    }


def test_knowledge_search_result_preserves_full_curated_claim_text():
    claim = (
        "Workbench runtime facts must reach the answer prompt as complete curated "
        "claims, because cutting them at an arbitrary early boundary can remove "
        "the condition or limitation that makes the answer accurate."
    )

    result = KnowledgeSearchResult.from_tool_payload(
        {"results": [{"id": "runtime-entry-1", "score": 0.91, "content": claim}]}
    )

    assert result.to_state_patch() == {
        "knowledge_chunks": [
            {"id": "runtime-entry-1", "score": 0.91, "content": claim}
        ],
        "knowledge_retrieval_status": "retrieved",
        "knowledge_retrieval_error_type": None,
    }
