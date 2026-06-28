from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from src.contexts.capacity_admission_queue.application.capacity_window_admission_pass import (
    CapacityWindowAdmissionPassCommand,
)
from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
    CapacityAdmissionAdmittedItemSummary,
    CapacityAdmissionDispatchContextSummary,
    CapacityAdmissionFrontendEventSummary,
    CapacityAdmissionLaneSummary,
    CapacityAdmissionProjectionLeaseSummary,
    CapacityAdmissionStartedAttemptSummary,
    CapacityWindowAdmissionLogEvent,
    CapacityWindowAdmissionPassResult,
)
from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_repository_port import (
    WorkItemAttemptDispatchRecord,
)
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    DueWorkItemRecord,
    LeasedWorkItemRecord,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.knowledge_workbench.application.sagas.capacity_admission_phase_mapping import (
    CLAIM_BUILDER_ADMISSION_PHASE_PROFILE,
)
from src.contexts.knowledge_workbench.application.sagas.handle_prepare_claim_builder_dispatch_batch_command import (
    HandlePrepareClaimBuilderDispatchBatchCommand,
    HandlePrepareClaimBuilderDispatchBatchCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    default_groq_llm_model_route_catalog,
)
from src.contexts.llm_runtime.infrastructure.postgres.postgres_llm_route_capacity_reservation_repository import (
    LlmRouteCapacityReservation,
    LlmRouteCapacityReservationTotal,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.entities.workflow_progress_snapshot import (
    WorkflowProgressSnapshot,
)
from src.contexts.workflow_runtime.domain.entities.workflow_resource_usage_snapshot import (
    WorkflowResourceUsageSnapshot,
)
from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


def _now() -> datetime:
    return datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "workflow-1"


def _workflow_command() -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(
            "workflow-command:prepare-claim-builder-dispatch-batch:workflow-1"
        ),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
        ),
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(
            "prepare-claim-builder-dispatch-batch:workflow-1"
        ),
        payload={
            "workflow_run_id": _workflow_run_id(),
            "source_document_ref": "source-document-1",
            "scheduled_work_item_count": 1,
            "llm_dispatch_preparation": {
                "profile": {
                    "profile_id": "faq_claim_observations",
                    "input_tokens": 100,
                    "artifact_tokens": 10,
                    "request_count": 1,
                },
                "account_capacities": (
                    {
                        "provider": "groq",
                        "account_ref": "groq-account-1",
                        "model_ref": "qwen/qwen3-32b",
                        "remaining_minute_requests": 2,
                        "remaining_minute_tokens": 7000,
                        "remaining_daily_requests": 100,
                        "remaining_daily_tokens": 50000,
                    },
                ),
                "active_model_ref": "qwen/qwen3-32b",
            },
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _work_item(
    work_item_id: str,
    *,
    status: WorkItemStatus = WorkItemStatus.READY,
    attempt_count: int = 0,
) -> WorkItem:
    return WorkItem(
        work_item_id=work_item_id,
        work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
        status=status,
        attempt_count=attempt_count,
        last_error_kind="rate_limit"
        if status is WorkItemStatus.RETRYABLE_FAILED
        else None,
    )


def _schedule_payload(work_item_id: str) -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "source_document_ref": "source-document-1",
        "source_unit_ref": f"source-unit-{work_item_id[-1]}",
    }


def _lane() -> CapacityAdmissionLaneSummary:
    return CapacityAdmissionLaneSummary(
        work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
        provider="groq",
        account_ref="groq-account-1",
        model_ref="qwen/qwen3-32b",
    )


