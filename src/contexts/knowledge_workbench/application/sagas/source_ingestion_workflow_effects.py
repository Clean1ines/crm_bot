from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionReadModelName,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)


class SourceIngestionWorkflowEffectType(StrEnum):
    WORKFLOW_COMMAND_COMPLETED = "WORKFLOW_COMMAND_COMPLETED"
    WORKFLOW_EVENT_APPENDED = "WORKFLOW_EVENT_APPENDED"
    NEXT_WORKFLOW_COMMAND_APPENDED = "NEXT_WORKFLOW_COMMAND_APPENDED"
    PROGRESS_READ_MODEL_AFFECTED = "PROGRESS_READ_MODEL_AFFECTED"


@dataclass(frozen=True, slots=True)
class SourceIngestionWorkflowEventEffect:
    event_type: KnowledgeExtractionCanonicalEventType
    workflow_run_id: str
    payload: Mapping[str, object]
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, KnowledgeExtractionCanonicalEventType):
            raise TypeError("event_type must be KnowledgeExtractionCanonicalEventType")
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        _require_timezone_aware(self.occurred_at, field_name="occurred_at")
        object.__setattr__(self, "payload", _freeze_payload(self.payload))


@dataclass(frozen=True, slots=True)
class SourceIngestionNextCommandEffect:
    command_type: KnowledgeExtractionCanonicalCommandType
    workflow_run_id: str
    idempotency_key: str
    payload: Mapping[str, object]
    run_after: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.command_type, KnowledgeExtractionCanonicalCommandType):
            raise TypeError(
                "command_type must be KnowledgeExtractionCanonicalCommandType"
            )
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        _require_non_empty_text(self.idempotency_key, field_name="idempotency_key")
        _require_timezone_aware(self.run_after, field_name="run_after")
        object.__setattr__(self, "payload", _freeze_payload(self.payload))


@dataclass(frozen=True, slots=True)
class SourceIngestionWorkflowCommandCompletionEffect:
    command_type: KnowledgeExtractionCanonicalCommandType
    workflow_run_id: str
    idempotency_key: str
    completed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.command_type, KnowledgeExtractionCanonicalCommandType):
            raise TypeError(
                "command_type must be KnowledgeExtractionCanonicalCommandType"
            )
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        _require_non_empty_text(self.idempotency_key, field_name="idempotency_key")
        _require_timezone_aware(self.completed_at, field_name="completed_at")


@dataclass(frozen=True, slots=True)
class SourceIngestionProgressReadModelEffect:
    read_model_name: KnowledgeExtractionReadModelName
    workflow_run_id: str
    payload: Mapping[str, object]
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.read_model_name, KnowledgeExtractionReadModelName):
            raise TypeError("read_model_name must be KnowledgeExtractionReadModelName")
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        _require_timezone_aware(self.occurred_at, field_name="occurred_at")
        object.__setattr__(self, "payload", _freeze_payload(self.payload))


@dataclass(frozen=True, slots=True)
class SourceIngestionWorkflowEffects:
    workflow_run_id: str
    source_document_ref: str
    source_unit_count: int
    event_effects: tuple[SourceIngestionWorkflowEventEffect, ...]
    next_command_effects: tuple[SourceIngestionNextCommandEffect, ...]
    command_completion_effect: SourceIngestionWorkflowCommandCompletionEffect
    progress_effects: tuple[SourceIngestionProgressReadModelEffect, ...]

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        _require_non_empty_text(
            self.source_document_ref,
            field_name="source_document_ref",
        )
        _require_positive_int(self.source_unit_count, field_name="source_unit_count")
        if not self.event_effects:
            raise ValueError("event_effects must be non-empty")
        if not self.next_command_effects:
            raise ValueError("next_command_effects must be non-empty")
        if not self.progress_effects:
            raise ValueError("progress_effects must be non-empty")


