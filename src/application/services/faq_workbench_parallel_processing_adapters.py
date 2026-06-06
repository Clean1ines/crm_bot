from __future__ import annotations

from src.application.services.faq_workbench_canonicalization_barrier_service import (
    ProcessDocumentCanonicalizationBarrierCommand,
)
from src.application.services.faq_workbench_parallel_processing_coordinator_service import (
    ProcessParallelCanonicalizationBarrierCommand,
)

from dataclasses import dataclass
from typing import Protocol

from src.infrastructure.logging.logger import get_logger

from src.application.services.faq_workbench_parallel_processing_coordinator_service import (
    ProcessParallelRegistryApplicationWorkItemCommand,
    ProcessParallelSectionWorkItemCommand,
)
from src.application.services.faq_workbench_registry_application_work_item_processor_service import (
    FaqWorkbenchRegistryApplicationWorkItemProcessorService,
    ProcessRegistryApplicationWorkItemCommand,
)
from src.application.services.faq_workbench_section_work_item_lease_service import (
    ClaimSectionWorkItemCommand,
    FaqWorkbenchSectionWorkItemLeaseService,
)
from src.application.services.faq_workbench_section_work_item_processor_service import (
    FaqWorkbenchSectionWorkItemProcessorService,
    ProcessOneSectionWorkItemCommand,
)


logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FaqWorkbenchParallelSectionNoWorkResult:
    outcome: str = "no_work"
    restored_stale_lease_count: int = 0


@dataclass(frozen=True, slots=True)
class FaqWorkbenchParallelSectionProcessedResult:
    processed_result: object
    outcome: str = "processed"


@dataclass(frozen=True, slots=True)
class FaqWorkbenchParallelSectionProcessorAdapter:
    lease_service: FaqWorkbenchSectionWorkItemLeaseService
    processor: FaqWorkbenchSectionWorkItemProcessorService

    async def process_next_section_work_item(
        self,
        command: ProcessParallelSectionWorkItemCommand,
    ) -> object:
        claim_result = await self.lease_service.claim_next_ready_section_work_item(
            ClaimSectionWorkItemCommand(
                project_id=command.project_id,
                document_id=command.document_id,
                processing_run_id=command.processing_run_id,
                worker_id=command.worker_id,
                lease_seconds=command.lease_seconds,
            )
        )

        if claim_result.leased_item is None:
            if claim_result.restored_stale_lease_count:
                logger.info(
                    "Workbench section worker restored stale leases",
                    extra={
                        "project_id": command.project_id,
                        "document_id": command.document_id,
                        "processing_run_id": command.processing_run_id,
                        "worker_id": command.worker_id,
                        "restored_stale_lease_count": claim_result.restored_stale_lease_count,
                    },
                )
            return FaqWorkbenchParallelSectionNoWorkResult(
                restored_stale_lease_count=claim_result.restored_stale_lease_count,
            )

        leased_item = claim_result.leased_item
        logger.info(
            "Workbench section worker leased item",
            extra={
                "project_id": command.project_id,
                "document_id": command.document_id,
                "processing_run_id": command.processing_run_id,
                "worker_id": command.worker_id,
                "queue_item_id": leased_item.queue_item_id,
                "section_id": leased_item.section_id,
                "section_index": leased_item.section_index,
                "lane_id": leased_item.lane_id,
                "lane_index": leased_item.lane_index,
                "attempt_count": leased_item.attempt_count,
            },
        )

        processed_result = await self.processor.process_one_section_work_item(
            ProcessOneSectionWorkItemCommand(
                queue_item=claim_result.leased_item,
                worker_id=command.worker_id,
            )
        )
        persisted_item = processed_result.claim_observations_persisted_item
        logger.info(
            "Workbench section worker completed item",
            extra={
                "project_id": command.project_id,
                "document_id": command.document_id,
                "processing_run_id": command.processing_run_id,
                "worker_id": command.worker_id,
                "queue_item_id": persisted_item.queue_item_id,
                "section_id": persisted_item.section_id,
                "section_index": persisted_item.section_index,
                "lane_id": persisted_item.lane_id,
                "lane_index": persisted_item.lane_index,
                "status": persisted_item.status.value,
                "claim_observations_node_run_id": persisted_item.claim_observations_node_run_id,
            },
        )
        return FaqWorkbenchParallelSectionProcessedResult(
            processed_result=processed_result,
        )


@dataclass(frozen=True, slots=True)
class FaqWorkbenchParallelRegistryApplicationProcessorAdapter:
    processor: FaqWorkbenchRegistryApplicationWorkItemProcessorService

    async def process_next_registry_application_work_item(
        self,
        command: ProcessParallelRegistryApplicationWorkItemCommand,
    ) -> object:
        return await self.processor.process_next_registry_application_work_item(
            ProcessRegistryApplicationWorkItemCommand(
                project_id=command.project_id,
                document_id=command.document_id,
                processing_run_id=command.processing_run_id,
                worker_id=command.worker_id,
                lease_seconds=command.lease_seconds,
            )
        )


__all__ = [
    "FaqWorkbenchParallelRegistryApplicationProcessorAdapter",
    "FaqWorkbenchParallelSectionNoWorkResult",
    "FaqWorkbenchParallelSectionProcessedResult",
    "FaqWorkbenchParallelSectionProcessorAdapter",
]


class CanonicalizationBarrierServicePort(Protocol):
    async def process_document_canonicalization_barrier(
        self,
        command: ProcessDocumentCanonicalizationBarrierCommand,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class FaqWorkbenchCanonicalizationBarrierProcessorAdapter:
    """Adapter from the parallel coordinator barrier command to the real barrier service."""

    barrier_service: CanonicalizationBarrierServicePort

    async def process_document_canonicalization_barrier(
        self,
        command: ProcessParallelCanonicalizationBarrierCommand,
    ) -> object:
        return await self.barrier_service.process_document_canonicalization_barrier(
            ProcessDocumentCanonicalizationBarrierCommand(
                project_id=command.project_id,
                document_id=command.document_id,
                processing_run_id=command.processing_run_id,
                worker_id=command.worker_id,
                lease_seconds=command.lease_seconds,
            )
        )