def _admission_result() -> CapacityWindowAdmissionPassResult:
    projection_event_id = UUID("00000000-0000-0000-0000-000000000201")
    return CapacityWindowAdmissionPassResult(
        workflow_run_id=_workflow_run_id(),
        phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
        operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
        work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
        lane=_lane(),
        admitted_items=(
            CapacityAdmissionAdmittedItemSummary(
                work_item_id="work-item-1",
                lane=_lane(),
                selection_kind="fresh",
                input_tokens=100,
                artifact_tokens=10,
                required_window_tokens=150,
                dispatch_context=CapacityAdmissionDispatchContextSummary(
                    source_ref="source-document-1",
                    source_unit_ref="source-unit-1",
                ),
            ),
        ),
        projection_leases=(
            CapacityAdmissionProjectionLeaseSummary(
                work_item_id="work-item-1",
                lane=_lane(),
                previous_status="ready",
                status="leased",
                event_id=projection_event_id,
            ),
        ),
        started_attempts=(
            CapacityAdmissionStartedAttemptSummary(
                work_item_id="work-item-1",
                attempt_id="attempt-1",
                attempt_number=1,
            ),
        ),
        frontend_event_summary=CapacityAdmissionFrontendEventSummary(
            event_kind="capacity_admission_pass_completed",
            workflow_run_id=_workflow_run_id(),
            phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
            operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
            work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
            lane=_lane(),
            admitted_count=1,
            started_attempt_count=1,
            work_item_ids=("work-item-1",),
            attempt_ids=("attempt-1",),
            projection_event_ids=(projection_event_id,),
            occurred_at=_now(),
        ),
        log_event=CapacityWindowAdmissionLogEvent.PASS_COMPLETED,
    )


@dataclass(slots=True)
class FakeCapacityWindowAdmissionPass:
    result: CapacityWindowAdmissionPassResult
    calls: list[CapacityWindowAdmissionPassCommand] = field(default_factory=list)

    async def execute(self, command: CapacityWindowAdmissionPassCommand) -> object:
        self.calls.append(command)
        return self.result


@dataclass(slots=True)
class FakeWorkItemLeaseRepository:
    due_records: list[DueWorkItemRecord]
    peek_calls: int = 0
    lease_by_id_calls: list[str] = field(default_factory=list)
    leased_records: list[LeasedWorkItemRecord] = field(default_factory=list)

    async def peek_due_work_items(
        self,
        *,
        work_kind: WorkKind,
        requested_items: int,
        now: datetime,
    ) -> tuple[DueWorkItemRecord, ...]:
        del now
        assert work_kind == CLAIM_BUILDER_SECTION_WORK_KIND
        self.peek_calls += 1
        ordered = sorted(
            self.due_records,
            key=lambda record: (
                0 if record.work_item.status is WorkItemStatus.RETRYABLE_FAILED else 1,
                record.work_item.work_item_id,
            ),
        )
        return tuple(ordered[:requested_items])

    async def lease_due_work_item(
        self,
        *,
        work_kind: WorkKind,
        worker: WorkerRef,
        lease_token: LeaseToken,
        lease_expires_at: datetime,
        now: datetime,
    ) -> LeasedWorkItemRecord | None:
        due = await self.peek_due_work_items(
            work_kind=work_kind,
            requested_items=1,
            now=now,
        )
        if not due:
            return None
        return await self.lease_due_work_item_by_id(
            work_kind=work_kind,
            work_item_id=due[0].work_item.work_item_id,
            worker=worker,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            now=now,
        )

    async def lease_due_work_item_by_id(
        self,
        *,
        work_kind: WorkKind,
        work_item_id: str,
        worker: WorkerRef,
        lease_token: LeaseToken,
        lease_expires_at: datetime,
        now: datetime,
    ) -> LeasedWorkItemRecord | None:
        assert work_kind == CLAIM_BUILDER_SECTION_WORK_KIND
        self.lease_by_id_calls.append(work_item_id)
        for index, record in enumerate(self.due_records):
            if record.work_item.work_item_id != work_item_id:
                continue
            if record.work_item.status not in {
                WorkItemStatus.READY,
                WorkItemStatus.RETRYABLE_FAILED,
            }:
                return None
            leased = WorkItemStateMachine.lease_ready(
                record.work_item,
                worker=worker,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
                now=now,
            )
            self.due_records.pop(index)
            leased_record = LeasedWorkItemRecord(
                work_item=leased,
                schedule_payload=record.schedule_payload,
            )
            self.leased_records.append(leased_record)
            return leased_record
        return None

    def complete(self, work_item_id: str) -> None:
        for index, record in enumerate(self.leased_records):
            if record.work_item.work_item_id == work_item_id:
                self.leased_records.pop(index)
                return


@dataclass(slots=True)
class FakeAttemptDispatchRepository:
    records: list[WorkItemAttemptDispatchRecord] = field(default_factory=list)

    async def save_started_dispatch_attempt(
        self,
        record: WorkItemAttemptDispatchRecord,
    ) -> None:
        self.records.append(record)


