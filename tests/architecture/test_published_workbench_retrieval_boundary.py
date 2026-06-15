from __future__ import annotations

from pathlib import Path


def test_published_workbench_retrieval_boundary_does_not_use_legacy_surface() -> None:
    root = Path("src/contexts/knowledge_workbench/retrieval")
    sources = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))

    forbidden = (
        "knowledge_retrieval_surface",
        "knowledge_workbench_surfaces",
        "KnowledgeRepository",
        "knowledge_search_queries",
        "RUNTIME_VECTOR_SEARCH_SQL",
        "RUNTIME_HYBRID_SEARCH_SQL",
    )
    for marker in forbidden:
        assert marker not in sources


def test_published_workbench_retrieval_boundary_has_no_llm_provider_calls() -> None:
    root = Path("src/contexts/knowledge_workbench/retrieval")
    sources = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))

    forbidden = ("Groq", "AsyncGroq", "OpenAI", "openai", "chat.completions")
    for marker in forbidden:
        assert marker not in sources


def test_published_workbench_retrieval_uses_embedding_generation_port_only() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/retrieval/application/use_cases/"
        "search_published_workbench_runtime.py"
    ).read_text(encoding="utf-8")

    assert "EmbeddingGenerationPort" in source
    assert "EmbeddingGenerationRequest" in source
    assert 'task="retrieval.query"' in source


def test_published_workbench_retrieval_model_has_no_answer_text_semantics() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/retrieval/application/models/"
        "published_workbench_retrieval.py"
    ).read_text(encoding="utf-8")

    assert "answer_text" not in source
