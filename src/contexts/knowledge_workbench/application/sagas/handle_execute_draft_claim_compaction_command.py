from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, TypeGuard, cast

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
    LlmAttemptCapacityObservationRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.application.sagas.append_capacity_window_prepare_wakeup import (
    append_capacity_window_prepare_wakeup,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_apply_result import (
    raw_claim_node_ref,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_attempt_input import (
    DraftClaimCompactionExpectedOutputKind,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionOutputClaim,
    DraftClaimCompactionTriple,
    DraftClaimReducedRewriteOutput,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_output_validator import (
    DraftClaimCompactionOutputValidator,
    InvalidDraftClaimCompactionOutput,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionStatus,
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
from src.domain.project_plane.json_types import JsonObject, JsonValue
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt import (
    ExecutePreparedLlmDispatchAttemptCommand,
    ExecutePreparedLlmDispatchAttemptResult,
    LlmDispatchOutputValidationResult,
)


DRAFT_CLAIM_COMPACTION_WORK_KIND = "knowledge_workbench.draft_claim_compaction"


class ExecutePreparedLlmDispatchAttemptPort(Protocol):
    async def execute(
        self,
        command: ExecutePreparedLlmDispatchAttemptCommand,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionLlmDispatchOutputValidator:
    expected_output_kind: DraftClaimCompactionExpectedOutputKind
    output_validator: DraftClaimCompactionOutputValidator
    source_claim_refs: tuple[str, ...] = ()

    def validate(
        self,
        *,
        dispatch_payload: Mapping[str, object],
        output_payload: Mapping[str, object] | None,
        llm_status: LlmDispatchExecutionStatus,
        finished_at: datetime,
        attempt_number: int,
    ) -> LlmDispatchOutputValidationResult:
        del attempt_number
        if llm_status is not LlmDispatchExecutionStatus.SUCCEEDED:
            return LlmDispatchOutputValidationResult(
                status=llm_status,
                error_kind=None,
                next_attempt_at=None,
                metadata={
                    "draft_claim_compaction_validation_decision": None,
                    "expected_output_kind": self.expected_output_kind.value,
                    "retry_recommended": False,
                },
            )

        try:
            decoded_payload = _decoded_output_payload(output_payload)
            if (
                self.expected_output_kind
                is DraftClaimCompactionExpectedOutputKind.COMPACTED_CLAIMS
            ):
                input_refs = self.source_claim_refs or _input_claim_refs(
                    dispatch_payload,
                    decoded_payload=decoded_payload,
                )
                validated_output = self.output_validator.validate(
                    payload=decoded_payload,
                    input_claim_refs=input_refs,
                )
                return LlmDispatchOutputValidationResult(
                    status=LlmDispatchExecutionStatus.SUCCEEDED,
                    error_kind=None,
                    next_attempt_at=None,
                    metadata={
                        "draft_claim_compaction_validation_decision": "valid_output",
                        "expected_output_kind": self.expected_output_kind.value,
                        "validated_compacted_claim_count": len(
                            validated_output.compacted_claims
                        ),
                        "retry_recommended": False,
                        "compacted_claims": [
                            _compacted_claim_payload(claim)
                            for claim in validated_output.compacted_claims
                        ],
                        "_compacted_claims": validated_output.compacted_claims,
                    },
                )

            reduced_rewrite = self.output_validator.validate_reduced_rewrite_output(
                payload=decoded_payload,
            )
            return LlmDispatchOutputValidationResult(
                status=LlmDispatchExecutionStatus.SUCCEEDED,
                error_kind=None,
                next_attempt_at=None,
                metadata={
                    "draft_claim_compaction_validation_decision": "valid_output",
                    "expected_output_kind": self.expected_output_kind.value,
                    "validated_compacted_claim_count": 0,
                    "retry_recommended": False,
                    "reduced_rewrite": _reduced_rewrite_payload(reduced_rewrite),
                    "_reduced_rewrite": reduced_rewrite,
                },
            )
        except (InvalidDraftClaimCompactionOutput, ValueError, TypeError) as exc:
            return LlmDispatchOutputValidationResult(
                status=LlmDispatchExecutionStatus.RETRYABLE_FAILED,
                error_kind="draft_claim_compaction_output_validation_failed",
                next_attempt_at=None,
                metadata={
                    "draft_claim_compaction_validation_decision": "invalid_output",
                    "expected_output_kind": self.expected_output_kind.value,
                    "validation_error": str(exc),
                    "retry_recommended": True,
                },
            )


@dataclass(frozen=True, slots=True)
class HandleExecuteDraftClaimCompactionCommand:
    workflow_command: WorkflowCommand


@dataclass(frozen=True, slots=True)
class HandleExecuteDraftClaimCompactionResult:
    workflow_run_id: str
    dispatch_attempt_id: str
    work_item_id: str
    outcome_status: str
    appended_event_count: int
    appended_next_command_count: int
    completed_command_id: WorkflowCommandId


class HandleExecuteDraftClaimCompactionCommandHandler:
    async def execute(
        self,
        command: HandleExecuteDraftClaimCompactionCommand,
        *,
        execute_prepared_llm_dispatch_attempt: ExecutePreparedLlmDispatchAttemptPort,
        capacity_observation_repository: LlmAttemptCapacityObservationRepositoryPort,
        draft_claim_compaction_output_validator: DraftClaimCompactionOutputValidator,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
    ) -> HandleExecuteDraftClaimCompactionResult:
        workflow_command = command.workflow_command
        _validate_workflow_command(workflow_command)

        workflow_run_id = _payload_text(
            workflow_command.payload,
            "workflow_run_id",
            fallback=workflow_command.workflow_run_id,
        )
        if workflow_run_id != workflow_command.workflow_run_id:
            raise ValueError("payload workflow_run_id must match workflow command")

        dispatch_attempt_id = _payload_text(
            workflow_command.payload, "dispatch_attempt_id"
        )
        work_item_id = _payload_text(workflow_command.payload, "work_item_id")
        group_ref = _payload_text(workflow_command.payload, "group_ref")
        batch_ref = _payload_text(workflow_command.payload, "batch_ref")
        round_index = _payload_int(workflow_command.payload, "round_index")
        expected_output_kind = DraftClaimCompactionExpectedOutputKind(
            _payload_text(workflow_command.payload, "expected_output_kind"),
        )
        source_claim_refs = _payload_text_tuple(
            workflow_command.payload,
            "source_claim_refs",
            allow_missing=True,
        )

        execution_result = cast(
            ExecutePreparedLlmDispatchAttemptResult,
            await execute_prepared_llm_dispatch_attempt.execute(
                ExecutePreparedLlmDispatchAttemptCommand(
                    attempt_id=dispatch_attempt_id,
                    output_validator=DraftClaimCompactionLlmDispatchOutputValidator(
                        expected_output_kind=expected_output_kind,
                        output_validator=draft_claim_compaction_output_validator,
                        source_claim_refs=source_claim_refs,
                    ),
                )
            ),
        )
        if execution_result.dispatch.work_item_id != work_item_id:
            raise ValueError(
                "dispatch work_item_id must match workflow command payload"
            )

        finished_at = execution_result.llm_result.finished_at
        capacity_observation = _capacity_observation_from_result(execution_result)
        appended_event_count = 0
        capacity_window_wakeup_count = 0

        if capacity_observation is not None:
            await capacity_observation_repository.record_observation(
                capacity_observation
            )
            persisted_capacity_event = await workflow_unit_of_work.outbox.append_event(
                _capacity_observed_event(
                    workflow_command=workflow_command,
                    workflow_run_id=workflow_run_id,
                    dispatch_attempt_id=dispatch_attempt_id,
                    work_item_id=work_item_id,
                    capacity_observation=capacity_observation,
                    occurred_at=finished_at,
                )
            )
            if frontend_event_projection_writer is not None:
                await frontend_event_projection_writer.execute(
                    persisted_capacity_event,
                )
            appended_event_count += 1
            wakeup = await append_capacity_window_prepare_wakeup(
                workflow_unit_of_work=workflow_unit_of_work,
                source_command=workflow_command,
                workflow_run_id=workflow_run_id,
                prepare_command_type=(
                    KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH
                ),
                capacity_observation=capacity_observation,
                occurred_at=finished_at,
            )
            if wakeup is not None:
                capacity_window_wakeup_count = 1

        outcome_event = _attempt_outcome_event(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            execution_result=execution_result,
            capacity_observation=capacity_observation,
        )
        await workflow_unit_of_work.outbox.append_event(outcome_event)
        appended_event_count += 1

        next_command = _next_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            group_ref=group_ref,
            batch_ref=batch_ref,
            round_index=round_index,
            expected_output_kind=expected_output_kind,
            execution_result=execution_result,
            dispatch_payload=execution_result.dispatch.dispatch_payload,
            occurred_at=finished_at,
        )
        await workflow_unit_of_work.command_log.append_pending_command(next_command)
        appended_next_command_count = 1 + capacity_window_wakeup_count

        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_run_id=workflow_run_id,
            status=execution_result.llm_result.status,
            capacity_observation=capacity_observation,
            validation_metadata=execution_result.validation_metadata,
            occurred_at=finished_at,
        )
        await workflow_unit_of_work.timeline.append_entry(
            _timeline_entry(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                dispatch_attempt_id=dispatch_attempt_id,
                work_item_id=work_item_id,
                execution_result=execution_result,
                capacity_observation=capacity_observation,
            )
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=finished_at,
        )

        return HandleExecuteDraftClaimCompactionResult(
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            outcome_status=execution_result.llm_result.status.value,
            appended_event_count=appended_event_count,
            appended_next_command_count=appended_next_command_count,
            completed_command_id=workflow_command.command_id,
        )


def _validate_workflow_command(workflow_command: WorkflowCommand) -> None:
    if (
        workflow_command.command_type
        != KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION.value
    ):
        raise ValueError(
            "workflow_command command_type must be ExecuteDraftClaimCompaction"
        )
    if workflow_command.status is not WorkflowCommandStatus.PENDING:
        raise ValueError("workflow_command status must be PENDING")


def _decoded_output_payload(
    output_payload: Mapping[str, object] | None,
) -> Mapping[str, JsonValue]:
    if output_payload is None:
        raise ValueError("output payload is required")
    raw_text = output_payload.get("raw_text")
    if isinstance(raw_text, str):
        try:
            decoded = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError("output raw_text must be valid JSON") from exc
        if _is_json_mapping(decoded):
            return decoded
        raise ValueError("decoded output must be JSON object")

    if _is_json_mapping(output_payload):
        return output_payload
    raise ValueError("output payload must be JSON object")


def _is_json_mapping(value: object) -> TypeGuard[Mapping[str, JsonValue]]:
    return isinstance(value, Mapping) and all(
        isinstance(key, str) and _is_json_value(item) for key, item in value.items()
    )


def _is_json_value(value: object) -> TypeGuard[JsonValue]:
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return all(
            isinstance(key, str) and _is_json_value(item) for key, item in value.items()
        )
    return False


def _input_claim_refs(
    dispatch_payload: Mapping[str, object],
    *,
    decoded_payload: Mapping[str, JsonValue],
) -> tuple[str, ...]:
    schedule_payload = _dispatch_schedule_payload(dispatch_payload)
    direct_refs = _mapping_text_tuple(schedule_payload, "source_claim_refs")
    if direct_refs:
        return direct_refs

    payload_value = schedule_payload.get("payload")
    if isinstance(payload_value, Mapping):
        payload_refs = _claim_refs_from_claim_objects(payload_value.get("claims"))
        if payload_refs:
            return payload_refs

    output_refs = _source_refs_from_compacted_output(decoded_payload)
    if output_refs:
        return output_refs

    raise ValueError("source_claim_refs are required for compacted_claims validation")


def _source_refs_from_compacted_output(
    decoded_payload: Mapping[str, JsonValue],
) -> tuple[str, ...]:
    claims_value = decoded_payload.get("compacted_claims")
    if not isinstance(claims_value, list):
        return ()
    refs: list[str] = []
    for claim_value in claims_value:
        if not isinstance(claim_value, Mapping):
            continue
        source_refs = claim_value.get("source_claim_refs")
        if not isinstance(source_refs, list):
            continue
        for source_ref in source_refs:
            if isinstance(source_ref, str) and source_ref.strip():
                refs.append(source_ref)
    return tuple(refs)


def _claim_refs_from_claim_objects(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    refs: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        claim_ref = item.get("id")
        if isinstance(claim_ref, str) and claim_ref.strip():
            refs.append(claim_ref)
            continue
        observation_ref = item.get("observation_ref")
        if isinstance(observation_ref, str) and observation_ref.strip():
            refs.append(observation_ref)
    return tuple(refs)


def _next_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    group_ref: str,
    batch_ref: str,
    round_index: int,
    expected_output_kind: DraftClaimCompactionExpectedOutputKind,
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
    dispatch_payload: Mapping[str, object],
    occurred_at: datetime,
) -> WorkflowCommand:
    if execution_result.llm_result.status is LlmDispatchExecutionStatus.SUCCEEDED:
        return _apply_result_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            group_ref=group_ref,
            batch_ref=batch_ref,
            round_index=round_index,
            expected_output_kind=expected_output_kind,
            validation_metadata=_required_validation_metadata(execution_result),
            dispatch_payload=dispatch_payload,
            occurred_at=occurred_at,
        )
    return _reconcile_progress_command(
        workflow_command=workflow_command,
        workflow_run_id=workflow_run_id,
        dispatch_attempt_id=dispatch_attempt_id,
        work_item_id=work_item_id,
        occurred_at=occurred_at,
    )


def _apply_result_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    group_ref: str,
    batch_ref: str,
    round_index: int,
    expected_output_kind: DraftClaimCompactionExpectedOutputKind,
    validation_metadata: Mapping[str, object],
    dispatch_payload: Mapping[str, object],
    occurred_at: datetime,
) -> WorkflowCommand:
    idempotency_key = (
        f"draft-claim-compaction-apply:{workflow_run_id}:{work_item_id}:"
        f"{dispatch_attempt_id}"
    )
    payload = _apply_result_payload(
        workflow_command=workflow_command,
        workflow_run_id=workflow_run_id,
        group_ref=group_ref,
        batch_ref=batch_ref,
        work_item_id=work_item_id,
        round_index=round_index,
        expected_output_kind=expected_output_kind,
        validation_metadata=validation_metadata,
        dispatch_payload=dispatch_payload,
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT.value
        ),
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _apply_result_payload(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    group_ref: str,
    batch_ref: str,
    work_item_id: str,
    round_index: int,
    expected_output_kind: DraftClaimCompactionExpectedOutputKind,
    validation_metadata: Mapping[str, object],
    dispatch_payload: Mapping[str, object],
) -> JsonObject:
    compared_node_refs = _derived_compared_node_refs(
        workflow_run_id,
        group_ref,
        workflow_command.payload,
        dispatch_payload,
    )

    if expected_output_kind is DraftClaimCompactionExpectedOutputKind.COMPACTED_CLAIMS:
        compacted_claims = _metadata_payload_list(
            validation_metadata,
            "compacted_claims",
        )
        return {
            "workflow_run_id": workflow_run_id,
            "group_ref": group_ref,
            "batch_ref": batch_ref,
            "work_item_id": work_item_id,
            "round_index": round_index,
            "output_kind": DraftClaimCompactionExpectedOutputKind.COMPACTED_CLAIMS.value,
            "compared_node_refs": list(compared_node_refs),
            "compacted_claims": compacted_claims,
            "reduced_rewrite": None,
        }

    if len(compared_node_refs) != 2:
        raise ValueError("reduced rewrite requires exactly two compared node refs")
    return {
        "workflow_run_id": workflow_run_id,
        "group_ref": group_ref,
        "batch_ref": batch_ref,
        "work_item_id": work_item_id,
        "round_index": round_index,
        "output_kind": DraftClaimCompactionExpectedOutputKind.REDUCED_REWRITE.value,
        "compared_node_refs": list(compared_node_refs),
        "source_node_refs": list(compared_node_refs),
        "compacted_claims": [],
        "reduced_rewrite": _metadata_payload_mapping(
            validation_metadata,
            "reduced_rewrite",
        ),
    }


def _required_validation_metadata(
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
) -> Mapping[str, object]:
    metadata = execution_result.validation_metadata
    if metadata is None:
        raise ValueError(
            "successful draft claim compaction requires validation metadata"
        )
    decision = metadata.get("draft_claim_compaction_validation_decision")
    if decision != "valid_output":
        raise ValueError("successful draft claim compaction requires valid output")
    return metadata


def _reconcile_progress_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    occurred_at: datetime,
) -> WorkflowCommand:
    idempotency_key = (
        f"draft-claim-compaction-progress:{workflow_run_id}:{dispatch_attempt_id}"
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS.value
        ),
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload={
            "workflow_run_id": workflow_run_id,
            "dispatch_attempt_id": dispatch_attempt_id,
            "work_item_id": work_item_id,
            "caused_by_command_id": workflow_command.command_id.value,
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _derived_compared_node_refs(
    workflow_run_id: str,
    group_ref: str,
    payload: Mapping[str, object],
    dispatch_payload: Mapping[str, object],
) -> tuple[str, ...]:
    payload_refs = _compared_node_refs_from_payload(
        workflow_run_id,
        group_ref,
        payload,
    )
    if payload_refs:
        return payload_refs

    schedule_payload = _dispatch_schedule_payload(dispatch_payload)
    schedule_refs = _compared_node_refs_from_payload(
        workflow_run_id,
        group_ref,
        schedule_payload,
    )
    if schedule_refs:
        return schedule_refs

    nested_payload = schedule_payload.get("payload")
    if isinstance(nested_payload, Mapping):
        nested_refs = _compared_node_refs_from_payload(
            workflow_run_id,
            group_ref,
            nested_payload,
        )
        if nested_refs:
            return nested_refs
        nested_claim_refs = _claim_refs_from_claim_objects(nested_payload.get("claims"))
        if nested_claim_refs:
            return _raw_node_refs_for_claim_refs(
                workflow_run_id,
                group_ref,
                nested_claim_refs,
            )

    raise ValueError("compared node refs are required")


def _compared_node_refs_from_payload(
    workflow_run_id: str,
    group_ref: str,
    payload: Mapping[str, object],
) -> tuple[str, ...]:
    compared_node_refs = _payload_text_tuple(
        payload, "compared_node_refs", allow_missing=True
    )
    if compared_node_refs:
        return compared_node_refs

    node_refs = _payload_text_tuple(payload, "node_refs", allow_missing=True)
    if node_refs:
        return node_refs

    source_node_refs = _payload_text_tuple(
        payload, "source_node_refs", allow_missing=True
    )
    if source_node_refs:
        return source_node_refs

    source_claim_refs = _payload_text_tuple(
        payload, "source_claim_refs", allow_missing=True
    )
    if source_claim_refs:
        return _raw_node_refs_for_claim_refs(
            workflow_run_id,
            group_ref,
            source_claim_refs,
        )

    left_node_ref = _payload_optional_text(payload, "left_node_ref")
    right_node_ref = _payload_optional_text(payload, "right_node_ref")
    if left_node_ref is None:
        return ()
    if right_node_ref is None:
        return (left_node_ref,)
    return tuple(sorted((left_node_ref, right_node_ref)))


def _raw_node_refs_for_claim_refs(
    workflow_run_id: str,
    group_ref: str,
    source_claim_refs: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        raw_claim_node_ref(
            workflow_run_id=workflow_run_id,
            group_ref=group_ref,
            observation_ref=source_claim_ref,
        )
        for source_claim_ref in source_claim_refs
    )


def _capacity_observation_from_result(
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
) -> LlmAttemptCapacityObservation | None:
    payload = execution_result.llm_result.capacity_observation
    if payload is None:
        return None
    return LlmAttemptCapacityObservation.from_payload(payload)


def _capacity_observed_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    capacity_observation: LlmAttemptCapacityObservation,
    occurred_at: datetime,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value}:"
            f"{dispatch_attempt_id}"
        ),
        event_type=KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value,
        workflow_run_id=workflow_run_id,
        payload={
            "workflow_run_id": workflow_run_id,
            "dispatch_attempt_id": dispatch_attempt_id,
            "work_item_id": work_item_id,
            "operation_key": "execute_draft_claim_compaction",
            "canonical_phase": (
                KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value
            ),
            **capacity_observation.to_event_payload(),
        },
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=dispatch_attempt_id,
    )