@dataclass(slots=True)
class FakeReservationRepository:
    active: tuple[LlmRouteCapacityReservationTotal, ...] = ()
    reservations: list[LlmRouteCapacityReservation] = field(default_factory=list)
    locked_routes: list[tuple[str, str, str]] = field(default_factory=list)

    async def lock_route(
        self,
        *,
        provider: str,
        account_ref: str,
        model_ref: str,
    ) -> None:
        self.locked_routes.append((provider, account_ref, model_ref))

    async def active_totals(
        self,
        *,
        provider: str,
        account_refs: tuple[str, ...],
        model_ref: str,
        now: datetime,
    ) -> tuple[LlmRouteCapacityReservationTotal, ...]:
        del provider, account_refs, model_ref, now
        return self.active

    async def reserve(self, reservation: LlmRouteCapacityReservation) -> None:
        self.reservations.append(reservation)


@dataclass(slots=True)
class FakeCapacityObservationReadRepository:
    async def latest_observations_for_accounts(
        self,
        *,
        provider: str,
        account_refs: tuple[str, ...],
        model_ref: str,
    ) -> tuple[object, ...]:
        del provider, account_refs, model_ref
        return ()


@dataclass(slots=True)
class FakeCommandLogRepository:
    pending_commands: list[WorkflowCommand] = field(default_factory=list)
    completed_command_ids: list[WorkflowCommandId] = field(default_factory=list)

    async def append_pending_command(self, command: WorkflowCommand) -> WorkflowCommand:
        self.pending_commands.append(command)
        return command

    async def mark_command_completed(
        self,
        *,
        command_id: WorkflowCommandId,
        completed_at: datetime,
    ) -> WorkflowCommand:
        del completed_at
        self.completed_command_ids.append(command_id)
        return _workflow_command()


@dataclass(slots=True)
class FakeOutboxRepository:
    events: list[WorkflowEvent] = field(default_factory=list)

    async def append_event(self, event: WorkflowEvent) -> WorkflowEvent:
        self.events.append(event)
        return event


@dataclass(slots=True)
class FakeProgressSnapshotRepository:
    snapshot: WorkflowProgressSnapshot | None = None

    async def get_snapshot(
        self,
        workflow_run_id: str,
    ) -> WorkflowProgressSnapshot | None:
        if (
            self.snapshot is not None
            and self.snapshot.workflow_run_id == workflow_run_id
        ):
            return self.snapshot
        return None

    async def save_snapshot(
        self,
        snapshot: WorkflowProgressSnapshot,
    ) -> WorkflowProgressSnapshot:
        self.snapshot = snapshot
        return snapshot


@dataclass(slots=True)
class FakeTimelineRepository:
    entries: list[WorkflowTimelineEntry] = field(default_factory=list)

    async def append_entry(
        self,
        entry: WorkflowTimelineEntry,
    ) -> WorkflowTimelineEntry:
        self.entries.append(entry)
        return entry


@dataclass(slots=True)
class FakeResourceUsageRepository:
    usage: WorkflowResourceUsageSnapshot | None = None


@dataclass(slots=True)
class FakeWorkflowRuntimeUnitOfWork:
    command_log: FakeCommandLogRepository = field(
        default_factory=FakeCommandLogRepository
    )
    outbox: FakeOutboxRepository = field(default_factory=FakeOutboxRepository)
    progress_snapshots: FakeProgressSnapshotRepository = field(
        default_factory=FakeProgressSnapshotRepository
    )
    timeline: FakeTimelineRepository = field(default_factory=FakeTimelineRepository)
    resource_usage: FakeResourceUsageRepository = field(
        default_factory=FakeResourceUsageRepository
    )


def _due_records(
    *items: tuple[str, WorkItemStatus],
) -> list[DueWorkItemRecord]:
    return [
        DueWorkItemRecord(
            work_item=_work_item(
                work_item_id,
                status=status,
                attempt_count=1 if status is WorkItemStatus.RETRYABLE_FAILED else 0,
            ),
            schedule_payload=_schedule_payload(work_item_id),
        )
        for work_item_id, status in items
    ]


