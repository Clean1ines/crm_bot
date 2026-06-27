from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections.abc import Mapping

import pytest

from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
    CapacityAdmissionDispatchContextSummary,
)
from src.contexts.capacity_admission_queue.application.ports.capacity_window_budget_repository_port import (
    CapacityReservation,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
)
from src.contexts.knowledge_workbench.application.sagas.claim_builder_capacity_drain_bridge import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
    ClaimBuilderCapacityDrainBridge,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from tests.contexts.knowledge_workbench.application.sagas.test_claim_builder_capacity_admission_phase_plan_applier import (
    _admitted_result,
    _apply,
)


def _now() -> datetime:
    return datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc)


def _selection_lane() -> CapacityAdmissionLaneKey:
    return CapacityAdmissionLaneKey(
        work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
        provider="groq",
        model_ref="qwen/qwen3-32b",
        account_ref=None,
    )


def _execution_window() -> CapacityAdmissionLaneKey:
    return CapacityAdmissionLaneKey(
        work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
        provider="groq",
        model_ref="qwen/qwen3-32b",
        account_ref="account-1",
    )


@dataclass(slots=True)
class FakeCommandLog:
    pending_commands: list[object] = field(default_factory=list)

    async def append_pending_command(self, command):
        self.pending_commands.append(command)


@dataclass(slots=True)
class FakeOutbox:
    events: list[object] = field(default_factory=list)

    async def append_event(self, event):
        self.events.append(event)
        return event


@dataclass(slots=True)
class FakeWorkflowUnitOfWork:
    command_log: FakeCommandLog = field(default_factory=FakeCommandLog)
    outbox: FakeOutbox = field(default_factory=FakeOutbox)


@dataclass(frozen=True, slots=True)
class FakeContextResolver:
    async def resolve_dispatch_context(
        self,
        *,
        work_item_id: str,
    ) -> CapacityAdmissionDispatchContextSummary:
        return CapacityAdmissionDispatchContextSummary(
            source_ref="source-document-1",
            source_unit_ref="source-unit-1",
        )


def _reservation() -> CapacityReservation:
    return CapacityReservation(
        provider="groq",
        account_ref="account-1",
        model_ref="qwen/qwen3-32b",
        request_count=1,
        token_count=512,
        reserved_at=_now(),
    )


@pytest.mark.asyncio
async def test_bridge_creates_execute_claim_builder_section_command_with_legacy_payload_shape() -> (
    None
):
    uow = FakeWorkflowUnitOfWork()

    result = await _bridge(uow).execute_admitted_work_item(
        work_item_id="work-item-1",
        selection_lane_key=_selection_lane(),
        execution_window_key=_execution_window(),
        reservation=_reservation(),
        worker_ref="worker-1",
        now=_now(),
    )

    command = uow.command_log.pending_commands[0]
    assert command.command_type == (
        KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
    )
    assert command.payload["workflow_run_id"] == "workflow-1"
    assert command.payload["dispatch_attempt_id"] == result.dispatch_attempt_id
    assert command.payload["work_item_id"] == "work-item-1"
    assert command.payload["source_ref"] == "source-document-1"
    assert command.payload["source_unit_ref"] == "source-unit-1"
    assert "llm_dispatch_preparation" in command.payload
    assert isinstance(command.payload["llm_dispatch_preparation"], Mapping)


@pytest.mark.asyncio
async def test_bridge_execute_payload_is_compatible_with_legacy_applier_payload() -> (
    None
):
    legacy_uow, _, _ = await _apply(_admitted_result())
    legacy_command = legacy_uow.command_log.pending_commands[0]
    bridge_uow = FakeWorkflowUnitOfWork()

    result = await _bridge(bridge_uow).execute_admitted_work_item(
        work_item_id="work-item-1",
        selection_lane_key=_selection_lane(),
        execution_window_key=_execution_window(),
        reservation=_reservation(),
        worker_ref="worker-1",
        now=_now(),
    )

    bridge_command = bridge_uow.command_log.pending_commands[0]
    assert bridge_command.command_type == (
        KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
    )
    assert result.dispatch_attempt_id is not None
    assert bridge_command.idempotency_key.value == (
        f"execute-claim-builder-section:workflow-1:{result.dispatch_attempt_id}"
    )
    for required_key in (
        "workflow_run_id",
        "dispatch_attempt_id",
        "work_item_id",
        "work_kind",
        "claim_builder_prepare_command_id",
        "claim_builder_prepare_idempotency_key",
        "llm_dispatch_preparation",
        "source_ref",
        "source_unit_ref",
        "scheduled_work_item_count",
    ):
        assert required_key in bridge_command.payload
        assert required_key in legacy_command.payload

    assert (
        bridge_command.payload["workflow_run_id"]
        == legacy_command.payload["workflow_run_id"]
    )
    assert (
        bridge_command.payload["work_item_id"] == legacy_command.payload["work_item_id"]
    )
    assert bridge_command.payload["work_kind"] == legacy_command.payload["work_kind"]
    assert bridge_command.payload["source_ref"] == legacy_command.payload["source_ref"]
    assert (
        bridge_command.payload["source_unit_ref"]
        == legacy_command.payload["source_unit_ref"]
    )
    assert (
        bridge_command.payload["scheduled_work_item_count"]
        == (legacy_command.payload["scheduled_work_item_count"])
    )
    assert isinstance(bridge_command.payload["llm_dispatch_preparation"], Mapping)
    legacy_preparation = legacy_command.payload["llm_dispatch_preparation"]
    assert isinstance(legacy_preparation, Mapping)
    assert (
        bridge_command.payload["active_model_ref"]
        == legacy_preparation["active_model_ref"]
    )


