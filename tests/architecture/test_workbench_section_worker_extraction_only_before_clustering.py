from __future__ import annotations

from pathlib import Path

SECTION_WORKER = Path(
    "src/application/services/faq_workbench_section_work_item_processor_service.py"
)


FORBIDDEN_SECTION_WORKER_TOKENS = (
    # Prompt C / registry merge belongs after document-level local-claim
    # retrieval and clustering, not inside per-section extraction.
    "FaqWorkbenchRegistryMergeGenerationCommand",
    "FaqWorkbenchRegistryMergeGeneratorPort",
    "FaqWorkbenchRegistryMergeService",
    "PersistRegistryMergeNodeOutputCommand",
    "PersistRegistryMergeNodeOutputResult",
    "registry_merge_generator",
    "registry_merge_service",
    "generate_registry_updates",
    "persist_registry_merge_output",

    # Candidate sets for Prompt C must be produced by the document-level
    # retrieval/clustering stage, not by the section worker.
    "CandidateFactSet",
    "_candidate_fact_sets_for_claim_observations",
    "_candidate_facts_for_claim_observation",
    "candidate_fact_sets",

    # Registry application queue must receive canonicalized cluster outputs,
    # not raw per-section Prompt C outputs.
    "RegistryApplicationQueueItem",
    "create_registry_application_queue_item",
    "mark_section_batch_item_registry_application_queued",
    "registry_application_queue_item",
    "registry_application_queued_item",
)


REQUIRED_EXTRACTION_ONLY_TOKENS = (
    "claim_observations_runner",
    "process_leased_claim_observations",
    "mark_section_batch_item_claim_observations_persisted",
    "claim_observations_node_run_id",
    "CLAIM_OBSERVATIONS_PERSISTED",
)


def test_section_worker_stops_after_prompt_a_local_claim_artifact_persistence() -> None:
    source = SECTION_WORKER.read_text(encoding="utf-8")

    for token in REQUIRED_EXTRACTION_ONLY_TOKENS:
        assert token in source

    for token in FORBIDDEN_SECTION_WORKER_TOKENS:
        assert token not in source


def test_section_worker_does_not_load_claim_observations_for_prompt_c() -> None:
    source = SECTION_WORKER.read_text(encoding="utf-8")

    assert "_load_claim_observations_for_node_run" not in source
    assert "claim_inputs=claim_observations" not in source
    assert "registry_snapshot_payload=latest_registry_snapshot.entries_payload" not in source


def test_section_worker_result_contract_is_extraction_only() -> None:
    source = SECTION_WORKER.read_text(encoding="utf-8")

    assert "ProcessOneSectionWorkItemResult" in source
    assert "claim_observations_result" in source
    assert "claim_observations_persisted_item" in source

    assert "registry_merge_result" not in source
    assert "registry_application_queue_item" not in source
    assert "registry_application_queued_item" not in source
