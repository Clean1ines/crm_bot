from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, cast

from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.entities.workflow_progress_snapshot import (
    WorkflowProgressSnapshot,
)
from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
    WorkflowTimelineSeverity,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    PrepareLlmDispatchBatchCommand,
    PrepareLlmDispatchBatchResult,
)


class PrepareLlmDispatchBatchPort(Protocol):
    async def execute(self, command: PrepareLlmDispatchBatchCommand) -> object: ...


@dataclass(frozen=True, slots=True)
class HandlePrepareClaimBuilderDispatchBatchCommand:
    workflow_command: WorkflowCommand

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")


@dataclass(frozen=True, slots=True)
class HandlePrepareClaimBuilderDispatchBatchResult:
    workflow_run_id: str
    prepared_dispatch_count: int
    appended_event_count: int
    appended_next_command_count: int
    completed_command_id: WorkflowCommandId

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        for field_name, value in (
            ("prepared_dispatch_count", self.prepared_dispatch_count),
            ("appended_event_count", self.appended_event_count),
            ("appended_next_command_count", self.appended_next_command_count),
        ):
            _require_non_negative_int(value, field_name)
        if not isinstance(self.completed_command_id, WorkflowCommandId):
            raise TypeError("completed_command_id must be WorkflowCommandId")


class HandlePrepareClaimBuilderDispatchBatchCommandHandler:
    async def execute(
        self,
        command: HandlePrepareClaimBuilderDispatchBatchCommand,
        *,
        prepare_llm_dispatch_batch: PrepareLlmDispatchBatchPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    ) -> HandlePrepareClaimBuilderDispatchBatchResult:
        workflow_command = command.workflow_command
        _validate_workflow_command(workflow_command)

        workflow_run_id = _payload_text(
            workflow_command.payload,
            "workflow_run_id",
            fallback=workflow_command.workflow_run_id,
        )
        if workflow_run_id != workflow_command.workflow_run_id:
            raise ValueError("payload workflow_run_id must match workflow command")

        occurred_at = workflow_command.updated_at
        prepare_result = await prepare_llm_dispatch_batch.execute(
            _prepare_llm_dispatch_batch_command(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                occurred_at=occurred_at,
            ),
        )
        started_attempts = cast(
            PrepareLlmDispatchBatchResult,
            prepare_result,
        ).attempt_result.started_attempts
        prepared_dispatch_count = len(started_attempts)

        appended_event_count = 0
        appended_next_command_count = 0

        if prepared_dispatch_count > 0:
            prepared_event = _claim_builder_dispatch_batch_prepared_event(
                workflow_run_id=workflow_run_id,
                started_attempts=started_attempts,
                occurred_at=occurred_at,
            )
            await workflow_unit_of_work.outbox.append_event(prepared_event)
            appended_event_count = 1

            next_commands = _execute_claim_builder_section_commands(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                started_attempts=started_attempts,
                occurred_at=occurred_at,
            )
            for next_command in next_commands:
                await workflow_unit_of_work.command_log.append_pending_command(
                    next_command,
                )
            appended_next_command_count = len(next_commands)

            for timeline_entry in _timeline_entries(
                workflow_command=workflow_command,
                prepared_event=prepared_event,
                started_attempts=started_attempts,
                occurred_at=occurred_at,
            ):
                await workflow_unit_of_work.timeline.append_entry(timeline_entry)

        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_run_id=workflow_run_id,
            prepared_dispatch_count=prepared_dispatch_count,
            occurred_at=occurred_at,
        )

        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=occurred_at,
        )

        return HandlePrepareClaimBuilderDispatchBatchResult(
            workflow_run_id=workflow_run_id,
            prepared_dispatch_count=prepared_dispatch_count,
            appended_event_count=appended_event_count,
            appended_next_command_count=appended_next_command_count,
            completed_command_id=workflow_command.command_id,
        )


def _validate_workflow_command(workflow_command: WorkflowCommand) -> None:
    if (
        workflow_command.command_type
        != KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
    ):
        raise ValueError(
            "workflow_command command_type must be PrepareClaimBuilderDispatchBatch"
        )
    if workflow_command.status is not WorkflowCommandStatus.PENDING:
        raise ValueError("workflow_command status must be PENDING")


def _prepare_llm_dispatch_batch_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    occurred_at: datetime,
) -> PrepareLlmDispatchBatchCommand:
    dispatch_payload = _payload_mapping(
        workflow_command.payload,
        "llm_dispatch_preparation",
    )
    requested_items = _payload_positive_int(
        dispatch_payload,
        "requested_items",
        fallback=_payload_positive_int(
            workflow_command.payload,
            "scheduled_work_item_count",
        ),
    )

    return PrepareLlmDispatchBatchCommand(
        work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
        profile=_profile_from_payload(_payload_mapping(dispatch_payload, "profile")),
        account_capacities=_account_capacities_from_payload(dispatch_payload),
        active_model_ref=_payload_text(dispatch_payload, "active_model_ref"),
        requested_items=requested_items,
        worker=WorkerRef(
            _payload_text(
                dispatch_payload,
                "worker_ref",
                fallback="knowledge-workbench-claim-builder-dispatch",
            ),
        ),
        lease_token_prefix=_payload_text(
            dispatch_payload,
            "lease_token_prefix",
            fallback=f"claim-builder-dispatch:{workflow_run_id}",
        ),
        lease_expires_at=occurred_at
        + timedelta(
            seconds=_payload_positive_int(
                dispatch_payload,
                "lease_ttl_seconds",
                fallback=300,
            ),
        ),
        now=occurred_at,
        started_at=occurred_at,
        dispatch_preparation_strategy=_dispatch_preparation_strategy(
            workflow_command.payload,
        ),
    )


