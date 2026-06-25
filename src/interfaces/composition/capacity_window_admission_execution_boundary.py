from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.contexts.capacity_admission_queue.application.admit_capacity_admission_work_item import (
    CapacityAdmissionProjectionLeaseResult,
)
from src.contexts.capacity_admission_queue.application.capacity_window_admission_pass import (
    CapacityWindowAdmissionExecutionReference,
)
from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
    CapacityAdmissionCapacityReservationSummary,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
    CapacityAdmissionSelectableWorkItem,
)
from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_repository_port import (
    WorkItemAttemptDispatchRepositoryPort,
)
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    LeasedWorkItemRecord,
)
from src.contexts.llm_runtime.application.capacity.project_llm_capacity_to_capacity_runtime import (
    LlmCapacityAllocationSlot,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelRouteCatalog,
)
from src.interfaces.composition.lease_llm_admitted_work_items import (
    LlmAdmittedLeasedWorkItem,
)
from src.interfaces.composition.start_llm_admitted_work_item_attempts import (
    StartLlmAdmittedWorkItemAttempts,
    StartLlmAdmittedWorkItemAttemptsCommand,
)


CapacityWindowAdmissionSelectionKind = Literal["fresh", "retryable"]


@dataclass(frozen=True, slots=True)
class StartAttemptCapacityWindowAdmissionExecutionBoundary:
    attempt_dispatch_repository: WorkItemAttemptDispatchRepositoryPort
    route_catalog: LlmModelRouteCatalog

    async def start_or_append_execution(
        self,
        *,
        selected_work_item: CapacityAdmissionSelectableWorkItem,
        execution_lane_key: CapacityAdmissionLaneKey,
        leased_work_item: LeasedWorkItemRecord,
        projection_lease: CapacityAdmissionProjectionLeaseResult,
        capacity_reservation: CapacityAdmissionCapacityReservationSummary,
        now,
    ) -> CapacityWindowAdmissionExecutionReference:
        del projection_lease
        lane = execution_lane_key
        if lane.account_ref is None:
            raise ValueError("capacity admission execution requires account_ref")
        if selected_work_item.lane_key.work_kind != lane.work_kind:
            raise ValueError("execution lane work_kind must match selected work item")
        if selected_work_item.lane_key.provider != lane.provider:
            raise ValueError("execution lane provider must match selected work item")
        if selected_work_item.lane_key.model_ref != lane.model_ref:
            raise ValueError("execution lane model_ref must match selected work item")

        result = await StartLlmAdmittedWorkItemAttempts(
            repository=self.attempt_dispatch_repository,
        ).execute(
            StartLlmAdmittedWorkItemAttemptsCommand(
                leased_items=(
                    LlmAdmittedLeasedWorkItem(
                        leased=leased_work_item,
                        allocation=LlmCapacityAllocationSlot(
                            provider=lane.provider,
                            account_ref=lane.account_ref,
                            model_ref=lane.model_ref,
                            slot_index=_slot_index_from_reservation_ref(
                                capacity_reservation.reservation_ref
                            ),
                        ),
                        execution_settings=(
                            self.route_catalog.execution_settings_for_model_ref(
                                lane.model_ref,
                            )
                        ),
                        selection_kind=_selection_kind(selected_work_item),
                    ),
                ),
                started_at=now,
            )
        )

        if len(result.started_attempts) != 1:
            raise RuntimeError("capacity admission execution must start one attempt")
        started_attempt = result.started_attempts[0]
        return CapacityWindowAdmissionExecutionReference(
            work_item_id=started_attempt.work_item_id,
            attempt_id=started_attempt.attempt_id,
            attempt_number=started_attempt.attempt_number,
        )


def _selection_kind(
    selected_work_item: CapacityAdmissionSelectableWorkItem,
) -> CapacityWindowAdmissionSelectionKind:
    if selected_work_item.status == "retryable_failed":
        return "retryable"
    if selected_work_item.status == "ready":
        return "fresh"
    raise ValueError("unsupported capacity admission projection status")


def _slot_index_from_reservation_ref(reservation_ref: str) -> int:
    parts = reservation_ref.split(":")
    if len(parts) < 2:
        raise ValueError("reservation_ref must include admission index")
    raw_index = parts[-2]
    if not raw_index.isdigit():
        raise ValueError("reservation_ref admission index must be numeric")
    admission_number = int(raw_index)
    if admission_number <= 0:
        raise ValueError("reservation_ref admission index must be positive")
    return admission_number - 1