@pytest.mark.asyncio
async def test_bridge_uses_dispatch_attempt_id_in_idempotency_key() -> None:
    uow = FakeWorkflowUnitOfWork()

    result = await _bridge(uow).execute_admitted_work_item(
        work_item_id="work-item-1",
        selection_lane_key=_selection_lane(),
        execution_window_key=_execution_window(),
        reservation=_reservation(),
        worker_ref="worker-1",
        now=_now(),
    )

    command = uow.command_log.pending_commands[0]
    assert result.dispatch_attempt_id is not None
    assert command.idempotency_key.value == (
        f"execute-claim-builder-section:workflow-1:{result.dispatch_attempt_id}"
    )


@pytest.mark.asyncio
async def test_bridge_does_not_create_prepare_claim_builder_dispatch_batch() -> None:
    uow = FakeWorkflowUnitOfWork()

    await _bridge(uow).execute_admitted_work_item(
        work_item_id="work-item-1",
        selection_lane_key=_selection_lane(),
        execution_window_key=_execution_window(),
        reservation=_reservation(),
        worker_ref="worker-1",
        now=_now(),
    )

    command_types = {
        command.command_type for command in uow.command_log.pending_commands
    }
    assert len(uow.command_log.pending_commands) == 1
    assert (
        KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
        not in command_types
    )


@pytest.mark.asyncio
async def test_bridge_does_not_call_provider() -> None:
    uow = FakeWorkflowUnitOfWork()

    result = await _bridge(uow).execute_admitted_work_item(
        work_item_id="work-item-1",
        selection_lane_key=_selection_lane(),
        execution_window_key=_execution_window(),
        reservation=_reservation(),
        worker_ref="worker-1",
        now=_now(),
    )

    assert result.provider_call_started is False
    assert result.capacity_observation_recorded is False


@pytest.mark.asyncio
async def test_bridge_preserves_prepared_dispatch_event_shape_if_existing_ui_uses_it() -> (
    None
):
    uow = FakeWorkflowUnitOfWork()

    result = await _bridge(uow).execute_admitted_work_item(
        work_item_id="work-item-1",
        selection_lane_key=_selection_lane(),
        execution_window_key=_execution_window(),
        reservation=_reservation(),
        worker_ref="worker-1",
        now=_now(),
    )

    event = uow.outbox.events[0]
    assert event.event_type == (
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_ATTEMPT_PREPARED.value
    )
    assert event.payload["dispatch_attempt_id"] == result.dispatch_attempt_id
    assert event.payload["work_item_id"] == "work-item-1"
    assert event.payload["provider"] == "groq"
    assert event.payload["account_ref"] == "account-1"
    assert event.payload["model_ref"] == "qwen/qwen3-32b"
    assert event.payload["selection_account_ref"] is None
    assert event.payload["reserved_requests"] == 1
    assert event.payload["reserved_tokens"] == 512
    assert event.payload["source_unit_ref"] == "source-unit-1"


def _bridge(uow: FakeWorkflowUnitOfWork) -> ClaimBuilderCapacityDrainBridge:
    return ClaimBuilderCapacityDrainBridge(
        workflow_run_id="workflow-1",
        workflow_unit_of_work=uow,
        dispatch_context_resolver=FakeContextResolver(),
        source_document_ref="source-document-1",
        active_model_ref="qwen/qwen3-32b",
        scheduled_work_item_count=1,
    )
