from src.domain.runtime.knowledge_search import (
    KnowledgeSearchContext,
    KnowledgeSearchResult,
)


def test_knowledge_search_context_hashes_query():
    context = KnowledgeSearchContext.from_state({"project_id": "project-1", "user_input": "hello"})

    assert context.project_id == "project-1"
    assert context.query == "hello"
    assert len(context.query_hash) == 32


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
        ]
    }
