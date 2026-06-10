from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.events.artifact_events import ArtifactStored
from src.contexts.artifact_runtime.domain.value_objects.artifact_kind import (
    ArtifactKind,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_lineage import (
    ArtifactLineage,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import (
    ArtifactPayload,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.artifact_runtime.domain.value_objects.artifact_status import (
    ArtifactStatus,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_visibility import (
    ArtifactVisibility,
)
from src.contexts.artifact_runtime.domain.value_objects.retention_policy import (
    RetentionPolicy,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import (
    WorkItemAttempt,
)
from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemDeferred,
    WorkItemUserActionResolved,
)
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.knowledge_workbench.extraction.application.ports.claim_extraction_work_item_unit_of_work_port import (
    ClaimExtractionRuntimeEvent,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.apply_claim_extraction_daily_exhausted_decision import (
    ApplyClaimExtractionDailyExhaustedDecision,
    ApplyClaimExtractionDailyExhaustedDecisionCommand,
    ClaimExtractionDailyExhaustedDecision,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.record_claim_extraction_daily_exhausted import (
    DAILY_EXHAUSTED_DECISION_KIND,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask


@dataclass(slots=True)
class FakeClaimExtractionWorkItemUnitOfWork:
    saved_work_items: list[WorkItem] = field(default_factory=list)
    saved_work_item_attempts: list[WorkItemAttempt] = field(default_factory=list)
    saved_llm_tasks: list[LlmTask] = field(default_factory=list)
    saved_llm_attempts: list[LlmAttempt] = field(default_factory=list)
    saved_artifacts: list[PipelineArtifact] = field(default_factory=list)
    appended_events: list[ClaimExtractionRuntimeEvent] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    fail_on_commit: bool = False

    def save_work_item(self, item: WorkItem) -> None:
        self.actions.append("save_work_item")
        self.saved_work_items.append(item)

    def save_work_item_attempt(self, attempt: WorkItemAttempt) -> None:
        self.actions.append("save_work_item_attempt")
        self.saved_work_item_attempts.append(attempt)

    def save_llm_task(self, task: LlmTask) -> None:
        self.actions.append("save_llm_task")
        self.saved_llm_tasks.append(task)

    def save_llm_attempt(self, attempt: LlmAttempt) -> None:
        self.actions.append("save_llm_attempt")
        self.saved_llm_attempts.append(attempt)

    def save_artifact(self, artifact: PipelineArtifact) -> None:
        self.actions.append("save_artifact")
        self.saved_artifacts.append(artifact)

    def append_event(self, event: ClaimExtractionRuntimeEvent) -> None:
        self.actions.append("append_event")
        self.appended_events.append(event)

    def commit(self) -> None:
        self.actions.append("commit")
        if self.fail_on_commit:
            raise RuntimeError("commit failed")
        self.committed = True

    def rollback(self) -> None:
        self.actions.append("rollback")
        self.rolled_back = True


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _blocked_work_item() -> WorkItem:
    now = _now()
    leased = WorkItemStateMachine.lease_ready(
        WorkItem(
            work_item_id="work-1",
            work_kind=WorkKind("knowledge_workbench.claim_extraction"),
        ),
        worker=WorkerRef("worker-1"),
        lease_token=LeaseToken("lease-1"),
        lease_expires_at=now + timedelta(seconds=30),
        now=now,
    )
    return WorkItemStateMachine.require_user_action_leased(
        leased,
        error_kind="daily_limit",
    )


def _decision_artifact(
    decision: ClaimExtractionDailyExhaustedDecision,
) -> PipelineArtifact:
    return PipelineArtifact(
        artifact_ref=ArtifactRef("decision-artifact-1"),
        artifact_kind=ArtifactKind(
            "knowledge_workbench.claim_extraction.daily_decision"
        ),
        payload=ArtifactPayload(
            {
                "decision_kind": DAILY_EXHAUSTED_DECISION_KIND,
                "decision_value": decision.value,
            },
        ),
        status=ArtifactStatus.STORED,
        visibility=ArtifactVisibility.REVIEWABLE,
        retention_policy=RetentionPolicy.durable(),
        lineage=ArtifactLineage(),
        created_at=_now(),
        updated_at=_now(),
    )


def test_continue_with_degraded_model_requeues_work_item_immediately() -> None:
    unit_of_work = FakeClaimExtractionWorkItemUnitOfWork()
    decision = ClaimExtractionDailyExhaustedDecision.CONTINUE_WITH_DEGRADED_MODEL
    artifact = _decision_artifact(decision)

    result = ApplyClaimExtractionDailyExhaustedDecision(
        repository=unit_of_work
    ).execute(
        ApplyClaimExtractionDailyExhaustedDecisionCommand(
            blocked_work_item=_blocked_work_item(),
            decision=decision,
            decision_artifact=artifact,
            occurred_at=_now(),
        ),
    )

    assert result.resolved_work_item.status is WorkItemStatus.READY
    assert result.resolved_work_item.next_attempt_at is None
    assert result.resolved_work_item.last_error_kind == decision.value
    assert isinstance(result.decision_event, WorkItemUserActionResolved)
    assert result.decision_event.decision_kind == DAILY_EXHAUSTED_DECISION_KIND
    assert result.decision_event.decision_value == decision.value
    assert isinstance(result.decision_artifact_event, ArtifactStored)
    assert result.deferred_event is None

    assert unit_of_work.saved_work_items == [result.resolved_work_item]
    assert unit_of_work.saved_artifacts == [artifact]
    assert unit_of_work.appended_events == [
        result.decision_event,
        result.decision_artifact_event,
    ]
    assert unit_of_work.actions == [
        "save_work_item",
        "save_artifact",
        "append_event",
        "append_event",
        "commit",
    ]
    assert unit_of_work.committed
    assert not unit_of_work.rolled_back


def test_resume_after_daily_reset_defers_work_item_until_reset() -> None:
    unit_of_work = FakeClaimExtractionWorkItemUnitOfWork()
    decision = ClaimExtractionDailyExhaustedDecision.RESUME_AFTER_DAILY_RESET
    artifact = _decision_artifact(decision)
    resume_after = WaitUntil(_now() + timedelta(hours=12))

    result = ApplyClaimExtractionDailyExhaustedDecision(
        repository=unit_of_work
    ).execute(
        ApplyClaimExtractionDailyExhaustedDecisionCommand(
            blocked_work_item=_blocked_work_item(),
            decision=decision,
            decision_artifact=artifact,
            resume_after=resume_after,
            occurred_at=_now(),
        ),
    )

    assert result.resolved_work_item.status is WorkItemStatus.DEFERRED
    assert result.resolved_work_item.next_attempt_at == resume_after
    assert result.resolved_work_item.last_error_kind == decision.value
    assert isinstance(result.decision_event, WorkItemUserActionResolved)
    assert isinstance(result.decision_artifact_event, ArtifactStored)
    assert isinstance(result.deferred_event, WorkItemDeferred)
    assert result.deferred_event.wait_until == resume_after.value
    assert result.deferred_event.error_kind == decision.value

    assert unit_of_work.saved_work_items == [result.resolved_work_item]
    assert unit_of_work.saved_artifacts == [artifact]
    assert unit_of_work.appended_events == [
        result.decision_event,
        result.decision_artifact_event,
        result.deferred_event,
    ]
    assert unit_of_work.committed


def test_daily_exhausted_decision_rolls_back_when_commit_fails() -> None:
    unit_of_work = FakeClaimExtractionWorkItemUnitOfWork(fail_on_commit=True)
    decision = ClaimExtractionDailyExhaustedDecision.CONTINUE_WITH_DEGRADED_MODEL

    with pytest.raises(RuntimeError, match="commit failed"):
        ApplyClaimExtractionDailyExhaustedDecision(repository=unit_of_work).execute(
            ApplyClaimExtractionDailyExhaustedDecisionCommand(
                blocked_work_item=_blocked_work_item(),
                decision=decision,
                decision_artifact=_decision_artifact(decision),
                occurred_at=_now(),
            ),
        )

    assert not unit_of_work.committed
    assert unit_of_work.rolled_back
    assert unit_of_work.actions[-2:] == ["commit", "rollback"]


def test_resume_after_daily_reset_requires_resume_after() -> None:
    with pytest.raises(ValueError):
        ApplyClaimExtractionDailyExhaustedDecisionCommand(
            blocked_work_item=_blocked_work_item(),
            decision=ClaimExtractionDailyExhaustedDecision.RESUME_AFTER_DAILY_RESET,
            decision_artifact=_decision_artifact(
                ClaimExtractionDailyExhaustedDecision.RESUME_AFTER_DAILY_RESET,
            ),
            occurred_at=_now(),
        )


def test_continue_with_degraded_model_rejects_resume_after() -> None:
    with pytest.raises(ValueError):
        ApplyClaimExtractionDailyExhaustedDecisionCommand(
            blocked_work_item=_blocked_work_item(),
            decision=ClaimExtractionDailyExhaustedDecision.CONTINUE_WITH_DEGRADED_MODEL,
            decision_artifact=_decision_artifact(
                ClaimExtractionDailyExhaustedDecision.CONTINUE_WITH_DEGRADED_MODEL,
            ),
            resume_after=WaitUntil(_now() + timedelta(hours=12)),
            occurred_at=_now(),
        )


def test_daily_exhausted_decision_requires_timezone_aware_occurred_at() -> None:
    decision = ClaimExtractionDailyExhaustedDecision.CONTINUE_WITH_DEGRADED_MODEL

    with pytest.raises(ValueError):
        ApplyClaimExtractionDailyExhaustedDecisionCommand(
            blocked_work_item=_blocked_work_item(),
            decision=decision,
            decision_artifact=_decision_artifact(decision),
            occurred_at=datetime(2026, 6, 8, 12, 0),
        )
