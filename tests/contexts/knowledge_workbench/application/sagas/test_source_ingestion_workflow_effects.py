from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionReadModelName,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_workflow_effects import (
    BuildSourceIngestionWorkflowEffects,
    BuildSourceIngestionWorkflowEffectsCommand,
    SourceIngestionWorkflowEffectType,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _command(
    *,
    workflow_run_id: str = "knowledge-extraction:source-document:project-1:abc",
    source_unit_count: int = 3,
) -> BuildSourceIngestionWorkflowEffectsCommand:
    return BuildSourceIngestionWorkflowEffectsCommand(
        workflow_run_id=workflow_run_id,
        project_id="project-1",
        source_document_ref="source-document:project-1:abc",
        source_unit_count=source_unit_count,
        source_format=SourceFormat.MARKDOWN,
        content_hash="sha256:abc",
        occurred_at=_now(),
    )


def _effects():
    return BuildSourceIngestionWorkflowEffects().execute(_command())


def test_effect_type_vocabulary() -> None:
    assert tuple(
        effect_type.value for effect_type in SourceIngestionWorkflowEffectType
    ) == (
        "WORKFLOW_COMMAND_COMPLETED",
        "WORKFLOW_EVENT_APPENDED",
        "NEXT_WORKFLOW_COMMAND_APPENDED",
        "PROGRESS_READ_MODEL_AFFECTED",
    )


def test_builds_source_document_persisted_event_effect() -> None:
    effect = _effects().event_effects[0]

    assert (
        effect.event_type
        is KnowledgeExtractionCanonicalEventType.SOURCE_DOCUMENT_PERSISTED
    )
    assert (
        effect.workflow_run_id == "knowledge-extraction:source-document:project-1:abc"
    )
    assert effect.payload["source_document_ref"] == "source-document:project-1:abc"
    assert effect.payload["content_hash"] == "sha256:abc"
    assert effect.occurred_at == _now()


def test_builds_source_units_created_event_effect() -> None:
    effect = _effects().event_effects[1]

    assert (
        effect.event_type is KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED
    )
    assert effect.payload["source_unit_count"] == 3
    assert effect.payload["source_format"] == "markdown"


def test_builds_schedule_claim_builder_section_work_next_command() -> None:
    effect = _effects().next_command_effects[0]

    assert (
        effect.command_type
        is KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
    )
    assert effect.idempotency_key == (
        "schedule-claim-builder-section-work:"
        "knowledge-extraction:source-document:project-1:abc"
    )
    assert effect.payload["workflow_run_id"] == (
        "knowledge-extraction:source-document:project-1:abc"
    )
    assert effect.payload["source_unit_count"] == 3
    assert effect.run_after == _now()


def test_builds_ingest_source_document_command_completion() -> None:
    effect = _effects().command_completion_effect

    assert (
        effect.command_type
        is KnowledgeExtractionCanonicalCommandType.INGEST_SOURCE_DOCUMENT
    )
    assert effect.idempotency_key == (
        "source-ingestion:knowledge-extraction:source-document:project-1:abc"
    )
    assert effect.completed_at == _now()


def test_builds_progress_snapshot_and_timeline_effects() -> None:
    effects = _effects().progress_effects

    assert tuple(effect.read_model_name for effect in effects) == (
        KnowledgeExtractionReadModelName.PROGRESS_SNAPSHOT,
        KnowledgeExtractionReadModelName.TIMELINE,
    )
    assert effects[0].payload["phase"] == "SOURCE_INGESTION"
    assert effects[0].payload["status"] == "COMPLETED"
    assert effects[1].payload["timeline_event"] == "source_ingestion_completed"


def test_effects_reject_empty_workflow_run_id() -> None:
    with pytest.raises(ValueError, match="workflow_run_id must be non-empty"):
        _command(workflow_run_id=" ")


def test_effects_reject_zero_source_unit_count() -> None:
    with pytest.raises(ValueError, match="source_unit_count must be > 0"):
        _command(source_unit_count=0)
