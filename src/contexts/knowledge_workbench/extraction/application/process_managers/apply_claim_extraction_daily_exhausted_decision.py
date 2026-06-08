from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.events.artifact_events import ArtifactStored
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemDeferred,
    WorkItemUserActionResolved,
)
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.knowledge_workbench.extraction.application.ports.claim_extraction_work_item_unit_of_work_port import (
    ClaimExtractionWorkItemUnitOfWorkPort,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.record_claim_extraction_daily_exhausted import (
    DAILY_EXHAUSTED_DECISION_KIND,
)


class ClaimExtractionDailyExhaustedDecision(StrEnum):
    CONTINUE_WITH_DEGRADED_MODEL = "continue_with_degraded_model"
    RESUME_AFTER_DAILY_RESET = "resume_after_daily_reset"


@dataclass(frozen=True, slots=True)
class ApplyClaimExtractionDailyExhaustedDecisionCommand:
    blocked_work_item: WorkItem
    decision: ClaimExtractionDailyExhaustedDecision
    decision_artifact: PipelineArtifact
    occurred_at: datetime
    resume_after: WaitUntil | None = None

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if (
            self.decision
            is ClaimExtractionDailyExhaustedDecision.RESUME_AFTER_DAILY_RESET
            and self.resume_after is None
        ):
            raise ValueError("resume_after is required for RESUME_AFTER_DAILY_RESET")
        if (
            self.decision
            is ClaimExtractionDailyExhaustedDecision.CONTINUE_WITH_DEGRADED_MODEL
            and self.resume_after is not None
        ):
            raise ValueError(
                "resume_after must not be provided for CONTINUE_WITH_DEGRADED_MODEL",
            )


@dataclass(frozen=True, slots=True)
class ApplyClaimExtractionDailyExhaustedDecisionResult:
    resolved_work_item: WorkItem
    decision_event: WorkItemUserActionResolved
    decision_artifact_event: ArtifactStored
    deferred_event: WorkItemDeferred | None = None


class ApplyClaimExtractionDailyExhaustedDecision:
    """Apply user's daily-exhausted decision for claim extraction.

    CONTINUE_WITH_DEGRADED_MODEL requeues the work item immediately.
    RESUME_AFTER_DAILY_RESET defers it until daily limits reset.
    """

    def __init__(
        self,
        *,
        unit_of_work: ClaimExtractionWorkItemUnitOfWorkPort,
    ) -> None:
        self._unit_of_work = unit_of_work

    def execute(
        self,
        command: ApplyClaimExtractionDailyExhaustedDecisionCommand,
    ) -> ApplyClaimExtractionDailyExhaustedDecisionResult:
        resolved_work_item = _resolve_work_item(command)
        decision_event = WorkItemUserActionResolved(
            work_item_id=resolved_work_item.work_item_id,
            occurred_at=command.occurred_at,
            decision_kind=DAILY_EXHAUSTED_DECISION_KIND,
            decision_value=command.decision.value,
        )
        decision_artifact_event = ArtifactStored(
            artifact_ref=command.decision_artifact.artifact_ref,
            occurred_at=command.occurred_at,
        )
        deferred_event = _deferred_event(command=command, item=resolved_work_item)

        try:
            self._unit_of_work.save_work_item(resolved_work_item)
            self._unit_of_work.save_artifact(command.decision_artifact)
            self._unit_of_work.append_event(decision_event)
            self._unit_of_work.append_event(decision_artifact_event)
            if deferred_event is not None:
                self._unit_of_work.append_event(deferred_event)
            self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise

        return ApplyClaimExtractionDailyExhaustedDecisionResult(
            resolved_work_item=resolved_work_item,
            decision_event=decision_event,
            decision_artifact_event=decision_artifact_event,
            deferred_event=deferred_event,
        )


def _resolve_work_item(
    command: ApplyClaimExtractionDailyExhaustedDecisionCommand,
) -> WorkItem:
    if (
        command.decision
        is ClaimExtractionDailyExhaustedDecision.CONTINUE_WITH_DEGRADED_MODEL
    ):
        return WorkItemStateMachine.resolve_user_action_required_to_ready(
            command.blocked_work_item,
            reason=command.decision.value,
        )

    if command.resume_after is None:
        raise ValueError("resume_after is required for RESUME_AFTER_DAILY_RESET")

    return WorkItemStateMachine.resolve_user_action_required_to_deferred(
        command.blocked_work_item,
        wait_until=command.resume_after,
        reason=command.decision.value,
    )


def _deferred_event(
    *,
    command: ApplyClaimExtractionDailyExhaustedDecisionCommand,
    item: WorkItem,
) -> WorkItemDeferred | None:
    if (
        command.decision
        is not ClaimExtractionDailyExhaustedDecision.RESUME_AFTER_DAILY_RESET
    ):
        return None
    if command.resume_after is None:
        raise ValueError("resume_after is required for RESUME_AFTER_DAILY_RESET")

    return WorkItemDeferred(
        work_item_id=item.work_item_id,
        occurred_at=command.occurred_at,
        wait_until=command.resume_after.value,
        error_kind=command.decision.value,
    )