def _dispatch_preparation_strategy(
    payload: Mapping[str, object],
) -> str | None:
    for key in (
        "llm_dispatch_preparation_strategy",
        "claim_builder_next_model_strategy",
        "selected_retry_strategy",
    ):
        value = payload.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"workflow command payload {key} must be non-empty text")
        return value
    return None


def _profile_from_payload(payload: Mapping[str, object]) -> LlmTaskCapacityProfile:
    return LlmTaskCapacityProfile(
        profile_id=_payload_text(payload, "profile_id"),
        estimated_prompt_tokens=_payload_positive_int(
            payload,
            "estimated_prompt_tokens",
        ),
        estimated_completion_tokens=_payload_non_negative_int(
            payload,
            "estimated_completion_tokens",
        ),
        estimated_requests=_payload_positive_int(
            payload,
            "estimated_requests",
            fallback=1,
        ),
    )


def _account_capacities_from_payload(
    payload: Mapping[str, object],
) -> tuple[LlmProviderAccountCapacity, ...]:
    account_payloads = _payload_mapping_sequence(payload, "account_capacities")
    if not account_payloads:
        raise ValueError(
            "llm_dispatch_preparation account_capacities must be non-empty"
        )

    return tuple(
        LlmProviderAccountCapacity(
            provider=_payload_text(account_payload, "provider"),
            account_ref=_payload_text(account_payload, "account_ref"),
            model_ref=_payload_text(account_payload, "model_ref"),
            remaining_minute_requests=_payload_non_negative_int(
                account_payload,
                "remaining_minute_requests",
            ),
            remaining_minute_tokens=_payload_non_negative_int(
                account_payload,
                "remaining_minute_tokens",
            ),
            remaining_daily_requests=_payload_non_negative_int(
                account_payload,
                "remaining_daily_requests",
            ),
            remaining_daily_tokens=_payload_non_negative_int(
                account_payload,
                "remaining_daily_tokens",
            ),
        )
        for account_payload in account_payloads
    )


def _claim_builder_dispatch_batch_prepared_event(
    *,
    workflow_run_id: str,
    started_attempts: Sequence[object],
    occurred_at: datetime,
) -> WorkflowEvent:
    dispatch_attempt_ids = _dispatch_attempt_ids(started_attempts)
    work_item_ids = _work_item_ids(started_attempts)
    batch_key = _dispatch_batch_key(dispatch_attempt_ids)

    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_BATCH_PREPARED.value}:"
            f"{batch_key}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_BATCH_PREPARED.value
        ),
        workflow_run_id=workflow_run_id,
        payload={
            "workflow_run_id": workflow_run_id,
            "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
            "prepared_dispatch_count": len(dispatch_attempt_ids),
            "dispatch_attempt_ids": dispatch_attempt_ids,
            "work_item_ids": work_item_ids,
        },
        occurred_at=occurred_at,
    )


def _execute_claim_builder_section_commands(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    started_attempts: Sequence[object],
    occurred_at: datetime,
) -> tuple[WorkflowCommand, ...]:
    commands: list[WorkflowCommand] = []
    dispatch_preparation = workflow_command.payload.get("llm_dispatch_preparation")
    for attempt in started_attempts:
        dispatch_attempt_id = _attempt_text(attempt, "attempt_id")
        work_item_id = _attempt_text(attempt, "work_item_id")
        idempotency_key = (
            f"execute-claim-builder-section:{workflow_run_id}:{dispatch_attempt_id}"
        )
        command_payload: dict[str, object] = {
            "workflow_run_id": workflow_run_id,
            "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
            "dispatch_attempt_id": dispatch_attempt_id,
            "work_item_id": work_item_id,
        }
        if dispatch_preparation is not None:
            if not isinstance(dispatch_preparation, Mapping):
                raise ValueError("llm_dispatch_preparation must be mapping")
            command_payload["llm_dispatch_preparation"] = dict(dispatch_preparation)

        commands.append(
            WorkflowCommand(
                command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
                command_type=(
                    KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
                ),
                workflow_run_id=workflow_run_id,
                idempotency_key=WorkflowIdempotencyKey(idempotency_key),
                payload=command_payload,
                status=WorkflowCommandStatus.PENDING,
                run_after=occurred_at,
                created_at=occurred_at,
                updated_at=occurred_at,
            ),
        )
    return tuple(commands)


