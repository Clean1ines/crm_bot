from pathlib import Path


SECTION_PROCESSOR = Path(
    "src/application/services/faq_workbench_section_work_item_processor_service.py"
)
REGISTRY_WORKER = Path(
    "src/application/services/faq_workbench_registry_application_work_item_processor_service.py"
)
REGISTRY_APPLICATION_SERVICE = Path(
    "src/application/services/faq_workbench_registry_application_service.py"
)
REPOSITORY_PORT = Path("src/application/ports/knowledge_workbench.py")
QUEUE_DOMAIN = Path(
    "src/domain/project_plane/knowledge_workbench/registry_application_queue.py"
)


def test_parallel_section_worker_queues_canonicalization_instead_of_upserting_facts() -> None:
    source = SECTION_PROCESSOR.read_text(encoding="utf-8")

    assert "create_registry_application_queue_item" in source
    assert "claim_input_refs" in source
    assert "mark_section_batch_item_registry_application_queued" in source

    assert "upsert_canonical_facts(" not in source
    assert "create_registry_update_applications(" not in source
    assert "create_registry_snapshot(" not in source


def test_single_writer_registry_worker_is_the_canonical_graph_mutation_path() -> None:
    worker_source = REGISTRY_WORKER.read_text(encoding="utf-8")
    service_source = REGISTRY_APPLICATION_SERVICE.read_text(encoding="utf-8")

    assert "RegistryApplicationQueueItem" in worker_source
    assert "ProcessRegistryApplicationWorkItemCommand" in worker_source
    assert "ApplyFactRegistrySnapshotCommand" in worker_source
    assert "create_registry_snapshot" in service_source
    assert "canonical_facts" in service_source
    assert "fact_relations" in service_source


def test_registry_application_queue_carries_claim_observation_refs_not_surface_refs() -> None:
    source = QUEUE_DOMAIN.read_text(encoding="utf-8")

    assert "claim_input_refs" in source
    assert "ClaimObservationId" in source

    forbidden = (
        "surface_key",
        "canonical_question",
        "question_scope",
        "SectionFinding",
        "finding_id",
    )
    for token in forbidden:
        assert token not in source


def test_repository_port_keeps_extraction_and_canonical_mutation_separate() -> None:
    source = REPOSITORY_PORT.read_text(encoding="utf-8")

    assert "create_claim_observations" in source
    assert "create_registry_application_queue_item" in source
    assert "upsert_canonical_facts" in source

    create_claim_index = source.index("create_claim_observations")
    queue_index = source.index("create_registry_application_queue_item")
    upsert_index = source.index("upsert_canonical_facts")

    assert create_claim_index < upsert_index
    assert queue_index < upsert_index
