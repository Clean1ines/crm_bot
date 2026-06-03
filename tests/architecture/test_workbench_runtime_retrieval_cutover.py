from __future__ import annotations

from pathlib import Path


RUNTIME_WIRING_FILES = (
    "src/interfaces/composition/fastapi_lifespan.py",
    "src/interfaces/http/rag_eval.py",
    "src/infrastructure/queue/handlers/rag_eval.py",
)


def test_runtime_rag_wiring_uses_workbench_runtime_retrieval_adapter() -> None:
    for path in RUNTIME_WIRING_FILES:
        source = Path(path).read_text(encoding="utf-8")

        assert "WorkbenchRuntimeRetrievalRepository" in source
        assert "KnowledgeRepository(" not in source
        assert "src.infrastructure.db.repositories.knowledge_repository" not in source


def test_workbench_runtime_retrieval_adapter_reads_workbench_runtime_table() -> None:
    source = Path(
        "src/infrastructure/db/workbench_runtime_retrieval_repository.py"
    ).read_text(encoding="utf-8")

    assert "knowledge_workbench_runtime_retrieval_entries" in source
    assert "status = 'published'" in source
    assert "visibility = 'runtime'" in source
    assert "knowledge_base" not in source
    assert "knowledge_compilation" not in source
    assert "CanonicalKnowledgeEntry" not in source
    assert "AnswerCandidate" not in source
    assert "SourceChunk" not in source


def test_fastapi_lifespan_no_longer_uses_knowledge_repository_for_search_tool() -> None:
    source = Path("src/interfaces/composition/fastapi_lifespan.py").read_text(
        encoding="utf-8"
    )

    register_block = source[source.index("def register_builtin_tools") :]
    assert "SearchKnowledgeTool" in register_block
    assert "RAGService" in register_block
    assert "WorkbenchRuntimeRetrievalRepository" in register_block
    assert "KnowledgeRepository" not in register_block
    assert (
        "src.infrastructure.db.repositories.knowledge_repository" not in register_block
    )
