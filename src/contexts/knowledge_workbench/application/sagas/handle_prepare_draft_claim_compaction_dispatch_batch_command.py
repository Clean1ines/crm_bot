from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol, cast

from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.knowledge_workbench.application.sagas.capacity_window_workflow_events import (
    DRAFT_CLAIM_COMPACTION_CANONICAL_PHASE,
    DRAFT_CLAIM_COMPACTION_PREPARE_OPERATION_KEY,
    capacity_window_exhausted_event,
    capacity_window_leased_work_item_event,
    capacity_window_scheduled_wakeup_event,
    compaction_context_from_schedule_payload,
)
from src.interfaces.composition.lease_llm_admitted_work_items import (
    LlmAdmittedLeasedWorkItem,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)
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
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
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

        occurred_at = _execution_occurred_at(workflow_command)
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
        appended_next_command_count = 0
        if (
            prepared_dispatch_count == 0
            and typed_prepare_result is not None
            and typed_prepare_result.capacity_retry_at is not None
        ):
            capacity_retry_at = _future_capacity_retry_at(
                typed_prepare_result.capacity_retry_at,
                occurred_at=occurred_at,
            )
            capacity_window_exhaustion = typed_prepare_result.capacity_window_exhaustion
            if capacity_window_exhaustion is not None:
                exhausted_event = capacity_window_exhausted_event(
                    workflow_run_id=workflow_run_id,
                    exhaustion=capacity_window_exhaustion,
                    operation_key=DRAFT_CLAIM_COMPACTION_PREPARE_OPERATION_KEY,
                    canonical_phase=DRAFT_CLAIM_COMPACTION_CANONICAL_PHASE,
                    occurred_at=occurred_at,
                    causation_command_id=workflow_command.command_id,
                    correlation_id=(
                        f"{capacity_window_exhaustion.provider}:"
                        f"{capacity_window_exhaustion.account_ref}:"
                        f"{capacity_window_exhaustion.model_ref}:"
                        f"{capacity_retry_at.isoformat()}"
                    ),
                )
                await workflow_unit_of_work.outbox.append_event(exhausted_event)
                appended_event_count += 1

                scheduled_wakeup_event = capacity_window_scheduled_wakeup_event(
                    workflow_run_id=workflow_run_id,
                    provider=capacity_window_exhaustion.provider,
                    account_ref=capacity_window_exhaustion.account_ref,
                    model_ref=capacity_window_exhaustion.model_ref,
                    run_after=capacity_retry_at,
                    reset_at=capacity_window_exhaustion.reset_at,
                    wakeup_command_id=workflow_command.command_id,
                    prepare_command_type=workflow_command.command_type,
                    wakeup_reason="prepare_capacity_retry_at",
                    operation_key=DRAFT_CLAIM_COMPACTION_PREPARE_OPERATION_KEY,
                    canonical_phase=DRAFT_CLAIM_COMPACTION_CANONICAL_PHASE,
                    occurred_at=occurred_at,
                    causation_command_id=workflow_command.command_id,
                )
                await workflow_unit_of_work.outbox.append_event(scheduled_wakeup_event)
                appended_event_count += 1

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
                appended_next_command_count=appended_next_command_count,
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
            if typed_prepare_result is None or prepare_command is None:
                raise RuntimeError(
                    "prepared compaction dispatch requires prepare result"
                )
            prepared_event = _dispatch_batch_prepared_event(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                started_attempts=started_attempts,
                preflight_metadata=preflight_metadata,
                occurred_at=occurred_at,
            )
            await workflow_unit_of_work.outbox.append_event(prepared_event)
            appended_event_count = 1

            next_commands = _execute_draft_claim_compaction_commands(
                workflow_run_id=workflow_run_id,
                started_attempts=started_attempts,
                occurred_at=occurred_at,
            )
            for next_command in next_commands:
                await workflow_unit_of_work.command_log.append_pending_command(
                    next_command
                )
            appended_next_command_count = len(next_commands)

            leased_items = typed_prepare_result.lease_result.leased
            for leased_item, started_attempt in zip(
                leased_items,
                started_attempts,
                strict=True,
            ):
                await workflow_unit_of_work.outbox.append_event(
                    _capacity_window_leased_work_item_event(
                        workflow_command=workflow_command,
                        workflow_run_id=workflow_run_id,
                        leased_item=leased_item,
                        started_attempt=started_attempt,
                        lease_expires_at=prepare_command.lease_expires_at,
                        occurred_at=occurred_at,
                    )
                )
                appended_event_count += 1

            for timeline_entry in _timeline_entries(
                workflow_command=workflow_command,
                prepared_event=prepared_event,
                started_attempts=started_attempts,
                next_commands=next_commands,
                occurred_at=occurred_at,
            ):
                await workflow_unit_of_work.timeline.append_entry(timeline_entry)

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
            appended_next_command_count=appended_next_command_count,
            completed_command_id=workflow_command.command_id,
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _execution_occurred_at(workflow_command: WorkflowCommand) -> datetime:
    execution_now = _utc_now()
    if workflow_command.updated_at > execution_now:
        return workflow_command.updated_at
    return execution_now


