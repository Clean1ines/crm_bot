from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from src.contexts.capacity_admission_queue.application.admit_capacity_admission_work_item import (
    CapacityAdmissionProjectionLeaseResult,
)
from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
    CapacityAdmissionCapacityReservationSummary,
    CapacityAdmissionLaneSummary,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
    CapacityAdmissionSelectableWorkItem,
)
from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_repository_port import (
    WorkItemAttemptDispatchRecord,
)
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    LeasedWorkItemRecord,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    default_groq_llm_model_route_catalog,
)
from src.interfaces.composition.capacity_window_admission_execution_boundary import (
    StartAttemptCapacityWindowAdmissionExecutionBoundary,
)


def _now() -> datetime:
    return datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)


def _lease_expires_at() -> datetime:
    return _now() + timedelta(seconds=90)


class FakeAttemptDispatchRepository:
    def __init__(self) -> None:
        self.records: list[WorkItemAttemptDispatchRecord] = []

    async def save_started_dispatch_attempt(
        self,
        record: WorkItemAttemptDispatchRecord,
    ) -> None:
        self.records.append(record)


def _lane_key() -> CapacityAdmissionLaneKey:
    return CapacityAdmissionLaneKey(
        work_kind="knowledge_workbench.claim_builder.section_extraction",
        provider="groq",
        account_ref="groq-account-1",
        model_ref="qwen/qwen3-32b",
    )


def _leased_work_item() -> LeasedWorkItemRecord:
    return LeasedWorkItemRecord(
        work_item=WorkItem(
            work_item_id="work-1",
            work_kind=WorkKind("knowledge_workbench.claim_builder.section_extraction"),
            status=WorkItemStatus.LEASED,
            attempt_count=3,
            leased_by=WorkerRef("worker-1"),
            lease_token=LeaseToken("lease-token-1"),
            lease_expires_at=_lease_expires_at(),
        ),
        schedule_payload={
            "workflow_run_id": "workflow-1",
            "source_document_ref": "source-document-1",
            "source_unit_ref": "source-unit-1",
        },
    )


@pytest.mark.asyncio
async def test_execution_boundary_starts_real_dispatch_attempt() -> None:
    repository = FakeAttemptDispatchRepository()
    boundary = StartAttemptCapacityWindowAdmissionExecutionBoundary(
        attempt_dispatch_repository=repository,
        route_catalog=default_groq_llm_model_route_catalog(),
    )

    result = await boundary.start_or_append_execution(
        selected_work_item=CapacityAdmissionSelectableWorkItem(
            work_item_id="work-1",
            lane_key=_lane_key(),
            status="ready",
            required_window_tokens=150,
            input_tokens=100,
            artifact_tokens=10,
        ),
        execution_lane_key=_lane_key(),
        leased_work_item=_leased_work_item(),
        projection_lease=CapacityAdmissionProjectionLeaseResult(
            work_item_id="work-1",
            lane_key=_lane_key(),
            previous_status="ready",
            status="leased",
            event_id=UUID("00000000-0000-0000-0000-000000000701"),
        ),
        capacity_reservation=CapacityAdmissionCapacityReservationSummary(
            reservation_ref="claim-builder-dispatch:2:work-1",
            work_item_id="work-1",
            lane=CapacityAdmissionLaneSummary(
                work_kind="knowledge_workbench.claim_builder.section_extraction",
                provider="groq",
                account_ref="groq-account-1",
                model_ref="qwen/qwen3-32b",
            ),
            reserved_requests=1,
            reserved_tokens=150,
            expires_at=_lease_expires_at(),
        ),
        now=_now(),
    )

    assert result.work_item_id == "work-1"
    assert result.attempt_id == "lease-token-1"
    assert result.attempt_number == 3
    assert result.execute_command_ref is None

    record = repository.records[0]
    assert record.attempt_id == "lease-token-1"
    assert record.work_item_id == "work-1"
    assert record.attempt_number == 3
    assert record.llm_allocation_payload == {
        "provider": "groq",
        "account_ref": "groq-account-1",
        "model_ref": "qwen/qwen3-32b",
        "slot_index": 1,
    }
    assert record.dispatch_payload["llm_execution_settings"] == {
        "reasoning_enabled": False
    }
    assert record.dispatch_payload["schedule_payload"]["source_unit_ref"] == (
        "source-unit-1"
    )
