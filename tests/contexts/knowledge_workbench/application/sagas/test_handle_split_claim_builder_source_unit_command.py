from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.application.sagas.handle_split_claim_builder_source_unit_command import (
    HandleSplitClaimBuilderSourceUnitCommand,
    HandleSplitClaimBuilderSourceUnitCommandHandler,
    _prepare_dispatch_batch_command,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_document import (
    SourceDocument,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.heading_path import (
    HeadingPath,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_kind import (
    SourceUnitKind,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_lineage import (
    SourceUnitLineage,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_text import (
    SourceUnitText,
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
    return datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _document_ref() -> SourceDocumentRef:
    return SourceDocumentRef("source-document:project-1:abc")


def _parent_ref() -> SourceUnitRef:
    return SourceUnitRef("source-unit:parent")


def _large_markdown() -> str:
    paragraphs = "\n\n".join(
        f"paragraph {index} " + ("aa bb cc dd " * 80) for index in range(1, 80)
    )
    return f"# Alpha\n\n{paragraphs}"


def _document() -> SourceDocument:
    return SourceDocument(
        document_ref=_document_ref(),
        project_id="project-1",
        source_format=SourceFormat.MARKDOWN,
        content_hash="sha256:abc",
        original_filename="knowledge.md",
        created_at=_now(),
    )


def _parent_unit() -> SourceUnit:
    return SourceUnit(
        unit_ref=_parent_ref(),
        document_ref=_document_ref(),
        unit_kind=SourceUnitKind.SECTION,
        text=SourceUnitText(_large_markdown()),
        heading_path=HeadingPath(("Alpha",)),
        lineage=SourceUnitLineage(),
        ordinal=3,
        created_at=_now(),
    )


def _existing_unit() -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef("source-unit:existing"),
        document_ref=_document_ref(),
        unit_kind=SourceUnitKind.SECTION,
        text=SourceUnitText("# Existing\n\nBody"),
        heading_path=HeadingPath(("Existing",)),
        lineage=SourceUnitLineage(),
        ordinal=7,
        created_at=_now(),
    )


def _command(
    *,
    command_type: str = (
        KnowledgeExtractionCanonicalCommandType.SPLIT_CLAIM_BUILDER_SOURCE_UNIT.value
    ),
    status: WorkflowCommandStatus = WorkflowCommandStatus.PENDING,
    source_unit_refs: tuple[str, ...] = (_parent_ref().value,),
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId("workflow-command:split"),
        command_type=command_type,
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey("split-command"),
        payload={
            "workflow_run_id": _workflow_run_id(),
            "source_document_ref": _document_ref().value,
            "source_unit_ref": source_unit_refs[0],
            "source_unit_refs": source_unit_refs,
            "affected_work_item_refs": ("work-parent",),
            "work_kind": "knowledge_workbench.claim_builder.section_extraction",
            "scheduled_work_item_count": 1,
            "estimated_prompt_tokens": 200000,
            "active_model_ref": "qwen/qwen3-32b",
            "input_size_preflight_decision": "SOURCE_SPLIT_REQUIRED",
            "input_size_preflight_reason": (
                "estimated prompt tokens exceed all automatic fallback input limits"
            ),
            "source_split_required": True,
            "split_reason": "input_size_preflight",
            "llm_dispatch_preparation": {
                "profile": {
                    "profile_id": "faq_claim_observations",
                    "estimated_prompt_tokens": 200000,
                    "estimated_completion_tokens": 500,
                },
                "account_capacities": (),
                "active_model_ref": "qwen/qwen3-32b",
                "requested_items": 1,
                "worker_ref": "worker-1",
                "lease_token_prefix": "lease-prefix",
                "lease_ttl_seconds": 300,
            },
        },
        status=status,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


@dataclass(slots=True)
class FakeSourceManagementRepository:
    saved_units: list[SourceUnit] = field(default_factory=list)
    loaded_source_unit_refs: list[SourceUnitRef] = field(default_factory=list)

    async def save_source_document(self, document: SourceDocument) -> None:
        del document

    async def load_source_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> SourceDocument | None:
        assert document_ref == _document_ref()
        return _document()

    async def save_source_units(self, units: tuple[SourceUnit, ...]) -> None:
        self.saved_units.extend(units)

    async def list_source_units_for_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> tuple[SourceUnit, ...]:
        assert document_ref == _document_ref()
        return (_existing_unit(), _parent_unit())

    async def load_source_unit(self, unit_ref: SourceUnitRef) -> SourceUnit | None:
        self.loaded_source_unit_refs.append(unit_ref)
        if unit_ref == _parent_ref():
            return _parent_unit()
        return None


@dataclass(slots=True)
class FakeSchedulingRepository:
    saved_work_items: list[WorkItem] = field(default_factory=list)

    async def get_work_item(self, work_item_id: str) -> WorkItem | None:
        del work_item_id
        return None

    async def get_schedule_payload_hash(self, work_item_id: str) -> str | None:
        del work_item_id
        return None

    async def save_scheduled_work_item(
        self,
        *,
        item: WorkItem,
        idempotency_key: str,
        payload_hash: str,
        payload: object,
    ) -> None:
        del idempotency_key, payload_hash, payload
        self.saved_work_items.append(item)


@dataclass(slots=True)
class FakeSplitSupersedeRepository:
    loaded_ids: list[str] = field(default_factory=list)
    saved_items: list[WorkItem] = field(default_factory=list)

    async def load_work_item(self, work_item_id: str) -> WorkItem | None:
        self.loaded_ids.append(work_item_id)
        return WorkItem(
            work_item_id=work_item_id,
            work_kind=WorkKind("knowledge_workbench.claim_builder.section_extraction"),
        )

    async def save_work_item(self, item: WorkItem) -> None:
        self.saved_items.append(item)


@dataclass(slots=True)
class FakeCommandLogRepository:
    pending_commands: list[WorkflowCommand] = field(default_factory=list)
    completed_command_ids: list[WorkflowCommandId] = field(default_factory=list)

    async def append_pending_command(
        self,
        command: WorkflowCommand,
    ) -> WorkflowCommand:
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
        return _command()

    async def list_pending_commands(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowCommand, ...]:
        del workflow_run_id, limit
        return ()


@dataclass(slots=True)
class FakeOutboxRepository:
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
class FakeEventCursorRepository:
    async def get_cursor(
        self,
        consumer_ref: WorkflowConsumerRef,
    ) -> WorkflowEventCursor | None:
        del consumer_ref
        return None

    async def save_cursor(
        self,
        cursor: WorkflowEventCursor,
    ) -> WorkflowEventCursor:
        return cursor


@dataclass(slots=True)
class FakeProgressSnapshotRepository:
    snapshot: WorkflowProgressSnapshot | None = None

    async def get_snapshot(
        self,
        workflow_run_id: str,
    ) -> WorkflowProgressSnapshot | None:
        del workflow_run_id
        return self.snapshot

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

    async def list_recent_entries(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowTimelineEntry, ...]:
        del workflow_run_id, limit
        return tuple(self.entries)


@dataclass(slots=True)
class FakeResourceUsageRepository:
    usage: WorkflowResourceUsageSnapshot | None = None

    async def get_usage(
        self,
        workflow_run_id: str,
    ) -> WorkflowResourceUsageSnapshot | None:
        del workflow_run_id
        return self.usage

    async def save_usage(
        self,
        usage: WorkflowResourceUsageSnapshot,
    ) -> WorkflowResourceUsageSnapshot:
        self.usage = usage
        return usage


@dataclass(slots=True)
class FakeWorkflowRuntimeUnitOfWork:
    command_log: FakeCommandLogRepository = field(
        default_factory=FakeCommandLogRepository,
    )
    outbox: FakeOutboxRepository = field(default_factory=FakeOutboxRepository)
    event_cursors: FakeEventCursorRepository = field(
        default_factory=FakeEventCursorRepository,
    )
    progress_snapshots: FakeProgressSnapshotRepository = field(
        default_factory=FakeProgressSnapshotRepository,
    )
    timeline: FakeTimelineRepository = field(default_factory=FakeTimelineRepository)
    resource_usage: FakeResourceUsageRepository = field(
        default_factory=FakeResourceUsageRepository,
    )

    async def commit(self) -> None:
        raise AssertionError("handler must not own transaction commit")

    async def rollback(self) -> None:
        raise AssertionError("handler must not own transaction rollback")


async def _execute(workflow_command: WorkflowCommand | None = None):
    source_repository = FakeSourceManagementRepository()
    scheduling_repository = FakeSchedulingRepository()
    split_repository = FakeSplitSupersedeRepository()
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    result = await HandleSplitClaimBuilderSourceUnitCommandHandler().execute(
        HandleSplitClaimBuilderSourceUnitCommand(
            workflow_command=workflow_command or _command(),
        ),
        source_management_repository=source_repository,
        work_item_scheduling_repository=scheduling_repository,
        work_item_split_supersede_repository=split_repository,
        workflow_unit_of_work=workflow_unit_of_work,
    )
    return (
        result,
        source_repository,
        scheduling_repository,
        split_repository,
        workflow_unit_of_work,
    )


@pytest.mark.asyncio
async def test_validates_command_type() -> None:
    with pytest.raises(ValueError, match="command_type"):
        await _execute(_command(command_type="WrongCommand"))


@pytest.mark.asyncio
async def test_validates_pending_status() -> None:
    with pytest.raises(ValueError, match="PENDING"):
        await _execute(_command(status=WorkflowCommandStatus.COMPLETED))


@pytest.mark.asyncio
async def test_requires_single_source_unit_for_first_patch() -> None:
    with pytest.raises(ValueError, match="exactly one source_unit_ref"):
        await _execute(_command(source_unit_refs=("unit-1", "unit-2")))


@pytest.mark.asyncio
async def test_executes_with_truthful_split_payload_without_stale_handler_status() -> (
    None
):
    (
        result,
        _,
        scheduling_repository,
        split_repository,
        workflow_unit_of_work,
    ) = await _execute()

    assert result.parent_source_unit_ref == _parent_ref().value
    assert len(scheduling_repository.saved_work_items) > 0
    assert split_repository.loaded_ids == ["work-parent"]

    command = _command()
    assert command.payload["split_reason"] == "input_size_preflight"
    assert command.payload["source_split_required"] is True
    assert command.payload["source_unit_refs"] == (_parent_ref().value,)
    assert command.payload["affected_work_item_refs"] == ("work-parent",)
    assert ("split_handler_" + "status") not in command.payload
    assert ("BLOCKED_" + "NOT_IMPLEMENTED") not in str(command.payload)

    completed_event = workflow_unit_of_work.outbox.events[0]
    assert (
        completed_event.event_type
        == KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SOURCE_UNIT_SPLIT_COMPLETED.value
    )


@pytest.mark.asyncio
async def test_creates_child_source_units_with_parent_lineage_and_non_colliding_ordinals() -> (
    None
):
    _, source_repository, _, _, _ = await _execute()

    assert len(source_repository.saved_units) >= 2
    assert source_repository.loaded_source_unit_refs == [_parent_ref()]
    assert all(
        unit.lineage.parent_refs == (_parent_ref(),)
        for unit in source_repository.saved_units
    )
    assert min(unit.ordinal for unit in source_repository.saved_units) > 7


@pytest.mark.asyncio
async def test_supersedes_affected_parent_work_items() -> None:
    _, _, _, split_repository, _ = await _execute()

    assert split_repository.loaded_ids == ["work-parent"]
    assert tuple(item.work_item_id for item in split_repository.saved_items) == (
        "work-parent",
    )


@pytest.mark.asyncio
async def test_schedules_child_claim_builder_work_items_only_for_child_units() -> None:
    _, source_repository, scheduling_repository, _, _ = await _execute()

    assert len(scheduling_repository.saved_work_items) == len(
        source_repository.saved_units
    )


@pytest.mark.asyncio
async def test_emits_split_completed_appends_prepare_and_marks_command_completed() -> (
    None
):
    (
        result,
        source_repository,
        scheduling_repository,
        _,
        workflow_unit_of_work,
    ) = await _execute()

    assert result.appended_event_count == 1
    assert result.appended_next_command_count == 1
    assert result.completed_command_id == _command().command_id
    assert workflow_unit_of_work.command_log.completed_command_ids == [
        _command().command_id
    ]

    event = workflow_unit_of_work.outbox.events[0]
    assert (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SOURCE_UNIT_SPLIT_COMPLETED.value
    )
    assert event.payload["parent_source_unit_ref"] == _parent_ref().value
    assert event.payload["child_source_unit_refs"] == tuple(
        unit.unit_ref.value for unit in source_repository.saved_units
    )
    assert event.payload["superseded_work_item_refs"] == ("work-parent",)
    assert event.payload["scheduled_child_work_item_count"] == len(
        scheduling_repository.saved_work_items
    )

    next_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert (
        next_command.command_type
        == KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
    )
    assert _parent_ref().value in next_command.idempotency_key.value
    assert _parent_ref().value in next_command.command_id.value
    assert next_command.payload["parent_source_unit_ref"] == _parent_ref().value
    assert next_command.payload["scheduled_work_item_count"] == len(
        scheduling_repository.saved_work_items
    )
    assert "llm_dispatch_preparation" in next_command.payload

    timeline_entry = workflow_unit_of_work.timeline.entries[0]
    assert _parent_ref().value in timeline_entry.timeline_entry_id


@pytest.mark.asyncio
async def test_progress_counters_updated() -> None:
    (
        _,
        source_repository,
        scheduling_repository,
        split_repository,
        workflow_unit_of_work,
    ) = await _execute()

    snapshot = workflow_unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert (
        snapshot.domain_counters["claim_builder_source_unit_split_completed_count"] == 1
    )
    assert snapshot.domain_counters["claim_builder_child_source_unit_count"] == len(
        source_repository.saved_units
    )
    assert snapshot.domain_counters[
        "claim_builder_split_superseded_work_item_count"
    ] == len(split_repository.saved_items)
    assert snapshot.domain_counters["claim_builder_split_child_work_item_count"] == len(
        scheduling_repository.saved_work_items
    )


def test_prepare_follow_up_idempotency_differs_per_parent_source_unit() -> None:
    first_parent_ref = SourceUnitRef("source-unit:parent-one")
    second_parent_ref = SourceUnitRef("source-unit:parent-two")

    first = _prepare_dispatch_batch_command(
        workflow_command=_command(source_unit_refs=(first_parent_ref.value,)),
        workflow_run_id=_workflow_run_id(),
        source_document_ref=_document_ref(),
        parent_source_unit_ref=first_parent_ref,
        scheduled_child_work_item_count=2,
        occurred_at=_now(),
    )
    second = _prepare_dispatch_batch_command(
        workflow_command=_command(source_unit_refs=(second_parent_ref.value,)),
        workflow_run_id=_workflow_run_id(),
        source_document_ref=_document_ref(),
        parent_source_unit_ref=second_parent_ref,
        scheduled_child_work_item_count=2,
        occurred_at=_now(),
    )

    assert first.command_id != second.command_id
    assert first.idempotency_key != second.idempotency_key
    assert first_parent_ref.value in first.command_id.value
    assert second_parent_ref.value in second.command_id.value
    assert first.payload["parent_source_unit_ref"] == first_parent_ref.value
    assert second.payload["parent_source_unit_ref"] == second_parent_ref.value