def _attempt_outcome_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
    capacity_observation: LlmAttemptCapacityObservation | None,
) -> WorkflowEvent:
    event_type = _event_type_for_status(execution_result.llm_result.status)
    return WorkflowEvent(
        event_id=WorkflowEventId(
            f"workflow-event:{workflow_run_id}:{event_type.value}:{dispatch_attempt_id}"
        ),
        event_type=event_type.value,
        workflow_run_id=workflow_run_id,
        payload=_event_payload(
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            execution_result=execution_result,
            capacity_observation=capacity_observation,
        ),
        occurred_at=execution_result.llm_result.finished_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=dispatch_attempt_id,
    )


def _event_type_for_status(
    status: LlmDispatchExecutionStatus,
) -> KnowledgeExtractionCanonicalEventType:
    if status is LlmDispatchExecutionStatus.SUCCEEDED:
        return KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_COMPLETED
    if status is LlmDispatchExecutionStatus.TERMINAL_FAILED:
        return KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_TERMINAL_FAILED
    return KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_RETRYABLE_FAILED


def _event_payload(
    *,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
    capacity_observation: LlmAttemptCapacityObservation | None,
) -> JsonObject:
    capacity_payload = (
        capacity_observation.to_event_payload()
        if capacity_observation is not None
        else _allocation_payload(execution_result.dispatch.dispatch_payload)
    )
    payload: JsonObject = {
        "workflow_run_id": workflow_run_id,
        "dispatch_attempt_id": dispatch_attempt_id,
        "work_item_id": work_item_id,
        "work_kind": DRAFT_CLAIM_COMPACTION_WORK_KIND,
        "outcome_status": execution_result.llm_result.status.value,
        "error_kind": execution_result.llm_result.error_kind,
        "next_attempt_at": _datetime_payload(
            execution_result.llm_result.next_attempt_at
        ),
        "provider": _json_payload_value(capacity_payload, "provider"),
        "account_ref": _json_payload_value(capacity_payload, "account_ref"),
        "model_ref": _json_payload_value(capacity_payload, "model_ref"),
        "actual_prompt_tokens": _json_payload_value(
            capacity_payload,
            "actual_prompt_tokens",
        ),
        "actual_completion_tokens": _json_payload_value(
            capacity_payload,
            "actual_completion_tokens",
        ),
        "actual_total_tokens": _json_payload_value(
            capacity_payload,
            "actual_total_tokens",
        ),
    }
    if execution_result.validation_metadata is not None:
        payload.update(
            _public_validation_metadata(execution_result.validation_metadata)
        )
    return payload


