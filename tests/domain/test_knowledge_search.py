from src.domain.runtime.knowledge_search import (
    KnowledgeSearchContext,
    KnowledgeSearchResult,
)


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
            "turn_relation": "continuation",
            "cta": "continue_explanation",
        }
    )

    assert context.query == "подробнее как работает продукт и его возможности"
    assert context.original_user_input == "Да"


def test_knowledge_search_context_ignores_stale_resolved_query_on_new_topic():
    context = KnowledgeSearchContext.from_state(
        {
            "project_id": "project-1",
            "user_input": "Сколько это стоит?",
            "knowledge_query": "подробнее как работает продукт и его возможности",
            "turn_relation": "new_topic",
            "cta": "none",
        }
    )

    assert context.query == "Сколько это стоит?"


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
