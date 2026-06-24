from __future__ import annotations

from dataclasses import dataclass

from src.contexts.capacity_admission_queue.application.build_capacity_admission_projection_candidates import (
    BuildCapacityAdmissionProjectionCandidates,
    CapacityAdmissionLaneTarget,
)
from src.contexts.capacity_admission_queue.application.ports.capacity_admission_projection_writer_port import (
    CapacityAdmissionProjectionWriterPort,
)
from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    EnsureWorkItemScheduledOutcome,
    EnsureWorkItemsScheduled,
    EnsureWorkItemsScheduledCommand,
    work_item_schedule_payload_hash,
)
from src.contexts.knowledge_workbench.application.sagas.map_claim_builder_section_plans_to_execution_schedule import (
    MapClaimBuilderSectionPlansToExecutionSchedule,
    MapClaimBuilderSectionPlansToExecutionScheduleCommand,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    ClaimBuilderSectionWorkPlan,
    PlanClaimBuilderSectionWork,
    PlanClaimBuilderSectionWorkCommand,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)


@dataclass(frozen=True, slots=True)
class ScheduleClaimBuilderSectionWorkCommand:
    workflow_run_id: str
    source_document_ref: SourceDocumentRef
    source_units: tuple[SourceUnit, ...]
    project_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        if self.project_id is not None:
            _require_non_empty_text(self.project_id, field_name="project_id")
        if not isinstance(self.source_document_ref, SourceDocumentRef):
            raise TypeError("source_document_ref must be SourceDocumentRef")
        if not isinstance(self.source_units, tuple):
            raise TypeError("source_units must be tuple")
        for source_unit in self.source_units:
            if not isinstance(source_unit, SourceUnit):
                raise TypeError("source_units must contain only SourceUnit")


@dataclass(frozen=True, slots=True)
class ClaimBuilderScheduledWorkItemSummary:
    source_unit_ref: str
    source_unit_ordinal: int
    work_item_id: str
    work_kind: str
    idempotency_key: str
    payload_hash: str
    schedule_status: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.source_unit_ref, field_name="source_unit_ref")
        if not isinstance(self.source_unit_ordinal, int):
            raise TypeError("source_unit_ordinal must be int")
        if self.source_unit_ordinal < 0:
            raise ValueError("source_unit_ordinal must be >= 0")
        _require_non_empty_text(self.work_item_id, field_name="work_item_id")
        _require_non_empty_text(self.work_kind, field_name="work_kind")
        _require_non_empty_text(self.idempotency_key, field_name="idempotency_key")
        _require_non_empty_text(self.payload_hash, field_name="payload_hash")
        _require_non_empty_text(self.schedule_status, field_name="schedule_status")

    def to_checkpoint_payload(self) -> dict[str, object]:
        return {
            "source_unit_ref": self.source_unit_ref,
            "source_unit_ordinal": self.source_unit_ordinal,
            "work_item_id": self.work_item_id,
            "work_kind": self.work_kind,
            "idempotency_key": self.idempotency_key,
            "payload_hash": self.payload_hash,
            "schedule_status": self.schedule_status,
        }


@dataclass(frozen=True, slots=True)
class ScheduleClaimBuilderSectionWorkResult:
    planned_count: int
    created_count: int
    already_exists_count: int
    conflict_count: int
    scheduled_items: tuple[ClaimBuilderScheduledWorkItemSummary, ...]
    capacity_admission_projection_persisted_count: int = 0

    def __post_init__(self) -> None:
        for field_name, value in (
            ("planned_count", self.planned_count),
            ("created_count", self.created_count),
            ("already_exists_count", self.already_exists_count),
            ("conflict_count", self.conflict_count),
            (
                "capacity_admission_projection_persisted_count",
                self.capacity_admission_projection_persisted_count,
            ),
        ):
            if not isinstance(value, int):
                raise TypeError(f"{field_name} must be int")
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")

        if not isinstance(self.scheduled_items, tuple):
            raise TypeError("scheduled_items must be tuple")
        for item in self.scheduled_items:
            if not isinstance(item, ClaimBuilderScheduledWorkItemSummary):
                raise TypeError(
                    "scheduled_items must contain only "
                    "ClaimBuilderScheduledWorkItemSummary",
                )
        if len(self.scheduled_items) != self.planned_count:
            raise ValueError("scheduled_items length must equal planned_count")

    @property
    def is_conflict_free(self) -> bool:
        return self.conflict_count == 0


