from pathlib import Path


def test_scheduling_service_materializes_scheduled_work_item_summary() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "schedule_draft_observation_extraction_work.py",
    ).read_text(encoding="utf-8")

    required_markers = (
        "DraftObservationScheduledWorkItemSummary",
        "scheduled_items",
        "payload_hash",
        "schedule_status",
        "work_item_schedule_payload_hash",
        "source_unit_ref",
        "source_unit_ordinal",
        "work_item_id",
        "idempotency_key",
        "to_checkpoint_payload",
    )
    forbidden_markers = (
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
        "execution_runtime.infrastructure",
        "Postgres",
        "asyncpg",
        "Groq",
        "qwen",
        "ClaimExtractionStageRuntime",
        "PostgresClaimExtractionWorkItemUnitOfWork",
    )

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source


def test_prompt_a_work_scheduled_checkpoint_persists_schedule_summary() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "advance_to_draft_observation_scheduling_phase.py",
    ).read_text(encoding="utf-8")

    required_markers = (
        "schedule_schema_version",
        "scheduled_items",
        "to_checkpoint_payload",
        "PROMPT_A_WORK_SCHEDULED",
    )
    forbidden_markers = (
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
        "execution_runtime.infrastructure",
        "Postgres",
        "asyncpg",
        "Groq",
        "qwen",
        "ClaimExtractionStageRuntime",
        "PostgresClaimExtractionWorkItemUnitOfWork",
    )

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source


def test_draft_observation_schedule_payload_contains_prompt_a_dispatch_seed() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "map_draft_observation_plans_to_execution_schedule.py",
    ).read_text(encoding="utf-8")

    required_markers = (
        "provider_messages",
        "prompt_a_provenance",
        "faq_claim_observations",
        "source_unit_text",
    )
    forbidden_markers = (
        "GroqDispatchExecutor",
        "GroqProviderAdapter",
        "LlmProviderPort",
        "ExecuteLlmTask",
        "ExecuteAndRecordLlmTask",
        "RecordWorkItemAttemptOutcome",
        "PersistArtifact",
        "ArtifactStored",
        "outbox",
        "capacity_runtime",
    )

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source