def _allocation_payload(dispatch_payload: Mapping[str, object]) -> dict[str, object]:
    allocation = dispatch_payload.get("llm_allocation")
    if not isinstance(allocation, Mapping):
        return {}
    return {
        "provider": allocation.get("provider"),
        "account_ref": allocation.get("account_ref"),
        "model_ref": allocation.get("model_ref"),
    }


async def _save_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_run_id: str,
    status: LlmDispatchExecutionStatus,
    capacity_observation: LlmAttemptCapacityObservation | None,
    validation_metadata: Mapping[str, object] | None,
    occurred_at: datetime,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_run_id,
    )
    domain_counters = dict(existing.domain_counters) if existing is not None else {}
    domain_counters["draft_claim_compaction_executed_attempt_count"] = (
        domain_counters.get("draft_claim_compaction_executed_attempt_count", 0) + 1
    )
    if capacity_observation is not None:
        domain_counters["capacity_observation_count"] = (
            domain_counters.get("capacity_observation_count", 0) + 1
        )
    _apply_validation_counters(
        domain_counters=domain_counters,
        validation_metadata=validation_metadata,
    )

    completed_delta = 1 if status is LlmDispatchExecutionStatus.SUCCEEDED else 0
    deferred_delta = 1 if status is LlmDispatchExecutionStatus.DEFERRED else 0
    retryable_delta = 1 if status is LlmDispatchExecutionStatus.RETRYABLE_FAILED else 0
    terminal_delta = 1 if status is LlmDispatchExecutionStatus.TERMINAL_FAILED else 0
    running_before = existing.running_work_items if existing is not None else 0

    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=workflow_run_id,
            current_phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value,
            workflow_status="RUNNING",
            total_work_items=existing.total_work_items if existing is not None else 0,
            scheduled_work_items=(
                existing.scheduled_work_items if existing is not None else 0
            ),
            running_work_items=max(0, running_before - 1),
            completed_work_items=(
                (existing.completed_work_items if existing is not None else 0)
                + completed_delta
            ),
            deferred_work_items=(
                (existing.deferred_work_items if existing is not None else 0)
                + deferred_delta
            ),
            retryable_failed_work_items=(
                (existing.retryable_failed_work_items if existing is not None else 0)
                + retryable_delta
            ),
            terminal_failed_work_items=(
                (existing.terminal_failed_work_items if existing is not None else 0)
                + terminal_delta
            ),
            blocked_work_items=existing.blocked_work_items
            if existing is not None
            else 0,
            domain_counters=domain_counters,
            started_at=existing.started_at if existing is not None else occurred_at,
            updated_at=occurred_at,
            completed_at=existing.completed_at if existing is not None else None,
        )
    )


