from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    DomainInvariantError,
    JsonValue,
)
from src.domain.project_plane.knowledge_workbench.section_batch_queue import (
    SectionBatchQueueItem,
    SectionBatchQueueItemStatus,
    mark_section_batch_item_claim_observations_persisted,
)


class IdFactory(Protocol):
    def new_id(self, prefix: str) -> str: ...


class TimeProvider(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class SystemTimeProvider:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class SectionWorkItemProcessorRepositoryPort(Protocol):
    async def get_document_section(
        self,
        *,
        project_id: str,
        document_id: str,
        section_id: str,
    ) -> DocumentSection | None: ...

    async def update_section_batch_queue_item(
        self,
        item: SectionBatchQueueItem,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ProcessLeasedClaimObservationsCommand:
    queue_item: SectionBatchQueueItem
    section: DocumentSection

    def __post_init__(self) -> None:
        if self.queue_item.status is not SectionBatchQueueItemStatus.LEASED:
            raise DomainInvariantError(
                "claim observations command requires LEASED section item"
            )


@dataclass(frozen=True, slots=True)
class ProcessLeasedClaimObservationsResult:
    claim_observations_node_run_id: str
    claim_input_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.claim_observations_node_run_id:
            raise DomainInvariantError("claim observations result requires node run id")
        if not self.claim_input_refs:
            raise DomainInvariantError("claim observations result requires claim ids")


class LeasedClaimObservationsRunnerPort(Protocol):
    async def process_leased_claim_observations(
        self,
        command: ProcessLeasedClaimObservationsCommand,
    ) -> ProcessLeasedClaimObservationsResult: ...


@dataclass(frozen=True, slots=True)
class ProcessOneSectionWorkItemCommand:
    queue_item: SectionBatchQueueItem
    worker_id: str

    def __post_init__(self) -> None:
        if not self.worker_id:
            raise DomainInvariantError(
                "section work item processing requires worker_id"
            )


@dataclass(frozen=True, slots=True)
class ProcessOneSectionWorkItemResult:
    section: DocumentSection
    claim_observations_result: ProcessLeasedClaimObservationsResult
    claim_observations_persisted_item: SectionBatchQueueItem


@dataclass(frozen=True, slots=True)
class ProcessClaimObservationsPersistedSectionWorkItemResult:
    section: DocumentSection
    claim_observations_persisted_item: SectionBatchQueueItem


@dataclass(frozen=True, slots=True)
class FaqWorkbenchSectionWorkItemProcessorService:
    repository: SectionWorkItemProcessorRepositoryPort
    claim_observations_runner: LeasedClaimObservationsRunnerPort
    id_factory: IdFactory
    time_provider: TimeProvider = SystemTimeProvider()

    async def process_claim_observations_persisted_section_work_item(
        self,
        *,
        queue_item: SectionBatchQueueItem,
    ) -> ProcessClaimObservationsPersistedSectionWorkItemResult:
        if (
            queue_item.status
            is not SectionBatchQueueItemStatus.CLAIM_OBSERVATIONS_PERSISTED
        ):
            raise DomainInvariantError(
                "claim observations persisted recovery requires CLAIM_OBSERVATIONS_PERSISTED item"
            )
        if queue_item.claim_observations_node_run_id is None:
            raise DomainInvariantError(
                "claim observations persisted recovery requires claim observations node run"
            )

        section = await self.repository.get_document_section(
            project_id=queue_item.project_id,
            document_id=queue_item.document_id,
            section_id=queue_item.section_id,
        )
        if section is None:
            raise DomainInvariantError(
                "cannot recover claim observations persisted section item without section"
            )

        return ProcessClaimObservationsPersistedSectionWorkItemResult(
            section=section,
            claim_observations_persisted_item=queue_item,
        )

    async def process_one_section_work_item(
        self,
        command: ProcessOneSectionWorkItemCommand,
    ) -> ProcessOneSectionWorkItemResult:
        queue_item = command.queue_item
        if queue_item.status is not SectionBatchQueueItemStatus.LEASED:
            raise DomainInvariantError(
                "section work item processing requires LEASED item"
            )

        section = await self.repository.get_document_section(
            project_id=queue_item.project_id,
            document_id=queue_item.document_id,
            section_id=queue_item.section_id,
        )
        if section is None:
            raise DomainInvariantError("section work item requires document section")

        claim_observations_result = (
            await self.claim_observations_runner.process_leased_claim_observations(
                ProcessLeasedClaimObservationsCommand(
                    queue_item=queue_item,
                    section=section,
                )
            )
        )

        claim_observations_persisted_item = (
            mark_section_batch_item_claim_observations_persisted(
                queue_item=queue_item,
                claim_observations_node_run_id=(
                    claim_observations_result.claim_observations_node_run_id
                ),
                updated_at=self.time_provider.now(),
            )
        )
        await self.repository.update_section_batch_queue_item(
            claim_observations_persisted_item
        )

        return ProcessOneSectionWorkItemResult(
            section=section,
            claim_observations_result=claim_observations_result,
            claim_observations_persisted_item=claim_observations_persisted_item,
        )

    @staticmethod
    def _claim_observation_ids(
        claim_observations: tuple[dict[str, JsonValue], ...],
    ) -> tuple[str, ...]:
        refs: list[str] = []
        for index, observation in enumerate(claim_observations):
            local_ref = observation.get("local_ref")
            if isinstance(local_ref, str) and local_ref.strip():
                refs.append(local_ref.strip())
            else:
                refs.append(f"claim-{index + 1}")
        return tuple(refs)


__all__ = [
    "FaqWorkbenchSectionWorkItemProcessorService",
    "IdFactory",
    "LeasedClaimObservationsRunnerPort",
    "ProcessClaimObservationsPersistedSectionWorkItemResult",
    "ProcessLeasedClaimObservationsCommand",
    "ProcessLeasedClaimObservationsResult",
    "ProcessOneSectionWorkItemCommand",
    "ProcessOneSectionWorkItemResult",
    "SectionWorkItemProcessorRepositoryPort",
    "SystemTimeProvider",
    "TimeProvider",
]
