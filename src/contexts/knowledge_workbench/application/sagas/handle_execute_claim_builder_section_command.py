from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TypeGuard
from typing import Protocol, cast

import structlog

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
    LlmAttemptCapacityObservationRepositoryPort,
)
from src.shared.json_value import JsonInputValue
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_attempt_decision_policy import (
    ClaimBuilderAttemptDecision,
    ClaimBuilderAttemptDecisionPolicy,
    ClaimBuilderAttemptOutcomeKind,
    ClaimBuilderNextModelStrategy,
    DecideClaimBuilderAttemptOutcomeCommand,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_attempt_next_action_policy import (
    ClaimBuilderAttemptNextAction,
    ClaimBuilderAttemptNextActionKind,
    ClaimBuilderAttemptNextActionPolicy,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_output_validation_policy import (
    ClaimBuilderOutputValidationDecision,
    ClaimBuilderOutputValidationFailureReason,
    ClaimBuilderOutputValidationPolicy,
    ClaimBuilderOutputValidationResult,
    ValidateClaimBuilderOutputCommand,
    ValidatedClaimBuilderClaim,
)
from src.contexts.knowledge_workbench.extraction.application.ports.validated_draft_claim_observation_persistence_port import (
    PersistValidatedDraftClaimObservationsPort,
    ValidatedDraftClaimObservationCandidate,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.application.sagas.append_capacity_window_prepare_wakeup import (
    append_capacity_window_prepare_wakeup,
)
from src.contexts.knowledge_workbench.application.sagas.capacity_window_workflow_events import (
    CLAIM_BUILDER_CANONICAL_PHASE,
    CLAIM_BUILDER_EXECUTE_OPERATION_KEY,
    capacity_exhaustion_from_observation,
    capacity_window_exhausted_event,
    capacity_window_scheduled_wakeup_event,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
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
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt import (
    ExecutePreparedLlmDispatchAttemptCommand,
    ExecutePreparedLlmDispatchAttemptResult,
    LlmDispatchOutputValidationResult,
)


LOGGER = structlog.get_logger(__name__)

DAILY_LIMIT_ERROR_KIND = "daily_limit"
MINUTE_LIMIT_ERROR_KIND = "minute_limit"
REQUEST_TOO_LARGE_ERROR_KIND = "request_too_large"
OUTPUT_TOO_LARGE_ERROR_KIND = "output_too_large"
AUTH_ERROR_KIND = "auth_error"
DAILY_LIMIT_FALLBACK_MODEL_STRATEGY = "DAILY_LIMIT_FALLBACK_MODEL_REQUIRED"
CLAIM_BUILDER_LOG_INVALID_RAW_OUTPUT_ENV = "CLAIM_BUILDER_LOG_INVALID_RAW_OUTPUT"


class ExecutePreparedLlmDispatchAttemptPort(Protocol):
    async def execute(
        self,
        command: ExecutePreparedLlmDispatchAttemptCommand,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class ClaimBuilderLlmDispatchOutputValidator:
    policy: ClaimBuilderOutputValidationPolicy
    decision_policy: ClaimBuilderAttemptDecisionPolicy = (
        ClaimBuilderAttemptDecisionPolicy()
    )
    next_action_policy: ClaimBuilderAttemptNextActionPolicy = (
        ClaimBuilderAttemptNextActionPolicy()
    )

    def validate(
        self,
        *,
        dispatch_payload: Mapping[str, object],
        output_payload: Mapping[str, object] | None,
        llm_status: LlmDispatchExecutionStatus,
        finished_at: datetime,
        attempt_number: int,
    ) -> LlmDispatchOutputValidationResult:
        if llm_status is not LlmDispatchExecutionStatus.SUCCEEDED:
            return LlmDispatchOutputValidationResult(
                status=llm_status,
                error_kind=None,
                next_attempt_at=None,
                metadata={
                    "validation_decision": None,
                    "validated_claim_count": 0,
                    "retry_recommended": False,
                },
            )

        raw_output_text = _raw_output_text(output_payload)
        decoded_output = _decoded_claim_builder_output(output_payload)
        validation_result: ClaimBuilderOutputValidationResult | None
        decoded_payload: JsonInputValue | None
        if isinstance(decoded_output, ClaimBuilderOutputValidationResult):
            validation_result = decoded_output
            decoded_payload = None
        else:
            decoded_payload = decoded_output
            validation_result = self.policy.validate(
                ValidateClaimBuilderOutputCommand(
                    output_payload=decoded_payload,
                    source_unit_text=_source_context_text(dispatch_payload),
                    source_unit_ref=_source_unit_ref(dispatch_payload),
                    empty_claims_attempt_count=max(attempt_number - 1, 0),
                )
            )

        decision = self.decision_policy.decide(
            DecideClaimBuilderAttemptOutcomeCommand(
                workflow_run_id=_dispatch_workflow_run_id(dispatch_payload),
                work_item_id=_dispatch_work_item_id(dispatch_payload),
                dispatch_attempt_id=_dispatch_attempt_id(dispatch_payload),
                attempt_number=attempt_number,
                provider=_dispatch_provider(dispatch_payload),
                model_ref=_dispatch_model_ref(dispatch_payload),
                output_payload=decoded_payload,
                raw_output_text=raw_output_text,
                source_unit_text=_source_context_text(dispatch_payload),
                is_output_truncated=_is_output_truncated(output_payload),
                validation_result=validation_result,
            )
        )
        next_action = self.next_action_policy.decide_next_action(decision)
        _log_invalid_raw_output_if_enabled(
            dispatch_payload=dispatch_payload,
            raw_output_text=raw_output_text,
            validation_result=validation_result,
            decision=decision,
        )
        return _decision_to_dispatch_result(
            decision=decision,
            next_action=next_action,
            finished_at=finished_at,
        )


def _log_invalid_raw_output_if_enabled(
    *,
    dispatch_payload: Mapping[str, object],
    raw_output_text: str | None,
    validation_result: ClaimBuilderOutputValidationResult,
    decision: ClaimBuilderAttemptDecision,
) -> None:
    if os.environ.get(CLAIM_BUILDER_LOG_INVALID_RAW_OUTPUT_ENV) != "1":
        return
    if validation_result.decision is ClaimBuilderOutputValidationDecision.VALID_CLAIMS:
        return
    if validation_result.decision is ClaimBuilderOutputValidationDecision.VALID_EMPTY:
        return

    LOGGER.warning(
        "knowledge_claim_builder_invalid_raw_output_debug",
        workflow_run_id=_dispatch_workflow_run_id(dispatch_payload),
        work_item_id=_dispatch_work_item_id(dispatch_payload),
        dispatch_attempt_id=_dispatch_attempt_id(dispatch_payload),
        provider=_dispatch_provider(dispatch_payload),
        model_ref=_dispatch_model_ref(dispatch_payload),
        validation_decision=validation_result.decision.value,
        validation_failure_reason=validation_result.failure_reason.value
        if validation_result.failure_reason is not None
        else None,
        outcome_kind=decision.outcome_kind.value,
        raw_output_text=raw_output_text,
    )


@dataclass(frozen=True, slots=True)
class HandleExecuteClaimBuilderSectionCommand:
    workflow_command: WorkflowCommand

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")


@dataclass(frozen=True, slots=True)
class HandleExecuteClaimBuilderSectionResult:
    workflow_run_id: str
    dispatch_attempt_id: str
    work_item_id: str
    outcome_status: str
    appended_event_count: int
    appended_next_command_count: int
    completed_command_id: WorkflowCommandId

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text(self.dispatch_attempt_id, "dispatch_attempt_id")
        _require_non_empty_text(self.work_item_id, "work_item_id")
        _require_non_empty_text(self.outcome_status, "outcome_status")
        _require_non_negative_int(self.appended_event_count, "appended_event_count")
        _require_non_negative_int(
            self.appended_next_command_count,
            "appended_next_command_count",
        )
        if not isinstance(self.completed_command_id, WorkflowCommandId):
            raise TypeError("completed_command_id must be WorkflowCommandId")


class HandleExecuteClaimBuilderSectionCommandHandler:
    async def execute(
        self,
        command: HandleExecuteClaimBuilderSectionCommand,
        *,
        execute_prepared_llm_dispatch_attempt: ExecutePreparedLlmDispatchAttemptPort,
        capacity_observation_repository: LlmAttemptCapacityObservationRepositoryPort,
        claim_builder_output_validation_policy: ClaimBuilderOutputValidationPolicy,
        draft_claim_observation_persistence: PersistValidatedDraftClaimObservationsPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
    ) -> HandleExecuteClaimBuilderSectionResult:
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
            workflow_command.payload,
            "dispatch_attempt_id",
        )
        work_item_id = _payload_text(workflow_command.payload, "work_item_id")
        LOGGER.info(
            "knowledge_claim_builder_execute_command_start",
            workflow_run_id=workflow_run_id,
            command_id=workflow_command.command_id.value,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
        )

        execution_result = cast(
            ExecutePreparedLlmDispatchAttemptResult,
            await execute_prepared_llm_dispatch_attempt.execute(
                ExecutePreparedLlmDispatchAttemptCommand(
                    attempt_id=dispatch_attempt_id,
                    output_validator=ClaimBuilderLlmDispatchOutputValidator(
                        policy=claim_builder_output_validation_policy,
                    ),
                ),
            ),
        )
        if execution_result.dispatch.work_item_id != work_item_id:
            raise ValueError(
                "dispatch work_item_id must match workflow command payload"
            )

        finished_at = execution_result.llm_result.finished_at
        outcome_status = execution_result.llm_result.status.value
        attempt_action_metadata = _attempt_action_metadata(execution_result)
        LOGGER.info(
            "knowledge_claim_builder_execute_llm_result",
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            outcome_status=outcome_status,
            error_kind=execution_result.llm_result.error_kind,
            next_attempt_at=execution_result.llm_result.next_attempt_at.isoformat()
            if execution_result.llm_result.next_attempt_at is not None
            else None,
            has_output_payload=execution_result.llm_result.output_payload is not None,
            validation_metadata=attempt_action_metadata,
        )

        capacity_observation = _capacity_observation_from_result(execution_result)
        appended_event_count = 0
        capacity_window_wakeup_count = 0

        if capacity_observation is not None:
            await capacity_observation_repository.record_observation(
                capacity_observation,
            )
            LOGGER.info(
                "knowledge_claim_builder_capacity_observation_record",
                workflow_run_id=workflow_run_id,
                dispatch_attempt_id=dispatch_attempt_id,
                work_item_id=work_item_id,
                provider=capacity_observation.provider,
                account_ref=capacity_observation.account_ref,
                model_ref=capacity_observation.model_ref,
                remaining_minute_requests=capacity_observation.remaining_minute_requests,
                remaining_minute_tokens=capacity_observation.remaining_minute_tokens,
                remaining_daily_requests=capacity_observation.remaining_daily_requests,
                remaining_daily_tokens=capacity_observation.remaining_daily_tokens,
                minute_reset_at=capacity_observation.minute_reset_at.isoformat()
                if capacity_observation.minute_reset_at is not None
                else None,
                outcome_class=capacity_observation.outcome_class,
            )
            persisted_capacity_event = await workflow_unit_of_work.outbox.append_event(
                _capacity_observed_event(
                    workflow_command=workflow_command,
                    workflow_run_id=workflow_run_id,
                    dispatch_attempt_id=dispatch_attempt_id,
                    work_item_id=work_item_id,
                    capacity_observation=capacity_observation,
                    occurred_at=finished_at,
                ),
            )
            if frontend_event_projection_writer is not None:
                await frontend_event_projection_writer.execute(
                    persisted_capacity_event,
                )
            appended_event_count += 1

            capacity_exhaustion = capacity_exhaustion_from_observation(
                capacity_observation=capacity_observation,
                workflow_run_id=workflow_run_id,
                dispatch_attempt_id=dispatch_attempt_id,
                work_item_id=work_item_id,
            )
            if capacity_exhaustion is not None:
                exhausted_event = capacity_window_exhausted_event(
                    workflow_run_id=workflow_run_id,
                    exhaustion=capacity_exhaustion,
                    operation_key=CLAIM_BUILDER_EXECUTE_OPERATION_KEY,
                    canonical_phase=CLAIM_BUILDER_CANONICAL_PHASE,
                    occurred_at=finished_at,
                    causation_command_id=workflow_command.command_id,
                    correlation_id=dispatch_attempt_id,
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

            wakeup = await append_capacity_window_prepare_wakeup(
                workflow_unit_of_work=workflow_unit_of_work,
                source_command=workflow_command,
                workflow_run_id=workflow_run_id,
                prepare_command_type=(
                    KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH
                ),
                capacity_observation=capacity_observation,
                occurred_at=finished_at,
            )
            if wakeup is not None:
                capacity_window_wakeup_count = 1
                scheduled_wakeup_event = capacity_window_scheduled_wakeup_event(
                    workflow_run_id=workflow_run_id,
                    provider=wakeup.provider,
                    account_ref=wakeup.account_ref,
                    model_ref=wakeup.model_ref,
                    run_after=wakeup.run_after,
                    reset_at=wakeup.reset_at,
                    wakeup_command_id=wakeup.command_id,
                    prepare_command_type=wakeup.prepare_command_type,
                    wakeup_reason=wakeup.wakeup_reason,
                    operation_key=CLAIM_BUILDER_EXECUTE_OPERATION_KEY,
                    canonical_phase=CLAIM_BUILDER_CANONICAL_PHASE,
                    occurred_at=finished_at,
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

        persisted_draft_claim_count = await _persist_validated_draft_claims(
            persistence=draft_claim_observation_persistence,
            execution_result=execution_result,
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
        )
        LOGGER.info(
            "knowledge_claim_builder_draft_claims_persisted",
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            persisted_draft_claim_count=persisted_draft_claim_count,
        )

        outcome_event = _claim_builder_attempt_outcome_event(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            execution_result=execution_result,
            capacity_observation=capacity_observation,
            validation_metadata=attempt_action_metadata,
            persisted_draft_claim_count=persisted_draft_claim_count,
        )
        persisted_outcome_event = await workflow_unit_of_work.outbox.append_event(
            outcome_event,
        )
        if frontend_event_projection_writer is not None:
            await frontend_event_projection_writer.execute(persisted_outcome_event)
        appended_event_count += 1

        next_command = _reconcile_claim_builder_progress_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            occurred_at=finished_at,
        )
        await workflow_unit_of_work.command_log.append_pending_command(next_command)
        appended_next_command_count = 1 + capacity_window_wakeup_count

        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_run_id=workflow_run_id,
            status=execution_result.llm_result.status,
            capacity_observation=capacity_observation,
            validation_metadata=attempt_action_metadata,
            persisted_draft_claim_count=persisted_draft_claim_count,
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
                validation_metadata=attempt_action_metadata,
                persisted_draft_claim_count=persisted_draft_claim_count,
            ),
        )

        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=finished_at,
        )

        LOGGER.info(
            "knowledge_claim_builder_execute_command_completed",
            workflow_run_id=workflow_run_id,
            command_id=workflow_command.command_id.value,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            outcome_status=outcome_status,
            appended_event_count=appended_event_count,
            appended_next_command_count=appended_next_command_count,
        )

        return HandleExecuteClaimBuilderSectionResult(
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            outcome_status=outcome_status,
            appended_event_count=appended_event_count,
            appended_next_command_count=appended_next_command_count,
            completed_command_id=workflow_command.command_id,
        )


def _decoded_claim_builder_output(
    output_payload: Mapping[str, object] | None,
) -> JsonInputValue | ClaimBuilderOutputValidationResult:
    if output_payload is None:
        return _synthetic_validation_failure(
            ClaimBuilderOutputValidationFailureReason.OUTPUT_NOT_OBJECT,
        )

    raw_text = output_payload.get("raw_text")
    if isinstance(raw_text, str):
        try:
            decoded = json.loads(raw_text)
        except json.JSONDecodeError:
            return _synthetic_validation_failure(
                ClaimBuilderOutputValidationFailureReason.INVALID_JSON_RETRY_REQUIRED,
            )
        if _is_json_input_value(decoded):
            return decoded
        return _synthetic_validation_failure(
            ClaimBuilderOutputValidationFailureReason.OUTPUT_NOT_OBJECT,
        )

    if _is_json_input_value(output_payload):
        return output_payload

    return _synthetic_validation_failure(
        ClaimBuilderOutputValidationFailureReason.OUTPUT_NOT_OBJECT,
    )


def _is_json_input_value(value: object) -> TypeGuard[JsonInputValue]:
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, list):
        return all(_is_json_input_value(item) for item in value)
    if isinstance(value, tuple):
        return all(_is_json_input_value(item) for item in value)
    if isinstance(value, Mapping):
        return all(
            isinstance(key, str) and _is_json_input_value(item)
            for key, item in value.items()
        )
    return False


def _synthetic_validation_failure(
    failure_reason: ClaimBuilderOutputValidationFailureReason,
) -> ClaimBuilderOutputValidationResult:
    return ClaimBuilderOutputValidationResult(
        decision=ClaimBuilderOutputValidationDecision.RETRY_SAME_ROUTE,
        claims=(),
        failure_reason=failure_reason,
    )


def _source_context_text(dispatch_payload: Mapping[str, object]) -> str:
    full_user_message = _source_user_message_content(dispatch_payload)
    if full_user_message.strip():
        return full_user_message
    return _source_unit_text(dispatch_payload)


def _source_user_message_content(dispatch_payload: Mapping[str, object]) -> str:
    schedule_payload = dispatch_payload.get("schedule_payload")
    if not isinstance(schedule_payload, Mapping):
        return ""

    provider_messages = schedule_payload.get("provider_messages")
    if not isinstance(provider_messages, list):
        return ""

    for message in provider_messages:
        if not isinstance(message, Mapping):
            continue

        role = message.get("role")
        content = message.get("content")
        if role == "user" and isinstance(content, str):
            return content

    return ""


def _source_unit_text(dispatch_payload: Mapping[str, object]) -> str:
    schedule_payload = dispatch_payload.get("schedule_payload")
    if not isinstance(schedule_payload, Mapping):
        raise ValueError("dispatch payload schedule_payload must be mapping")

    provider_messages = schedule_payload.get("provider_messages")
    if not isinstance(provider_messages, (list, tuple)):
        raise ValueError("schedule_payload provider_messages must be list")

    for raw_message in provider_messages:
        if not isinstance(raw_message, Mapping):
            continue
        role = raw_message.get("role")
        content = raw_message.get("content")
        if role == "user" and isinstance(content, str):
            source_unit_text = _source_text_from_user_message(content)
            if source_unit_text.strip():
                return source_unit_text

    raise ValueError("source_unit_text missing from claim builder dispatch payload")


def _source_text_from_user_message(content: str) -> str:
    _, separator, source_text = content.partition("\n\n")
    if not separator:
        return ""
    return source_text


def _decision_to_dispatch_result(
    *,
    decision: ClaimBuilderAttemptDecision,
    next_action: ClaimBuilderAttemptNextAction,
    finished_at: datetime,
) -> LlmDispatchOutputValidationResult:
    metadata = _decision_metadata(decision, next_action=next_action)
    if decision.outcome_kind in {
        ClaimBuilderAttemptOutcomeKind.VALID_CLAIMS,
        ClaimBuilderAttemptOutcomeKind.VALID_EMPTY,
    }:
        return LlmDispatchOutputValidationResult(
            status=LlmDispatchExecutionStatus.SUCCEEDED,
            error_kind=None,
            next_attempt_at=None,
            metadata=metadata,
        )

    if decision.outcome_kind is ClaimBuilderAttemptOutcomeKind.TERMINAL_INVALID:
        return LlmDispatchOutputValidationResult(
            status=LlmDispatchExecutionStatus.TERMINAL_FAILED,
            error_kind="claim_builder_output_validation_failed",
            next_attempt_at=None,
            metadata=metadata,
        )

    return LlmDispatchOutputValidationResult(
        status=LlmDispatchExecutionStatus.RETRYABLE_FAILED,
        error_kind="claim_builder_output_validation_failed",
        next_attempt_at=None,
        metadata=metadata,
    )


def _decision_metadata(
    decision: ClaimBuilderAttemptDecision,
    *,
    next_action: ClaimBuilderAttemptNextAction,
) -> dict[str, object]:
    return {
        "claim_builder_attempt_outcome_kind": decision.outcome_kind.value,
        "claim_builder_attempt_next_action_kind": next_action.kind.value,
        "claim_builder_attempt_next_action_reason": next_action.reason,
        "claim_builder_attempt_next_model_strategy": (
            next_action.next_model_strategy.value
            if next_action.next_model_strategy is not None
            else None
        ),
        "claim_builder_should_persist_claims": next_action.should_persist_claims,
        "claim_builder_should_mark_work_item_completed": (
            next_action.should_mark_work_item_completed
        ),
        "claim_builder_requires_source_split": next_action.requires_source_split,
        "claim_builder_next_run_after": (
            next_action.run_after.isoformat()
            if next_action.run_after is not None
            else None
        ),
        "validation_decision": (
            decision.validation_decision.value
            if decision.validation_decision is not None
            else None
        ),
        "validation_failure_reason": (
            decision.validation_failure_reason.value
            if decision.validation_failure_reason is not None
            else None
        ),
        "validated_claim_count": len(decision.claims),
        "next_model_strategy": (
            decision.next_model_strategy.value
            if decision.next_model_strategy is not None
            else None
        ),
        "retry_recommended": decision.retry_recommended,
        "_validated_claims": decision.claims,
    }


def _apply_validation_counters(
    *,
    domain_counters: dict[str, int],
    validation_metadata: Mapping[str, object] | None,
) -> None:
    if validation_metadata is None:
        return

    decision = validation_metadata.get("validation_decision")
    claim_count = validation_metadata.get("validated_claim_count")
    if not isinstance(claim_count, int):
        claim_count = 0

    if decision in {
        ClaimBuilderOutputValidationDecision.VALID_CLAIMS.value,
        ClaimBuilderOutputValidationDecision.VALID_EMPTY.value,
    }:
        domain_counters["claim_builder_valid_output_count"] = (
            domain_counters.get("claim_builder_valid_output_count", 0) + 1
        )
        domain_counters["claim_builder_valid_claim_count"] = (
            domain_counters.get("claim_builder_valid_claim_count", 0) + claim_count
        )
        return

    if decision in {
        ClaimBuilderOutputValidationDecision.RETRY_SAME_ROUTE.value,
        ClaimBuilderOutputValidationDecision.RETRY_EMPTY_CLAIMS_CHECK_MODEL.value,
        ClaimBuilderOutputValidationDecision.RETRY_FALLBACK_MODEL.value,
        ClaimBuilderOutputValidationDecision.RETRY_LARGER_OUTPUT_LIMIT_MODEL.value,
    }:
        domain_counters["claim_builder_invalid_output_count"] = (
            domain_counters.get("claim_builder_invalid_output_count", 0) + 1
        )
        domain_counters["claim_builder_validation_retryable_failed_count"] = (
            domain_counters.get(
                "claim_builder_validation_retryable_failed_count",
                0,
            )
            + 1
        )

    _apply_next_action_counters(
        domain_counters=domain_counters,
        validation_metadata=validation_metadata,
    )


def _apply_next_action_counters(
    *,
    domain_counters: dict[str, int],
    validation_metadata: Mapping[str, object] | None,
) -> None:
    if validation_metadata is None:
        return

    action_kind = validation_metadata.get("claim_builder_attempt_next_action_kind")
    if not isinstance(action_kind, str):
        return

    if action_kind == ClaimBuilderAttemptNextActionKind.ACCEPT_VALID_EMPTY.value:
        domain_counters["sections_with_valid_empty_claims"] = (
            domain_counters.get("sections_with_valid_empty_claims", 0) + 1
        )
        return

    if action_kind in {
        ClaimBuilderAttemptNextActionKind.RETRY_SAME_ROUTE.value,
        ClaimBuilderAttemptNextActionKind.RETRY_EMPTY_CLAIMS_CHECK_MODEL.value,
        ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL.value,
        ClaimBuilderAttemptNextActionKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL.value,
        ClaimBuilderAttemptNextActionKind.RETRY_LARGER_INPUT_LIMIT_MODEL.value,
    }:
        domain_counters["claim_builder_retry_action_count"] = (
            domain_counters.get("claim_builder_retry_action_count", 0) + 1
        )

    if (
        action_kind
        == ClaimBuilderAttemptNextActionKind.RETRY_EMPTY_CLAIMS_CHECK_MODEL.value
    ):
        domain_counters["claim_builder_empty_claims_check_retry_required_count"] = (
            domain_counters.get(
                "claim_builder_empty_claims_check_retry_required_count",
                0,
            )
            + 1
        )
        return

    if action_kind == ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL.value:
        domain_counters["claim_builder_fallback_retry_required_count"] = (
            domain_counters.get("claim_builder_fallback_retry_required_count", 0) + 1
        )
        return

    if (
        action_kind
        == ClaimBuilderAttemptNextActionKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL.value
    ):
        domain_counters["claim_builder_larger_output_retry_required_count"] = (
            domain_counters.get(
                "claim_builder_larger_output_retry_required_count",
                0,
            )
            + 1
        )
        return

    if (
        action_kind
        == ClaimBuilderAttemptNextActionKind.RETRY_LARGER_INPUT_LIMIT_MODEL.value
    ):
        domain_counters["claim_builder_larger_input_retry_required_count"] = (
            domain_counters.get(
                "claim_builder_larger_input_retry_required_count",
                0,
            )
            + 1
        )
        return

    if (
        action_kind
        == ClaimBuilderAttemptNextActionKind.DEFER_UNTIL_CAPACITY_RESET.value
    ):
        domain_counters["claim_builder_capacity_wait_required_count"] = (
            domain_counters.get("claim_builder_capacity_wait_required_count", 0) + 1
        )
        return

    if (
        action_kind
        == ClaimBuilderAttemptNextActionKind.PAUSE_FOR_DAILY_LIMIT_RESET.value
    ):
        domain_counters["claim_builder_daily_reset_wait_required_count"] = (
            domain_counters.get(
                "claim_builder_daily_reset_wait_required_count",
                0,
            )
            + 1
        )
        return

    if action_kind == ClaimBuilderAttemptNextActionKind.TERMINAL_FAILURE.value:
        domain_counters["claim_builder_terminal_invalid_count"] = (
            domain_counters.get("claim_builder_terminal_invalid_count", 0) + 1
        )


def _raw_output_text(output_payload: Mapping[str, object] | None) -> str | None:
    if output_payload is None:
        return None
    value = output_payload.get("raw_text")
    return value if isinstance(value, str) else None


def _is_output_truncated(output_payload: Mapping[str, object] | None) -> bool:
    if output_payload is None:
        return False
    for key in ("output_truncated", "is_truncated", "truncated"):
        value = output_payload.get(key)
        if isinstance(value, bool):
            return value
    finish_reason = output_payload.get("finish_reason")
    return finish_reason == "length"


def _dispatch_workflow_run_id(dispatch_payload: Mapping[str, object]) -> str:
    schedule_payload = _dispatch_schedule_payload(dispatch_payload)
    value = schedule_payload.get("workflow_run_id")
    if isinstance(value, str) and value.strip():
        return value
    return "unknown-workflow-run"


def _dispatch_work_item_id(dispatch_payload: Mapping[str, object]) -> str:
    value = dispatch_payload.get("work_item_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("dispatch payload work_item_id must be non-empty")
    return value


def _dispatch_attempt_id(dispatch_payload: Mapping[str, object]) -> str:
    value = dispatch_payload.get("attempt_id")
    if isinstance(value, str) and value.strip():
        return value
    return "unknown-dispatch-attempt"


def _dispatch_provider(dispatch_payload: Mapping[str, object]) -> str:
    allocation = _allocation_mapping(dispatch_payload)
    value = allocation.get("provider")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("llm_allocation provider must be non-empty")
    return value


def _dispatch_model_ref(dispatch_payload: Mapping[str, object]) -> str:
    allocation = _allocation_mapping(dispatch_payload)
    value = allocation.get("model_ref")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("llm_allocation model_ref must be non-empty")
    return value


def _allocation_mapping(dispatch_payload: Mapping[str, object]) -> Mapping[str, object]:
    allocation = dispatch_payload.get("llm_allocation")
    if not isinstance(allocation, Mapping):
        raise ValueError("dispatch payload llm_allocation must be mapping")
    return allocation


def _dispatch_schedule_payload(
    dispatch_payload: Mapping[str, object],
) -> Mapping[str, object]:
    schedule_payload = dispatch_payload.get("schedule_payload")
    if not isinstance(schedule_payload, Mapping):
        raise ValueError("dispatch payload schedule_payload must be mapping")
    return schedule_payload


async def _persist_validated_draft_claims(
    *,
    persistence: PersistValidatedDraftClaimObservationsPort,
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
) -> int:
    if not _should_persist_claims(execution_result.validation_metadata):
        return 0

    claims = _validated_claims_from_metadata(execution_result.validation_metadata)
    if not claims:
        return 0

    result = await persistence.persist_validated_claims(
        _draft_claim_candidates(
            execution_result=execution_result,
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            claims=claims,
        )
    )
    return result.persisted_count


def _attempt_action_metadata(
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
) -> Mapping[str, object] | None:
    if execution_result.validation_metadata is not None:
        return execution_result.validation_metadata
    return _provider_retry_metadata(execution_result)


def _provider_retry_metadata(
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
) -> dict[str, object] | None:
    error_kind = execution_result.llm_result.error_kind
    next_attempt_at = execution_result.llm_result.next_attempt_at
    if error_kind == MINUTE_LIMIT_ERROR_KIND:
        if next_attempt_at is None:
            return None
        return {
            "claim_builder_attempt_outcome_kind": (
                ClaimBuilderAttemptOutcomeKind.RETRY_SAME_ROUTE.value
            ),
            "claim_builder_attempt_next_action_kind": (
                ClaimBuilderAttemptNextActionKind.DEFER_UNTIL_CAPACITY_RESET.value
            ),
            "claim_builder_attempt_next_action_reason": MINUTE_LIMIT_ERROR_KIND,
            "claim_builder_attempt_next_model_strategy": (
                ClaimBuilderNextModelStrategy.SAME_MODEL.value
            ),
            "claim_builder_should_persist_claims": False,
            "claim_builder_should_mark_work_item_completed": False,
            "claim_builder_requires_source_split": False,
            "claim_builder_next_run_after": next_attempt_at.isoformat(),
            "validation_decision": None,
            "validation_failure_reason": None,
            "validated_claim_count": 0,
            "next_model_strategy": ClaimBuilderNextModelStrategy.SAME_MODEL.value,
            "retry_recommended": True,
        }
    if error_kind == DAILY_LIMIT_ERROR_KIND:
        return {
            "claim_builder_attempt_outcome_kind": (
                ClaimBuilderAttemptOutcomeKind.RETRY_FALLBACK_MODEL.value
            ),
            "claim_builder_attempt_next_action_kind": (
                ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL.value
            ),
            "claim_builder_attempt_next_action_reason": DAILY_LIMIT_ERROR_KIND,
            "claim_builder_attempt_next_model_strategy": (
                DAILY_LIMIT_FALLBACK_MODEL_STRATEGY
            ),
            "claim_builder_should_persist_claims": False,
            "claim_builder_should_mark_work_item_completed": False,
            "claim_builder_requires_source_split": False,
            "claim_builder_next_run_after": None,
            "validation_decision": None,
            "validation_failure_reason": None,
            "validated_claim_count": 0,
            "next_model_strategy": DAILY_LIMIT_FALLBACK_MODEL_STRATEGY,
            "retry_recommended": True,
        }
    if error_kind == REQUEST_TOO_LARGE_ERROR_KIND:
        return {
            "claim_builder_attempt_outcome_kind": (
                ClaimBuilderAttemptOutcomeKind.RETRY_LARGER_INPUT_LIMIT_MODEL.value
            ),
            "claim_builder_attempt_next_action_kind": (
                ClaimBuilderAttemptNextActionKind.RETRY_LARGER_INPUT_LIMIT_MODEL.value
            ),
            "claim_builder_attempt_next_action_reason": (REQUEST_TOO_LARGE_ERROR_KIND),
            "claim_builder_attempt_next_model_strategy": (
                ClaimBuilderNextModelStrategy.LARGER_INPUT_LIMIT_MODEL_REQUIRED.value
            ),
            "claim_builder_should_persist_claims": False,
            "claim_builder_should_mark_work_item_completed": False,
            "claim_builder_requires_source_split": False,
            "claim_builder_next_run_after": None,
            "validation_decision": None,
            "validation_failure_reason": None,
            "validated_claim_count": 0,
            "next_model_strategy": (
                ClaimBuilderNextModelStrategy.LARGER_INPUT_LIMIT_MODEL_REQUIRED.value
            ),
            "retry_recommended": True,
        }
    if error_kind == OUTPUT_TOO_LARGE_ERROR_KIND:
        return {
            "claim_builder_attempt_outcome_kind": (
                ClaimBuilderAttemptOutcomeKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL.value
            ),
            "claim_builder_attempt_next_action_kind": (
                ClaimBuilderAttemptNextActionKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL.value
            ),
            "claim_builder_attempt_next_action_reason": OUTPUT_TOO_LARGE_ERROR_KIND,
            "claim_builder_attempt_next_model_strategy": (
                ClaimBuilderNextModelStrategy.LARGER_OUTPUT_LIMIT_MODEL_REQUIRED.value
            ),
            "claim_builder_should_persist_claims": False,
            "claim_builder_should_mark_work_item_completed": False,
            "claim_builder_requires_source_split": False,
            "claim_builder_next_run_after": None,
            "validation_decision": None,
            "validation_failure_reason": None,
            "validated_claim_count": 0,
            "next_model_strategy": (
                ClaimBuilderNextModelStrategy.LARGER_OUTPUT_LIMIT_MODEL_REQUIRED.value
            ),
            "retry_recommended": True,
        }
    if error_kind in {
        "invalid_output",
        "validation_failed",
        "empty_output",
        "network_error",
        "unknown",
    }:
        return {
            "claim_builder_attempt_outcome_kind": (
                ClaimBuilderAttemptOutcomeKind.RETRY_SAME_ROUTE.value
            ),
            "claim_builder_attempt_next_action_kind": (
                ClaimBuilderAttemptNextActionKind.RETRY_SAME_ROUTE.value
            ),
            "claim_builder_attempt_next_action_reason": error_kind,
            "claim_builder_attempt_next_model_strategy": (
                ClaimBuilderNextModelStrategy.SAME_MODEL.value
            ),
            "claim_builder_should_persist_claims": False,
            "claim_builder_should_mark_work_item_completed": False,
            "claim_builder_requires_source_split": False,
            "claim_builder_next_run_after": None,
            "validation_decision": None,
            "validation_failure_reason": None,
            "validated_claim_count": 0,
            "next_model_strategy": ClaimBuilderNextModelStrategy.SAME_MODEL.value,
            "retry_recommended": True,
        }
    if error_kind == AUTH_ERROR_KIND:
        return {
            "claim_builder_attempt_outcome_kind": (
                ClaimBuilderAttemptOutcomeKind.TERMINAL_INVALID.value
            ),
            "claim_builder_attempt_next_action_kind": (
                ClaimBuilderAttemptNextActionKind.TERMINAL_FAILURE.value
            ),
            "claim_builder_attempt_next_action_reason": AUTH_ERROR_KIND,
            "claim_builder_attempt_next_model_strategy": None,
            "claim_builder_should_persist_claims": False,
            "claim_builder_should_mark_work_item_completed": False,
            "claim_builder_requires_source_split": False,
            "claim_builder_next_run_after": None,
            "validation_decision": None,
            "validation_failure_reason": None,
            "validated_claim_count": 0,
            "next_model_strategy": None,
            "retry_recommended": False,
        }
    return None


def _should_persist_claims(
    validation_metadata: Mapping[str, object] | None,
) -> bool:
    if validation_metadata is None:
        return False

    action_kind = validation_metadata.get("claim_builder_attempt_next_action_kind")
    should_persist = validation_metadata.get("claim_builder_should_persist_claims")
    return (
        action_kind == ClaimBuilderAttemptNextActionKind.PERSIST_VALID_CLAIMS.value
        and should_persist is True
    )


def _validated_claims_from_metadata(
    validation_metadata: Mapping[str, object] | None,
) -> tuple[ValidatedClaimBuilderClaim, ...]:
    if validation_metadata is None:
        return ()
    value = validation_metadata.get("_validated_claims")
    if not isinstance(value, tuple):
        return ()
    claims: list[ValidatedClaimBuilderClaim] = []
    for item in value:
        if not isinstance(item, ValidatedClaimBuilderClaim):
            raise TypeError("_validated_claims must contain ValidatedClaimBuilderClaim")
        claims.append(item)
    return tuple(claims)


def _draft_claim_candidates(
    *,
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    claims: tuple[ValidatedClaimBuilderClaim, ...],
) -> tuple[ValidatedDraftClaimObservationCandidate, ...]:
    dispatch_payload = execution_result.dispatch.dispatch_payload
    schedule_payload = _dispatch_schedule_payload(dispatch_payload)
    allocation = _allocation_mapping(dispatch_payload)
    provider = _require_mapping_text(allocation, "provider")
    model_ref = _require_mapping_text(allocation, "model_ref")
    source_unit_ref = _source_unit_ref(dispatch_payload)
    claim_builder_provenance = _claim_builder_provenance(
        schedule_payload=schedule_payload,
        workflow_run_id=workflow_run_id,
        source_unit_ref=source_unit_ref,
        work_item_id=work_item_id,
    )
    validation_decision = _validation_decision_text(
        execution_result.validation_metadata
    )

    candidates: list[ValidatedDraftClaimObservationCandidate] = []
    for index, claim in enumerate(claims):
        candidates.append(
            ValidatedDraftClaimObservationCandidate(
                workflow_run_id=workflow_run_id,
                stage_run_id=_require_mapping_text(
                    claim_builder_provenance,
                    "stage_run_id",
                ),
                prompt_id=_require_mapping_text(
                    claim_builder_provenance,
                    "prompt_id",
                ),
                prompt_version=_require_mapping_text(
                    claim_builder_provenance,
                    "prompt_version",
                ),
                source_document_ref=_optional_mapping_text(
                    schedule_payload,
                    "source_document_ref",
                ),
                source_unit_ref=source_unit_ref,
                source_unit_ordinal=_optional_mapping_int(
                    schedule_payload,
                    "source_unit_ordinal",
                ),
                work_item_id=work_item_id,
                dispatch_attempt_id=dispatch_attempt_id,
                claim_index=index,
                provider=provider,
                model_ref=model_ref,
                claim=claim.claim,
                granularity=claim.granularity,
                possible_questions=claim.possible_questions,
                exclusion_scope=claim.exclusion_scope,
                evidence_block=claim.evidence_block,
                validation_decision=validation_decision,
            )
        )
    return tuple(candidates)


def _claim_builder_provenance(
    *,
    schedule_payload: Mapping[str, object],
    workflow_run_id: str,
    source_unit_ref: str,
    work_item_id: str,
) -> Mapping[str, object]:
    value = schedule_payload.get("claim_builder_provenance")
    if not isinstance(value, Mapping):
        raise ValueError("schedule_payload claim_builder_provenance must be mapping")

    provenance_workflow_run_id = _require_mapping_text(value, "workflow_run_id")
    if provenance_workflow_run_id != workflow_run_id:
        raise ValueError(
            "claim_builder_provenance workflow_run_id must match workflow_run_id"
        )

    provenance_source_unit_ref = _require_mapping_text(value, "source_unit_ref")
    if provenance_source_unit_ref != source_unit_ref:
        raise ValueError(
            "claim_builder_provenance source_unit_ref must match source_unit_ref"
        )

    provenance_work_item_id = _require_mapping_text(value, "work_item_id")
    if provenance_work_item_id != work_item_id:
        raise ValueError(
            "claim_builder_provenance work_item_id must match work_item_id"
        )

    _require_mapping_text(value, "stage_run_id")
    _require_mapping_text(value, "prompt_id")
    _require_mapping_text(value, "prompt_version")
    return value


def _source_unit_ref(dispatch_payload: Mapping[str, object]) -> str:
    schedule_payload = _dispatch_schedule_payload(dispatch_payload)
    direct = _optional_mapping_text(schedule_payload, "source_unit_ref")
    if direct is not None:
        return direct

    provider_messages = schedule_payload.get("provider_messages")
    if not isinstance(provider_messages, (list, tuple)):
        raise ValueError("schedule_payload provider_messages must be list")

    for raw_message in provider_messages:
        if not isinstance(raw_message, Mapping):
            continue
        content = raw_message.get("content")
        if isinstance(content, str):
            for line in content.splitlines():
                if line.startswith("source_unit_ref:"):
                    value = line.removeprefix("source_unit_ref:").strip()
                    if value:
                        return value
    raise ValueError("source_unit_ref missing from claim builder dispatch payload")


def _source_document_ref(dispatch_payload: Mapping[str, object]) -> str:
    schedule_payload = _dispatch_schedule_payload(dispatch_payload)
    value = _optional_mapping_text(schedule_payload, "source_document_ref")
    if value is None:
        raise ValueError(
            "source_document_ref missing from claim builder dispatch payload"
        )
    return value


def _validation_decision_text(
    validation_metadata: Mapping[str, object] | None,
) -> str:
    if validation_metadata is None:
        raise ValueError("validation_metadata is required for draft claim persistence")
    value = validation_metadata.get("validation_decision")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("validation_decision must be non-empty")
    return value


def _public_validation_metadata(
    validation_metadata: Mapping[str, object],
) -> dict[str, object]:
    return {
        key: value
        for key, value in validation_metadata.items()
        if not key.startswith("_")
    }


def _require_mapping_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value


def _optional_mapping_text(
    payload: Mapping[str, object],
    key: str,
) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text when provided")
    return value


def _optional_mapping_int(
    payload: Mapping[str, object],
    key: str,
) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError(f"{key} must be int when provided")
    return value


def _validate_workflow_command(workflow_command: WorkflowCommand) -> None:
    if (
        workflow_command.command_type
        != KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
    ):
        raise ValueError(
            "workflow_command command_type must be ExecuteClaimBuilderSection"
        )
    if workflow_command.status is not WorkflowCommandStatus.PENDING:
        raise ValueError("workflow_command status must be PENDING")


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
    occurred_at,
) -> WorkflowEvent:
    payload = {
        "workflow_run_id": workflow_run_id,
        "dispatch_attempt_id": dispatch_attempt_id,
        "work_item_id": work_item_id,
        "operation_key": "execute_claim_builder_section",
        "canonical_phase": (
            KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
        ),
        **capacity_observation.to_event_payload(),
    }
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value}:"
            f"{dispatch_attempt_id}"
        ),
        event_type=KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value,
        workflow_run_id=workflow_run_id,
        payload=payload,
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=dispatch_attempt_id,
    )


