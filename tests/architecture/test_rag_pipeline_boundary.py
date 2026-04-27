from pathlib import Path


def test_rag_service_does_not_instantiate_groq_client_directly():
    source = Path("src/infrastructure/llm/rag_service.py").read_text(encoding="utf-8")

    assert "AsyncGroq(" not in source
    assert "from groq import" not in source
    assert "GroqQueryExpander" not in source


def test_groq_query_expansion_is_isolated_to_adapter():
    source = Path("src/infrastructure/llm/query_expander.py").read_text(
        encoding="utf-8"
    )

    assert "class GroqQueryExpander" in source
    assert "AsyncGroq" in source


def test_rag_contract_has_no_infrastructure_imports():
    source = Path("src/infrastructure/llm/rag_contract.py").read_text(encoding="utf-8")

    forbidden = [
        "groq",
        "asyncpg",
        "redis",
        "fastapi",
        "KnowledgeRepository",
    ]

    violations = [item for item in forbidden if item in source]
    assert violations == []
