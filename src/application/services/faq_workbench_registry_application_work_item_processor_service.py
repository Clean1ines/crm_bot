from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Protocol, cast

from src.application.ports.knowledge_workbench import (
    KnowledgeWorkbenchRegistryApplicationRepositoryPort,
)
from src.application.services.faq_workbench_registry_application_service import (
    ApplyFactRegistrySnapshotCommand,
    FaqWorkbenchRegistryApplicationService,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    JsonValue,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
    FactRegistry,
    RegistrySnapshot,
)
from src.domain.project_plane.knowledge_workbench.registry_application_queue import (
    RegistryApplicationFreshnessCheck,
    RegistryApplicationFreshnessDecision,
    RegistryApplicationQueueItem,
    RegistryApplicationQueueItemStatus,
    decide_registry_application_freshness,
    mark_registry_application_item_applied,
    mark_registry_application_item_for_rebase,
)
from src.domain.project_plane.knowledge_workbench.section_batch_queue import (
    SectionBatchQueueItem,
    mark_section_batch_item_registry_application_applied,
)


class RegistryApplicationWorkItemOutcome(StrEnum):
    NO_WORK = "no_work"
    APPLIED = "applied"
    REBASE_REQUIRED = "rebase_required"
    WAIT_FOR_SNAPSHOT = "wait_for_snapshot"
    SKIP_TERMINAL = "skip_terminal"


