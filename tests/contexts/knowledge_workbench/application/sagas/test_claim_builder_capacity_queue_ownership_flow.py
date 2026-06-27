from __future__ import annotations

import pytest

from src.contexts.capacity_admission_queue.application.run_capacity_window_drain import (
    RunCapacityWindowDrain,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
    CapacityAdmissionSelectableWorkItem,
    SelectCapacityAdmissionWorkItem,
)
from src.contexts.knowledge_workbench.application.sagas import llm_dispatch_ownership
from src.contexts.knowledge_workbench.application.sagas.claim_builder_capacity_drain_bridge import (
    ClaimBuilderCapacityDrainBridge,
)
from src.contexts.knowledge_workbench.application.sagas.dispatch_knowledge_extraction_workflow_command import (
    DispatchKnowledgeExtractionWorkflowCommand,
    DispatchKnowledgeExtractionWorkflowCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
)
from src.contexts.knowledge_workbench.application.sagas.run_claim_builder_capacity_queue_once import (
    RunClaimBuilderCapacityQueueOnce,
)
from src.contexts.knowledge_workbench.application.sagas.trigger_claim_builder_capacity_drain_if_enabled import (
    TriggerClaimBuilderCapacityDrainIfEnabled,
    TriggerClaimBuilderCapacityDrainIfEnabledCommand,
    TriggerClaimBuilderCapacityDrainIfEnabledResult,
)
from tests.contexts.knowledge_workbench.application.sagas.test_claim_builder_capacity_drain_bridge import (
    FakeContextResolver,
)
from tests.contexts.knowledge_workbench.application.sagas.test_handle_schedule_claim_builder_section_work_command import (
    FakeWorkItemSchedulingRepository,
    _execute as _execute_schedule,
    _workflow_run_id,
)
from tests.contexts.knowledge_workbench.application.sagas.test_run_claim_builder_capacity_queue_once import (
    FakeBudget,
    FakeLaneClaims,
    FakeLifecycle,
    _item,
)


@pytest.mark.asyncio
async def test_claim_builder_ownership_flow_schedules_trigger_and_creates_execute_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm_dispatch_ownership,
        "CAPACITY_QUEUE_RUNTIME_CORE_ENABLED",
        True,
    )
    monkeypatch.setattr(
        llm_dispatch_ownership, "CAPACITY_QUEUE_OWNS_LLM_DISPATCH", True
    )
    monkeypatch.setattr(
        llm_dispatch_ownership,
        "CLAIM_BUILDER_CAPACITY_DRAIN_BRIDGE_ENABLED",
        True,
    )
    monkeypatch.setattr(
        llm_dispatch_ownership,
        "DRAFT_CLAIM_COMPACTION_CAPACITY_DRAIN_BRIDGE_ENABLED",
        False,
    )

    (
        _schedule_result,
        source_repository,
        scheduling_repository,
        workflow_unit_of_work,
    ) = await _execute_schedule()

    trigger_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert trigger_command.command_type == (
        KnowledgeExtractionCanonicalCommandType.TRIGGER_CLAIM_BUILDER_CAPACITY_DRAIN.value
    )
    assert (
        _command_type_count(
            workflow_unit_of_work.command_log.pending_commands,
            KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH,
        )
        == 0
    )

    work_item_id = _first_scheduled_work_item_id(scheduling_repository)
    run_once = _run_once_for_work_item(
        workflow_run_id=_workflow_run_id(),
        workflow_unit_of_work=workflow_unit_of_work,
        work_item_id=work_item_id,
    )

    trigger = RecordingTrigger(TriggerClaimBuilderCapacityDrainIfEnabled(run_once))
    dispatch_result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(workflow_command=trigger_command),
        source_unit_repository=source_repository,
        knowledge_unit_of_work=scheduling_repository,
        workflow_unit_of_work=workflow_unit_of_work,
        trigger_claim_builder_capacity_drain_if_enabled=trigger,
    )

    assert dispatch_result.dispatched is True
    assert (
        dispatch_result.handler_name
        == "HandleTriggerClaimBuilderCapacityDrainCommandHandler"
    )
    assert trigger.results[0].provider_call_count == 0
    execute_commands = [
        command
        for command in workflow_unit_of_work.command_log.pending_commands
        if command.command_type
        == KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
    ]
    assert len(execute_commands) == 1
    assert execute_commands[0].payload["workflow_run_id"] == _workflow_run_id()
    assert execute_commands[0].payload["work_item_id"] == work_item_id
    assert (
        _command_type_count(
            workflow_unit_of_work.command_log.pending_commands,
            KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH,
        )
        == 0
    )


def _run_once_for_work_item(
    *,
    workflow_run_id: str,
    workflow_unit_of_work,
    work_item_id: str,
) -> RunClaimBuilderCapacityQueueOnce:
    bridge = ClaimBuilderCapacityDrainBridge(
        workflow_run_id=workflow_run_id,
        workflow_unit_of_work=workflow_unit_of_work,
        dispatch_context_resolver=FakeContextResolver(),
        source_document_ref="source-document:project-1:abc",
        active_model_ref="qwen/qwen3-32b",
        scheduled_work_item_count=1,
    )
    drain = RunCapacityWindowDrain(
        lane_claim_repository=FakeLaneClaims(),
        budget_repository=FakeBudget(),
        capacity_selector=SelectCapacityAdmissionWorkItem(
            OneShotReadySelector(_item(work_item_id))
        ),
        projection_lifecycle_synchronizer=FakeLifecycle(),
        strategy=bridge,
    )
    return RunClaimBuilderCapacityQueueOnce(capacity_window_drain=drain)


class RecordingTrigger:
    def __init__(self, delegate: TriggerClaimBuilderCapacityDrainIfEnabled) -> None:
        self._delegate = delegate
        self.results: list[TriggerClaimBuilderCapacityDrainIfEnabledResult] = []

    async def execute(
        self,
        command: TriggerClaimBuilderCapacityDrainIfEnabledCommand,
    ) -> TriggerClaimBuilderCapacityDrainIfEnabledResult:
        result = await self._delegate.execute(command)
        self.results.append(result)
        return result


class OneShotReadySelector:
    def __init__(self, item: CapacityAdmissionSelectableWorkItem) -> None:
        self._item = item
        self._returned = False

    async def select_first_retryable_failed_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        **_: object,
    ) -> None:
        assert lane_key.account_ref is None
        return None

    async def select_first_ready_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        **_: object,
    ) -> CapacityAdmissionSelectableWorkItem | None:
        assert lane_key.account_ref is None
        if self._returned:
            return None
        self._returned = True
        return self._item


def _first_scheduled_work_item_id(
    scheduling_repository: FakeWorkItemSchedulingRepository,
) -> str:
    assert scheduling_repository.saved
    return scheduling_repository.saved[0].item.work_item_id


def _command_type_count(
    commands, command_type: KnowledgeExtractionCanonicalCommandType
) -> int:
    return sum(1 for command in commands if command.command_type == command_type.value)
