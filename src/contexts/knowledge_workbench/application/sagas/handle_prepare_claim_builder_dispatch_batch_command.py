from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol, cast

from src.contexts.execution_runtime.domain.value_objects.work_item_retry_plan import (
    WorkItemRetryPlan,
)
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.knowledge_workbench.application.sagas.capacity_window_workflow_events import (
    CLAIM_BUILDER_CANONICAL_PHASE,
    CLAIM_BUILDER_PREPARE_OPERATION_KEY,
    capacity_window_exhausted_event,
    capacity_window_leased_work_item_event,
    capacity_window_scheduled_wakeup_event,
    source_unit_ref_from_schedule_payload,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
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
from src.interfaces.composition.lease_llm_admitted_work_items import (
    LlmAdmittedLeasedWorkItem,
)
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    PrepareLlmDispatchBatchCommand,
    PrepareLlmDispatchBatchResult,
)


CLAIM_BUILDER_ACTIVE_MODEL_REF = "qwen/qwen3-32b"


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


@dataclass(frozen=True, slots=True)
class HandlePrepareClaimBuilderDispatchBatchCommandHandler:
    async def execute(
        self,
        command: HandlePrepareClaimBuilderDispatchBatchCommand,
        *,
        prepare_llm_dispatch_batch: PrepareLlmDispatchBatchPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
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

        occurred_at = _execution_occurred_at(workflow_command)
        prepare_command = _prepare_llm_dispatch_batch_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            occurred_at=occurred_at,
        )
        prepare_result = await prepare_llm_dispatch_batch.execute(
            prepare_command,
        )
        typed_prepare_result = cast(
            PrepareLlmDispatchBatchResult,
            prepare_result,
        )
        started_attempts = typed_prepare_result.attempt_result.started_attempts
        prepared_dispatch_count = len(started_attempts)
        preflight_metadata = _preflight_metadata_from_prepare_result(
            typed_prepare_result,
        )

        appended_event_count = 0
        appended_next_command_count = 0

        if _source_split_required(preflight_metadata):
            split_required_event = _claim_builder_source_unit_split_required_event(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                preflight_metadata=preflight_metadata,
                occurred_at=occurred_at,
            )
            await workflow_unit_of_work.outbox.append_event(split_required_event)
            appended_event_count = 1

            split_command = _split_claim_builder_source_unit_command(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                preflight_metadata=preflight_metadata,
                occurred_at=occurred_at,
            )
            await workflow_unit_of_work.command_log.append_pending_command(
                split_command,
            )
            appended_next_command_count = 1

            await workflow_unit_of_work.timeline.append_entry(
                _source_split_required_timeline_entry(
                    workflow_command=workflow_command,
                    split_required_event=split_required_event,
                    split_command=split_command,
                    occurred_at=occurred_at,
                )
            )

        elif prepared_dispatch_count > 0:
            prepared_event = _claim_builder_dispatch_batch_prepared_event(
                workflow_run_id=workflow_run_id,
                started_attempts=started_attempts,
                preflight_metadata=preflight_metadata,
                occurred_at=occurred_at,
            )
            persisted_prepared_event = await workflow_unit_of_work.outbox.append_event(
                prepared_event
            )
            if frontend_event_projection_writer is not None:
                await frontend_event_projection_writer.execute(persisted_prepared_event)
            appended_event_count = 1
            for attempt_event in _claim_builder_dispatch_attempt_prepared_events(
                workflow_run_id=workflow_run_id,
                started_attempts=started_attempts,
                lease_expires_at=prepare_command.lease_expires_at,
                occurred_at=occurred_at,
            ):
                persisted_attempt_event = (
                    await workflow_unit_of_work.outbox.append_event(attempt_event)
                )
                if frontend_event_projection_writer is not None:
                    await frontend_event_projection_writer.execute(
                        persisted_attempt_event
                    )
                appended_event_count += 1

            leased_items = typed_prepare_result.lease_result.leased
            for leased_item, started_attempt in zip(
                leased_items,
                started_attempts,
                strict=True,
            ):
                leased_event = _capacity_window_leased_work_item_event(
                    workflow_command=workflow_command,
                    workflow_run_id=workflow_run_id,
                    leased_item=leased_item,
                    started_attempt=started_attempt,
                    lease_expires_at=prepare_command.lease_expires_at,
                    occurred_at=occurred_at,
                )
                persisted_leased_event = (
                    await workflow_unit_of_work.outbox.append_event(
                        leased_event,
                    )
                )
                if frontend_event_projection_writer is not None:
                    await frontend_event_projection_writer.execute(
                        persisted_leased_event,
                    )
                appended_event_count += 1

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

        scheduled_work_item_count = _payload_positive_int(
            workflow_command.payload,
            "scheduled_work_item_count",
        )
        if (
            prepared_dispatch_count == 0
            and scheduled_work_item_count > 0
            and not _source_split_required(preflight_metadata)
        ):
            capacity_retry_at = _future_capacity_retry_at(
                _capacity_retry_at_from_prepare_result(typed_prepare_result),
                occurred_at=occurred_at,
            )
            if capacity_retry_at is not None:
                capacity_window_exhaustion = (
                    typed_prepare_result.capacity_window_exhaustion
                )
                if capacity_window_exhaustion is not None:
                    exhausted_event = capacity_window_exhausted_event(
                        workflow_run_id=workflow_run_id,
                        exhaustion=capacity_window_exhaustion,
                        operation_key=CLAIM_BUILDER_PREPARE_OPERATION_KEY,
                        canonical_phase=CLAIM_BUILDER_CANONICAL_PHASE,
                        occurred_at=occurred_at,
                        causation_command_id=workflow_command.command_id,
                        correlation_id=(
                            f"{capacity_window_exhaustion.provider}:"
                            f"{capacity_window_exhaustion.account_ref}:"
                            f"{capacity_window_exhaustion.model_ref}:"
                            f"{capacity_retry_at.isoformat()}"
                        ),
                    )
                    persisted_exhausted_event = (
                        await workflow_unit_of_work.outbox.append_event(
                            exhausted_event,
                        )
                    )
                    if frontend_event_projection_writer is not None:
                        await frontend_event_projection_writer.execute(
                            persisted_exhausted_event,
                        )
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
                        operation_key=CLAIM_BUILDER_PREPARE_OPERATION_KEY,
                        canonical_phase=CLAIM_BUILDER_CANONICAL_PHASE,
                        occurred_at=occurred_at,
                        causation_command_id=workflow_command.command_id,
                    )
                    persisted_wakeup_event = (
                        await workflow_unit_of_work.outbox.append_event(
                            scheduled_wakeup_event,
                        )
                    )
                    if frontend_event_projection_writer is not None:
                        await frontend_event_projection_writer.execute(
                            persisted_wakeup_event,
                        )
                    appended_event_count += 1

                await workflow_unit_of_work.timeline.append_entry(
                    _capacity_throttled_timeline_entry(
                        workflow_command=workflow_command,
                        workflow_run_id=workflow_run_id,
                        scheduled_work_item_count=scheduled_work_item_count,
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
                return HandlePrepareClaimBuilderDispatchBatchResult(
                    workflow_run_id=workflow_run_id,
                    prepared_dispatch_count=prepared_dispatch_count,
                    appended_event_count=appended_event_count,
                    appended_next_command_count=appended_next_command_count,
                    completed_command_id=workflow_command.command_id,
                )

            await workflow_unit_of_work.timeline.append_entry(
                _zero_dispatch_after_scheduling_timeline_entry(
                    workflow_command=workflow_command,
                    workflow_run_id=workflow_run_id,
                    scheduled_work_item_count=scheduled_work_item_count,
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
            return HandlePrepareClaimBuilderDispatchBatchResult(
                workflow_run_id=workflow_run_id,
                prepared_dispatch_count=prepared_dispatch_count,
                appended_event_count=appended_event_count,
                appended_next_command_count=appended_next_command_count,
                completed_command_id=workflow_command.command_id,
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

        return HandlePrepareClaimBuilderDispatchBatchResult(
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
) -> datetime | None:
    if capacity_retry_at is None:
        return None
    if capacity_retry_at > occurred_at:
        return capacity_retry_at
    return occurred_at + timedelta(seconds=60)


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
    requested_items = _payload_positive_int(
        workflow_command.payload,
        "scheduled_work_item_count",
    )

    return PrepareLlmDispatchBatchCommand(
        work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
        active_model_ref=_active_model_ref_from_payload(workflow_command.payload),
        requested_items=requested_items,
        worker=WorkerRef("knowledge-workbench-claim-builder-dispatch"),
        lease_token_prefix=f"claim-builder-dispatch:{workflow_run_id}",
        lease_expires_at=occurred_at + timedelta(seconds=90),
        now=occurred_at,
        started_at=occurred_at,
        profile=_profile_from_dispatch_preparation(workflow_command.payload),
        account_capacities=_account_capacities_from_dispatch_preparation(
            workflow_command.payload,
        ),
        dispatch_preparation_strategy=_legacy_dispatch_preparation_strategy_from_payload(
            workflow_command.payload,
        ),
        retry_plan=_retry_plan_from_payload(workflow_command.payload),
        provider_account_refs=_provider_account_refs_from_payload(
            workflow_command.payload,
        ),
    )


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
    dispatch_preparation = _optional_payload_mapping(
        payload,
        "llm_dispatch_preparation",
    )
    if dispatch_preparation is not None:
        return _payload_text(
            dispatch_preparation,
            "active_model_ref",
            fallback=CLAIM_BUILDER_ACTIVE_MODEL_REF,
        )
    return _payload_text(
        payload,
        "active_model_ref",
        fallback=CLAIM_BUILDER_ACTIVE_MODEL_REF,
    )


def _claim_builder_profile_positive_int_with_legacy_fallback(
    payload: Mapping[str, object],
    *,
    key: str,
    legacy_key: str,
) -> int:
    if key in payload:
        return _payload_positive_int(payload, key)
    return _payload_positive_int(payload, legacy_key)


def _claim_builder_profile_non_negative_int_with_legacy_fallback(
    payload: Mapping[str, object],
    *,
    key: str,
    legacy_key: str,
) -> int:
    if key in payload:
        return _payload_non_negative_int(payload, key)
    return _payload_non_negative_int(payload, legacy_key)


def _profile_from_dispatch_preparation(
    payload: Mapping[str, object],
) -> LlmTaskCapacityProfile | None:
    dispatch_preparation = _optional_payload_mapping(
        payload,
        "llm_dispatch_preparation",
    )
    if dispatch_preparation is None:
        return None

    profile_payload = _payload_mapping(dispatch_preparation, "profile")
    return LlmTaskCapacityProfile(
        profile_id=_payload_text(profile_payload, "profile_id"),
        estimated_prompt_tokens=(
            _claim_builder_profile_positive_int_with_legacy_fallback(
                profile_payload,
                key="estimated_input_tokens",
                legacy_key="estimated_prompt_tokens",
            )
        ),
        estimated_completion_tokens=(
            _claim_builder_profile_non_negative_int_with_legacy_fallback(
                profile_payload,
                key="estimated_output_tokens",
                legacy_key="estimated_completion_tokens",
            )
        ),
        estimated_requests=_payload_positive_int(
            profile_payload,
            "estimated_requests",
        ),
    )


def _account_capacities_from_dispatch_preparation(
    payload: Mapping[str, object],
) -> tuple[LlmProviderAccountCapacity, ...]:
    dispatch_preparation = _optional_payload_mapping(
        payload,
        "llm_dispatch_preparation",
    )
    if dispatch_preparation is None:
        return ()

    raw_account_payloads = dispatch_preparation.get("account_capacities")
    if raw_account_payloads is None and _provider_account_refs_from_payload(payload):
        return ()
    account_payloads = _payload_mapping_sequence(
        dispatch_preparation,
        "account_capacities",
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


def _optional_payload_mapping(
    payload: Mapping[str, object],
    key: str,
) -> Mapping[str, object] | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"workflow command payload {key} must be mapping")
    return value


def _retry_plan_from_payload(payload: Mapping[str, object]) -> WorkItemRetryPlan | None:
    for key in ("retry_plan", "selected_retry_plan", "claim_builder_retry_plan"):
        value = payload.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"workflow command payload {key} must be non-empty text")
        try:
            return WorkItemRetryPlan(value)
        except ValueError as exc:
            raise ValueError(f"workflow command payload {key} is unknown") from exc
    return None


def _legacy_dispatch_preparation_strategy_from_payload(
    payload: Mapping[str, object],
) -> str | None:
    if _retry_plan_from_payload(payload) is not None:
        return None

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


def _preflight_metadata_from_prepare_result(
    prepare_result: PrepareLlmDispatchBatchResult,
) -> dict[str, object]:
    active_model_ref = prepare_result.input_size_preflight_active_model_ref
    if active_model_ref is None:
        active_model_ref = ""

    metadata: dict[str, object] = {
        "input_size_preflight_decision": (prepare_result.input_size_preflight_decision),
        "input_size_preflight_reason": prepare_result.input_size_preflight_reason,
        "input_size_preflight_active_model_ref": active_model_ref,
        "source_split_required": prepare_result.source_split_required,
        "affected_work_item_refs": prepare_result.affected_work_item_refs,
        "source_unit_refs": prepare_result.source_unit_refs,
    }
    return metadata


def _source_split_required(metadata: Mapping[str, object]) -> bool:
    return metadata.get("source_split_required") is True


def _capacity_retry_at_from_prepare_result(
    prepare_result: PrepareLlmDispatchBatchResult,
) -> datetime | None:
    return prepare_result.capacity_retry_at


def _claim_builder_source_unit_split_required_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    preflight_metadata: Mapping[str, object],
    occurred_at: datetime,
) -> WorkflowEvent:
    payload = _source_split_payload(
        workflow_command=workflow_command,
        workflow_run_id=workflow_run_id,
        preflight_metadata=preflight_metadata,
    )
    source_document_ref = _payload_text(
        workflow_command.payload,
        "source_document_ref",
    )
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SOURCE_UNIT_SPLIT_REQUIRED.value}:"
            f"{source_document_ref}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SOURCE_UNIT_SPLIT_REQUIRED.value
        ),
        workflow_run_id=workflow_run_id,
        payload=payload,
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.idempotency_key.value,
    )


