from pathlib import Path


COMPOSITION_PATH = Path("src/interfaces/composition/faq_workbench_publish_ready.py")
RUNTIME_PUBLICATION_SERVICE_PATH = Path(
    "src/application/services/faq_workbench_runtime_publication_service.py"
)


def test_publish_ready_composition_delegates_runtime_projection_to_runtime_publication_service() -> (
    None
):
    source = COMPOSITION_PATH.read_text()

    assert "FaqWorkbenchRuntimePublicationService" in source
    assert "published_runtime_entry_count" in source
    assert "published_retrieval_surface_entry_count" in source

    assert "PublishWorkbenchFactRetrievalSurfaceCommand" not in source
    assert "publish_workbench_fact_retrieval_surface" not in source


def test_runtime_publication_service_is_single_owner_of_workbench_runtime_projections() -> (
    None
):
    source = RUNTIME_PUBLICATION_SERVICE_PATH.read_text()

    assert "publish_fact_registry_runtime_entries" in source
    assert "publish_workbench_fact_retrieval_surface" in source
    assert "published_retrieval_surface_entry_count" in source
