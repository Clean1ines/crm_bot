from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_read_repository_port import (
    WorkItemAttemptDispatchForExecution,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.knowledge_workbench.application.sagas.handle_execute_claim_builder_section_command import (
    HandleExecuteClaimBuilderSectionCommand,
    HandleExecuteClaimBuilderSectionCommandHandler,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_output_validation_policy import (
    ClaimBuilderOutputValidationPolicy,
)
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt import (
    ExecutePreparedLlmDispatchAttemptCommand,
)
from tests.contexts.knowledge_workbench.application.sagas.test_claim_builder_capacity_drain_bridge import (
    FakeWorkflowUnitOfWork,
    _bridge,
    _execution_window,
    _now,
    _reservation,
    _selection_lane,
)
from tests.contexts.knowledge_workbench.application.sagas.test_handle_execute_claim_builder_section_command import (
    FakeCapacityObservationRepository,
    FakeDraftClaimObservationPersistence,
    FakeExecutePreparedLlmDispatchAttempt,
    FakeWorkflowRuntimeUnitOfWork,
    _execution_result,
    _finished_at,
    _schedule_payload,
)


@dataclass(slots=True)
class AssertingExecutePreparedLlmDispatchAttempt(FakeExecutePreparedLlmDispatchAttempt):
    expected_attempt_id: str = ""
    expected_work_item_id: str = ""

    async def execute(
        self,
        command: ExecutePreparedLlmDispatchAttemptCommand,
    ) -> object:
        assert command.attempt_id == self.expected_attempt_id
        assert self.result.dispatch.work_item_id == self.expected_work_item_id
        return await FakeExecutePreparedLlmDispatchAttempt.execute(self, command)


@pytest.mark.asyncio
async def test_bridge_command_is_accepted_by_execute_claim_builder_handler() -> None:
    bridge_uow = FakeWorkflowUnitOfWork()
    await _bridge(bridge_uow).execute_admitted_work_item(
        work_item_id="work-1",
        selection_lane_key=_selection_lane(),
        execution_window_key=_execution_window(),
        reservation=_reservation(),
        worker_ref="worker-1",
        now=_now(),
    )
    workflow_command = bridge_uow.command_log.pending_commands[0]
    dispatch_attempt_id = workflow_command.payload["dispatch_attempt_id"]
    work_item_id = workflow_command.payload["work_item_id"]
    source_unit_ref = workflow_command.payload["source_unit_ref"]
    assert isinstance(dispatch_attempt_id, str)
    assert isinstance(work_item_id, str)
    assert isinstance(source_unit_ref, str)

    dispatch = WorkItemAttemptDispatchForExecution(
        attempt_id=dispatch_attempt_id,
        work_item_id=work_item_id,
        attempt_number=1,
        lease_token=LeaseToken("lease-token-1"),
        worker_ref="worker-1",
        dispatch_payload={
            "work_item_id": work_item_id,
            "schedule_payload": _schedule_payload(
                claim_builder_provenance={
                    "workflow_run_id": workflow_command.workflow_run_id,
                    "stage_run_id": "claim_builder_section_extraction",
                    "source_unit_ref": source_unit_ref,
                    "work_item_id": work_item_id,
                    "prompt_id": "faq_claim_observations",
                    "prompt_version": "v1",
                },
                source_unit_ref=source_unit_ref,
            ),
            "llm_allocation": {
                "provider": "groq",
                "account_ref": "groq_org_primary",
                "model_ref": "qwen/qwen3-32b",
                "slot_index": 0,
            },
            "llm_execution_settings": {"reasoning_enabled": False},
        },
        started_at=_now(),
    )
    executor = AssertingExecutePreparedLlmDispatchAttempt(
        result=_execution_result(dispatch=dispatch),
        expected_attempt_id=dispatch_attempt_id,
        expected_work_item_id=work_item_id,
    )

    result = await HandleExecuteClaimBuilderSectionCommandHandler().execute(
        HandleExecuteClaimBuilderSectionCommand(workflow_command=workflow_command),
        execute_prepared_llm_dispatch_attempt=executor,
        capacity_observation_repository=FakeCapacityObservationRepository(),
        claim_builder_output_validation_policy=ClaimBuilderOutputValidationPolicy(),
        draft_claim_observation_persistence=FakeDraftClaimObservationPersistence(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
    )

    assert result.dispatch_attempt_id == dispatch_attempt_id
    assert result.work_item_id == work_item_id
    assert executor.calls[0].attempt_id == dispatch_attempt_id
    assert (
        executor.result.dispatch.dispatch_payload["schedule_payload"]["source_unit_ref"]
        == source_unit_ref
    )
    assert executor.result.llm_result.finished_at == _finished_at()
