from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.application.services.faq_workbench_local_claim_retrieval_surface_indexing_service import (
    CheckLocalClaimRetrievalSurfaceIndexedCommand,
    IndexDocumentLocalClaimRetrievalSurfaceCommand,
)
from src.application.services.faq_workbench_section_work_item_processor_service import (
    FaqWorkbenchSectionWorkItemProcessorService,
    ProcessClaimObservationsPersistedSectionWorkItemResult,
)
from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    DocumentSectionStatus,
    SectionBatchQueueItem,
    SectionBatchQueueItemStatus,
)


@dataclass(frozen=True, slots=True)
class IndexedResult:
    indexed: bool


@dataclass(slots=True)
class FakeRepository:
    section: DocumentSection

    async def get_document_section(
        self,
        *,
        project_id: str,
        document_id: str,
        section_id: str,
    ) -> DocumentSection | None:
        assert project_id == self.section.project_id
        assert document_id == self.section.document_id
        assert section_id == self.section.section_id
        return self.section

    async def update_section_batch_queue_item(
        self,
        item: SectionBatchQueueItem,
    ) -> None:
        raise AssertionError(f"unexpected queue update: {item}")


@dataclass(slots=True)
class FakeClaimRunner:
    async def process_leased_claim_observations(self, command: object) -> object:
        raise AssertionError(f"unexpected Prompt A runner: {command}")


@dataclass(slots=True)
class FakeIndexingService:
    indexed: bool
    checks: list[CheckLocalClaimRetrievalSurfaceIndexedCommand] = field(
        default_factory=list
    )
    index_commands: list[IndexDocumentLocalClaimRetrievalSurfaceCommand] = field(
        default_factory=list
    )

    async def has_indexed_node_run(
        self,
        command: CheckLocalClaimRetrievalSurfaceIndexedCommand,
    ) -> IndexedResult:
        self.checks.append(command)
        return IndexedResult(indexed=self.indexed)

    async def index_document_local_claim_retrieval_surface(
        self,
        command: IndexDocumentLocalClaimRetrievalSurfaceCommand,
    ) -> object:
        self.index_commands.append(command)
        return object()


@dataclass(slots=True)
class FakeIdFactory:
    def new_id(self, prefix: str) -> str:
        return f"{prefix}-1"


def _section() -> DocumentSection:
    return DocumentSection(
        section_id="section-1",
        document_id="document-1",
        project_id="project-1",
        section_index=0,
        section_key="section-1",
        heading_path=(),
        title="Section 1",
        raw_text="Бот отвечает клиентам.",
        normalized_text="Бот отвечает клиентам.",
        source_refs=(),
        source_chunk_indexes=(),
        status=DocumentSectionStatus.PROCESSED,
        metadata={},
    )


def _persisted_item() -> SectionBatchQueueItem:
    return SectionBatchQueueItem(
        queue_item_id="queue-1",
        batch_plan_id="plan-1",
        processing_run_id="run-1",
        project_id="project-1",
        document_id="document-1",
        section_id="section-1",
        section_key="section-1",
        section_index=0,
        lane_id="lane-1",
        lane_index=0,
        observed_registry_snapshot_id="snapshot-1",
        observed_registry_snapshot_sequence=1,
        status=SectionBatchQueueItemStatus.CLAIM_OBSERVATIONS_PERSISTED,
        claimed_by_worker_id=None,
        lease_expires_at=None,
        claim_observations_node_run_id="node-run-1",
        registry_application_queue_item_id=None,
        error_kind=None,
        attempt_count=1,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_persisted_section_work_item_does_not_touch_local_claim_index_when_node_run_is_indexed() -> (
    None
):
    indexing_service = FakeIndexingService(indexed=True)
    service = FaqWorkbenchSectionWorkItemProcessorService(
        repository=FakeRepository(section=_section()),
        claim_observations_runner=FakeClaimRunner(),
        id_factory=FakeIdFactory(),
        local_claim_retrieval_surface_indexing_service=indexing_service,
    )

    result = await service.process_claim_observations_persisted_section_work_item(
        queue_item=_persisted_item()
    )

    assert isinstance(result, ProcessClaimObservationsPersistedSectionWorkItemResult)
    assert indexing_service.checks == []
    assert indexing_service.index_commands == []


@pytest.mark.asyncio
async def test_persisted_section_work_item_does_not_index_local_claims_when_node_run_is_missing() -> (
    None
):
    indexing_service = FakeIndexingService(indexed=False)
    service = FaqWorkbenchSectionWorkItemProcessorService(
        repository=FakeRepository(section=_section()),
        claim_observations_runner=FakeClaimRunner(),
        id_factory=FakeIdFactory(),
        local_claim_retrieval_surface_indexing_service=indexing_service,
    )

    await service.process_claim_observations_persisted_section_work_item(
        queue_item=_persisted_item()
    )

    assert indexing_service.checks == []
    assert indexing_service.index_commands == []
