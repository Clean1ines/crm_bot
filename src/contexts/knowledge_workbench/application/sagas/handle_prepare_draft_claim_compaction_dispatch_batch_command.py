from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, cast

from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
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
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    PrepareLlmDispatchBatchCommand,
    PrepareLlmDispatchBatchResult,
)


DRAFT_CLAIM_COMPACTION_WORK_KIND = WorkKind(
    "knowledge_workbench.draft_claim_compaction"
)
DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF = "openai/gpt-oss-120b"
DRAFT_CLAIM_COMPACTION_WORKER_REF = (
    "knowledge-workbench-draft-claim-compaction-dispatch"
)
DRAFT_CLAIM_COMPACTION_DEGRADED_MODEL_REF = "llama-3.3-70b-versatile"


class PrepareLlmDispatchBatchPort(Protocol):
    async def execute(self, command: PrepareLlmDispatchBatchCommand) -> object: ...


@dataclass(frozen=True, slots=True)
class HandlePrepareDraftClaimCompactionDispatchBatchCommand:
    workflow_command: WorkflowCommand

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")


@dataclass(frozen=True, slots=True)
class HandlePrepareDraftClaimCompactionDispatchBatchResult:
    workflow_run_id: str
    prepared_dispatch_count: int
    appended_event_count: int
    appended_next_command_count: int
    completed_command_id: WorkflowCommandId

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_negative_int(
            self.prepared_dispatch_count,
            "prepared_dispatch_count",
        )
        _require_non_negative_int(self.appended_event_count, "appended_event_count")
        _require_non_negative_int(
            self.appended_next_command_count,
            "appended_next_command_count",
        )
        if not isinstance(self.completed_command_id, WorkflowCommandId):
            raise TypeError("completed_command_id must be WorkflowCommandId")


class HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler:
    async def execute(
        self,
        command: HandlePrepareDraftClaimCompactionDispatchBatchCommand,
        *,
        prepare_llm_dispatch_batch: PrepareLlmDispatchBatchPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    ) -> HandlePrepareDraftClaimCompactionDispatchBatchResult:
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
        prepare_command = _prepare_llm_dispatch_batch_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            occurred_at=occurred_at,
        )

        prepared_dispatch_count = 0
        preflight_metadata = _empty_preflight_metadata(
            _active_model_ref_from_payload(workflow_command.payload)
        )
        typed_prepare_result: PrepareLlmDispatchBatchResult | None = None
        if prepare_command is not None:
            typed_prepare_result = _typed_prepare_result(
                await prepare_llm_dispatch_batch.execute(prepare_command)
            )
            started_attempts = typed_prepare_result.attempt_result.started_attempts
            prepared_dispatch_count = len(started_attempts)
            preflight_metadata = _preflight_metadata_from_prepare_result(
                typed_prepare_result,
            )

        appended_event_count = 0
        if (
            prepared_dispatch_count == 0
            and typed_prepare_result is not None
            and typed_prepare_result.capacity_retry_at is not None
        ):
            capacity_retry_at = typed_prepare_result.capacity_retry_at
            await workflow_unit_of_work.timeline.append_entry(
                _capacity_throttled_timeline_entry(
                    workflow_command=workflow_command,
                    workflow_run_id=workflow_run_id,
                    scheduled_work_item_count=_payload_positive_int(
                        workflow_command.payload,
                        "scheduled_work_item_count",
                    ),
                    capacity_retry_at=capacity_retry_at,
                    preflight_metadata=preflight_metadata,
                    occurred_at=occurred_at,
                )
            )
            await _save_progress_snapshot(
                workflow_unit_of_work=workflow_unit_of_work,
                workflow_run_id=workflow_run_id,
                prepared_dispatch_count=prepared_dispatch_count,
                preflight_metadata=preflight_metadata,
                occurred_at=occurred_at,
            )
            await workflow_unit_of_work.command_log.reschedule_pending_command(
                command_id=workflow_command.command_id,
                run_after=capacity_retry_at,
                rescheduled_at=occurred_at,
            )
            return HandlePrepareDraftClaimCompactionDispatchBatchResult(
                workflow_run_id=workflow_run_id,
                prepared_dispatch_count=prepared_dispatch_count,
                appended_event_count=appended_event_count,
                appended_next_command_count=0,
                completed_command_id=workflow_command.command_id,
            )

        if (
            prepared_dispatch_count == 0
            and typed_prepare_result is not None
            and _waiting_user_model_choice_required(
                payload=workflow_command.payload,
                prepare_result=typed_prepare_result,
            )
        ):
            waiting_event = _waiting_user_model_choice_event(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                scheduled_work_item_count=_payload_positive_int(
                    workflow_command.payload,
                    "scheduled_work_item_count",
                ),
                preflight_metadata=preflight_metadata,
                occurred_at=occurred_at,
            )
            await workflow_unit_of_work.outbox.append_event(waiting_event)
            appended_event_count = 1
            await workflow_unit_of_work.timeline.append_entry(
                _waiting_user_model_choice_timeline_entry(
                    workflow_command=workflow_command,
                    workflow_run_id=workflow_run_id,
                    scheduled_work_item_count=_payload_positive_int(
                        workflow_command.payload,
                        "scheduled_work_item_count",
                    ),
                    preflight_metadata=preflight_metadata,
                    occurred_at=occurred_at,
                )
            )
            await _save_progress_snapshot(
                workflow_unit_of_work=workflow_unit_of_work,
                workflow_run_id=workflow_run_id,
                prepared_dispatch_count=prepared_dispatch_count,
                preflight_metadata=preflight_metadata,
                occurred_at=occurred_at,
            )
            await workflow_unit_of_work.command_log.mark_command_completed(
                command_id=workflow_command.command_id,
                completed_at=occurred_at,
            )
            return HandlePrepareDraftClaimCompactionDispatchBatchResult(
                workflow_run_id=workflow_run_id,
                prepared_dispatch_count=prepared_dispatch_count,
                appended_event_count=appended_event_count,
                appended_next_command_count=0,
                completed_command_id=workflow_command.command_id,
            )

        if prepared_dispatch_count > 0:
            prepared_event = _dispatch_batch_prepared_event(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                started_attempts=started_attempts,
                preflight_metadata=preflight_metadata,
                occurred_at=occurred_at,
            )
            await workflow_unit_of_work.outbox.append_event(prepared_event)
            appended_event_count = 1
            await workflow_unit_of_work.timeline.append_entry(
                _timeline_entry(
                    workflow_command=workflow_command,
                    prepared_event=prepared_event,
                    started_attempts=started_attempts,
                    occurred_at=occurred_at,
                )
            )

        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_run_id=workflow_run_id,
            prepared_dispatch_count=prepared_dispatch_count,
            preflight_metadata=preflight_metadata,
            occurred_at=occurred_at,
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=occurred_at,
        )

        return HandlePrepareDraftClaimCompactionDispatchBatchResult(
            workflow_run_id=workflow_run_id,
            prepared_dispatch_count=prepared_dispatch_count,
            appended_event_count=appended_event_count,
            appended_next_command_count=0,
            completed_command_id=workflow_command.command_id,
        )


def _validate_workflow_command(workflow_command: WorkflowCommand) -> None:
    if (
        workflow_command.command_type
        != KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
    ):
        raise ValueError(
            "workflow_command command_type must be "
            "PrepareDraftClaimCompactionDispatchBatch"
        )
    if workflow_command.status is not WorkflowCommandStatus.PENDING:
        raise ValueError("workflow_command status must be PENDING")


def _active_model_ref_from_payload(payload: Mapping[str, object]) -> str:
    return _payload_text(
        payload,
        "active_model_ref",
        fallback=DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF,
    )


def _prepare_llm_dispatch_batch_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    occurred_at: datetime,
) -> PrepareLlmDispatchBatchCommand | None:
    requested_items = _payload_positive_int(
        workflow_command.payload,
        "scheduled_work_item_count",
    )
    llm_dispatch_preparation = workflow_command.payload.get("llm_dispatch_preparation")
    if isinstance(llm_dispatch_preparation, Mapping):
        account_capacities = llm_dispatch_preparation.get("account_capacities")
        if (
            isinstance(account_capacities, Sequence)
            and not isinstance(account_capacities, str)
            and not isinstance(account_capacities, bytes)
            and len(account_capacities) == 0
        ):
            return None

    return PrepareLlmDispatchBatchCommand(
        work_kind=DRAFT_CLAIM_COMPACTION_WORK_KIND,
        active_model_ref=_active_model_ref_from_payload(workflow_command.payload),
        requested_items=requested_items,
        worker=WorkerRef(
            _payload_text(
                workflow_command.payload,
                "worker_ref",
                fallback=DRAFT_CLAIM_COMPACTION_WORKER_REF,
            ),
        ),
        lease_token_prefix=f"draft-claim-compaction-dispatch:{workflow_run_id}",
        lease_expires_at=occurred_at + timedelta(seconds=90),
        now=occurred_at,
        started_at=occurred_at,
        dispatch_preparation_strategy=_dispatch_preparation_strategy(
            workflow_command.payload,
        ),
        use_local_active_model_tpm_budget=True,
    )