def _split_claim_builder_source_unit_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    preflight_metadata: Mapping[str, object],
    occurred_at: datetime,
) -> WorkflowCommand:
    payload = _source_split_payload(
        workflow_command=workflow_command,
        workflow_run_id=workflow_run_id,
        preflight_metadata=preflight_metadata,
    )
    dispatch_preparation = workflow_command.payload.get("llm_dispatch_preparation")
    if dispatch_preparation is not None:
        if not isinstance(dispatch_preparation, Mapping):
            raise ValueError("llm_dispatch_preparation must be mapping")
        payload["llm_dispatch_preparation"] = dict(dispatch_preparation)

    source_document_ref = _payload_text(
        workflow_command.payload,
        "source_document_ref",
    )
    idempotency_key = (
        f"split-claim-builder-source-unit:{workflow_run_id}:{source_document_ref}"
    )

    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.SPLIT_CLAIM_BUILDER_SOURCE_UNIT.value
        ),
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _source_split_payload(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    preflight_metadata: Mapping[str, object],
) -> dict[str, object]:
    dispatch_payload = _payload_mapping(
        workflow_command.payload,
        "llm_dispatch_preparation",
    )
    profile_payload = _payload_mapping(dispatch_payload, "profile")

    source_unit_refs = _metadata_text_tuple(preflight_metadata, "source_unit_refs")
    affected_work_item_refs = _metadata_text_tuple(
        preflight_metadata,
        "affected_work_item_refs",
    )

    return {
        "workflow_run_id": workflow_run_id,
        "source_document_ref": _payload_text(
            workflow_command.payload,
            "source_document_ref",
        ),
        "source_unit_ref": source_unit_refs[0],
        "source_unit_refs": source_unit_refs,
        "affected_work_item_refs": affected_work_item_refs,
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "scheduled_work_item_count": _payload_positive_int(
            workflow_command.payload,
            "scheduled_work_item_count",
        ),
        "estimated_input_tokens": (
            _claim_builder_profile_positive_int_with_legacy_fallback(
                profile_payload,
                key="estimated_input_tokens",
                legacy_key="estimated_prompt_tokens",
            )
        ),
        "estimated_prompt_tokens": (
            _claim_builder_profile_positive_int_with_legacy_fallback(
                profile_payload,
                key="estimated_input_tokens",
                legacy_key="estimated_prompt_tokens",
            )
        ),
        "active_model_ref": _metadata_text(
            preflight_metadata,
            "input_size_preflight_active_model_ref",
        ),
        "input_size_preflight_decision": _metadata_text(
            preflight_metadata,
            "input_size_preflight_decision",
        ),
        "input_size_preflight_reason": _metadata_text(
            preflight_metadata,
            "input_size_preflight_reason",
        ),
        "source_split_required": True,
        "split_reason": "input_size_preflight",
    }