def _apply_validation_counters(
    *,
    domain_counters: dict[str, int],
    validation_metadata: Mapping[str, object] | None,
) -> None:
    if validation_metadata is None:
        return
    decision = validation_metadata.get("draft_claim_compaction_validation_decision")
    if decision == "valid_output":
        domain_counters["draft_claim_compaction_valid_output_count"] = (
            domain_counters.get("draft_claim_compaction_valid_output_count", 0) + 1
        )
        return
    if decision == "invalid_output":
        domain_counters["draft_claim_compaction_invalid_output_count"] = (
            domain_counters.get("draft_claim_compaction_invalid_output_count", 0) + 1
        )


def _timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
    capacity_observation: LlmAttemptCapacityObservation | None,
) -> WorkflowTimelineEntry:
    event_type = _event_type_for_status(execution_result.llm_result.status)
    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{workflow_run_id}:"
            f"DraftClaimCompactionAttemptExecuted:{dispatch_attempt_id}"
        ),
        workflow_run_id=workflow_run_id,
        event_type=event_type.value,
        phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value,
        severity=_severity_for_status(execution_result.llm_result.status),
        message="Draft claim compaction attempt executed",
        payload_summary=_event_payload(
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            execution_result=execution_result,
            capacity_observation=capacity_observation,
        ),
        occurred_at=execution_result.llm_result.finished_at,
        source_ref=workflow_command.command_type,
        work_item_id=work_item_id,
        attempt_id=dispatch_attempt_id,
    )


