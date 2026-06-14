from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.handle_build_cluster_preview_command import (
    HandleBuildClusterPreviewCommand,
    HandleBuildClusterPreviewCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_cluster_preview import (
    DraftClaimClusterPreview,
    DraftClaimClusterPreviewBuildResult,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.entities.workflow_event_cursor import (
    WorkflowEventCursor,
)
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
from src.contexts.workflow_runtime.domain.value_objects.workflow_consumer_ref import (
    WorkflowConsumerRef,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


def _now() -> datetime:
    return datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def _workflow_command(
    *,
    command_type: KnowledgeExtractionCanonicalCommandType = (
        KnowledgeExtractionCanonicalCommandType.BUILD_CLUSTER_PREVIEW
    ),
    status: WorkflowCommandStatus = WorkflowCommandStatus.PENDING,
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{command_type.value}"),
        command_type=command_type.value,
        workflow_run_id="workflow-1",
        idempotency_key=WorkflowIdempotencyKey(f"{command_type.value}:workflow-1"),
        payload={"workflow_run_id": "workflow-1"},
        status=status,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


@dataclass(slots=True)
class FakeReductionRepository:
    active_raw_count: int = 0

    async def count_active_raw_nodes(self, *, workflow_run_id: str) -> int:
        assert workflow_run_id == "workflow-1"
        return self.active_raw_count

    async def list_final_compacted_nodes_for_preview(
        self,
        *,
        workflow_run_id: str,
    ) -> tuple[object, ...]:
        assert workflow_run_id == "workflow-1"
        return (
            {
                "group_ref": "group-1",
                "key": "refund_support",
                "claim": "Product supports refunds.",
                "claim_kind": "capability",
                "granularity": "atomic",
                "source_claim_refs": ["claim-a"],
                "triples": [
                    {"subject": "Product", "predicate": "supports", "object": "refunds"}
                ],
            },
        )


@dataclass(slots=True)
class FakePreviewRepository:
    saved: list[DraftClaimClusterPreview] = field(default_factory=list)

    async def save_preview(
        self,
        preview: DraftClaimClusterPreview,
    ) -> DraftClaimClusterPreviewBuildResult:
        self.saved.append(preview)
        return DraftClaimClusterPreviewBuildResult(
            workflow_run_id=preview.workflow_run_id,
            claim_count=preview.claim_count,
            group_count=preview.group_count,
            created_preview=len(self.saved) == 1,
            updated_preview=len(self.saved) > 1,
        )

    async def load_preview(
        self, *, workflow_run_id: str
    ) -> DraftClaimClusterPreview | None:
        del workflow_run_id
        return self.saved[-1] if self.saved else None


@dataclass(slots=True)
class FakeCommandLog:
    completed: list[WorkflowCommandId] = field(default_factory=list)

    async def append_pending_command(self, command: WorkflowCommand) -> WorkflowCommand:
        return command

    async def mark_command_completed(
        self,
        *,
        command_id: WorkflowCommandId,
        completed_at: datetime,
    ) -> WorkflowCommand:
        del completed_at
        self.completed.append(command_id)
        return _workflow_command()

    async def list_pending_commands(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowCommand, ...]:
        del workflow_run_id, limit
        return ()


@dataclass(slots=True)
class FakeOutbox:
    events: list[WorkflowEvent] = field(default_factory=list)

    async def append_event(self, event: WorkflowEvent) -> WorkflowEvent:
        self.events.append(event)
        return event

    async def list_events_after(
        self,
        *,
        consumer_ref: WorkflowConsumerRef,
        after_sequence_number: int,
        limit: int,
    ) -> tuple[WorkflowEvent, ...]:
        del consumer_ref, after_sequence_number, limit
        return tuple(self.events)


@dataclass(slots=True)
class FakeEventCursors:
    async def get_cursor(
        self, consumer_ref: WorkflowConsumerRef
    ) -> WorkflowEventCursor | None:
        del consumer_ref
        return None

    async def save_cursor(self, cursor: WorkflowEventCursor) -> WorkflowEventCursor:
        return cursor


@dataclass(slots=True)
class FakeProgressSnapshots:
    snapshot: WorkflowProgressSnapshot | None = None

    async def get_snapshot(
        self, workflow_run_id: str
    ) -> WorkflowProgressSnapshot | None:
        del workflow_run_id
        return self.snapshot

    async def save_snapshot(
        self, snapshot: WorkflowProgressSnapshot
    ) -> WorkflowProgressSnapshot:
        self.snapshot = snapshot
        return snapshot


@dataclass(slots=True)
class FakeTimeline:
    entries: list[WorkflowTimelineEntry] = field(default_factory=list)

    async def append_entry(self, entry: WorkflowTimelineEntry) -> WorkflowTimelineEntry:
        self.entries.append(entry)
        return entry

    async def list_recent_entries(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowTimelineEntry, ...]:
        del workflow_run_id, limit
        return tuple(self.entries)


@dataclass(slots=True)
class FakeResourceUsage:
    async def get_usage(
        self, workflow_run_id: str
    ) -> WorkflowResourceUsageSnapshot | None:
        del workflow_run_id
        return None

    async def save_usage(
        self,
        usage: WorkflowResourceUsageSnapshot,
    ) -> WorkflowResourceUsageSnapshot:
        return usage


@dataclass(slots=True)
class FakeWorkflowUnitOfWork:
    command_log: FakeCommandLog = field(default_factory=FakeCommandLog)
    outbox: FakeOutbox = field(default_factory=FakeOutbox)
    event_cursors: FakeEventCursors = field(default_factory=FakeEventCursors)
    progress_snapshots: FakeProgressSnapshots = field(
        default_factory=FakeProgressSnapshots
    )
    timeline: FakeTimeline = field(default_factory=FakeTimeline)
    resource_usage: FakeResourceUsage = field(default_factory=FakeResourceUsage)

    async def commit(self) -> None:
        raise AssertionError("handler must not commit")

    async def rollback(self) -> None:
        raise AssertionError("handler must not rollback")


@pytest.mark.asyncio
async def test_build_cluster_preview_command_creates_preview_and_completes() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    preview_repository = FakePreviewRepository()

    result = await HandleBuildClusterPreviewCommandHandler().execute(
        HandleBuildClusterPreviewCommand(workflow_command=_workflow_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=FakeReductionRepository(),
        cluster_preview_repository=preview_repository,
    )

    assert result.claim_count == 1
    assert result.group_count == 1
    assert len(preview_repository.saved) == 1
    assert [event.event_type for event in workflow_uow.outbox.events] == [
        KnowledgeExtractionCanonicalEventType.CLUSTER_PREVIEW_READY.value
    ]
    assert workflow_uow.progress_snapshots.snapshot is not None
    assert (
        workflow_uow.progress_snapshots.snapshot.domain_counters[
            "draft_claim_cluster_preview_claim_count"
        ]
        == 1
    )
    assert len(workflow_uow.timeline.entries) == 1
    assert workflow_uow.command_log.completed == [_workflow_command().command_id]


@pytest.mark.asyncio
async def test_build_cluster_preview_rejects_wrong_command_type() -> None:
    with pytest.raises(ValueError, match="BuildClusterPreview"):
        await HandleBuildClusterPreviewCommandHandler().execute(
            HandleBuildClusterPreviewCommand(
                workflow_command=_workflow_command(
                    command_type=KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS
                )
            ),
            workflow_unit_of_work=FakeWorkflowUnitOfWork(),
            compaction_reduction_state_repository=FakeReductionRepository(),
            cluster_preview_repository=FakePreviewRepository(),
        )


@pytest.mark.asyncio
async def test_build_cluster_preview_rejects_non_pending_command() -> None:
    with pytest.raises(ValueError, match="PENDING"):
        await HandleBuildClusterPreviewCommandHandler().execute(
            HandleBuildClusterPreviewCommand(
                workflow_command=_workflow_command(
                    status=WorkflowCommandStatus.COMPLETED
                )
            ),
            workflow_unit_of_work=FakeWorkflowUnitOfWork(),
            compaction_reduction_state_repository=FakeReductionRepository(),
            cluster_preview_repository=FakePreviewRepository(),
        )