@pytest.mark.asyncio
async def test_prepare_claim_builder_ignores_capacity_admission_branch_when_provided() -> (
    None
):
    admission_pass = FakeCapacityWindowAdmissionPass(result=_admission_result())
    lease_repository = FakeWorkItemLeaseRepository(
        due_records=_due_records(("work-item-1", WorkItemStatus.READY)),
    )
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    result = await HandlePrepareClaimBuilderDispatchBatchCommandHandler().execute(
        HandlePrepareClaimBuilderDispatchBatchCommand(
            workflow_command=_workflow_command(),
        ),
        capacity_window_admission_pass=admission_pass,
        workflow_unit_of_work=workflow_unit_of_work,
        work_item_lease_repository=lease_repository,
        attempt_dispatch_repository=FakeAttemptDispatchRepository(),
        capacity_reservation_repository=FakeReservationRepository(),
        capacity_observation_read_repository=FakeCapacityObservationReadRepository(),
        route_catalog=default_groq_llm_model_route_catalog(),
    )

    assert result.prepared_dispatch_count == 1
    assert result.appended_next_command_count == 1
    assert admission_pass.calls == []
    assert lease_repository.lease_by_id_calls == ["work-item-1"]

    assert workflow_unit_of_work.outbox.events[0].event_type == (
        "ClaimBuilderDispatchBatchPrepared"
    )
    execute_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert (
        execute_command.command_type
        == KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
    )
    assert str(execute_command.payload["dispatch_attempt_id"]).startswith(
        "claim-builder-dispatch:workflow-1:0:work-item-1"
    )
    assert execute_command.payload["work_item_id"] == "work-item-1"
    assert workflow_unit_of_work.command_log.completed_command_ids == [
        _workflow_command().command_id
    ]


async def _execute_direct_prepare(
    *,
    lease_repository: FakeWorkItemLeaseRepository,
    reservation_repository: FakeReservationRepository | None = None,
    workflow_unit_of_work: FakeWorkflowRuntimeUnitOfWork | None = None,
    workflow_command: WorkflowCommand | None = None,
) -> tuple[
    object,
    FakeWorkflowRuntimeUnitOfWork,
    FakeAttemptDispatchRepository,
    FakeReservationRepository,
]:
    attempt_repository = FakeAttemptDispatchRepository()
    reservation_repository = reservation_repository or FakeReservationRepository()
    workflow_unit_of_work = workflow_unit_of_work or FakeWorkflowRuntimeUnitOfWork()

    result = await HandlePrepareClaimBuilderDispatchBatchCommandHandler().execute(
        HandlePrepareClaimBuilderDispatchBatchCommand(
            workflow_command=workflow_command or _workflow_command(),
        ),
        workflow_unit_of_work=workflow_unit_of_work,
        work_item_lease_repository=lease_repository,
        attempt_dispatch_repository=attempt_repository,
        capacity_reservation_repository=reservation_repository,
        capacity_observation_read_repository=FakeCapacityObservationReadRepository(),
        route_catalog=default_groq_llm_model_route_catalog(),
    )

    return result, workflow_unit_of_work, attempt_repository, reservation_repository


@pytest.mark.asyncio
async def test_prepare_claim_builder_direct_path_works_without_admission_pass() -> None:
    lease_repository = FakeWorkItemLeaseRepository(
        due_records=_due_records(("work-item-1", WorkItemStatus.READY)),
    )

    (
        result,
        workflow_unit_of_work,
        attempt_repository,
        reservation_repository,
    ) = await _execute_direct_prepare(lease_repository=lease_repository)

    assert result.prepared_dispatch_count == 1
    assert lease_repository.peek_calls == 1
    assert lease_repository.lease_by_id_calls == ["work-item-1"]
    assert len(attempt_repository.records) == 1
    assert len(reservation_repository.reservations) == 1
    execute_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert (
        execute_command.command_type
        == KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
    )
    assert execute_command.payload["work_item_id"] == "work-item-1"