def _severity_for_status(
    status: LlmDispatchExecutionStatus,
) -> WorkflowTimelineSeverity:
    if status is LlmDispatchExecutionStatus.SUCCEEDED:
        return WorkflowTimelineSeverity.INFO
    if status in {
        LlmDispatchExecutionStatus.DEFERRED,
        LlmDispatchExecutionStatus.RETRYABLE_FAILED,
    }:
        return WorkflowTimelineSeverity.WARNING
    return WorkflowTimelineSeverity.ERROR


def _public_validation_metadata(
    validation_metadata: Mapping[str, object],
) -> JsonObject:
    return {
        key: value
        for key, value in validation_metadata.items()
        if not key.startswith("_") and _is_json_value(value)
    }


def _json_payload_value(payload: Mapping[str, object], key: str) -> JsonValue:
    value = payload.get(key)
    if _is_json_value(value):
        return value
    return None


def _compacted_claim_payload(claim: DraftClaimCompactionOutputClaim) -> JsonObject:
    return {
        "key": claim.key,
        "claim": claim.claim,
        "claim_kind": claim.claim_kind.value,
        "source_claim_refs": list(claim.source_claim_refs),
        "triples": [_triple_payload(triple) for triple in claim.triples],
        "merge_decision": claim.merge_decision.value,
    }