def _dispatch_preparation_strategy(
    payload: Mapping[str, object],
) -> str | None:
    for key in (
        "llm_dispatch_preparation_strategy",
        "draft_claim_compaction_next_model_strategy",
        "selected_retry_strategy",
    ):
        value = payload.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"workflow command payload {key} must be non-empty text")
        return value
    return None


def _dispatch_batch_prepared_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    started_attempts: Sequence[object],
    preflight_metadata: Mapping[str, object],
    occurred_at: datetime,
) -> WorkflowEvent:
    dispatch_attempt_ids = _dispatch_attempt_ids(started_attempts)
    work_item_ids = _work_item_ids(started_attempts)
    batch_key = _dispatch_batch_key(dispatch_attempt_ids)
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH_PREPARED.value}:"
            f"{batch_key}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH_PREPARED.value
        ),
        workflow_run_id=workflow_run_id,
        payload={
            "workflow_run_id": workflow_run_id,
            "work_kind": DRAFT_CLAIM_COMPACTION_WORK_KIND.value,
            "prepared_dispatch_count": len(dispatch_attempt_ids),
            "dispatch_attempt_ids": dispatch_attempt_ids,
            "work_item_ids": work_item_ids,
            **preflight_metadata,
        },
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.command_id.value,
    )


async def _save_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_run_id: str,
    prepared_dispatch_count: int,
    preflight_metadata: Mapping[str, object],
    occurred_at: datetime,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_run_id,
    )
    domain_counters = dict(existing.domain_counters) if existing is not None else {}
    domain_counters["draft_claim_compaction_prepared_dispatch_count"] = (
        prepared_dispatch_count
    )
    domain_counters[
        "draft_claim_compaction_input_size_preflight_larger_input_model_count"
    ] = (
        1
        if preflight_metadata.get("input_size_preflight_decision")
        == "USE_LARGER_INPUT_MODEL"
        else 0
    )

    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=workflow_run_id,
            current_phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value,
            workflow_status="RUNNING",
            total_work_items=existing.total_work_items if existing is not None else 0,
            scheduled_work_items=existing.scheduled_work_items
            if existing is not None
            else 0,
            running_work_items=max(
                existing.running_work_items if existing is not None else 0,
                prepared_dispatch_count,
            ),
            completed_work_items=existing.completed_work_items
            if existing is not None
            else 0,
            deferred_work_items=existing.deferred_work_items
            if existing is not None
            else 0,
            retryable_failed_work_items=existing.retryable_failed_work_items
            if existing is not None
            else 0,
            terminal_failed_work_items=existing.terminal_failed_work_items
            if existing is not None
            else 0,
            blocked_work_items=existing.blocked_work_items
            if existing is not None
            else 0,
            domain_counters=domain_counters,
            started_at=existing.started_at if existing is not None else occurred_at,
            updated_at=occurred_at,
            completed_at=existing.completed_at if existing is not None else None,
        )
    )


def _timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    prepared_event: WorkflowEvent,
    started_attempts: Sequence[object],
    occurred_at: datetime,
) -> WorkflowTimelineEntry:
    payload_summary = {
        "workflow_run_id": workflow_command.workflow_run_id,
        "work_kind": DRAFT_CLAIM_COMPACTION_WORK_KIND.value,
        "prepared_dispatch_count": len(started_attempts),
        "dispatch_attempt_ids": _dispatch_attempt_ids(started_attempts),
        "work_item_ids": _work_item_ids(started_attempts),
    }
    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{workflow_command.workflow_run_id}:"
            "DraftClaimCompactionDispatchBatchPrepared"
        ),
        workflow_run_id=workflow_command.workflow_run_id,
        event_type=prepared_event.event_type,
        phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value,
        severity=WorkflowTimelineSeverity.INFO,
        message="Draft claim compaction dispatch batch prepared",
        payload_summary=payload_summary,
        occurred_at=occurred_at,
        source_ref=DRAFT_CLAIM_COMPACTION_WORK_KIND.value,
    )


