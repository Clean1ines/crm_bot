from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from src.domain.project_plane.knowledge_workbench import (
    JsonValue,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
    ProcessingNodeKind,
    ProcessingNodeName,
    ProcessingNodeRun,
    ProcessingNodeStatus,
    RegistrySnapshot,
)


class IdFactory(Protocol):
    def new_id(self, prefix: str) -> str: ...


class TimeProvider(Protocol):
    def now(self) -> datetime: ...


class KnowledgeWorkbenchRegistrySnapshotRepositoryPort(Protocol):
    async def create_processing_node_run(self, node_run: ProcessingNodeRun) -> None: ...

    async def create_processing_node_artifact(
        self,
        artifact: ProcessingNodeArtifact,
    ) -> None: ...

    async def create_registry_snapshot(self, snapshot: RegistrySnapshot) -> None: ...


@dataclass(frozen=True, slots=True)
class SystemTimeProvider:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class PersistRegistrySnapshotNodeCommand:
    registry_snapshot: RegistrySnapshot
    input_payload: JsonValue
    snapshot_payload: JsonValue


@dataclass(frozen=True, slots=True)
class PersistRegistrySnapshotNodeResult:
    node_run: ProcessingNodeRun
    input_artifact: ProcessingNodeArtifact
    output_artifact: ProcessingNodeArtifact
    registry_snapshot: RegistrySnapshot


class FaqWorkbenchRegistrySnapshotService:
    def __init__(
        self,
        repository: KnowledgeWorkbenchRegistrySnapshotRepositoryPort,
        *,
        id_factory: IdFactory,
        time_provider: TimeProvider | None = None,
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._time_provider = time_provider or SystemTimeProvider()

    async def persist_registry_snapshot_node(
        self,
        command: PersistRegistrySnapshotNodeCommand,
    ) -> PersistRegistrySnapshotNodeResult:
        snapshot = command.registry_snapshot
        now = self._time_provider.now()

        node_run_id = self._id_factory.new_id("node-run")
        input_artifact_id = self._id_factory.new_id("artifact")
        output_artifact_id = self._id_factory.new_id("artifact")

        node_run = ProcessingNodeRun(
            node_run_id=node_run_id,
            processing_run_id=snapshot.processing_run_id,
            project_id=snapshot.project_id,
            document_id=snapshot.document_id,
            section_id=snapshot.after_section_id,
            node_name=ProcessingNodeName.REGISTRY_SNAPSHOT,
            node_kind=ProcessingNodeKind.PERSISTENCE,
            status=ProcessingNodeStatus.COMPLETED,
            input_snapshot_id=input_artifact_id,
            output_snapshot_id=output_artifact_id,
            started_at=now,
            completed_at=now,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        )

        input_artifact = ProcessingNodeArtifact(
            artifact_id=input_artifact_id,
            node_run_id=node_run_id,
            processing_run_id=snapshot.processing_run_id,
            project_id=snapshot.project_id,
            document_id=snapshot.document_id,
            section_id=snapshot.after_section_id,
            artifact_type=ProcessingNodeArtifactType.INPUT_SNAPSHOT,
            payload_json={
                "node": ProcessingNodeName.REGISTRY_SNAPSHOT.value,
                "registry_id": snapshot.registry_id,
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_sequence_number": snapshot.sequence_number,
                "input": command.input_payload,
            },
            schema_version=1,
            created_at=now,
            metadata={
                "node": ProcessingNodeName.REGISTRY_SNAPSHOT.value,
                "registry_snapshot_id": snapshot.snapshot_id,
                "registry_snapshot_sequence_number": snapshot.sequence_number,
            },
        )

        output_artifact = ProcessingNodeArtifact(
            artifact_id=output_artifact_id,
            node_run_id=node_run_id,
            processing_run_id=snapshot.processing_run_id,
            project_id=snapshot.project_id,
            document_id=snapshot.document_id,
            section_id=snapshot.after_section_id,
            artifact_type=ProcessingNodeArtifactType.REGISTRY_SNAPSHOT,
            payload_json={
                "node": ProcessingNodeName.REGISTRY_SNAPSHOT.value,
                "registry_id": snapshot.registry_id,
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_sequence_number": snapshot.sequence_number,
                "snapshot": command.snapshot_payload,
            },
            schema_version=1,
            created_at=now,
            metadata={
                "node": ProcessingNodeName.REGISTRY_SNAPSHOT.value,
                "registry_snapshot_id": snapshot.snapshot_id,
                "registry_snapshot_sequence_number": snapshot.sequence_number,
            },
        )

        await self._repository.create_processing_node_run(node_run)
        await self._repository.create_processing_node_artifact(input_artifact)
        await self._repository.create_registry_snapshot(snapshot)
        await self._repository.create_processing_node_artifact(output_artifact)

        return PersistRegistrySnapshotNodeResult(
            node_run=node_run,
            input_artifact=input_artifact,
            output_artifact=output_artifact,
            registry_snapshot=snapshot,
        )
