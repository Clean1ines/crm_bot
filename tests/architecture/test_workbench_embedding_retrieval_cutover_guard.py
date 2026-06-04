from pathlib import Path

from src.domain.project_plane.knowledge_entry_kind import (
    RUNTIME_ENTRY_KIND_VALUES,
)


RUNTIME_PUBLICATION_SERVICE = Path(
    "src/application/services/faq_workbench_runtime_publication_service.py"
)
PUBLISH_READY_COMPOSITION = Path("src/interfaces/composition/faq_workbench_publish_ready.py")
WORKBENCH_RUNTIME_REPOSITORY = Path(
    "src/infrastructure/db/workbench_runtime_retrieval_repository.py"
)
WORKBENCH_RETRIEVAL_SURFACE_REPOSITORY = Path(
    "src/infrastructure/db/workbench_retrieval_surface_repository.py"
)
WORKBENCH_RETRIEVAL_SURFACE_EMBEDDING_ADAPTER = Path(
    "src/infrastructure/llm/workbench_retrieval_surface_embedding_adapter.py"
)
KNOWLEDGE_REPOSITORY = Path("src/infrastructure/db/repositories/knowledge_repository.py")
RAG_SERVICE = Path("src/infrastructure/llm/rag_service.py")
SEARCH_QUERIES = Path("src/infrastructure/db/repositories/knowledge_search_queries.py")
LOCAL_CLAIM_RETRIEVAL_SERVICE = Path(
    "src/application/services/faq_workbench_local_claim_retrieval_service.py"
)
LOCAL_CLAIM_INDEXING_SERVICE = Path(
    "src/application/services/faq_workbench_local_claim_retrieval_surface_indexing_service.py"
)
LOCAL_CLAIM_EMBEDDING_ADAPTER = Path(
    "src/infrastructure/llm/workbench_local_claim_embedding_adapter.py"
)
WORKBENCH_REPOSITORY = Path("src/infrastructure/db/knowledge_workbench_repository.py")
PARALLEL_COMPOSITION = Path("src/interfaces/composition/faq_workbench_parallel_processing.py")
DRAIN_POLICY = Path("src/domain/project_plane/knowledge_workbench/parallel_drain_policy.py")
LOCAL_CLAIM_MIGRATION = Path(
    "migrations/080_create_workbench_local_claim_retrieval_surface.sql"
)


def test_existing_customer_runtime_uses_vector_hybrid_retrieval_surface() -> None:
    repository_source = KNOWLEDGE_REPOSITORY.read_text()
    rag_source = RAG_SERVICE.read_text()
    query_source = SEARCH_QUERIES.read_text()

    assert "embed_text(query)" in repository_source
    assert "RUNTIME_HYBRID_SEARCH_SQL" in repository_source
    assert "knowledge_retrieval_surface" in query_source
    assert "rs.embedding <=> $1::vector" in query_source
    assert "websearch_to_tsquery" in query_source
    assert "search_with_expansion" in rag_source
    assert "faq_workbench_fact" in RUNTIME_ENTRY_KIND_VALUES


def test_workbench_runtime_publication_projects_into_customer_retrieval_surface() -> None:
    service_source = RUNTIME_PUBLICATION_SERVICE.read_text()
    composition_source = PUBLISH_READY_COMPOSITION.read_text()
    repository_source = WORKBENCH_RETRIEVAL_SURFACE_REPOSITORY.read_text()
    embedding_adapter_source = WORKBENCH_RETRIEVAL_SURFACE_EMBEDDING_ADAPTER.read_text()

    assert "FaqWorkbenchRuntimePublicationService" in composition_source
    assert "FaqWorkbenchRetrievalSurfacePublicationService" in composition_source
    assert "WorkbenchRetrievalSurfaceRepository" in composition_source
    assert "WorkbenchRetrievalSurfaceEmbeddingAdapter" in composition_source

    assert "knowledge_retrieval_surface" in service_source
    assert "knowledge_retrieval_surface" in repository_source
    assert "knowledge_entries" in repository_source
    assert "faq_workbench_fact" in repository_source

    assert "embed_batch" in embedding_adapter_source


def test_workbench_runtime_entries_are_not_the_only_publication_target() -> None:
    service_source = RUNTIME_PUBLICATION_SERVICE.read_text()
    workbench_runtime_repository_source = WORKBENCH_RUNTIME_REPOSITORY.read_text()
    retrieval_surface_repository_source = (
        WORKBENCH_RETRIEVAL_SURFACE_REPOSITORY.read_text()
    )

    assert "knowledge_workbench_runtime_retrieval_entries" in (
        workbench_runtime_repository_source
    )
    assert "knowledge_retrieval_surface" in retrieval_surface_repository_source
    assert "knowledge_entries" in retrieval_surface_repository_source
    assert "faq_workbench_fact" in retrieval_surface_repository_source
    assert "FaqWorkbenchRetrievalSurfacePublicationService" in service_source


def test_local_claim_retrieval_has_embedding_surface_before_prompt_c() -> None:
    retrieval_source = LOCAL_CLAIM_RETRIEVAL_SERVICE.read_text()
    indexing_source = LOCAL_CLAIM_INDEXING_SERVICE.read_text()
    embedding_adapter_source = LOCAL_CLAIM_EMBEDDING_ADAPTER.read_text()
    repository_source = WORKBENCH_REPOSITORY.read_text()
    composition_source = PARALLEL_COMPOSITION.read_text()
    drain_policy_source = DRAIN_POLICY.read_text()
    migration_source = LOCAL_CLAIM_MIGRATION.read_text()

    assert "retrieval_surface_indexing_service" in retrieval_source
    assert "embedding_similarity" in indexing_source
    assert "embed_batch" in embedding_adapter_source
    assert "knowledge_workbench_local_claim_retrieval_entries" in repository_source
    assert "replace_local_claim_retrieval_entries" in repository_source
    assert "FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService" in composition_source
    assert "local_claim_retrieval_indexed_artifacts_total" in drain_policy_source
    assert "knowledge_workbench_local_claim_retrieval_entries" in migration_source
    assert "embedding vector(384)" in migration_source