def _future_capacity_retry_at(
    capacity_retry_at: datetime | None,
    *,
    occurred_at: datetime,
) -> datetime:
    if capacity_retry_at is not None and capacity_retry_at > occurred_at:
        return capacity_retry_at
    return occurred_at + timedelta(seconds=60)


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


def _provider_account_refs_from_payload(
    payload: Mapping[str, object],
) -> tuple[str, ...]:
    value = payload.get("capacity_window_provider_account_refs")
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise ValueError(
            "workflow command payload capacity_window_provider_account_refs "
            "must be sequence"
        )
    refs: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                "workflow command payload capacity_window_provider_account_refs "
                "must contain non-empty strings"
            )
        refs.append(item)
    return tuple(refs)


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
        profile=_profile_from_payload(workflow_command.payload),
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
        allow_automatic_fallbacks=False,
        provider_account_refs=_provider_account_refs_from_payload(
            workflow_command.payload,
        ),
    )


def _profile_from_payload(
    payload: Mapping[str, object],
) -> LlmTaskCapacityProfile | None:
    llm_dispatch_preparation = payload.get("llm_dispatch_preparation")
    if not isinstance(llm_dispatch_preparation, Mapping):
        return None

    profile_payload = llm_dispatch_preparation.get("profile")
    if not isinstance(profile_payload, Mapping):
        return None

    return LlmTaskCapacityProfile(
        profile_id=_payload_text(profile_payload, "profile_id"),
        estimated_prompt_tokens=(
            _compaction_profile_positive_int_with_legacy_fallback(
                profile_payload,
                key="estimated_input_tokens",
                legacy_key="estimated_prompt_tokens",
            )
        ),
        estimated_completion_tokens=(
            _compaction_profile_non_negative_int_with_legacy_fallback(
                profile_payload,
                key="estimated_output_tokens",
                legacy_key="estimated_completion_tokens",
            )
        ),
        estimated_requests=_payload_positive_int(
            profile_payload,
            "estimated_requests",
            fallback=1,
        ),
    )


def _compaction_profile_positive_int_with_legacy_fallback(
    payload: Mapping[str, object],
    *,
    key: str,
    legacy_key: str,
) -> int:
    if key in payload:
        return _payload_positive_int(payload, key)
    return _payload_positive_int(payload, legacy_key)


def _compaction_profile_non_negative_int_with_legacy_fallback(
    payload: Mapping[str, object],
    *,
    key: str,
    legacy_key: str,
) -> int:
    if key in payload:
        return _payload_non_negative_int(payload, key)
    return _payload_non_negative_int(payload, legacy_key)


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
            "dispatch_contexts": _dispatch_contexts(started_attempts),
            **preflight_metadata,
        },
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.command_id.value,
    )