class RegistryApplicationWorkItemRepositoryPort(Protocol):
    async def restore_stale_registry_application_work_item_leases(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        now: datetime,
    ) -> int: ...

    async def lease_next_ready_registry_application_work_item(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        worker_id: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> RegistryApplicationQueueItem | None: ...

    async def update_registry_application_queue_item(
        self,
        item: RegistryApplicationQueueItem,
    ) -> None: ...

    async def get_section_batch_queue_item_by_registry_application_queue_item_id(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        registry_application_queue_item_id: str,
    ) -> SectionBatchQueueItem | None: ...

    async def update_section_batch_queue_item(
        self,
        item: SectionBatchQueueItem,
    ) -> None: ...

    async def get_fact_registry_for_run(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> FactRegistry | None: ...

    async def get_latest_registry_snapshot(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> RegistrySnapshot | None: ...

    async def get_processing_node_artifact_by_node_run_id_and_type(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        node_run_id: str,
        artifact_type: ProcessingNodeArtifactType,
    ) -> ProcessingNodeArtifact | None: ...


class IdFactory(Protocol):
    def new_id(self, prefix: str) -> str: ...


class TimeProvider(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class SystemTimeProvider:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ProcessRegistryApplicationWorkItemCommand:
    project_id: str
    document_id: str
    processing_run_id: str
    worker_id: str
    lease_seconds: int = 300

    def __post_init__(self) -> None:
        if not self.project_id:
            raise DomainInvariantError("registry work item requires project_id")
        if not self.document_id:
            raise DomainInvariantError("registry work item requires document_id")
        if not self.processing_run_id:
            raise DomainInvariantError("registry work item requires processing_run_id")
        if not self.worker_id:
            raise DomainInvariantError("registry work item requires worker_id")
        if self.lease_seconds < 1:
            raise DomainInvariantError(
                "registry work item lease_seconds must be positive"
            )


@dataclass(frozen=True, slots=True)
class ProcessRegistryApplicationWorkItemResult:
    outcome: RegistryApplicationWorkItemOutcome
    queue_item: RegistryApplicationQueueItem | None
    freshness: RegistryApplicationFreshnessCheck | None
    restored_stale_lease_count: int
    applied_snapshot: RegistrySnapshot | None = None

    @property
    def applied(self) -> bool:
        return self.outcome is RegistryApplicationWorkItemOutcome.APPLIED


class FaqWorkbenchRegistryApplicationWorkItemProcessorService:
    def __init__(
        self,
        repository: RegistryApplicationWorkItemRepositoryPort,
        *,
        id_factory: IdFactory,
        time_provider: TimeProvider | None = None,
        registry_application_service: FaqWorkbenchRegistryApplicationService
        | None = None,
    ) -> None:
        self._repository = repository
        self._time_provider = time_provider or SystemTimeProvider()
        self._registry_application_service = (
            registry_application_service
            or FaqWorkbenchRegistryApplicationService(
                cast(
                    KnowledgeWorkbenchRegistryApplicationRepositoryPort,
                    repository,
                ),
                id_factory=id_factory,
                time_provider=self._time_provider,
            )
        )

    async def process_next_registry_application_work_item(
        self,
        command: ProcessRegistryApplicationWorkItemCommand,
    ) -> ProcessRegistryApplicationWorkItemResult:
        now = self._time_provider.now()
        lease_expires_at = now + timedelta(seconds=command.lease_seconds)

        restored_count = (
            await self._repository.restore_stale_registry_application_work_item_leases(
                project_id=command.project_id,
                document_id=command.document_id,
                processing_run_id=command.processing_run_id,
                now=now,
            )
        )

        queue_item = (
            await self._repository.lease_next_ready_registry_application_work_item(
                project_id=command.project_id,
                document_id=command.document_id,
                processing_run_id=command.processing_run_id,
                worker_id=command.worker_id,
                lease_expires_at=lease_expires_at,
                now=now,
            )
        )
        if queue_item is None:
            return ProcessRegistryApplicationWorkItemResult(
                outcome=RegistryApplicationWorkItemOutcome.NO_WORK,
                queue_item=None,
                freshness=None,
                restored_stale_lease_count=restored_count,
            )

        latest_snapshot = await self._require_latest_registry_snapshot(queue_item)
        freshness = decide_registry_application_freshness(
            queue_item=queue_item,
            latest_registry_snapshot=latest_snapshot,
        )

        if freshness.decision is RegistryApplicationFreshnessDecision.REBASE_REQUIRED:
            stale_item = mark_registry_application_item_for_rebase(
                queue_item=queue_item,
                latest_registry_snapshot=latest_snapshot,
                updated_at=now,
            )
            await self._repository.update_registry_application_queue_item(stale_item)
            return ProcessRegistryApplicationWorkItemResult(
                outcome=RegistryApplicationWorkItemOutcome.REBASE_REQUIRED,
                queue_item=stale_item,
                freshness=freshness,
                restored_stale_lease_count=restored_count,
            )

        if freshness.decision is RegistryApplicationFreshnessDecision.WAIT_FOR_SNAPSHOT:
            waiting_item = replace(
                queue_item,
                status=RegistryApplicationQueueItemStatus.READY,
                claimed_by_worker_id=None,
                lease_expires_at=None,
                updated_at=now,
            )
            await self._repository.update_registry_application_queue_item(waiting_item)
            return ProcessRegistryApplicationWorkItemResult(
                outcome=RegistryApplicationWorkItemOutcome.WAIT_FOR_SNAPSHOT,
                queue_item=waiting_item,
                freshness=freshness,
                restored_stale_lease_count=restored_count,
            )

        if freshness.decision is RegistryApplicationFreshnessDecision.SKIP_TERMINAL:
            return ProcessRegistryApplicationWorkItemResult(
                outcome=RegistryApplicationWorkItemOutcome.SKIP_TERMINAL,
                queue_item=queue_item,
                freshness=freshness,
                restored_stale_lease_count=restored_count,
            )

        registry = await self._require_fact_registry(queue_item)
        fact_registry_artifact = await self._require_fact_registry_artifact(queue_item)
        fact_registry, registry_update_summary = self._fact_registry_payload(
            fact_registry_artifact
        )

        application_result = (
            await self._registry_application_service.apply_fact_registry_snapshot(
                ApplyFactRegistrySnapshotCommand(
                    registry=registry,
                    fact_registry=fact_registry,
                    registry_update_summary=registry_update_summary,
                    previous_snapshot_id=latest_snapshot.snapshot_id,
                    previous_snapshot_sequence_number=latest_snapshot.sequence_number,
                    after_node_run_id=fact_registry_artifact.node_run_id,
                    after_section_id=queue_item.section_id,
                )
            )
        )

        applied_item = mark_registry_application_item_applied(
            queue_item=queue_item,
            observed_registry_snapshot=latest_snapshot,
            applied_registry_snapshot=application_result.snapshot,
            updated_at=now,
        )
        await self._repository.update_registry_application_queue_item(applied_item)

        await self._mark_linked_section_item_applied(
            applied_item=applied_item,
            updated_at=now,
        )

        return ProcessRegistryApplicationWorkItemResult(
            outcome=RegistryApplicationWorkItemOutcome.APPLIED,
            queue_item=applied_item,
            freshness=freshness,
            restored_stale_lease_count=restored_count,
            applied_snapshot=application_result.snapshot,
        )

    async def _mark_linked_section_item_applied(
        self,
        *,
        applied_item: RegistryApplicationQueueItem,
        updated_at: datetime,
    ) -> None:
        linked_section_item = await self._repository.get_section_batch_queue_item_by_registry_application_queue_item_id(
            project_id=applied_item.project_id,
            document_id=applied_item.document_id,
            processing_run_id=applied_item.processing_run_id,
            registry_application_queue_item_id=applied_item.queue_item_id,
        )
        if linked_section_item is None:
            return

        await self._repository.update_section_batch_queue_item(
            mark_section_batch_item_registry_application_applied(
                queue_item=linked_section_item,
                updated_at=updated_at,
            )
        )

    async def _require_latest_registry_snapshot(
        self,
        queue_item: RegistryApplicationQueueItem,
    ) -> RegistrySnapshot:
        latest_snapshot = await self._repository.get_latest_registry_snapshot(
            project_id=queue_item.project_id,
            document_id=queue_item.document_id,
            processing_run_id=queue_item.processing_run_id,
        )
        if latest_snapshot is None:
            raise DomainInvariantError(
                "registry application worker requires latest registry snapshot"
            )
        return latest_snapshot

    async def _require_fact_registry(
        self,
        queue_item: RegistryApplicationQueueItem,
    ) -> FactRegistry:
        registry = await self._repository.get_fact_registry_for_run(
            project_id=queue_item.project_id,
            document_id=queue_item.document_id,
            processing_run_id=queue_item.processing_run_id,
        )
        if registry is None:
            raise DomainInvariantError(
                "registry application worker requires fact registry"
            )
        return registry

    async def _require_fact_registry_artifact(
        self,
        queue_item: RegistryApplicationQueueItem,
    ) -> ProcessingNodeArtifact:
        artifact = (
            await self._repository.get_processing_node_artifact_by_node_run_id_and_type(
                project_id=queue_item.project_id,
                document_id=queue_item.document_id,
                processing_run_id=queue_item.processing_run_id,
                node_run_id=queue_item.source_node_run_id,
                artifact_type=ProcessingNodeArtifactType.PARSED_LLM_OUTPUT,
            )
        )
        if artifact is None:
            raise DomainInvariantError(
                "registry application worker requires fact_registry parsed artifact"
            )
        return artifact

    def _fact_registry_payload(
        self,
        artifact: ProcessingNodeArtifact,
    ) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
        payload = artifact.payload_json
        if not isinstance(payload, dict):
            raise DomainInvariantError(
                "fact registry artifact payload must be an object"
            )

        fact_registry = payload.get("fact_registry")
        if not isinstance(fact_registry, dict):
            raise DomainInvariantError(
                "fact registry artifact payload requires fact_registry"
            )

        registry_update_summary = payload.get("registry_update_summary")
        if not isinstance(registry_update_summary, dict):
            raise DomainInvariantError(
                "fact registry artifact payload requires registry_update_summary"
            )

        return fact_registry, registry_update_summary


__all__ = [
    "FaqWorkbenchRegistryApplicationWorkItemProcessorService",
    "ProcessRegistryApplicationWorkItemCommand",
    "ProcessRegistryApplicationWorkItemResult",
    "RegistryApplicationWorkItemOutcome",
]
