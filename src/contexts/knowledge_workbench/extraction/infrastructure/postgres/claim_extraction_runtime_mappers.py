from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import TypeAlias
from uuid import uuid4

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import (
    WorkItemAttempt,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask


JsonScalar: TypeAlias = None | bool | int | float | str
JsonObject: TypeAlias = dict[str, "JsonCompatible"]
JsonArray: TypeAlias = list["JsonCompatible"]
JsonCompatible: TypeAlias = JsonScalar | JsonObject | JsonArray

RowValue: TypeAlias = JsonCompatible | datetime
SqlArgs: TypeAlias = tuple[RowValue, ...]


@dataclass(frozen=True, slots=True)
class WorkItemRow:
    work_item_id: str
    work_kind: str
    status: str
    attempt_count: int
    leased_by: str | None
    lease_token: str | None
    lease_expires_at: datetime | None
    next_attempt_at: datetime | None
    last_error_kind: str | None
    created_at: datetime
    updated_at: datetime

    def args(self) -> SqlArgs:
        return (
            self.work_item_id,
            self.work_kind,
            self.status,
            self.attempt_count,
            self.leased_by,
            self.lease_token,
            self.lease_expires_at,
            self.next_attempt_at,
            self.last_error_kind,
            self.created_at,
            self.updated_at,
        )


@dataclass(frozen=True, slots=True)
class WorkItemAttemptRow:
    attempt_id: str
    work_item_id: str
    attempt_number: int
    started_at: datetime
    finished_at: datetime | None
    outcome_status: str | None
    error_kind: str | None
    created_at: datetime

    def args(self) -> SqlArgs:
        return (
            self.attempt_id,
            self.work_item_id,
            self.attempt_number,
            self.started_at,
            self.finished_at,
            self.outcome_status,
            self.error_kind,
            self.created_at,
        )


@dataclass(frozen=True, slots=True)
class LlmTaskRow:
    task_id: str
    prompt_id: str
    prompt_version: str
    input_ref: str
    output_contract_ref: str
    status: str
    attempt_count: int
    selected_provider_id: str | None
    selected_model_id: str | None
    selected_account_ref: str | None
    wait_until: datetime | None
    last_error_kind: str | None
    created_at: datetime
    updated_at: datetime

    def args(self) -> SqlArgs:
        return (
            self.task_id,
            self.prompt_id,
            self.prompt_version,
            self.input_ref,
            self.output_contract_ref,
            self.status,
            self.attempt_count,
            self.selected_provider_id,
            self.selected_model_id,
            self.selected_account_ref,
            self.wait_until,
            self.last_error_kind,
            self.created_at,
            self.updated_at,
        )


@dataclass(frozen=True, slots=True)
class LlmAttemptRow:
    attempt_id: str
    task_id: str
    attempt_number: int
    provider_id: str
    model_id: str
    account_ref: str
    started_at: datetime
    finished_at: datetime | None
    input_tokens: int | None
    output_tokens: int | None
    error_kind: str | None
    created_at: datetime

    def args(self) -> SqlArgs:
        return (
            self.attempt_id,
            self.task_id,
            self.attempt_number,
            self.provider_id,
            self.model_id,
            self.account_ref,
            self.started_at,
            self.finished_at,
            self.input_tokens,
            self.output_tokens,
            self.error_kind,
            self.created_at,
        )


@dataclass(frozen=True, slots=True)
class PipelineArtifactRow:
    artifact_ref: str
    artifact_kind: str
    status: str
    visibility: str
    retention_policy_kind: str
    payload: JsonObject
    created_at: datetime
    updated_at: datetime

    def args(self) -> SqlArgs:
        return (
            self.artifact_ref,
            self.artifact_kind,
            self.status,
            self.visibility,
            self.retention_policy_kind,
            self.payload,
            self.created_at,
            self.updated_at,
        )


@dataclass(frozen=True, slots=True)
class PipelineArtifactLineageRow:
    artifact_ref: str
    parent_artifact_ref: str

    def args(self) -> SqlArgs:
        return (self.artifact_ref, self.parent_artifact_ref)


@dataclass(frozen=True, slots=True)
class OutboxEventRow:
    event_id: str
    event_type: str
    aggregate_ref: str | None
    payload: JsonObject
    occurred_at: datetime
    created_at: datetime

    def args(self) -> SqlArgs:
        return (
            self.event_id,
            self.event_type,
            self.aggregate_ref,
            self.payload,
            self.occurred_at,
            self.created_at,
        )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def value_object_to_str(value: object) -> str:
    raw = getattr(value, "value", value)
    if not isinstance(raw, str):
        return str(raw)
    return raw


def optional_value_object_to_str(value: object | None) -> str | None:
    if value is None:
        return None
    return value_object_to_str(value)


def enum_to_db(value: object) -> str:
    raw = getattr(value, "value", value)
    if not isinstance(raw, str):
        return str(raw)
    return raw


def optional_enum_to_db(value: object | None) -> str | None:
    if value is None:
        return None
    return enum_to_db(value)


def json_compatible(value: object) -> JsonCompatible:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, MappingProxyType):
        return {str(key): json_compatible(item) for key, item in value.items()}

    if isinstance(value, Mapping):
        return {str(key): json_compatible(item) for key, item in value.items()}

    if isinstance(value, tuple):
        return [json_compatible(item) for item in value]

    if isinstance(value, list):
        return [json_compatible(item) for item in value]

    if isinstance(value, datetime):
        return value.isoformat()

    raw_value = getattr(value, "value", None)
    if raw_value is not None:
        return json_compatible(raw_value)

    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def json_object(value: Mapping[str, object]) -> JsonObject:
    converted = json_compatible(value)
    if not isinstance(converted, dict):
        raise TypeError("Expected JSON object")
    return converted