def _dispatch_contexts(started_attempts: Sequence[object]) -> list[dict[str, object]]:
    contexts: list[dict[str, object]] = []
    for attempt in started_attempts:
        dispatch_attempt_id = _attempt_text(attempt, "attempt_id")
        work_item_id = _attempt_text(attempt, "work_item_id")
        schedule_payload = _attempt_schedule_payload(attempt)
        context: dict[str, object] = {
            "dispatch_attempt_id": dispatch_attempt_id,
            "work_item_id": work_item_id,
            "group_ref": _mapping_text(schedule_payload, "group_ref"),
            "batch_ref": _mapping_text(schedule_payload, "batch_ref"),
            "round_index": _mapping_int(schedule_payload, "round_index", fallback=0),
            "expected_output_kind": _mapping_text(
                schedule_payload,
                "expected_output_kind",
                fallback="compacted_claims",
            ),
        }

        for source_key, target_key in (
            ("source_node_refs", "input_node_refs"),
            ("compared_node_refs", "input_node_refs"),
            ("node_refs", "input_node_refs"),
            ("source_claim_refs", "input_claim_refs"),
        ):
            if source_key in schedule_payload and target_key not in context:
                context[target_key] = _mapping_text_list(schedule_payload, source_key)

        left_node_ref = schedule_payload.get("left_node_ref")
        right_node_ref = schedule_payload.get("right_node_ref")
        if "input_node_refs" not in context and isinstance(left_node_ref, str):
            input_node_refs = [left_node_ref]
            if isinstance(right_node_ref, str):
                input_node_refs.append(right_node_ref)
            context["input_node_refs"] = input_node_refs

        contexts.append(context)
    return contexts


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


def _capacity_window_leased_work_item_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    leased_item: LlmAdmittedLeasedWorkItem,
    started_attempt: object,
    lease_expires_at: datetime,
    occurred_at: datetime,
) -> WorkflowEvent:
    dispatch_attempt_id = _attempt_text(started_attempt, "attempt_id")
    work_item_id = _attempt_text(started_attempt, "work_item_id")
    schedule_payload = leased_item.admitted_schedule_payload()
    return capacity_window_leased_work_item_event(
        workflow_run_id=workflow_run_id,
        provider=leased_item.allocation.provider,
        account_ref=leased_item.allocation.account_ref,
        model_ref=leased_item.allocation.model_ref,
        work_item_id=work_item_id,
        dispatch_attempt_id=dispatch_attempt_id,
        lease_expires_at=lease_expires_at,
        selection_kind=leased_item.selection_kind,
        occurred_at=occurred_at,
        token_estimate=_optional_mapping_int(
            schedule_payload, "estimated_prompt_tokens"
        ),
        reserved_tokens=_optional_mapping_int(
            schedule_payload, "estimated_total_tokens"
        ),
        compaction_context=compaction_context_from_schedule_payload(
            schedule_payload,
            work_item_id=work_item_id,
            dispatch_attempt_id=dispatch_attempt_id,
        ),
        causation_command_id=workflow_command.command_id,
        operation_key=DRAFT_CLAIM_COMPACTION_PREPARE_OPERATION_KEY,
        canonical_phase=DRAFT_CLAIM_COMPACTION_CANONICAL_PHASE,
    )