def _source_split_required_timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    split_required_event: WorkflowEvent,
    split_command: WorkflowCommand,
    occurred_at: datetime,
) -> WorkflowTimelineEntry:
    payload_summary = {
        "workflow_run_id": workflow_command.workflow_run_id,
        "source_document_ref": split_required_event.payload["source_document_ref"],
        "input_size_preflight_decision": split_required_event.payload[
            "input_size_preflight_decision"
        ],
        "input_size_preflight_reason": split_required_event.payload[
            "input_size_preflight_reason"
        ],
        "next_command_type": split_command.command_type,
    }
    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{workflow_command.workflow_run_id}:"
            "ClaimBuilderSourceUnitSplitRequired"
        ),
        workflow_run_id=workflow_command.workflow_run_id,
        event_type=split_required_event.event_type,
        phase="CLAIM_BUILDER_SECTION_EXTRACTION",
        severity=WorkflowTimelineSeverity.WARNING,
        message="Claim builder source unit split required",
        payload_summary=payload_summary,
        occurred_at=occurred_at,
        source_ref=CLAIM_BUILDER_SECTION_WORK_KIND.value,
    )


def _zero_dispatch_after_scheduling_timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    scheduled_work_item_count: int,
    preflight_metadata: Mapping[str, object],
    occurred_at: datetime,
) -> WorkflowTimelineEntry:
    payload_summary = {
        "workflow_run_id": workflow_run_id,
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "scheduled_work_item_count": scheduled_work_item_count,
        "prepared_dispatch_count": 0,
        "input_size_preflight_decision": preflight_metadata[
            "input_size_preflight_decision"
        ],
        "input_size_preflight_reason": preflight_metadata[
            "input_size_preflight_reason"
        ],
        "input_size_preflight_active_model_ref": preflight_metadata[
            "input_size_preflight_active_model_ref"
        ],
        "source_split_required": preflight_metadata["source_split_required"],
    }
    source_document_ref = workflow_command.payload.get("source_document_ref")
    source_ref = (
        source_document_ref
        if isinstance(source_document_ref, str)
        else CLAIM_BUILDER_SECTION_WORK_KIND.value
    )
    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{workflow_run_id}:ClaimBuilderDispatchBatchPreparedZero"
        ),
        workflow_run_id=workflow_run_id,
        event_type="ClaimBuilderDispatchBatchPreparedZero",
        phase="CLAIM_BUILDER_SECTION_EXTRACTION",
        severity=WorkflowTimelineSeverity.INFO,
        message=(
            "Claim builder dispatch batch prepared zero attempts after "
            "scheduled work items"
        ),
        payload_summary=payload_summary,
        occurred_at=occurred_at,
        source_ref=source_ref,
    )


