from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)
from src.domain.project_plane.json_types import JsonObject


class DraftClaimCompactionDegradedFallbackNotPendingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionDegradedFallbackDecision:
    source_command_id: WorkflowCommandId
    source_command_payload: JsonObject
    degraded_model_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_command_id, WorkflowCommandId):
            raise TypeError("source_command_id must be WorkflowCommandId")
        _require_non_empty_text(self.degraded_model_ref, "degraded_model_ref")


class DraftClaimCompactionDegradedFallbackDecisionRepositoryPort(Protocol):
    async def load_pending_decision(
        self,
        *,
        workflow_run_id: str,
        project_id: str,
    ) -> DraftClaimCompactionDegradedFallbackDecision | None: ...


@dataclass(frozen=True, slots=True)
class ConfirmDraftClaimCompactionDegradedFallbackCommand:
    workflow_run_id: str
    project_id: str
    actor_user_id: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text(self.project_id, "project_id")
        _require_non_empty_text(self.actor_user_id, "actor_user_id")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ConfirmDraftClaimCompactionDegradedFallbackResult:
    workflow_run_id: str
    degraded_model_ref: str
    appended_command_id: WorkflowCommandId


@dataclass(frozen=True, slots=True)
class ConfirmDraftClaimCompactionDegradedFallback:
    decision_repository: DraftClaimCompactionDegradedFallbackDecisionRepositoryPort
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort

    async def execute(
        self,
        command: ConfirmDraftClaimCompactionDegradedFallbackCommand,
    ) -> ConfirmDraftClaimCompactionDegradedFallbackResult:
        decision = await self.decision_repository.load_pending_decision(
            workflow_run_id=command.workflow_run_id,
            project_id=command.project_id,
        )
        if decision is None:
            raise DraftClaimCompactionDegradedFallbackNotPendingError(
                "daily-capacity degraded fallback confirmation is not pending"
            )

        next_command = _degraded_prepare_command(
            command=command,
            decision=decision,
        )
        appended = await self.workflow_unit_of_work.command_log.append_pending_command(
            next_command
        )
        await self.workflow_unit_of_work.outbox.append_event(
            _resolved_event(
                command=command,
                decision=decision,
                appended_command=appended,
            )
        )
        return ConfirmDraftClaimCompactionDegradedFallbackResult(
            workflow_run_id=command.workflow_run_id,
            degraded_model_ref=decision.degraded_model_ref,
            appended_command_id=appended.command_id,
        )


def _degraded_prepare_command(
    *,
    command: ConfirmDraftClaimCompactionDegradedFallbackCommand,
    decision: DraftClaimCompactionDegradedFallbackDecision,
) -> WorkflowCommand:
    payload = deepcopy(decision.source_command_payload)
    payload["active_model_ref"] = decision.degraded_model_ref
    payload["user_confirmed_degraded_fallback"] = True
    payload["confirmed_by_user_id"] = command.actor_user_id
    payload["caused_by_command_id"] = decision.source_command_id.value

    preparation_value = payload.get("llm_dispatch_preparation")
    preparation = dict(preparation_value) if isinstance(preparation_value, dict) else {}
    preparation["active_model_ref"] = decision.degraded_model_ref
    preparation.pop("account_capacities", None)
    payload["llm_dispatch_preparation"] = preparation

    idempotency_key = (
        "draft-claim-compaction-user-degraded-fallback:"
        f"{command.workflow_run_id}:{decision.source_command_id.value}"
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
        ),
        workflow_run_id=command.workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=command.occurred_at,
        created_at=command.occurred_at,
        updated_at=command.occurred_at,
    )


def _resolved_event(
    *,
    command: ConfirmDraftClaimCompactionDegradedFallbackCommand,
    decision: DraftClaimCompactionDegradedFallbackDecision,
    appended_command: WorkflowCommand,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{command.workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_USER_MODEL_CHOICE_RESOLVED.value}:"
            f"{decision.source_command_id.value}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_USER_MODEL_CHOICE_RESOLVED.value
        ),
        workflow_run_id=command.workflow_run_id,
        payload={
            "workflow_run_id": command.workflow_run_id,
            "decision": "continue_with_degraded_model",
            "degraded_model_ref": decision.degraded_model_ref,
            "actor_user_id": command.actor_user_id,
            "appended_command_id": appended_command.command_id.value,
        },
        occurred_at=command.occurred_at,
        causation_command_id=decision.source_command_id,
        correlation_id=appended_command.command_id.value,
    )


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