def _capacity_throttled_timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    scheduled_work_item_count: int,
    capacity_retry_at: datetime,
    preflight_metadata: Mapping[str, object],
    occurred_at: datetime,
) -> WorkflowTimelineEntry:
    payload_summary = {
        "workflow_run_id": workflow_run_id,
        "scheduled_work_item_count": scheduled_work_item_count,
        "capacity_retry_at": capacity_retry_at.isoformat(),
        "input_size_preflight_decision": preflight_metadata[
            "input_size_preflight_decision"
        ],
        "input_size_preflight_reason": preflight_metadata[
            "input_size_preflight_reason"
        ],
    }
    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{workflow_command.workflow_run_id}:"
            "PrepareDraftClaimCompactionDispatchBatch:capacity-throttled:"
            f"{occurred_at.isoformat()}"
        ),
        workflow_run_id=workflow_run_id,
        event_type=workflow_command.command_type,
        phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value,
        severity=WorkflowTimelineSeverity.INFO,
        message="Draft claim compaction dispatch capacity temporarily unavailable",
        payload_summary=payload_summary,
        occurred_at=occurred_at,
        source_ref=DRAFT_CLAIM_COMPACTION_WORK_KIND.value,
    )


def _waiting_user_model_choice_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    scheduled_work_item_count: int,
    preflight_metadata: Mapping[str, object],
    occurred_at: datetime,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_WAITING_USER_MODEL_CHOICE.value}:"
            f"{workflow_command.command_id.value}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_WAITING_USER_MODEL_CHOICE.value
        ),
        workflow_run_id=workflow_run_id,
        payload={
            "workflow_run_id": workflow_run_id,
            "reason": "primary_model_daily_capacity_exhausted",
            "scheduled_work_item_count": scheduled_work_item_count,
            "primary_model_id": DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF,
            "degraded_candidate_model_id": DRAFT_CLAIM_COMPACTION_DEGRADED_MODEL_REF,
            **preflight_metadata,
        },
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.command_id.value,
    )


def _waiting_user_model_choice_timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    scheduled_work_item_count: int,
    preflight_metadata: Mapping[str, object],
    occurred_at: datetime,
) -> WorkflowTimelineEntry:
    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{workflow_run_id}:"
            "PrepareDraftClaimCompactionDispatchBatch:waiting-user-model-choice:"
            f"{occurred_at.isoformat()}"
        ),
        workflow_run_id=workflow_run_id,
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_WAITING_USER_MODEL_CHOICE.value
        ),
        phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value,
        severity=WorkflowTimelineSeverity.INFO,
        message="Draft claim compaction waiting for user model choice",
        payload_summary={
            "workflow_run_id": workflow_run_id,
            "reason": "primary_model_daily_capacity_exhausted",
            "scheduled_work_item_count": scheduled_work_item_count,
            "primary_model_id": DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF,
            "degraded_candidate_model_id": DRAFT_CLAIM_COMPACTION_DEGRADED_MODEL_REF,
            "input_size_preflight_decision": preflight_metadata[
                "input_size_preflight_decision"
            ],
            "input_size_preflight_reason": preflight_metadata[
                "input_size_preflight_reason"
            ],
        },
        occurred_at=occurred_at,
        source_ref=workflow_command.command_type,
    )


def _waiting_user_model_choice_required(
    *,
    payload: Mapping[str, object],
    prepare_result: PrepareLlmDispatchBatchResult,
) -> bool:
    if prepare_result.capacity_retry_at is not None:
        return False

    if (
        _active_model_ref_from_payload(payload)
        != DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF
    ):
        return False

    account_capacities = _account_capacity_payloads(payload)
    active_account_capacities = tuple(
        account_capacity
        for account_capacity in account_capacities
        if account_capacity.get("model_ref") == DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF
    )
    if not active_account_capacities:
        return False

    return all(
        _daily_capacity_exhausted_payload(account_capacity)
        for account_capacity in active_account_capacities
    )


def _account_capacity_payloads(
    payload: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    llm_dispatch_preparation = payload.get("llm_dispatch_preparation")
    if not isinstance(llm_dispatch_preparation, Mapping):
        return ()

    value = llm_dispatch_preparation.get("account_capacities")
    if (
        not isinstance(value, Sequence)
        or isinstance(value, str)
        or isinstance(value, bytes)
    ):
        return ()

    account_capacities: list[Mapping[str, object]] = []
    for item in value:
        if isinstance(item, Mapping):
            account_capacities.append(item)
    return tuple(account_capacities)


def _daily_capacity_exhausted_payload(
    account_capacity: Mapping[str, object],
) -> bool:
    return (
        _mapping_non_negative_int(account_capacity, "remaining_daily_requests") == 0
        or _mapping_non_negative_int(account_capacity, "remaining_daily_tokens") == 0
    )


def _mapping_non_negative_int(
    payload: Mapping[str, object],
    key: str,
) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"account capacity payload must include integer {key}")
    if value < 0:
        raise ValueError(f"account capacity payload {key} must be >= 0")
    return value