def _metadata_text_tuple(
    payload: Mapping[str, object],
    key: str,
) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, tuple):
        raise ValueError(f"preflight metadata must include tuple {key}")
    if not value:
        raise ValueError(f"preflight metadata {key} must be non-empty")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"preflight metadata {key} must contain non-empty text")
    return value


def _metadata_text(
    payload: Mapping[str, object],
    key: str,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"preflight metadata must include {key}")
    return value


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
        source_unit_ref=source_unit_ref_from_schedule_payload(schedule_payload),
        causation_command_id=workflow_command.command_id,
        operation_key=CLAIM_BUILDER_PREPARE_OPERATION_KEY,
        canonical_phase=CLAIM_BUILDER_CANONICAL_PHASE,
    )


def _claim_builder_dispatch_batch_prepared_event(
    *,
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
            **preflight_metadata,
        },
        occurred_at=occurred_at,
    )


def _claim_builder_dispatch_attempt_prepared_events(
    *,
    workflow_run_id: str,
    started_attempts: Sequence[object],
    lease_expires_at: datetime,
    occurred_at: datetime,
) -> tuple[WorkflowEvent, ...]:
    events: list[WorkflowEvent] = []
    for attempt in started_attempts:
        dispatch_payload = _attempt_mapping(attempt, "dispatch_payload")
        schedule_payload = dispatch_payload.get("schedule_payload")
        allocation = dispatch_payload.get("llm_allocation")
        if not isinstance(schedule_payload, Mapping):
            raise ValueError("dispatch attempt schedule_payload must be mapping")
        if not isinstance(allocation, Mapping):
            raise ValueError("dispatch attempt llm_allocation must be mapping")
        attempt_id = _attempt_text(attempt, "attempt_id")
        work_item_id = _attempt_text(attempt, "work_item_id")
        attempt_number = _attempt_positive_int(attempt, "attempt_number")
        events.append(
            WorkflowEvent(
                event_id=WorkflowEventId(
                    "workflow-event:"
                    f"{workflow_run_id}:"
                    f"{KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_ATTEMPT_PREPARED.value}:"
                    f"{attempt_id}"
                ),
                event_type=(
                    KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_ATTEMPT_PREPARED.value
                ),
                workflow_run_id=workflow_run_id,
                payload={
                    "workflow_run_id": workflow_run_id,
                    "source_document_ref": _payload_text(
                        schedule_payload,
                        "source_document_ref",
                    ),
                    "source_unit_ref": _payload_text(
                        schedule_payload,
                        "source_unit_ref",
                    ),
                    "work_item_id": work_item_id,
                    "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
                    "dispatch_attempt_id": attempt_id,
                    "attempt_number": attempt_number,
                    "attempt_state": "leased",
                    "provider": _payload_text(allocation, "provider"),
                    "account_ref": _payload_text(allocation, "account_ref"),
                    "model_ref": _payload_text(allocation, "model_ref"),
                    "lease_expires_at": lease_expires_at.isoformat(),
                },
                occurred_at=occurred_at,
            )
        )
    return tuple(events)