@dataclass(frozen=True, slots=True)
class ScheduleClaimBuilderSectionWork:
    scheduling_repository: WorkItemSchedulingRepositoryPort
    capacity_admission_projection_writer: (
        CapacityAdmissionProjectionWriterPort | None
    ) = None
    capacity_admission_lane_target: CapacityAdmissionLaneTarget | None = None

    def __post_init__(self) -> None:
        if (self.capacity_admission_projection_writer is None) != (
            self.capacity_admission_lane_target is None
        ):
            raise ValueError(
                "capacity admission projection writer and lane target must be provided together"
            )

    async def execute(
        self,
        command: ScheduleClaimBuilderSectionWorkCommand,
    ) -> ScheduleClaimBuilderSectionWorkResult:
        workbench_plans = PlanClaimBuilderSectionWork().execute(
            PlanClaimBuilderSectionWorkCommand(
                workflow_run_id=command.workflow_run_id,
                source_document_ref=command.source_document_ref,
                source_units=command.source_units,
                project_id=command.project_id,
            ),
        )
        execution_schedule = MapClaimBuilderSectionPlansToExecutionSchedule().execute(
            MapClaimBuilderSectionPlansToExecutionScheduleCommand(
                plans=workbench_plans.plans,
            ),
        )
        scheduling_result = await EnsureWorkItemsScheduled(
            repository=self.scheduling_repository,
        ).execute(
            EnsureWorkItemsScheduledCommand(
                plans=execution_schedule.schedule_plans,
            ),
        )

        capacity_admission_projection_persisted_count = 0
        if (
            scheduling_result.conflict_count == 0
            and self.capacity_admission_projection_writer is not None
            and self.capacity_admission_lane_target is not None
        ):
            projection_candidates = BuildCapacityAdmissionProjectionCandidates(
                lane_target=self.capacity_admission_lane_target,
            ).execute(execution_schedule.schedule_plans)
            projection_result = await self.capacity_admission_projection_writer.persist_projection_candidates(
                projection_candidates,
            )
            capacity_admission_projection_persisted_count = (
                projection_result.persisted_count
            )

        return ScheduleClaimBuilderSectionWorkResult(
            planned_count=len(execution_schedule.schedule_plans),
            created_count=scheduling_result.created_count,
            already_exists_count=scheduling_result.already_exists_count,
            conflict_count=scheduling_result.conflict_count,
            scheduled_items=_build_scheduled_item_summaries(
                workbench_plans=workbench_plans.plans,
                scheduling_outcomes=scheduling_result.outcomes,
            ),
            capacity_admission_projection_persisted_count=(
                capacity_admission_projection_persisted_count
            ),
        )


def _build_scheduled_item_summaries(
    *,
    workbench_plans: tuple[ClaimBuilderSectionWorkPlan, ...],
    scheduling_outcomes: tuple[EnsureWorkItemScheduledOutcome, ...],
) -> tuple[ClaimBuilderScheduledWorkItemSummary, ...]:
    workbench_plan_by_work_item_id = {
        plan.work_item_id: plan for plan in workbench_plans
    }

    summaries: list[ClaimBuilderScheduledWorkItemSummary] = []
    for outcome in scheduling_outcomes:
        plan = outcome.plan
        workbench_plan = workbench_plan_by_work_item_id[plan.work_item_id]
        summaries.append(
            ClaimBuilderScheduledWorkItemSummary(
                source_unit_ref=workbench_plan.source_unit_ref.value,
                source_unit_ordinal=workbench_plan.source_unit_ordinal,
                work_item_id=plan.work_item_id,
                work_kind=plan.work_kind.value,
                idempotency_key=plan.idempotency_key,
                payload_hash=work_item_schedule_payload_hash(plan.payload),
                schedule_status=outcome.status.value,
            ),
        )
    return tuple(summaries)


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