def _claim_builder_attempt_outcome_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
    capacity_observation: LlmAttemptCapacityObservation | None,
    validation_metadata: Mapping[str, object] | None,
    persisted_draft_claim_count: int,
) -> WorkflowEvent:
    event_type = _event_type_for_status(execution_result.llm_result.status)
    payload = _event_payload(
        workflow_run_id=workflow_run_id,
        dispatch_attempt_id=dispatch_attempt_id,
        work_item_id=work_item_id,
        execution_result=execution_result,
        capacity_observation=capacity_observation,
        validation_metadata=validation_metadata,
        persisted_draft_claim_count=persisted_draft_claim_count,
    )
    return WorkflowEvent(
        event_id=WorkflowEventId(
            f"workflow-event:{workflow_run_id}:{event_type.value}:{dispatch_attempt_id}"
        ),
        event_type=event_type.value,
        workflow_run_id=workflow_run_id,
        payload=payload,
        occurred_at=execution_result.llm_result.finished_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=dispatch_attempt_id,
    )


def _event_type_for_status(
    status: LlmDispatchExecutionStatus,
) -> KnowledgeExtractionCanonicalEventType:
    if status is LlmDispatchExecutionStatus.SUCCEEDED:
        return KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTED
    if status is LlmDispatchExecutionStatus.DEFERRED:
        return KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED
    if status is LlmDispatchExecutionStatus.RETRYABLE_FAILED:
        return KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED
    if status is LlmDispatchExecutionStatus.TERMINAL_FAILED:
        return KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_TERMINAL_FAILED
    raise ValueError("unsupported LLM dispatch execution status")


