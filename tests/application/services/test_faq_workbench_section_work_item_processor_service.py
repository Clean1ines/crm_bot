from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.application.services.faq_workbench_section_work_item_processor_service import (
    FaqWorkbenchSectionWorkItemProcessorService,
    ProcessLeasedClaimObservationsCommand,
    ProcessLeasedClaimObservationsResult,
    ProcessOneSectionWorkItemCommand,
)
from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    DocumentSectionStatus,
    DomainInvariantError,
)
from src.domain.project_plane.knowledge_workbench.section_batch_queue import (
    SectionBatchQueueItem,
    SectionBatchQueueItemStatus,
)


class FakeIdFactory:
    def __init__(self) -> None:
        self._counter = 0

    def new_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter}"


class FixedTimeProvider:
    def now(self) -> datetime:
        return datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)


@dataclass
class FakeRepository:
    sections: dict[str, DocumentSection]
    updated_items: list[SectionBatchQueueItem] = field(default_factory=list)
    call_log: list[str] = field(default_factory=list)

    async def get_document_section(
        self,
        *,
        project_id: str,
        document_id: str,
        section_id: str,
    ) -> DocumentSection | None:
        self.call_log.append("repo.get_document_section")
        return self.sections.get(section_id)

    async def update_section_batch_queue_item(
        self,
        item: SectionBatchQueueItem,
    ) -> None:
        self.call_log.append(f"repo.update_section_batch_queue_item:{item.status.value}")
        self.updated_items.append(item)


@dataclass
class FakeClaimObservationsRunner:
    call_log: list[str] = field(default_factory=list)
    commands: list[ProcessLeasedClaimObservationsCommand] = field(default_factory=list)

    async def process_leased_claim_observations(
        self,
        command: ProcessLeasedClaimObservationsCommand,
    ) -> ProcessLeasedClaimObservationsResult:
        self.call_log.append("claim_observations_runner.process_leased_claim_observations")
        self.commands.append(command)
        return ProcessLeasedClaimObservationsResult(
            claim_observations_node_run_id="claim-observations-node-run-1",
            claim_input_refs=("c1", "c2"),
        )


def _utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, 3, hour, minute, 0, tzinfo=timezone.utc)


def _section() -> DocumentSection:
    return DocumentSection(
        section_id="section-1",
        document_id="document-1",
        project_id="project-1",
        section_index=1,
        section_key="section-key-1",
        heading_path=("Section 1",),
        title="Section 1",
        raw_text="Section content",
        normalized_text="Section content",
        source_refs=("source-ref-1",),
        source_chunk_indexes=(0,),
        status=DocumentSectionStatus.PENDING,
        parent_section_id=None,
        metadata={},
    )


def _leased_item() -> SectionBatchQueueItem:
    return SectionBatchQueueItem(
        queue_item_id="section-queue-item-1",
        batch_plan_id="batch-plan-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        section_id="section-1",
        section_key="section-key-1",
        section_index=1,
        lane_id="lane-1",
        lane_index=0,
        observed_registry_snapshot_id="snapshot-1",
        observed_registry_snapshot_sequence=1,
        status=SectionBatchQueueItemStatus.LEASED,
        claimed_by_worker_id="worker-1",
        lease_expires_at=_utc(12, 5),
        claim_observations_node_run_id=None,
        registry_application_queue_item_id=None,
        error_kind=None,
        attempt_count=1,
        created_at=_utc(11, 58),
        updated_at=_utc(11, 59),
    )


