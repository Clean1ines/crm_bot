from __future__ import annotations

from pathlib import Path


PUBLISH_READY = Path("src/application/workbench_commands/publish_ready.py")
REPOSITORY = Path("src/infrastructure/db/knowledge_workbench_repository.py")
COMPOSITION = Path("src/interfaces/composition/faq_workbench_publish_ready.py")


def _function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    next_method = source.find("\n    async def ", start + 1)
    next_sync_method = source.find("\n    def ", start + 1)
    next_class_or_module = source.find("\n\nclass ", start + 1)

    candidates = [
        index
        for index in (next_method, next_sync_method, next_class_or_module)
        if index != -1
    ]
    end = min(candidates) if candidates else len(source)
    return source[start:end]


def test_publish_ready_service_uses_current_final_snapshot_publication_contract() -> (
    None
):
    source = PUBLISH_READY.read_text(encoding="utf-8")

    assert "class FaqWorkbenchPublishReadyService" in source
    assert "async def publish_ready(" in source
    assert "publish_latest_reconciled_fact_registry_snapshot(" in source
    assert "PublishReadyRejectedError" in source
    assert "no reconciled fact registry snapshot is ready to publish" in source

    method_body = _function_body(source, "    async def publish_ready(")

    publish_index = method_body.index(
        "publish_latest_reconciled_fact_registry_snapshot("
    )
    reject_index = method_body.index("if snapshot_id is None:")
    result_index = method_body.index("return PublishReadyResult(")

    assert publish_index < reject_index < result_index
    assert "published_snapshot_id=snapshot_id" in method_body


def test_publish_ready_composition_wraps_snapshot_publish_and_runtime_projection_in_transaction() -> (
    None
):
    source = COMPOSITION.read_text(encoding="utf-8")

    assert "async with connection.transaction():" in source
    assert "FaqWorkbenchPublishReadyService" in source
    assert "await service.publish_ready(" in source

    assert "_load_published_fact_registry_payload" in source
    assert "FaqWorkbenchRuntimePublicationService" in source
    assert "WorkbenchRuntimeRetrievalRepository" in source
    assert "PublishFactRegistryRuntimeCommand" in source
    assert "publish_fact_registry_runtime_entries(" in source
    assert "published_runtime_entry_count" in source

    assert source.index("await service.publish_ready(") < source.index(
        "_load_published_fact_registry_payload"
    )
    assert source.index("_load_published_fact_registry_payload") < source.index(
        "publish_fact_registry_runtime_entries("
    )


def test_publish_ready_composition_loads_only_final_published_fact_registry_snapshot() -> (
    None
):
    source = COMPOSITION.read_text(encoding="utf-8")

    helper_body = _function_body(
        source,
        "async def _load_published_fact_registry_payload(",
    )

    assert "FROM knowledge_workbench_registry_snapshots" in helper_body
    assert "entries_payload" in helper_body
    assert "is_final_published IS TRUE" in helper_body
    assert "fact_registry" in helper_body
    assert "canonical_facts" in helper_body
    assert "fact_relations" in helper_body
    assert "published fact registry snapshot payload is unavailable" in helper_body


def test_repository_exposes_current_final_snapshot_publication_boundary() -> None:
    source = REPOSITORY.read_text(encoding="utf-8")

    assert "publish_latest_reconciled_fact_registry_snapshot" in source
    assert "knowledge_workbench_registry_snapshots" in source
    assert "is_final_published" in source
    assert "entries_payload" in source

    # Current retention boundary is intentionally collapsed into the repository
    # method used by PublishReadyService; do not require old split helper names.
    assert "mark_final_registry_retained_for_publication" not in source


def test_publish_ready_retention_cutover_does_not_restore_old_compiler() -> None:
    combined = (
        PUBLISH_READY.read_text(encoding="utf-8")
        + REPOSITORY.read_text(encoding="utf-8")
        + COMPOSITION.read_text(encoding="utf-8")
    )

    forbidden = (
        "KnowledgeService",
        "KnowledgeRepository(",
        "KnowledgeReadyAnswerPublicationService",
        "TASK_PUBLISH_KNOWLEDGE_READY_ANSWERS",
        "knowledge_publish_ready",
        "process_knowledge_upload",
        "knowledge_compilation",
        "AnswerCandidate",
        "CandidateCluster",
        "publish_ready_document(",
        "mark_final_registry_retained_for_publication(",
    )
    for marker in forbidden:
        assert marker not in combined
