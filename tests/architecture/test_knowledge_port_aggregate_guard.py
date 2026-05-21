from __future__ import annotations

import inspect

from src.application.ports import knowledge_port


def test_aggregate_knowledge_repository_port_is_composed_only() -> None:
    source = inspect.getsource(knowledge_port.KnowledgeRepositoryPort)

    assert "Temporary aggregate port. Do not add new methods here." in source
    assert "class KnowledgeRepositoryPort(" in source
    assert "KnowledgeDocumentPort" in source
    assert "KnowledgeSourceMaterialPort" in source
    assert "KnowledgeCompilationTracePort" in source
    assert "KnowledgeAnswerCandidatePort" in source
    assert "KnowledgeCanonicalEntryPort" in source
    assert "KnowledgeRuntimeRetrievalPort" in source
    assert "KnowledgeCurationPort" in source
    assert "async def " not in source
