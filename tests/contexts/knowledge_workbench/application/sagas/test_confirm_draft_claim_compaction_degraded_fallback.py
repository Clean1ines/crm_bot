from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.confirm_draft_claim_compaction_degraded_fallback import (
    ConfirmDraftClaimCompactionDegradedFallback,
    ConfirmDraftClaimCompactionDegradedFallbackCommand,
    DraftClaimCompactionDegradedFallbackDecision,
    DraftClaimCompactionDegradedFallbackNotPendingError,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)


@dataclass(slots=True)
class FakeDecisionRepository:
    decision: DraftClaimCompactionDegradedFallbackDecision | None

    async def load_pending_decision(
        self,
        *,
        workflow_run_id: str,
        project_id: str,
    ) -> DraftClaimCompactionDegradedFallbackDecision | None:
        assert workflow_run_id == "workflow-1"
        assert project_id == "project-1"
        return self.decision


@dataclass(slots=True)
class FakeCommandLog:
    commands: list[WorkflowCommand] = field(default_factory=list)

    async def append_pending_command(self, command: WorkflowCommand) -> WorkflowCommand:
        self.commands.append(command)
        return command


@dataclass(slots=True)
class FakeOutbox:
    events: list[object] = field(default_factory=list)

    async def append_event(self, event: object) -> object:
        self.events.append(event)
        return event


@dataclass(slots=True)
class FakeWorkflowUnitOfWork:
    command_log: FakeCommandLog = field(default_factory=FakeCommandLog)
    outbox: FakeOutbox = field(default_factory=FakeOutbox)


@dataclass(slots=True)
class FakeDegradedFallbackScheduler:
    calls: list[DraftClaimCompactionDegradedFallbackDecision] = field(
        default_factory=list
    )

    async def schedule_degraded_work(
        self,
        *,
        workflow_run_id: str,
        decision: DraftClaimCompactionDegradedFallbackDecision,
        created_at: datetime,
    ) -> None:
        assert workflow_run_id == "workflow-1"
        assert created_at == _now()
        self.calls.append(decision)


def _now() -> datetime:
    return datetime(2026, 6, 19, 10, 0, tzinfo=timezone.utc)


def _decision() -> DraftClaimCompactionDegradedFallbackDecision:
    return DraftClaimCompactionDegradedFallbackDecision(
        source_command_id=WorkflowCommandId("workflow-command:prepare-primary"),
        source_command_payload={
            "workflow_run_id": "workflow-1",
            "scheduled_work_item_count": 2,
            "active_model_ref": "openai/gpt-oss-120b",
            "llm_dispatch_preparation": {
                "active_model_ref": "openai/gpt-oss-120b",
                "requested_items": 2,
                "account_capacities": ({"account_ref": "stale"},),
            },
        },
        degraded_model_ref="llama-3.3-70b-versatile",
    )


@pytest.mark.asyncio
async def test_confirmation_appends_degraded_prepare_command_and_audit_event() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()

    result = await ConfirmDraftClaimCompactionDegradedFallback(
        decision_repository=FakeDecisionRepository(_decision()),
        workflow_unit_of_work=workflow_uow,
    ).execute(
        ConfirmDraftClaimCompactionDegradedFallbackCommand(
            workflow_run_id="workflow-1",
            project_id="project-1",
            actor_user_id="user-1",
            occurred_at=_now(),
        )
    )

    assert result.degraded_model_ref == "llama-3.3-70b-versatile"
    assert len(workflow_uow.command_log.commands) == 1
    appended = workflow_uow.command_log.commands[0]
    assert appended.command_type == (
        KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
    )
    assert appended.payload["active_model_ref"] == "llama-3.3-70b-versatile"
    preparation = appended.payload["llm_dispatch_preparation"]
    assert isinstance(preparation, dict)
    assert preparation["active_model_ref"] == "llama-3.3-70b-versatile"
    assert "account_capacities" not in preparation
    assert appended.payload["user_confirmed_degraded_fallback"] is True
    assert len(workflow_uow.outbox.events) == 1


@pytest.mark.asyncio
async def test_confirmation_rejects_when_capacity_choice_is_not_pending() -> None:
    with pytest.raises(DraftClaimCompactionDegradedFallbackNotPendingError):
        await ConfirmDraftClaimCompactionDegradedFallback(
            decision_repository=FakeDecisionRepository(None),
            workflow_unit_of_work=FakeWorkflowUnitOfWork(),
        ).execute(
            ConfirmDraftClaimCompactionDegradedFallbackCommand(
                workflow_run_id="workflow-1",
                project_id="project-1",
                actor_user_id="user-1",
                occurred_at=_now(),
            )
        )


@pytest.mark.asyncio
async def test_graph_confirmation_schedules_degraded_work_before_prepare() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    scheduler = FakeDegradedFallbackScheduler()
    decision = DraftClaimCompactionDegradedFallbackDecision(
        source_command_id=WorkflowCommandId("workflow-command:apply"),
        degraded_model_ref="llama-3.3-70b-versatile",
        group_ref="group-1",
        node_refs=("compacted-a", "compacted-b"),
        resume_work_type="compacted_vs_compacted",
        input_tokens=5250,
        artifact_tokens=3200,
    )

    result = await ConfirmDraftClaimCompactionDegradedFallback(
        decision_repository=FakeDecisionRepository(decision),
        workflow_unit_of_work=workflow_uow,
        degraded_fallback_scheduler=scheduler,
    ).execute(
        ConfirmDraftClaimCompactionDegradedFallbackCommand(
            workflow_run_id="workflow-1",
            project_id="project-1",
            actor_user_id="user-1",
            occurred_at=_now(),
        )
    )

    assert scheduler.calls == [decision]
    assert result.degraded_model_ref == "llama-3.3-70b-versatile"
    assert (
        workflow_uow.command_log.commands[0].payload["scheduled_work_item_count"] == 1
    )
