from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_read_repository_port import (
    WorkItemAttemptDispatchForExecution,
)
from src.contexts.execution_runtime.application.use_cases.record_work_item_attempt_outcome import (
    RecordWorkItemAttemptOutcomeResult,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.knowledge_workbench.application.sagas.handle_apply_draft_claim_compaction_result_command import (
    HandleApplyDraftClaimCompactionResultCommand,
    HandleApplyDraftClaimCompactionResultCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.handle_execute_draft_claim_compaction_command import (
    HandleExecuteDraftClaimCompactionCommand,
    HandleExecuteDraftClaimCompactionCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.handle_prepare_draft_claim_compaction_dispatch_batch_command import (
    DRAFT_CLAIM_COMPACTION_WORK_KIND,
    HandlePrepareDraftClaimCompactionDispatchBatchCommand,
    HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.handle_reconcile_draft_claim_compaction_progress_command import (
    HandleReconcileDraftClaimCompactionProgressCommand,
    HandleReconcileDraftClaimCompactionProgressCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_apply_result import (
    DraftClaimCompactionApplyResultCommand,
    DraftClaimCompactionApplyResultOutcome,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionNode,
    DraftClaimCompactionNodeKind,
    DraftClaimCompactionNextWorkItemType,
    DraftClaimCompactionPlannerDecision,
    DraftClaimCompactionPlannerState,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_output_validator import (
    DraftClaimCompactionOutputValidator,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionApplyPersistenceResult,
    DraftClaimCompactionReductionStatePersistenceResult,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionResult,
    LlmDispatchExecutionStatus,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt import (
    ExecutePreparedLlmDispatchAttemptCommand,
    ExecutePreparedLlmDispatchAttemptResult,
)
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    PrepareLlmDispatchBatchCommand,
)
from src.interfaces.composition.start_llm_admitted_work_item_attempts import (
    StartedLlmAdmittedAttempt,
)
from tests.contexts.knowledge_workbench.application.sagas.test_handle_apply_draft_claim_compaction_result_command import (
    FakeDraftClaimObservationReadRepository,
    FakeWorkItemSchedulingRepository,
    _decision,
)
from tests.contexts.knowledge_workbench.application.sagas.test_handle_prepare_draft_claim_compaction_dispatch_batch_command import (
    _fake_prepare_result,
)
from tests.contexts.knowledge_workbench.application.sagas.test_handle_reconcile_draft_claim_compaction_progress_command import (
    FakeWorkItemProgressReadRepository,
    FakeWorkflowUnitOfWork,
    _summary,
    _work_summary,
)


def _now() -> datetime:
    return datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "workflow-1"


@pytest.mark.asyncio
async def test_draft_claim_compaction_orchestrates_prepare_apply_reconcile_to_curation() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    prepare = SequencedPrepareLlmDispatchBatch()
    execute = SequencedExecutePreparedAttempt(prepare.attempt_payloads_by_id)
    apply_use_case = SequencedApplyResultUseCase(
        decisions=[
            _decision(
                DraftClaimCompactionNextWorkItemType.COMPACTED_VS_COMPACTED,
                node_refs=("compacted-a", "compacted-b"),
            ),
            _decision(DraftClaimCompactionNextWorkItemType.DONE),
        ],
    )
    reduction_repository = FlexibleReductionStateRepository()
    scheduling_repository = FakeWorkItemSchedulingRepository()

    first_prepare_command = _prepare_command(
        command_id="workflow-command:first-prepare",
        idempotency_key="draft-claim-compaction-dispatch:workflow-1:initial",
        scheduled_work_item_count=1,
        profile={
            "profile_id": "draft_claim_compaction",
            "estimated_prompt_tokens": 12345,
            "estimated_completion_tokens": 4000,
            "estimated_requests": 1,
        },
    )

    await HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler().execute(
        HandlePrepareDraftClaimCompactionDispatchBatchCommand(
            workflow_command=first_prepare_command
        ),
        prepare_llm_dispatch_batch=prepare,
        workflow_unit_of_work=workflow_uow,
    )
    first_execute_command = _single_command(
        workflow_uow,
        KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION,
    )
    assert first_execute_command.payload["scheduled_work_item_count"] == 1

    await HandleExecuteDraftClaimCompactionCommandHandler().execute(
        HandleExecuteDraftClaimCompactionCommand(
            workflow_command=first_execute_command
        ),
        execute_prepared_llm_dispatch_attempt=execute,
        capacity_observation_repository=FakeCapacityObservationRepository(),
        draft_claim_compaction_output_validator=DraftClaimCompactionOutputValidator(),
        workflow_unit_of_work=workflow_uow,
    )
    first_apply_command = _single_command(
        workflow_uow,
        KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT,
    )

    await HandleApplyDraftClaimCompactionResultCommandHandler(
        apply_result_use_case=apply_use_case,
    ).execute(
        HandleApplyDraftClaimCompactionResultCommand(
            workflow_command=first_apply_command
        ),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=reduction_repository,
        draft_claim_observation_read_repository=FakeDraftClaimObservationReadRepository(),
        work_item_scheduling_repository=scheduling_repository,
    )

    apply_prepare_commands = _commands(
        workflow_uow,
        KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH,
    )
    apply_reconcile_commands = _commands(
        workflow_uow,
        KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS,
    )
    assert len(apply_prepare_commands) == 0
    assert len(apply_reconcile_commands) == 1

    reduction_repository.summary = _summary(
        group_count=1,
        done_group_count=0,
        active_group_count=1,
    )
    first_reconcile_result = (
        await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
            HandleReconcileDraftClaimCompactionProgressCommand(
                workflow_command=apply_reconcile_commands[0]
            ),
            workflow_unit_of_work=workflow_uow,
            compaction_reduction_state_repository=reduction_repository,
            work_item_progress_read_repository=FakeWorkItemProgressReadRepository(
                _work_summary(ready_count=1)
            ),
            command_log_repository=workflow_uow.command_log,
        )
    )
    assert first_reconcile_result.decision == "PREPARE_NEXT_BATCH_NOW"

    reconcile_prepare_commands = _commands(
        workflow_uow,
        KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH,
    )
    assert len(reconcile_prepare_commands) == 1
    second_prepare_command = reconcile_prepare_commands[0]
    assert (
        second_prepare_command.payload["work_kind"]
        == DRAFT_CLAIM_COMPACTION_WORK_KIND.value
    )
    assert second_prepare_command.payload["scheduled_work_item_count"] == 1
    dispatch_preparation = second_prepare_command.payload["llm_dispatch_preparation"]
    assert isinstance(dispatch_preparation, dict)
    assert dispatch_preparation["requested_items"] == 1

    await HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler().execute(
        HandlePrepareDraftClaimCompactionDispatchBatchCommand(
            workflow_command=second_prepare_command
        ),
        prepare_llm_dispatch_batch=prepare,
        workflow_unit_of_work=workflow_uow,
    )
    second_execute_command = [
        command
        for command in _commands(
            workflow_uow,
            KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION,
        )
        if command is not first_execute_command
    ][0]
    assert second_execute_command.payload["scheduled_work_item_count"] == 1

    await HandleExecuteDraftClaimCompactionCommandHandler().execute(
        HandleExecuteDraftClaimCompactionCommand(
            workflow_command=second_execute_command
        ),
        execute_prepared_llm_dispatch_attempt=execute,
        capacity_observation_repository=FakeCapacityObservationRepository(),
        draft_claim_compaction_output_validator=DraftClaimCompactionOutputValidator(),
        workflow_unit_of_work=workflow_uow,
    )
    second_apply_command = [
        command
        for command in _commands(
            workflow_uow,
            KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT,
        )
        if command is not first_apply_command
    ][0]
    await HandleApplyDraftClaimCompactionResultCommandHandler(
        apply_result_use_case=apply_use_case,
    ).execute(
        HandleApplyDraftClaimCompactionResultCommand(
            workflow_command=second_apply_command
        ),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=reduction_repository,
        draft_claim_observation_read_repository=FakeDraftClaimObservationReadRepository(),
        work_item_scheduling_repository=scheduling_repository,
    )

    reduction_repository.summary = _summary(
        group_count=1,
        done_group_count=1,
        active_group_count=0,
    )
    execution_summary = _work_summary(completed_count=2)
    final_reconcile = _commands(
        workflow_uow,
        KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS,
    )[-1]
    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(
            workflow_command=final_reconcile
        ),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=reduction_repository,
        work_item_progress_read_repository=FakeWorkItemProgressReadRepository(
            execution_summary
        ),
        command_log_repository=workflow_uow.command_log,
    )

    assert result.decision == "ALL_GROUPS_COMPACTED"
    assert _event_count(
        workflow_uow,
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ALL_GROUPS_COMPACTED,
    ) == 1
    assert _event_count(
        workflow_uow,
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_BLOCKED,
    ) == 0
    assert len(
        _commands(
            workflow_uow,
            KnowledgeExtractionCanonicalCommandType.OPEN_DRAFT_CLAIM_CURATION_WORKSPACE,
        )
    ) == 1
    assert len(apply_reconcile_commands) == 1


@dataclass(slots=True)
class SequencedPrepareLlmDispatchBatch:
    calls: list[PrepareLlmDispatchBatchCommand] = field(default_factory=list)
    attempt_payloads_by_id: dict[str, Mapping[str, object]] = field(
        default_factory=dict
    )

    async def execute(self, command: PrepareLlmDispatchBatchCommand) -> object:
        self.calls.append(command)
        attempt_number = len(self.calls)
        attempt_id = f"attempt-{attempt_number}"
        work_item_id = f"work-item-{attempt_number}"
        dispatch_payload = _dispatch_payload(
            attempt_id=attempt_id,
            work_item_id=work_item_id,
            batch_ref=f"batch-{attempt_number}",
            source_node_refs=(
                (
                    "raw:workflow-1:group-1:claim-a",
                    "raw:workflow-1:group-1:claim-b",
                )
                if attempt_number == 1
                else ("compacted-a", "compacted-b")
            ),
        )
        self.attempt_payloads_by_id[attempt_id] = dispatch_payload
        return _fake_prepare_result(
            (
                StartedLlmAdmittedAttempt(
                    attempt_id=attempt_id,
                    work_item_id=work_item_id,
                    attempt_number=1,
                    dispatch_payload=dispatch_payload,
                ),
            )
        )


@dataclass(slots=True)
class SequencedExecutePreparedAttempt:
    attempt_payloads_by_id: Mapping[str, Mapping[str, object]]
    calls: list[ExecutePreparedLlmDispatchAttemptCommand] = field(default_factory=list)

    async def execute(
        self,
        command: ExecutePreparedLlmDispatchAttemptCommand,
    ) -> object:
        self.calls.append(command)
        dispatch_payload = self.attempt_payloads_by_id[command.attempt_id]
        return _execution_result(
            attempt_id=command.attempt_id,
            work_item_id=_text(dispatch_payload, "work_item_id"),
            dispatch_payload=dispatch_payload,
        )


@dataclass(slots=True)
class SequencedApplyResultUseCase:
    decisions: list[DraftClaimCompactionPlannerDecision]
    commands: list[DraftClaimCompactionApplyResultCommand] = field(default_factory=list)

    async def execute(
        self,
        command: DraftClaimCompactionApplyResultCommand,
    ) -> DraftClaimCompactionApplyResultOutcome:
        self.commands.append(command)
        return DraftClaimCompactionApplyResultOutcome(
            created_node_refs=(f"compacted-node-{len(self.commands)}",),
            superseded_node_refs=("left-node", "right-node"),
            comparison_refs=(f"comparison-{len(self.commands)}",),
            next_decision=self.decisions.pop(0),
        )


@dataclass(slots=True)
class FlexibleReductionStateRepository:
    summary: object = field(default_factory=lambda: _summary(active_group_count=1))

    async def summarize_compaction_progress(self, *, workflow_run_id: str) -> object:
        assert workflow_run_id == _workflow_run_id()
        return self.summary

    async def load_planner_state(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
    ) -> DraftClaimCompactionPlannerState | None:
        assert workflow_run_id == _workflow_run_id()
        assert group_ref == "group-1"
        return DraftClaimCompactionPlannerState(
            cluster_ref="group-1",
            nodes=(
                _compacted_node("compacted-a"),
                _compacted_node("compacted-b"),
            ),
        )

    async def seed_initial_planner_state(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        raw_nodes: object,
        created_at: datetime,
    ) -> DraftClaimCompactionReductionStatePersistenceResult:
        del workflow_run_id, group_ref, raw_nodes, created_at
        raise AssertionError("seed must not be called")

    async def apply_compacted_claims_result(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        batch_ref: str,
        work_item_id: str,
        round_index: int,
        compared_node_refs: object,
        compacted_claims: object,
        created_at: datetime,
    ) -> DraftClaimCompactionApplyPersistenceResult:
        del (
            group_ref,
            batch_ref,
            work_item_id,
            round_index,
            compared_node_refs,
            compacted_claims,
            created_at,
        )
        assert workflow_run_id == _workflow_run_id()
        return _apply_persistence()

    async def apply_reduced_rewrite_result(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        batch_ref: str,
        work_item_id: str,
        round_index: int,
        source_node_refs: object,
        rewrite: object,
        created_at: datetime,
    ) -> DraftClaimCompactionApplyPersistenceResult:
        del (
            group_ref,
            batch_ref,
            work_item_id,
            round_index,
            source_node_refs,
            rewrite,
            created_at,
        )
        assert workflow_run_id == _workflow_run_id()
        return _apply_persistence()


@dataclass(slots=True)
class FakeCapacityObservationRepository:
    observations: list[object] = field(default_factory=list)

    async def record_observation(self, observation: object) -> None:
        self.observations.append(observation)


def _prepare_command(
    *,
    command_id: str,
    idempotency_key: str,
    scheduled_work_item_count: int,
    profile: Mapping[str, object],
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(command_id),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
        ),
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload={
            "workflow_run_id": _workflow_run_id(),
            "work_kind": DRAFT_CLAIM_COMPACTION_WORK_KIND.value,
            "scheduled_work_item_count": scheduled_work_item_count,
            "active_model_ref": "openai/gpt-oss-120b",
            "worker_ref": "knowledge-workbench-draft-claim-compaction-dispatch",
            "llm_dispatch_preparation": {
                "active_model_ref": "openai/gpt-oss-120b",
                "requested_items": scheduled_work_item_count,
                "worker_ref": "knowledge-workbench-draft-claim-compaction-dispatch",
                "profile": dict(profile),
            },
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _dispatch_payload(
    *,
    attempt_id: str,
    work_item_id: str,
    batch_ref: str,
    source_node_refs: tuple[str, ...],
) -> dict[str, object]:
    return {
        "work_item_id": work_item_id,
        "attempt_id": attempt_id,
        "schedule_payload": {
            "workflow_run_id": _workflow_run_id(),
            "group_ref": "group-1",
            "batch_ref": batch_ref,
            "round_index": 0,
            "expected_output_kind": "compacted_claims",
            "source_claim_refs": ["claim-a", "claim-b"],
            "source_node_refs": list(source_node_refs),
        },
        "llm_allocation": {
            "provider": "groq",
            "account_ref": "groq_org_primary",
            "model_ref": "openai/gpt-oss-120b",
        },
        "llm_execution_settings": {},
    }


def _execution_result(
    *,
    attempt_id: str,
    work_item_id: str,
    dispatch_payload: Mapping[str, object],
) -> ExecutePreparedLlmDispatchAttemptResult:
    return ExecutePreparedLlmDispatchAttemptResult(
        dispatch=WorkItemAttemptDispatchForExecution(
            attempt_id=attempt_id,
            work_item_id=work_item_id,
            attempt_number=1,
            lease_token=LeaseToken(f"lease-token:{attempt_id}"),
            worker_ref="knowledge-workbench-draft-claim-compaction-dispatch",
            dispatch_payload=dispatch_payload,
            started_at=_now(),
        ),
        llm_result=LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.SUCCEEDED,
            finished_at=_now(),
            output_payload={"raw_text": "{}"},
            error_kind=None,
            next_attempt_at=None,
            capacity_observation=None,
        ),
        outcome_result=RecordWorkItemAttemptOutcomeResult(work_item=None),
        validation_metadata={
            "draft_claim_compaction_validation_decision": "valid_output",
            "expected_output_kind": "compacted_claims",
            "validated_compacted_claim_count": 1,
            "retry_recommended": False,
            "compacted_claims": [
                {
                    "key": "refund_support",
                    "claim": "Product supports refunds.",
                    "claim_kind": "capability",
                    "source_claim_refs": ["claim-a", "claim-b"],
                    "triples": [],
                    "merge_decision": "merged",
                }
            ],
        },
    )


def _single_command(
    workflow_uow: FakeWorkflowUnitOfWork,
    command_type: KnowledgeExtractionCanonicalCommandType,
) -> WorkflowCommand:
    commands = _commands(workflow_uow, command_type)
    assert len(commands) == 1
    return commands[0]


def _commands(
    workflow_uow: FakeWorkflowUnitOfWork,
    command_type: KnowledgeExtractionCanonicalCommandType,
) -> list[WorkflowCommand]:
    return [
        command
        for command in workflow_uow.command_log.pending_commands
        if command.command_type == command_type.value
        and command.command_id not in workflow_uow.command_log.completed
    ]


def _event_count(
    workflow_uow: FakeWorkflowUnitOfWork,
    event_type: KnowledgeExtractionCanonicalEventType,
) -> int:
    return sum(
        1 for event in workflow_uow.outbox.events if event.event_type == event_type.value
    )


def _compacted_node(node_ref: str) -> DraftClaimCompactionNode:
    return DraftClaimCompactionNode(
        node_ref=node_ref,
        node_kind=DraftClaimCompactionNodeKind.COMPACTED,
        source_claim_refs=(f"source-{node_ref}",),
        compacted_key=f"key-{node_ref}",
        compacted_claim=f"Compacted claim {node_ref}",
    )


def _apply_persistence() -> DraftClaimCompactionApplyPersistenceResult:
    return DraftClaimCompactionApplyPersistenceResult(
        inserted_node_count=1,
        updated_node_count=2,
        inserted_source_count=2,
        inserted_comparison_count=1,
        superseded_node_count=2,
        already_exists_count=0,
    )


def _text(payload: Mapping[str, object], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be text")
    return value
