from pathlib import Path


COMPOSITION = Path("src/interfaces/composition/faq_workbench_publish_ready.py")


def test_publish_ready_composition_wires_runtime_publication_after_snapshot_publish() -> None:
    source = COMPOSITION.read_text(encoding="utf-8")

    assert "FaqWorkbenchPublishReadyService" in source
    assert "FaqWorkbenchRuntimePublicationService" in source
    assert "PublishFactRegistryRuntimeCommand" in source
    assert "WorkbenchRuntimeRetrievalRepository" in source

    assert "_load_published_fact_registry_payload" in source
    assert "fact_registry_payload=fact_registry_payload" in source
    assert "published_runtime_entry_count" in source

    assert source.index("await service.publish_ready(") < source.index(
        "_load_published_fact_registry_payload"
    )
    assert source.index("_load_published_fact_registry_payload") < source.index(
        "publish_fact_registry_runtime_entries"
    )


def test_publish_ready_composition_loads_only_final_published_snapshot_payload() -> None:
    source = COMPOSITION.read_text(encoding="utf-8")

    assert "FROM knowledge_workbench_registry_snapshots" in source
    assert "entries_payload" in source
    assert "is_final_published IS TRUE" in source
    assert "fact_registry" in source
    assert "canonical_facts" in source
    assert "fact_relations" in source