def _event_payload(
    *,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
    capacity_observation: LlmAttemptCapacityObservation | None,
    validation_metadata: Mapping[str, object] | None,
    persisted_draft_claim_count: int,
) -> dict[str, object]:
    capacity_payload = (
        capacity_observation.to_event_payload()
        if capacity_observation is not None
        else _allocation_payload(execution_result.dispatch.dispatch_payload)
    )
    payload: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "source_document_ref": _source_document_ref(
            execution_result.dispatch.dispatch_payload
        ),
        "source_unit_ref": _source_unit_ref(execution_result.dispatch.dispatch_payload),
        "dispatch_attempt_id": dispatch_attempt_id,
        "work_item_id": work_item_id,
        "operation_key": "execute_claim_builder_section",
        "canonical_phase": (
            KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
        ),
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "outcome_status": execution_result.llm_result.status.value,
        "error_kind": execution_result.llm_result.error_kind,
        "next_attempt_at": _datetime_payload(
            execution_result.llm_result.next_attempt_at
        ),
        "provider": capacity_payload.get("provider"),
        "account_ref": capacity_payload.get("account_ref"),
        "model_ref": capacity_payload.get("model_ref"),
        "actual_prompt_tokens": capacity_payload.get("actual_prompt_tokens"),
        "actual_completion_tokens": capacity_payload.get("actual_completion_tokens"),
        "actual_total_tokens": capacity_payload.get("actual_total_tokens"),
    }
    if validation_metadata is not None:
        payload.update(_public_validation_metadata(validation_metadata))
    payload["persisted_draft_claim_count"] = persisted_draft_claim_count
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