def _reduced_rewrite_payload(rewrite: DraftClaimReducedRewriteOutput) -> JsonObject:
    return {
        "key": rewrite.key,
        "claim": rewrite.claim,
        "triples": [_triple_payload(triple) for triple in rewrite.triples],
    }


def _triple_payload(triple: DraftClaimCompactionTriple) -> JsonObject:
    return {
        "subject": triple.subject,
        "predicate": triple.predicate.value,
        "object": triple.object,
        "qualifiers": list(triple.qualifiers),
    }


def _metadata_payload_list(
    validation_metadata: Mapping[str, object],
    key: str,
) -> list[JsonValue]:
    value = validation_metadata.get(key)
    if not isinstance(value, list):
        raise ValueError(f"validation metadata {key} must be list")
    return value


def _metadata_payload_mapping(
    validation_metadata: Mapping[str, object],
    key: str,
) -> JsonObject:
    value = validation_metadata.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"validation metadata {key} must be object")
    if not _is_json_mapping(value):
        raise ValueError(f"validation metadata {key} must be JSON object")
    return dict(value)


def _dispatch_schedule_payload(
    dispatch_payload: Mapping[str, object],
) -> Mapping[str, object]:
    schedule_payload = dispatch_payload.get("schedule_payload")
    if not isinstance(schedule_payload, Mapping):
        raise ValueError("dispatch payload schedule_payload must be mapping")
    return schedule_payload


def _mapping_text_tuple(
    payload: Mapping[str, object],
    key: str,
) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list | tuple):
        return ()
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{key} must contain non-empty strings")
        result.append(item)
    return tuple(result)


def _payload_text_tuple(
    payload: Mapping[str, object],
    key: str,
    *,
    allow_missing: bool,
) -> tuple[str, ...]:
    value = payload.get(key)
    if value is None and allow_missing:
        return ()
    if not isinstance(value, list | tuple):
        raise ValueError(f"workflow command payload {key} must be sequence")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"workflow command payload {key} must contain text")
        result.append(item)
    return tuple(result)


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


def _payload_optional_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow command payload {key} must be non-empty text")
    return value


def _payload_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"workflow command payload must include integer {key}")
    return value


def _datetime_payload(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