@pytest.mark.asyncio
async def test_prepare_claim_builder_direct_path_does_not_call_capacity_admission_pass() -> (
    None
):
    lease_repository = FakeWorkItemLeaseRepository(
        due_records=_due_records(("work-item-1", WorkItemStatus.READY)),
    )
    admission_pass = FakeCapacityWindowAdmissionPass(result=_admission_result())

    result = await HandlePrepareClaimBuilderDispatchBatchCommandHandler().execute(
        HandlePrepareClaimBuilderDispatchBatchCommand(
            workflow_command=_workflow_command()
        ),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
        capacity_window_admission_pass=admission_pass,
        work_item_lease_repository=lease_repository,
        attempt_dispatch_repository=FakeAttemptDispatchRepository(),
        capacity_reservation_repository=FakeReservationRepository(),
        capacity_observation_read_repository=FakeCapacityObservationReadRepository(),
        route_catalog=default_groq_llm_model_route_catalog(),
    )

    assert result.prepared_dispatch_count == 1
    assert admission_pass.calls == []


@pytest.mark.asyncio
async def test_prepare_claim_builder_prefers_retryable_work_item_over_ready() -> None:
    lease_repository = FakeWorkItemLeaseRepository(
        due_records=_due_records(
            ("work-item-ready", WorkItemStatus.READY),
            ("work-item-retry", WorkItemStatus.RETRYABLE_FAILED),
        ),
    )

    _, workflow_unit_of_work, _, _ = await _execute_direct_prepare(
        lease_repository=lease_repository,
    )

    execute_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert execute_command.payload["work_item_id"] == "work-item-retry"


@pytest.mark.asyncio
async def test_prepare_claim_builder_capacity_exhausted_does_not_lease_or_execute() -> (
    None
):
    lease_repository = FakeWorkItemLeaseRepository(
        due_records=_due_records(("work-item-1", WorkItemStatus.READY)),
    )
    reservation_repository = FakeReservationRepository(
        active=(
            LlmRouteCapacityReservationTotal(
                provider="groq",
                account_ref="groq-account-1",
                model_ref="qwen/qwen3-32b",
                reserved_requests=2,
                reserved_tokens=7_000,
            ),
        ),
    )

    (
        result,
        workflow_unit_of_work,
        attempt_repository,
        reservation_repository,
    ) = await _execute_direct_prepare(
        lease_repository=lease_repository,
        reservation_repository=reservation_repository,
    )

    assert result.prepared_dispatch_count == 0
    assert lease_repository.lease_by_id_calls == []
    assert attempt_repository.records == []
    assert reservation_repository.reservations == []
    assert workflow_unit_of_work.command_log.pending_commands == []
    assert workflow_unit_of_work.command_log.completed_command_ids == [
        _workflow_command().command_id
    ]


@pytest.mark.asyncio
async def test_prepare_claim_builder_dispatches_next_item_after_first_completes() -> (
    None
):
    lease_repository = FakeWorkItemLeaseRepository(
        due_records=_due_records(
            ("work-item-1", WorkItemStatus.READY),
            ("work-item-2", WorkItemStatus.READY),
            ("work-item-3", WorkItemStatus.READY),
        ),
    )

    _, first_uow, first_attempt_repository, _ = await _execute_direct_prepare(
        lease_repository=lease_repository,
    )
    first_execute = first_uow.command_log.pending_commands[0]
    first_work_item_id = str(first_execute.payload["work_item_id"])
    assert first_work_item_id == "work-item-1"
    assert lease_repository.leased_records[0].work_item.work_item_id == "work-item-1"
    assert first_attempt_repository.records[0].work_item_id == "work-item-1"

    lease_repository.complete(first_work_item_id)

    next_prepare_command = replace(
        _workflow_command(),
        command_id=WorkflowCommandId(
            "workflow-command:prepare-claim-builder-dispatch-batch:workflow-1:second"
        ),
        idempotency_key=WorkflowIdempotencyKey(
            "prepare-claim-builder-dispatch-batch:workflow-1:second"
        ),
        run_after=_now() + timedelta(seconds=1),
        created_at=_now() + timedelta(seconds=1),
        updated_at=_now() + timedelta(seconds=1),
    )
    _, second_uow, second_attempt_repository, _ = await _execute_direct_prepare(
        lease_repository=lease_repository,
        workflow_command=next_prepare_command,
    )

    second_execute = second_uow.command_log.pending_commands[0]
    second_work_item_id = str(second_execute.payload["work_item_id"])
    assert second_work_item_id == "work-item-2"
    assert second_work_item_id != first_work_item_id
    assert second_attempt_repository.records[0].work_item_id == "work-item-2"
    assert [
        record.work_item.work_item_id for record in lease_repository.due_records
    ] == ["work-item-3"]
