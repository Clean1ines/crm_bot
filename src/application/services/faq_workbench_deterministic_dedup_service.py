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
)


class IdFactory(Protocol):
    def new_id(self, prefix: str) -> str: ...


class TimeProvider(Protocol):
    def now(self) -> datetime: ...


class KnowledgeWorkbenchDeterministicDedupRepositoryPort(Protocol):
    async def create_processing_node_run(self, node_run: ProcessingNodeRun) -> None: ...

    async def create_processing_node_artifact(
        self,
        artifact: ProcessingNodeArtifact,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class SystemTimeProvider:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class PersistDeterministicDedupNodeOutputCommand:
    project_id: str
    document_id: str
    processing_run_id: str
    section_id: str
    registry_snapshot_id: str
    registry_snapshot_sequence_number: int
    claim_observations_payload: JsonValue
    dedup_result_payload: JsonValue


@dataclass(frozen=True, slots=True)
class PersistDeterministicDedupNodeOutputResult:
    node_run: ProcessingNodeRun
    input_artifact: ProcessingNodeArtifact
    output_artifact: ProcessingNodeArtifact


class FaqWorkbenchDeterministicDedupService:
    def __init__(
        self,
        repository: KnowledgeWorkbenchDeterministicDedupRepositoryPort,
        *,
        id_factory: IdFactory,
        time_provider: TimeProvider | None = None,
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._time_provider = time_provider or SystemTimeProvider()

    async def persist_deterministic_dedup_output(
        self,
        command: PersistDeterministicDedupNodeOutputCommand,
    ) -> PersistDeterministicDedupNodeOutputResult:
        now = self._time_provider.now()
        node_run_id = self._id_factory.new_id("node-run")
        input_artifact_id = self._id_factory.new_id("artifact")
        output_artifact_id = self._id_factory.new_id("artifact")

        node_run = ProcessingNodeRun(
            node_run_id=node_run_id,
            processing_run_id=command.processing_run_id,
            project_id=command.project_id,
            document_id=command.document_id,
            section_id=command.section_id,
            node_name=ProcessingNodeName.DETERMINISTIC_DEDUP,
            node_kind=ProcessingNodeKind.DETERMINISTIC_CODE,
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
            processing_run_id=command.processing_run_id,
            project_id=command.project_id,
            document_id=command.document_id,
            section_id=command.section_id,
            artifact_type=ProcessingNodeArtifactType.INPUT_SNAPSHOT,
            payload_json={
                "node": ProcessingNodeName.DETERMINISTIC_DEDUP.value,
                "registry_snapshot_id": command.registry_snapshot_id,
                "registry_snapshot_sequence_number": (
                    command.registry_snapshot_sequence_number
                ),
                "claim_observations": command.claim_observations_payload,
            },
            schema_version=1,
            created_at=now,
            metadata={
                "node": ProcessingNodeName.DETERMINISTIC_DEDUP.value,
                "registry_snapshot_id": command.registry_snapshot_id,
            },
        )

        output_artifact = ProcessingNodeArtifact(
            artifact_id=output_artifact_id,
            node_run_id=node_run_id,
            processing_run_id=command.processing_run_id,
            project_id=command.project_id,
            document_id=command.document_id,
            section_id=command.section_id,
            artifact_type=ProcessingNodeArtifactType.DETERMINISTIC_RESULT,
            payload_json={
                "node": ProcessingNodeName.DETERMINISTIC_DEDUP.value,
                "registry_snapshot_id": command.registry_snapshot_id,
                "registry_snapshot_sequence_number": (
                    command.registry_snapshot_sequence_number
                ),
                "dedup_result": command.dedup_result_payload,
            },
            schema_version=1,
            created_at=now,
            metadata={
                "node": ProcessingNodeName.DETERMINISTIC_DEDUP.value,
                "registry_snapshot_id": command.registry_snapshot_id,
            },
        )

        await self._repository.create_processing_node_run(node_run)
        await self._repository.create_processing_node_artifact(input_artifact)
        await self._repository.create_processing_node_artifact(output_artifact)

        return PersistDeterministicDedupNodeOutputResult(
            node_run=node_run,
            input_artifact=input_artifact,
            output_artifact=output_artifact,
        )