def _next_prepare_claim_builder_dispatch_batch_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    capacity_retry_at: datetime,
    occurred_at: datetime,
) -> WorkflowCommand:
    idempotency_key = (
        "prepare-claim-builder-dispatch-batch:"
        f"{workflow_run_id}:"
        f"{capacity_retry_at.isoformat()}"
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
        ),
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload=dict(workflow_command.payload),
        status=WorkflowCommandStatus.PENDING,
        run_after=capacity_retry_at,
        created_at=occurred_at,
        updated_at=occurred_at,
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
            "claim_builder_prepare_command_id": workflow_command.command_id.value,
            "claim_builder_prepare_idempotency_key": (
                workflow_command.idempotency_key.value
            ),
        }
        for copied_key in (
            "source_document_ref",
            "scheduled_work_item_count",
            "active_model_ref",
            "retry_plan",
            "selected_retry_plan",
            "claim_builder_retry_plan",
        ):
            copied_value = workflow_command.payload.get(copied_key)
            if copied_value is not None:
                command_payload[copied_key] = copied_value
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
    preflight_metadata: Mapping[str, object],
    occurred_at: datetime,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_run_id,
    )
    existing_domain_counters = (
        dict(existing.domain_counters) if existing is not None else {}
    )
    existing_domain_counters["prepared_dispatch_count"] = prepared_dispatch_count
    existing_domain_counters["input_size_preflight_source_split_required_count"] = (
        1 if _source_split_required(preflight_metadata) else 0
    )
    existing_domain_counters["claim_builder_source_split_required_count"] = (
        1 if _source_split_required(preflight_metadata) else 0
    )
    existing_domain_counters["input_size_preflight_larger_input_model_count"] = (
        1
        if preflight_metadata.get("input_size_preflight_decision")
        == "USE_LARGER_INPUT_MODEL"
        else 0
    )

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
            "PrepareClaimBuilderDispatchBatch:capacity-throttled:"
            f"{occurred_at.isoformat()}"
        ),
        workflow_run_id=workflow_run_id,
        event_type=workflow_command.command_type,
        phase="CLAIM_BUILDER_SECTION_EXTRACTION",
        severity=WorkflowTimelineSeverity.INFO,
        message="Claim builder dispatch capacity temporarily unavailable",
        payload_summary=payload_summary,
        occurred_at=occurred_at,
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
        return "0:source-split-required"
    return f"{len(dispatch_attempt_ids)}:{dispatch_attempt_ids[0]}"


def _attempt_text(attempt: object, field_name: str) -> str:
    value = getattr(attempt, field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"started attempt {field_name} must be non-empty")
    return value


def _attempt_positive_int(attempt: object, field_name: str) -> int:
    value = getattr(attempt, field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"started attempt {field_name} must be positive int")
    return value


def _attempt_mapping(
    attempt: object,
    field_name: str,
) -> Mapping[str, object]:
    value = getattr(attempt, field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"started attempt {field_name} must be mapping")
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