def _persisted_item() -> SectionBatchQueueItem:
    return SectionBatchQueueItem(
        queue_item_id="section-queue-item-1",
        batch_plan_id="batch-plan-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        section_id="section-1",
        section_key="section-key-1",
        section_index=1,
        lane_id="lane-1",
        lane_index=0,
        observed_registry_snapshot_id="snapshot-1",
        observed_registry_snapshot_sequence=1,
        status=SectionBatchQueueItemStatus.CLAIM_OBSERVATIONS_PERSISTED,
        claimed_by_worker_id=None,
        lease_expires_at=None,
        claim_observations_node_run_id="claim-observations-node-run-1",
        registry_application_queue_item_id=None,
        error_kind=None,
        attempt_count=1,
        created_at=_utc(11, 58),
        updated_at=_utc(12, 0),
    )


@pytest.mark.asyncio
async def test_section_worker_persists_claim_observations_and_stops_before_prompt_c() -> None:
    runner = FakeClaimObservationsRunner()
    repository = FakeRepository(sections={"section-1": _section()})
    service = FaqWorkbenchSectionWorkItemProcessorService(
        repository=repository,
        claim_observations_runner=runner,
        id_factory=FakeIdFactory(),
        time_provider=FixedTimeProvider(),
    )

    result = await service.process_one_section_work_item(
        ProcessOneSectionWorkItemCommand(
            queue_item=_leased_item(),
            worker_id="worker-1",
        )
    )

    assert result.section.section_id == "section-1"
    assert result.claim_observations_result.claim_observations_node_run_id == (
        "claim-observations-node-run-1"
    )
    assert result.claim_observations_persisted_item.status is (
        SectionBatchQueueItemStatus.CLAIM_OBSERVATIONS_PERSISTED
    )
    assert result.claim_observations_persisted_item.claim_observations_node_run_id == (
        "claim-observations-node-run-1"
    )
    assert result.claim_observations_persisted_item.registry_application_queue_item_id is None

    assert repository.call_log == [
        "repo.get_document_section",
        "repo.update_section_batch_queue_item:claim_observations_persisted",
    ]
    assert runner.call_log == [
        "claim_observations_runner.process_leased_claim_observations",
    ]
    assert runner.commands[0].section.section_id == "section-1"


@pytest.mark.asyncio
async def test_claim_observations_persisted_recovery_is_idempotent_extraction_state() -> None:
    repository = FakeRepository(sections={"section-1": _section()})
    service = FaqWorkbenchSectionWorkItemProcessorService(
        repository=repository,
        claim_observations_runner=FakeClaimObservationsRunner(),
        id_factory=FakeIdFactory(),
        time_provider=FixedTimeProvider(),
    )

    persisted_item = _persisted_item()
    result = await service.process_claim_observations_persisted_section_work_item(
        queue_item=persisted_item,
    )

    assert result.section.section_id == "section-1"
    assert result.claim_observations_persisted_item is persisted_item
    assert repository.updated_items == []
    assert repository.call_log == ["repo.get_document_section"]


@pytest.mark.asyncio
async def test_section_worker_rejects_non_leased_items_for_fresh_processing() -> None:
    service = FaqWorkbenchSectionWorkItemProcessorService(
        repository=FakeRepository(sections={"section-1": _section()}),
        claim_observations_runner=FakeClaimObservationsRunner(),
        id_factory=FakeIdFactory(),
        time_provider=FixedTimeProvider(),
    )

    with pytest.raises(DomainInvariantError, match="LEASED"):
        await service.process_one_section_work_item(
            ProcessOneSectionWorkItemCommand(
                queue_item=_persisted_item(),
                worker_id="worker-1",
            )
        )


@pytest.mark.asyncio
async def test_section_worker_requires_section_for_processing() -> None:
    service = FaqWorkbenchSectionWorkItemProcessorService(
        repository=FakeRepository(sections={}),
        claim_observations_runner=FakeClaimObservationsRunner(),
        id_factory=FakeIdFactory(),
        time_provider=FixedTimeProvider(),
    )

    with pytest.raises(DomainInvariantError, match="document section"):
        await service.process_one_section_work_item(
            ProcessOneSectionWorkItemCommand(
                queue_item=_leased_item(),
                worker_id="worker-1",
            )
        )
