from __future__ import annotations

from pathlib import Path


FASTAPI_LIFESPAN = Path("src/interfaces/composition/fastapi_lifespan.py")
RAG_SERVICE = Path("src/infrastructure/llm/rag_service.py")
SEARCH_TOOL = Path("src/tools/builtins.py")
RUNTIME_REPOSITORY = Path("src/infrastructure/db/workbench_runtime_retrieval_repository.py")


def test_fastapi_lifespan_registers_search_tool_with_workbench_runtime_repository() -> None:
    source = FASTAPI_LIFESPAN.read_text(encoding="utf-8")

    assert "KnowledgeRuntimeRetrievalPort" in source
    assert "WorkbenchRuntimeRetrievalRepository" in source
    assert "runtime_retrieval = WorkbenchRuntimeRetrievalRepository(db_pool)" in source
    assert "RAGService(" in source
    assert "cast(KnowledgeRuntimeRetrievalPort, runtime_retrieval)" in source
    assert "tool_registry.register(SearchKnowledgeTool(rag_service))" in source

    assert source.index("WorkbenchRuntimeRetrievalRepository(db_pool)") < source.index(
        "RAGService("
    )
    assert source.index("RAGService(") < source.index(
        "tool_registry.register(SearchKnowledgeTool(rag_service))"
    )


def test_rag_service_depends_on_narrow_runtime_search_port() -> None:
    source = RAG_SERVICE.read_text(encoding="utf-8")

    assert "from src.application.ports.knowledge.runtime_search import" in source
    assert "KnowledgeRuntimeRetrievalPort" in source
    assert "knowledge_repo: KnowledgeRuntimeRetrievalPort" in source
    assert "results = await self._repo.search(" in source

    forbidden = (
        "KnowledgeRepository(",
        "knowledge_base",
        "source_chunks",
        "knowledge_chunks",
        "KnowledgeRuntimeRetrievalPort |",
    )
    for marker in forbidden:
        assert marker not in source


def test_search_knowledge_tool_uses_rag_service_not_legacy_repository() -> None:
    source = SEARCH_TOOL.read_text(encoding="utf-8")

    assert "class SearchKnowledgeTool" in source
    assert "def __init__(self, rag_service: RAGService)" in source
    assert "self._rag_service = rag_service" in source
    assert "search_with_expansion(" in source

    forbidden = (
        "KnowledgeRepository(",
        "knowledge_base",
        "source_chunks",
        "knowledge_chunks",
        "AnswerCandidate",
        "CandidateCluster",
    )
    for marker in forbidden:
        assert marker not in source


def test_workbench_runtime_repository_is_canonical_fact_runtime_surface() -> None:
    source = RUNTIME_REPOSITORY.read_text(encoding="utf-8")

    assert "knowledge_workbench_runtime_retrieval_entries" in source
    assert "fact_id" in source
    assert "possible_questions" in source
    assert "answer_text" in source
    assert "entry_kind=\"faq_workbench_fact\"" in source
    assert "retrieval_surface_role=\"faq_workbench_runtime\"" in source
    assert "publish_fact_registry_runtime_entries" in source
    assert "_runtime_rows_from_fact_registry" in source

    forbidden = (
        "surface_id",
        "question_variants::text",
        'row["answer"]',
        'row.get("answer")',
        "knowledge_base",
        "source_chunks",
        "knowledge_chunks",
    )
    for marker in forbidden:
        assert marker not in source