def _empty_preflight_metadata(active_model_ref: str) -> dict[str, object]:
    return {
        "input_size_preflight_decision": "NO_CAPACITY_AVAILABLE",
        "input_size_preflight_reason": "no account capacity was provided",
        "input_size_preflight_active_model_ref": active_model_ref,
        "source_split_required": False,
        "affected_work_item_refs": (),
        "source_unit_refs": (),
    }


def _typed_prepare_result(
    prepare_result: object,
) -> PrepareLlmDispatchBatchResult:
    for attribute_name in (
        "attempt_result",
        "capacity_retry_at",
        "input_size_preflight_decision",
        "input_size_preflight_reason",
        "input_size_preflight_active_model_ref",
        "source_split_required",
        "affected_work_item_refs",
        "source_unit_refs",
    ):
        if not hasattr(prepare_result, attribute_name):
            raise TypeError(
                "prepare_result must provide PrepareLlmDispatchBatchResult contract"
            )
    return cast(PrepareLlmDispatchBatchResult, prepare_result)


def _preflight_metadata_from_prepare_result(
    prepare_result: PrepareLlmDispatchBatchResult,
) -> dict[str, object]:
    active_model_ref = _optional_result_text(
        prepare_result,
        "input_size_preflight_active_model_ref",
    )
    return {
        "input_size_preflight_decision": _result_text(
            prepare_result,
            "input_size_preflight_decision",
        ),
        "input_size_preflight_reason": _result_text(
            prepare_result,
            "input_size_preflight_reason",
        ),
        "input_size_preflight_active_model_ref": active_model_ref or "",
        "source_split_required": _result_bool(prepare_result, "source_split_required"),
        "affected_work_item_refs": _result_text_tuple(
            prepare_result,
            "affected_work_item_refs",
        ),
        "source_unit_refs": _result_text_tuple(prepare_result, "source_unit_refs"),
    }


def _started_attempts(prepare_result: object) -> tuple[object, ...]:
    attempt_result = getattr(prepare_result, "attempt_result", None)
    started_attempts = getattr(attempt_result, "started_attempts", None)
    if not isinstance(started_attempts, tuple):
        raise TypeError("prepare result attempt_result.started_attempts must be tuple")
    return started_attempts


def _dispatch_attempt_ids(started_attempts: Sequence[object]) -> tuple[str, ...]:
    return tuple(_attempt_text(attempt, "attempt_id") for attempt in started_attempts)


def _work_item_ids(started_attempts: Sequence[object]) -> tuple[str, ...]:
    return tuple(_attempt_text(attempt, "work_item_id") for attempt in started_attempts)


def _dispatch_batch_key(dispatch_attempt_ids: tuple[str, ...]) -> str:
    if not dispatch_attempt_ids:
        return "0:no-attempts"
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
    if not isinstance(value, int):
        raise ValueError(f"workflow command payload must include integer {key}")
    if value <= 0:
        raise ValueError(f"workflow command payload {key} must be > 0")
    return value


def _payload_non_negative_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"workflow command payload must include integer {key}")
    if value < 0:
        raise ValueError(f"workflow command payload {key} must be >= 0")
    return value


def _result_text(result: object, field_name: str) -> str:
    value = getattr(result, field_name, None)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"prepare result {field_name} must be non-empty text")
    return value


def _optional_result_text(result: object, field_name: str) -> str | None:
    value = getattr(result, field_name, None)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"prepare result {field_name} must be non-empty text")
    return value


def _result_bool(result: object, field_name: str) -> bool:
    value = getattr(result, field_name, None)
    if not isinstance(value, bool):
        raise ValueError(f"prepare result {field_name} must be bool")
    return value


def _result_text_tuple(result: object, field_name: str) -> tuple[str, ...]:
    value = getattr(result, field_name, ())
    if not isinstance(value, tuple):
        raise ValueError(f"prepare result {field_name} must be tuple")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"prepare result {field_name} must contain text")
    return value


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