async def _save_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_run_id: str,
    prepared_dispatch_count: int,
    occurred_at: datetime,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_run_id,
    )
    existing_domain_counters = (
        dict(existing.domain_counters) if existing is not None else {}
    )
    existing_domain_counters["prepared_dispatch_count"] = prepared_dispatch_count

    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=workflow_run_id,
            current_phase="CLAIM_BUILDER_SECTION_EXTRACTION",
            workflow_status="RUNNING",
            total_work_items=existing.total_work_items if existing is not None else 0,
            scheduled_work_items=(
                existing.scheduled_work_items if existing is not None else 0
            ),
            running_work_items=max(
                existing.running_work_items if existing is not None else 0,
                prepared_dispatch_count,
            ),
            completed_work_items=(
                existing.completed_work_items if existing is not None else 0
            ),
            deferred_work_items=(
                existing.deferred_work_items if existing is not None else 0
            ),
            retryable_failed_work_items=(
                existing.retryable_failed_work_items if existing is not None else 0
            ),
            terminal_failed_work_items=(
                existing.terminal_failed_work_items if existing is not None else 0
            ),
            blocked_work_items=existing.blocked_work_items
            if existing is not None
            else 0,
            domain_counters=existing_domain_counters,
            started_at=existing.started_at if existing is not None else occurred_at,
            updated_at=occurred_at,
            completed_at=existing.completed_at if existing is not None else None,
        ),
    )


def _timeline_entries(
    *,
    workflow_command: WorkflowCommand,
    prepared_event: WorkflowEvent,
    started_attempts: Sequence[object],
    occurred_at: datetime,
) -> tuple[WorkflowTimelineEntry, ...]:
    payload_summary = {
        "workflow_run_id": workflow_command.workflow_run_id,
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "prepared_dispatch_count": len(started_attempts),
        "dispatch_attempt_ids": _dispatch_attempt_ids(started_attempts),
        "work_item_ids": _work_item_ids(started_attempts),
    }
    return (
        WorkflowTimelineEntry(
            timeline_entry_id=(
                f"workflow-timeline:{workflow_command.workflow_run_id}:"
                "ClaimBuilderDispatchBatchPrepared"
            ),
            workflow_run_id=workflow_command.workflow_run_id,
            event_type=prepared_event.event_type,
            phase="CLAIM_BUILDER_SECTION_EXTRACTION",
            severity=WorkflowTimelineSeverity.INFO,
            message="Claim builder dispatch batch prepared",
            payload_summary=payload_summary,
            occurred_at=occurred_at,
            source_ref=CLAIM_BUILDER_SECTION_WORK_KIND.value,
        ),
        WorkflowTimelineEntry(
            timeline_entry_id=(
                f"workflow-timeline:{workflow_command.workflow_run_id}:"
                "ExecuteClaimBuilderSection:requested"
            ),
            workflow_run_id=workflow_command.workflow_run_id,
            event_type=(
                KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
            ),
            phase="CLAIM_BUILDER_SECTION_EXTRACTION",
            severity=WorkflowTimelineSeverity.INFO,
            message="Execute claim builder section requested",
            payload_summary=payload_summary,
            occurred_at=occurred_at,
            source_ref=CLAIM_BUILDER_SECTION_WORK_KIND.value,
        ),
    )


def _dispatch_attempt_ids(started_attempts: Sequence[object]) -> tuple[str, ...]:
    return tuple(_attempt_text(attempt, "attempt_id") for attempt in started_attempts)


def _work_item_ids(started_attempts: Sequence[object]) -> tuple[str, ...]:
    return tuple(_attempt_text(attempt, "work_item_id") for attempt in started_attempts)


def _dispatch_batch_key(dispatch_attempt_ids: tuple[str, ...]) -> str:
    if not dispatch_attempt_ids:
        raise ValueError("dispatch_attempt_ids must be non-empty")
    return f"{len(dispatch_attempt_ids)}:{dispatch_attempt_ids[0]}"


def _attempt_text(attempt: object, field_name: str) -> str:
    value = getattr(attempt, field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"started attempt {field_name} must be non-empty")
    return value


def _payload_mapping(
    payload: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"workflow command payload must include mapping {key}")
    return value


def _payload_mapping_sequence(
    payload: Mapping[str, object],
    key: str,
) -> tuple[Mapping[str, object], ...]:
    value = payload.get(key)
    if (
        not isinstance(value, Sequence)
        or isinstance(value, str)
        or isinstance(value, bytes)
    ):
        raise ValueError(f"workflow command payload must include sequence {key}")

    items: list[Mapping[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError(f"workflow command payload {key} must contain mappings")
        items.append(item)
    return tuple(items)


def _payload_text(
    payload: Mapping[str, object],
    key: str,
    *,
    fallback: str | None = None,
) -> str:
    value = payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow command payload must include {key}")
    return value


def _payload_positive_int(
    payload: Mapping[str, object],
    key: str,
    *,
    fallback: int | None = None,
) -> int:
    value = payload.get(key, fallback)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"workflow command payload must include positive int {key}")
    return value


def _payload_non_negative_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"workflow command payload must include non-negative int {key}"
        )
    return value


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
