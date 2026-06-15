from pathlib import Path


REPOSITORY_PATH = Path("src/infrastructure/db/knowledge_workbench_repository.py")


def test_publication_purge_removes_transient_processing_retrieval_surfaces() -> None:
    source = REPOSITORY_PATH.read_text()

    assert "purge_transient_processing_workspace_after_publication" in source
    assert "DELETE FROM knowledge_workbench_local_claim_retrieval_entries" in source
    assert "DELETE FROM knowledge_workbench_runtime_retrieval_entries" in source
    assert "DELETE FROM knowledge_workbench_processing_runs" in source
    assert "retention_state = 'transient_purged'" in source


def test_publication_purge_preserves_production_runtime_vectors() -> None:
    method_source = REPOSITORY_PATH.read_text().split(
        "async def purge_transient_processing_workspace_after_publication",
        1,
    )[1]

    assert "DELETE FROM " + "knowledge_" + "retrieval_" + "surface" not in method_source
    assert "DELETE FROM knowledge_entries" not in method_source
    assert (
        "DELETE FROM " + "knowledge_" + "retrieval_" + "surface"
        not in method_source.replace("\\n", "\n")
    )
    assert "entry_kind = 'faq_workbench_fact'" not in _delete_statements(method_source)


def _delete_statements(source: str) -> str:
    statements: list[str] = []
    for chunk in source.split("DELETE FROM "):
        if not statements:
            statements.append(chunk)
            continue
        statements.append("DELETE FROM " + chunk.split('"""', 1)[0])
    return "\n".join(statements)


def test_publication_purge_documents_durable_state_contract() -> None:
    source = REPOSITORY_PATH.read_text()

    assert "Durable state after publication" in source
    assert "final published fact registry snapshot" in source
    assert "production runtime vectors in knowledge_entries" in source
    assert "pre-Prompt-C local claim retrieval vectors" in source