@dataclass(frozen=True, slots=True)
class BuildSourceIngestionWorkflowEffectsCommand:
    workflow_run_id: str
    project_id: str
    source_document_ref: str
    source_unit_count: int
    source_format: SourceFormat
    content_hash: str
    occurred_at: datetime
    source_units: tuple[SourceUnit, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        _require_non_empty_text(self.project_id, field_name="project_id")
        _require_non_empty_text(
            self.source_document_ref,
            field_name="source_document_ref",
        )
        _require_positive_int(self.source_unit_count, field_name="source_unit_count")
        if not isinstance(self.source_format, SourceFormat):
            raise TypeError("source_format must be SourceFormat")
        _require_non_empty_text(self.content_hash, field_name="content_hash")
        _require_timezone_aware(self.occurred_at, field_name="occurred_at")
        if not isinstance(self.source_units, tuple):
            raise TypeError("source_units must be tuple")
        if self.source_units and len(self.source_units) != self.source_unit_count:
            raise ValueError("source_units length must equal source_unit_count")


class BuildSourceIngestionWorkflowEffects:
    def execute(
        self,
        command: BuildSourceIngestionWorkflowEffectsCommand,
    ) -> SourceIngestionWorkflowEffects:
        base_payload = _base_payload(command)

        return SourceIngestionWorkflowEffects(
            workflow_run_id=command.workflow_run_id,
            source_document_ref=command.source_document_ref,
            source_unit_count=command.source_unit_count,
            event_effects=(
                SourceIngestionWorkflowEventEffect(
                    event_type=(
                        KnowledgeExtractionCanonicalEventType.SOURCE_DOCUMENT_PERSISTED
                    ),
                    workflow_run_id=command.workflow_run_id,
                    payload={
                        **base_payload,
                        "content_hash": command.content_hash,
                    },
                    occurred_at=command.occurred_at,
                ),
                SourceIngestionWorkflowEventEffect(
                    event_type=KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED,
                    workflow_run_id=command.workflow_run_id,
                    payload=base_payload,
                    occurred_at=command.occurred_at,
                ),
                *tuple(
                    _source_unit_created_effect(command, unit)
                    for unit in command.source_units
                ),
            ),
            next_command_effects=(
                SourceIngestionNextCommandEffect(
                    command_type=(
                        KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
                    ),
                    workflow_run_id=command.workflow_run_id,
                    idempotency_key=(
                        f"schedule-claim-builder-section-work:{command.workflow_run_id}"
                    ),
                    payload=base_payload,
                    run_after=command.occurred_at,
                ),
            ),
            command_completion_effect=SourceIngestionWorkflowCommandCompletionEffect(
                command_type=KnowledgeExtractionCanonicalCommandType.INGEST_SOURCE_DOCUMENT,
                workflow_run_id=command.workflow_run_id,
                idempotency_key=f"source-ingestion:{command.workflow_run_id}",
                completed_at=command.occurred_at,
            ),
            progress_effects=(
                SourceIngestionProgressReadModelEffect(
                    read_model_name=KnowledgeExtractionReadModelName.PROGRESS_SNAPSHOT,
                    workflow_run_id=command.workflow_run_id,
                    payload={
                        **base_payload,
                        "phase": "SOURCE_INGESTION",
                        "status": "COMPLETED",
                    },
                    occurred_at=command.occurred_at,
                ),
                SourceIngestionProgressReadModelEffect(
                    read_model_name=KnowledgeExtractionReadModelName.TIMELINE,
                    workflow_run_id=command.workflow_run_id,
                    payload={
                        **base_payload,
                        "timeline_event": "source_ingestion_completed",
                    },
                    occurred_at=command.occurred_at,
                ),
            ),
        )


def _base_payload(
    command: BuildSourceIngestionWorkflowEffectsCommand,
) -> dict[str, object]:
    return {
        "workflow_run_id": command.workflow_run_id,
        "project_id": command.project_id,
        "source_document_ref": command.source_document_ref,
        "source_unit_count": command.source_unit_count,
        "source_format": command.source_format.value,
    }


def _source_unit_created_effect(
    command: BuildSourceIngestionWorkflowEffectsCommand,
    unit: SourceUnit,
) -> SourceIngestionWorkflowEventEffect:
    payload: dict[str, object] = {
        "workflow_run_id": command.workflow_run_id,
        "project_id": command.project_id,
        "source_document_ref": command.source_document_ref,
        "source_unit_ref": unit.unit_ref.value,
        "source_unit_ordinal": unit.ordinal,
        "unit_kind": unit.unit_kind.value,
        "heading_path": unit.heading_path.parts,
    }
    if unit.lineage.parent_refs:
        payload["parent_source_unit_ref"] = unit.lineage.parent_refs[-1].value
    return SourceIngestionWorkflowEventEffect(
        event_type=KnowledgeExtractionCanonicalEventType.SOURCE_UNIT_CREATED,
        workflow_run_id=command.workflow_run_id,
        payload=payload,
        occurred_at=command.occurred_at,
    )


def _freeze_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(payload))


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_positive_int(value: int, *, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