def _execute_draft_claim_compaction_commands(
    *,
    workflow_run_id: str,
    started_attempts: Sequence[object],
    occurred_at: datetime,
) -> tuple[WorkflowCommand, ...]:
    commands: list[WorkflowCommand] = []
    for attempt in started_attempts:
        dispatch_attempt_id = _attempt_text(attempt, "attempt_id")
        work_item_id = _attempt_text(attempt, "work_item_id")
        schedule_payload = _attempt_schedule_payload(attempt)

        command_payload: dict[str, object] = {
            "workflow_run_id": workflow_run_id,
            "dispatch_attempt_id": dispatch_attempt_id,
            "work_item_id": work_item_id,
            "group_ref": _mapping_text(schedule_payload, "group_ref"),
            "batch_ref": _mapping_text(schedule_payload, "batch_ref"),
            "round_index": _mapping_int(schedule_payload, "round_index", fallback=0),
            "expected_output_kind": _mapping_text(
                schedule_payload,
                "expected_output_kind",
                fallback="compacted_claims",
            ),
        }

        for copied_key in (
            "source_claim_refs",
            "source_node_refs",
        ):
            copied_value = schedule_payload.get(copied_key)
            if copied_value is not None:
                command_payload[copied_key] = _mapping_text_list(
                    schedule_payload,
                    copied_key,
                )

        for copied_key in (
            "left_node_ref",
            "right_node_ref",
        ):
            copied_value = schedule_payload.get(copied_key)
            if copied_value is not None:
                command_payload[copied_key] = _mapping_text(
                    schedule_payload,
                    copied_key,
                )

        idempotency_key = (
            f"execute-draft-claim-compaction:{workflow_run_id}:{dispatch_attempt_id}"
        )
        commands.append(
            WorkflowCommand(
                command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
                command_type=(
                    KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION.value
                ),
                workflow_run_id=workflow_run_id,
                idempotency_key=WorkflowIdempotencyKey(idempotency_key),
                payload=command_payload,
                status=WorkflowCommandStatus.PENDING,
                run_after=occurred_at,
                created_at=occurred_at,
                updated_at=occurred_at,
            )
        )
    return tuple(commands)


def _attempt_schedule_payload(attempt: object) -> Mapping[str, object]:
    dispatch_payload = getattr(attempt, "dispatch_payload", None)
    if not isinstance(dispatch_payload, Mapping):
        raise ValueError("started attempt dispatch_payload must be mapping")

    schedule_payload = dispatch_payload.get("schedule_payload")
    if isinstance(schedule_payload, Mapping):
        return schedule_payload

    return dispatch_payload


def _optional_mapping_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _mapping_text(
    payload: Mapping[str, object],
    key: str,
    *,
    fallback: str | None = None,
) -> str:
    value = payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"mapping payload must include non-empty text {key}")
    return value


def _mapping_int(
    payload: Mapping[str, object],
    key: str,
    *,
    fallback: int | None = None,
) -> int:
    value = payload.get(key, fallback)
    if not isinstance(value, int):
        raise ValueError(f"mapping payload must include integer {key}")
    return value


def _mapping_text_list(
    payload: Mapping[str, object],
    key: str,
) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise ValueError(f"mapping payload must include sequence {key}")

    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"mapping payload {key} must contain non-empty text")
        result.append(item)
    return result


def _timeline_entries(
    *,
    workflow_command: WorkflowCommand,
    prepared_event: WorkflowEvent,
    started_attempts: Sequence[object],
    next_commands: Sequence[WorkflowCommand],
    occurred_at: datetime,
) -> tuple[WorkflowTimelineEntry, ...]:
    payload_summary = {
        "workflow_run_id": workflow_command.workflow_run_id,
        "work_kind": DRAFT_CLAIM_COMPACTION_WORK_KIND.value,
        "prepared_dispatch_count": len(started_attempts),
        "dispatch_attempt_ids": _dispatch_attempt_ids(started_attempts),
        "work_item_ids": _work_item_ids(started_attempts),
        "next_command_count": len(next_commands),
        "next_command_type": (
            KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION.value
        ),
    }
    return (
        WorkflowTimelineEntry(
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
        ),
        WorkflowTimelineEntry(
            timeline_entry_id=(
                f"workflow-timeline:{workflow_command.workflow_run_id}:"
                "ExecuteDraftClaimCompaction:requested"
            ),
            workflow_run_id=workflow_command.workflow_run_id,
            event_type=(
                KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION.value
            ),
            phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value,
            severity=WorkflowTimelineSeverity.INFO,
            message="Execute draft claim compaction requested",
            payload_summary=payload_summary,
            occurred_at=occurred_at,
            source_ref=DRAFT_CLAIM_COMPACTION_WORK_KIND.value,
        ),
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