def map_work_item_to_row(
    item: WorkItem,
    *,
    now: datetime | None = None,
) -> WorkItemRow:
    timestamp = now or utc_now()
    return WorkItemRow(
        work_item_id=item.work_item_id,
        work_kind=value_object_to_str(item.work_kind),
        status=enum_to_db(item.status),
        attempt_count=item.attempt_count,
        leased_by=optional_value_object_to_str(item.leased_by),
        lease_token=optional_value_object_to_str(item.lease_token),
        lease_expires_at=item.lease_expires_at,
        next_attempt_at=item.next_attempt_at.value if item.next_attempt_at else None,
        last_error_kind=item.last_error_kind,
        created_at=timestamp,
        updated_at=timestamp,
    )


def map_work_item_attempt_to_row(
    attempt: WorkItemAttempt,
    *,
    now: datetime | None = None,
) -> WorkItemAttemptRow:
    return WorkItemAttemptRow(
        attempt_id=attempt.attempt_id,
        work_item_id=attempt.work_item_id,
        attempt_number=attempt.attempt_number,
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
        outcome_status=attempt.outcome_status,
        error_kind=attempt.error_kind,
        created_at=now or utc_now(),
    )


def map_llm_task_to_row(
    task: LlmTask,
    *,
    now: datetime | None = None,
) -> LlmTaskRow:
    timestamp = now or utc_now()
    route = task.selected_route
    return LlmTaskRow(
        task_id=task.task_id,
        prompt_id=task.prompt_id,
        prompt_version=value_object_to_str(task.prompt_version),
        input_ref=value_object_to_str(task.input_ref),
        output_contract_ref=value_object_to_str(task.output_contract_ref),
        status=enum_to_db(task.status),
        attempt_count=task.attempt_count,
        selected_provider_id=value_object_to_str(route.provider_id) if route else None,
        selected_model_id=value_object_to_str(route.model_id) if route else None,
        selected_account_ref=value_object_to_str(route.account_ref) if route else None,
        wait_until=task.wait_until,
        last_error_kind=optional_enum_to_db(task.last_error_kind),
        created_at=timestamp,
        updated_at=timestamp,
    )


def map_llm_attempt_to_row(
    attempt: LlmAttempt,
    *,
    now: datetime | None = None,
) -> LlmAttemptRow:
    return LlmAttemptRow(
        attempt_id=attempt.attempt_id,
        task_id=attempt.task_id,
        attempt_number=attempt.attempt_number,
        provider_id=value_object_to_str(attempt.route.provider_id),
        model_id=value_object_to_str(attempt.route.model_id),
        account_ref=value_object_to_str(attempt.route.account_ref),
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
        input_tokens=attempt.usage.input_tokens if attempt.usage else None,
        output_tokens=attempt.usage.output_tokens if attempt.usage else None,
        error_kind=optional_enum_to_db(attempt.error_kind),
        created_at=now or utc_now(),
    )


def map_pipeline_artifact_to_row(artifact: PipelineArtifact) -> PipelineArtifactRow:
    payload = json_object(artifact.payload.value)
    return PipelineArtifactRow(
        artifact_ref=value_object_to_str(artifact.artifact_ref),
        artifact_kind=value_object_to_str(artifact.artifact_kind),
        status=enum_to_db(artifact.status),
        visibility=enum_to_db(artifact.visibility),
        retention_policy_kind=enum_to_db(artifact.retention_policy.kind),
        payload=payload,
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
    )


def map_pipeline_artifact_lineage_to_rows(
    artifact: PipelineArtifact,
) -> tuple[PipelineArtifactLineageRow, ...]:
    artifact_ref = value_object_to_str(artifact.artifact_ref)
    parent_refs: Sequence[ArtifactRef] = artifact.lineage.parent_refs
    return tuple(
        PipelineArtifactLineageRow(
            artifact_ref=artifact_ref,
            parent_artifact_ref=value_object_to_str(parent_ref),
        )
        for parent_ref in parent_refs
    )


def event_payload(event: object) -> JsonObject:
    payload: dict[str, object] = {}

    for attr in (
        "work_item_id",
        "task_id",
        "artifact_ref",
        "status",
        "error_kind",
        "wait_until",
        "occurred_at",
        "reason",
        "target_status",
    ):
        if hasattr(event, attr):
            payload[attr] = getattr(event, attr)

    return json_object(payload)


def event_aggregate_ref(event: object) -> str | None:
    for attr in ("work_item_id", "task_id", "artifact_ref"):
        if hasattr(event, attr):
            return value_object_to_str(getattr(event, attr))
    return None


def event_occurred_at(event: object) -> datetime:
    occurred_at = getattr(event, "occurred_at", None)
    if isinstance(occurred_at, datetime):
        return occurred_at
    return utc_now()


def map_domain_event_to_outbox_row(
    event: object,
    *,
    now: datetime | None = None,
) -> OutboxEventRow:
    event_id = getattr(event, "event_id", None)
    if not isinstance(event_id, str) or not event_id.strip():
        event_id = str(uuid4())

    return OutboxEventRow(
        event_id=event_id,
        event_type=event.__class__.__name__,
        aggregate_ref=event_aggregate_ref(event),
        payload=event_payload(event),
        occurred_at=event_occurred_at(event),
        created_at=now or utc_now(),
    )
