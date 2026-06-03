from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from src.domain.project_plane.knowledge_workbench import DomainInvariantError
from src.domain.project_plane.knowledge_workbench.section_batch_queue import (
    SectionBatchQueueItem,
)


class SectionWorkItemLeaseRepositoryPort(Protocol):
    async def restore_stale_section_work_item_leases(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        now: datetime,
    ) -> int: ...

    async def lease_next_ready_section_work_item(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        worker_id: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> SectionBatchQueueItem | None: ...


class TimeProvider(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class SystemTimeProvider:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ClaimSectionWorkItemCommand:
    project_id: str
    document_id: str
    processing_run_id: str
    worker_id: str
    lease_seconds: int = 300

    def __post_init__(self) -> None:
        if not self.project_id:
            raise DomainInvariantError("section work item claim requires project_id")
        if not self.document_id:
            raise DomainInvariantError("section work item claim requires document_id")
        if not self.processing_run_id:
            raise DomainInvariantError(
                "section work item claim requires processing_run_id"
            )
        if not self.worker_id:
            raise DomainInvariantError("section work item claim requires worker_id")
        if self.lease_seconds < 1:
            raise DomainInvariantError(
                "section work item lease_seconds must be positive"
            )


@dataclass(frozen=True, slots=True)
class ClaimSectionWorkItemResult:
    leased_item: SectionBatchQueueItem | None
    restored_stale_lease_count: int

    @property
    def claimed(self) -> bool:
        return self.leased_item is not None


@dataclass(frozen=True, slots=True)
class FaqWorkbenchSectionWorkItemLeaseService:
    repository: SectionWorkItemLeaseRepositoryPort
    time_provider: TimeProvider = SystemTimeProvider()

    async def claim_next_ready_section_work_item(
        self,
        command: ClaimSectionWorkItemCommand,
    ) -> ClaimSectionWorkItemResult:
        now = self.time_provider.now()
        lease_expires_at = now + timedelta(seconds=command.lease_seconds)

        restored_count = await self.repository.restore_stale_section_work_item_leases(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=command.processing_run_id,
            now=now,
        )

        leased_item = await self.repository.lease_next_ready_section_work_item(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=command.processing_run_id,
            worker_id=command.worker_id,
            lease_expires_at=lease_expires_at,
            now=now,
        )

        return ClaimSectionWorkItemResult(
            leased_item=leased_item,
            restored_stale_lease_count=restored_count,
        )


__all__ = [
    "ClaimSectionWorkItemCommand",
    "ClaimSectionWorkItemResult",
    "FaqWorkbenchSectionWorkItemLeaseService",
    "SectionWorkItemLeaseRepositoryPort",
]