def _reconcile_claim_builder_progress_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    occurred_at,
) -> WorkflowCommand:
    idempotency_key = (
        f"reconcile-claim-builder-progress:{workflow_run_id}:{dispatch_attempt_id}"
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.RECONCILE_CLAIM_BUILDER_PROGRESS.value
        ),
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload=_reconcile_command_payload(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
        ),
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _reconcile_command_payload(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "dispatch_attempt_id": dispatch_attempt_id,
        "work_item_id": work_item_id,
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
    }
    dispatch_preparation = workflow_command.payload.get("llm_dispatch_preparation")
    if dispatch_preparation is not None:
        if not isinstance(dispatch_preparation, Mapping):
            raise ValueError("llm_dispatch_preparation must be mapping")
        payload["llm_dispatch_preparation"] = dict(dispatch_preparation)

    for key in (
        "claim_builder_prepare_command_id",
        "claim_builder_prepare_idempotency_key",
    ):
        value = _optional_mapping_text(workflow_command.payload, key)
        if value is not None:
            payload[key] = value

    return payload


async def _save_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_run_id: str,
    status: LlmDispatchExecutionStatus,
    capacity_observation: LlmAttemptCapacityObservation | None,
    validation_metadata: Mapping[str, object] | None,
    persisted_draft_claim_count: int,
    occurred_at,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_run_id,
    )
    domain_counters = dict(existing.domain_counters) if existing is not None else {}
    domain_counters["executed_attempt_count"] = (
        domain_counters.get("executed_attempt_count", 0) + 1
    )
    if capacity_observation is not None:
        domain_counters["capacity_observation_count"] = (
            domain_counters.get("capacity_observation_count", 0) + 1
        )

    _apply_validation_counters(
        domain_counters=domain_counters,
        validation_metadata=validation_metadata,
    )
    if persisted_draft_claim_count:
        domain_counters["claim_builder_persisted_draft_claim_count"] = (
            domain_counters.get("claim_builder_persisted_draft_claim_count", 0)
            + persisted_draft_claim_count
        )
        domain_counters["draft_claim_observation_count"] = (
            domain_counters.get("draft_claim_observation_count", 0)
            + persisted_draft_claim_count
        )

    completed_delta = 1 if status is LlmDispatchExecutionStatus.SUCCEEDED else 0
    deferred_delta = 1 if status is LlmDispatchExecutionStatus.DEFERRED else 0
    retryable_delta = 1 if status is LlmDispatchExecutionStatus.RETRYABLE_FAILED else 0
    terminal_delta = 1 if status is LlmDispatchExecutionStatus.TERMINAL_FAILED else 0

    running_before = existing.running_work_items if existing is not None else 0

    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=workflow_run_id,
            current_phase="CLAIM_BUILDER_SECTION_EXTRACTION",
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
        ),
    )


def _timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
    capacity_observation: LlmAttemptCapacityObservation | None,
    validation_metadata: Mapping[str, object] | None,
    persisted_draft_claim_count: int,
) -> WorkflowTimelineEntry:
    event_type = _event_type_for_status(execution_result.llm_result.status)
    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{workflow_run_id}:"
            f"ClaimBuilderSectionAttemptExecuted:{dispatch_attempt_id}"
        ),
        workflow_run_id=workflow_run_id,
        event_type=event_type.value,
        phase="CLAIM_BUILDER_SECTION_EXTRACTION",
        severity=_severity_for_status(execution_result.llm_result.status),
        message="Claim builder section attempt executed",
        payload_summary=_event_payload(
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            execution_result=execution_result,
            capacity_observation=capacity_observation,
            validation_metadata=validation_metadata,
            persisted_draft_claim_count=persisted_draft_claim_count,
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


def _datetime_payload(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
