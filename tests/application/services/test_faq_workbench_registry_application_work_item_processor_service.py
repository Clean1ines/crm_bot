from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

import pytest

from src.application.services.faq_workbench_registry_application_work_item_processor_service import (
    FaqWorkbenchRegistryApplicationWorkItemProcessorService,
    ProcessRegistryApplicationWorkItemCommand,
    RegistryApplicationWorkItemOutcome,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
    FactRegistry,
    FactRegistryStatus,
    RegistrySnapshot,
)
from src.domain.project_plane.knowledge_workbench.registry_application_queue import (
    RegistryApplicationQueueItem,
    RegistryApplicationQueueItemStatus,
)
from src.domain.project_plane.knowledge_workbench.section_batch_queue import (
    SectionBatchQueueItem,
    SectionBatchQueueItemStatus,
)


@dataclass(frozen=True, slots=True)
class FixedTimeProvider:
    value: datetime

    def now(self) -> datetime:
        return self.value


@dataclass(slots=True)
class MonotonicIdFactory:
    value: int = 0

    def new_id(self, prefix: str) -> str:
        self.value += 1
        return f"{prefix}-{self.value}"


@dataclass(slots=True)
class InMemoryRegistryApplicationWorkerRepository:
    queue_item: RegistryApplicationQueueItem | None
    latest_snapshot: RegistrySnapshot | None
    registry: FactRegistry | None
    fact_registry_artifact: ProcessingNodeArtifact | None
    linked_section_item: SectionBatchQueueItem | None = None
    restored_stale_count: int = 0
    updated_queue_items: list[RegistryApplicationQueueItem] = field(
        default_factory=list
    )
    updated_section_items: list[SectionBatchQueueItem] = field(default_factory=list)
    snapshots: list[RegistrySnapshot] = field(default_factory=list)

    async def restore_stale_registry_application_work_item_leases(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        now: datetime,
    ) -> int:
        return self.restored_stale_count

    async def lease_next_ready_registry_application_work_item(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        worker_id: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> RegistryApplicationQueueItem | None:
        if self.queue_item is None:
            return None
        leased = replace(
            self.queue_item,
            status=RegistryApplicationQueueItemStatus.LEASED,
            claimed_by_worker_id=worker_id,
            lease_expires_at=lease_expires_at,
            updated_at=now,
        )
        self.queue_item = leased
        return leased

    async def update_registry_application_queue_item(
        self,
        item: RegistryApplicationQueueItem,
    ) -> None:
        self.updated_queue_items.append(item)
        self.queue_item = item

    async def get_section_batch_queue_item_by_registry_application_queue_item_id(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        registry_application_queue_item_id: str,
    ) -> SectionBatchQueueItem | None:
        return self.linked_section_item

    async def update_section_batch_queue_item(
        self,
        item: SectionBatchQueueItem,
    ) -> None:
        self.updated_section_items.append(item)
        self.linked_section_item = item

    async def get_fact_registry_for_run(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> FactRegistry | None:
        return self.registry

    async def get_latest_registry_snapshot(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> RegistrySnapshot | None:
        return self.latest_snapshot

    async def get_processing_node_artifact_by_node_run_id_and_type(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        node_run_id: str,
        artifact_type: ProcessingNodeArtifactType,
    ) -> ProcessingNodeArtifact | None:
        artifact = self.fact_registry_artifact
        if artifact is None:
            return None
        if artifact.node_run_id != node_run_id:
            return None
        if artifact.artifact_type is not artifact_type:
            return None
        return artifact

    async def create_registry_snapshot(self, snapshot: RegistrySnapshot) -> None:
        self.snapshots.append(snapshot)


def _registry() -> FactRegistry:
    return FactRegistry(
        registry_id="registry-1",
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
        status=FactRegistryStatus.BUILDING,
        version=1,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def _snapshot(
    *,
    snapshot_id: str = "registry-snapshot-1",
    sequence_number: int = 1,
) -> RegistrySnapshot:
    return RegistrySnapshot(
        snapshot_id=snapshot_id,
        registry_id="registry-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        after_node_run_id="bootstrap-node-run",
        sequence_number=sequence_number,
        entries_payload={
            "contract": "fact_registry",
            "fact_registry": {
                "version": 1,
                "canonical_facts": [],
                "fact_relations": [],
            },
        },
        relations_payload={"contract": "fact_registry_relations", "fact_relations": []},
        entry_count=0,
        relation_count=0,
        claim_observation_count=0,
        update_count=0,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def _queue_item(
    *,
    observed_snapshot_id: str = "registry-snapshot-1",
    observed_sequence: int = 1,
    status: RegistryApplicationQueueItemStatus = RegistryApplicationQueueItemStatus.READY,
) -> RegistryApplicationQueueItem:
    return RegistryApplicationQueueItem(
        queue_item_id="registry-queue-item-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        section_id="section-1",
        source_node_run_id="node-run-fact-registry-builder",
        observed_registry_snapshot_id=observed_snapshot_id,
        observed_registry_snapshot_sequence=observed_sequence,
        claim_input_refs=("claim-artifact-1",),
        status=status,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def _fact_registry() -> dict:
    return {
        "version": 1,
        "canonical_facts": [
            {
                "fact_id": "cf_product_definition",
                "claim": "Продукт является платформой управления AI-базами знаний.",
                "claim_kind": "definition",
                "granularity": "atomic",
                "triples": [
                    {
                        "subject": "Продукт",
                        "predicate": "is_a",
                        "object": "платформа управления AI-базами знаний",
                        "qualifiers": [],
                    },
                ],
                "mentions": [
                    {
                        "source_section_ref": "document-1#section-1",
                        "source_local_ref": "c1",
                        "evidence_block": "Продукт — это платформа управления AI-базами знаний.",
                        "mention_relation": "initial",
                    },
                ],
                "question_variants": ["Что такое продукт?"],
                "scope": "Общее определение",
                "exclusion_scope": "",
                "derived_fact_notes": [],
                "status": "active",
            },
        ],
        "fact_relations": [],
    }


def _summary() -> dict:
    return {
        "created_fact_count": 1,
        "updated_fact_count": 0,
        "created_relation_count": 0,
        "notes": [],
    }


def _artifact(payload: dict | None = None) -> ProcessingNodeArtifact:
    return ProcessingNodeArtifact(
        artifact_id="artifact-fact-registry",
        node_run_id="node-run-fact-registry-builder",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        section_id="section-1",
        artifact_type=ProcessingNodeArtifactType.PARSED_LLM_OUTPUT,
        payload_json=payload
        or {
            "fact_registry": _fact_registry(),
            "registry_update_summary": _summary(),
        },
        schema_version=1,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        metadata={"contract": "fact_registry_canonicalization"},
    )


def _linked_section_item() -> SectionBatchQueueItem:
    return SectionBatchQueueItem(
        queue_item_id="section-batch-item-1",
        batch_plan_id="batch-plan-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        section_id="section-1",
        section_key="intro",
        section_index=0,
        lane_id="section-lane-1",
        lane_index=0,
        observed_registry_snapshot_id="registry-snapshot-1",
        observed_registry_snapshot_sequence=1,
        status=SectionBatchQueueItemStatus.REGISTRY_APPLICATION_QUEUED,
        claim_observations_node_run_id="node-run-fact-registry-builder",
        registry_application_queue_item_id="registry-queue-item-1",
    )


def _service(repository: InMemoryRegistryApplicationWorkerRepository):
    return FaqWorkbenchRegistryApplicationWorkItemProcessorService(
        repository=repository,
        id_factory=MonotonicIdFactory(),
        time_provider=FixedTimeProvider(datetime(2026, 6, 1, tzinfo=timezone.utc)),
    )


def _command() -> ProcessRegistryApplicationWorkItemCommand:
    return ProcessRegistryApplicationWorkItemCommand(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
        worker_id="worker-1",
        lease_seconds=300,
    )


@pytest.mark.asyncio
async def test_single_writer_applies_fact_registry_artifact_and_marks_queue_item_applied() -> (
    None
):
    repository = InMemoryRegistryApplicationWorkerRepository(
        queue_item=_queue_item(),
        latest_snapshot=_snapshot(),
        registry=_registry(),
        fact_registry_artifact=_artifact(),
        linked_section_item=_linked_section_item(),
    )

    result = await _service(repository).process_next_registry_application_work_item(
        _command()
    )

    assert result.applied is True
    assert result.outcome is RegistryApplicationWorkItemOutcome.APPLIED
    assert result.applied_snapshot is not None
    assert result.applied_snapshot.sequence_number == 2
    assert result.applied_snapshot.entries_payload["fact_registry"] == _fact_registry()
    assert (
        result.applied_snapshot.entries_payload["registry_update_summary"] == _summary()
    )

    assert len(repository.snapshots) == 1
    assert repository.snapshots[0] is result.applied_snapshot

    assert (
        repository.updated_queue_items[-1].status
        is RegistryApplicationQueueItemStatus.APPLIED
    )
    assert (
        repository.updated_queue_items[-1].applied_registry_snapshot_id
        == result.applied_snapshot.snapshot_id
    )

    assert repository.updated_section_items
    assert (
        repository.updated_section_items[-1].status
        is SectionBatchQueueItemStatus.REGISTRY_APPLICATION_APPLIED
    )


@pytest.mark.asyncio
async def test_single_writer_marks_stale_queue_item_for_rebase_without_mutating_registry() -> (
    None
):
    repository = InMemoryRegistryApplicationWorkerRepository(
        queue_item=_queue_item(
            observed_snapshot_id="registry-snapshot-1",
            observed_sequence=1,
        ),
        latest_snapshot=_snapshot(snapshot_id="registry-snapshot-2", sequence_number=2),
        registry=_registry(),
        fact_registry_artifact=_artifact(),
    )

    result = await _service(repository).process_next_registry_application_work_item(
        _command()
    )

    assert result.outcome is RegistryApplicationWorkItemOutcome.REBASE_REQUIRED
    assert result.applied_snapshot is None
    assert repository.snapshots == []
    assert (
        repository.updated_queue_items[-1].status
        is RegistryApplicationQueueItemStatus.WAITING_FOR_FRESH_REGISTRY
    )


@pytest.mark.asyncio
async def test_single_writer_returns_no_work_when_queue_is_empty() -> None:
    repository = InMemoryRegistryApplicationWorkerRepository(
        queue_item=None,
        latest_snapshot=_snapshot(),
        registry=_registry(),
        fact_registry_artifact=_artifact(),
    )

    result = await _service(repository).process_next_registry_application_work_item(
        _command()
    )

    assert result.outcome is RegistryApplicationWorkItemOutcome.NO_WORK
    assert result.queue_item is None
    assert repository.snapshots == []


@pytest.mark.asyncio
async def test_single_writer_requires_fact_registry_artifact() -> None:
    repository = InMemoryRegistryApplicationWorkerRepository(
        queue_item=_queue_item(),
        latest_snapshot=_snapshot(),
        registry=_registry(),
        fact_registry_artifact=None,
    )

    with pytest.raises(DomainInvariantError, match="fact_registry parsed artifact"):
        await _service(repository).process_next_registry_application_work_item(
            _command()
        )


@pytest.mark.asyncio
async def test_single_writer_requires_fact_registry_payload_shape() -> None:
    repository = InMemoryRegistryApplicationWorkerRepository(
        queue_item=_queue_item(),
        latest_snapshot=_snapshot(),
        registry=_registry(),
        fact_registry_artifact=_artifact(payload={"registry_updates": []}),
    )

    with pytest.raises(DomainInvariantError, match="requires fact_registry"):
        await _service(repository).process_next_registry_application_work_item(
            _command()
        )


def test_registry_application_work_item_command_requires_worker_id() -> None:
    with pytest.raises(DomainInvariantError, match="worker_id"):
        ProcessRegistryApplicationWorkItemCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="",
        )


def test_registry_application_work_item_command_requires_positive_lease() -> None:
    with pytest.raises(DomainInvariantError, match="lease_seconds"):
        ProcessRegistryApplicationWorkItemCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="worker-1",
            lease_seconds=0,
        )


def test_registry_application_worker_no_longer_needs_old_entry_or_finding_loaders() -> (
    None
):
    repository = InMemoryRegistryApplicationWorkerRepository(
        queue_item=_queue_item(),
        latest_snapshot=_snapshot(),
        registry=_registry(),
        fact_registry_artifact=_artifact(),
    )

    assert not hasattr(repository, "list_fact_registry_entries")
    assert not hasattr(repository, "list_claim_observations_by_ids")
