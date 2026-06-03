from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from src.application.ports.knowledge_workbench import (
    KnowledgeWorkbenchRestoreCheckpointRepositoryPort,
)
from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    DomainInvariantError,
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


@dataclass(frozen=True, slots=True)
class SystemTimeProvider:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class RestoreWorkbenchCheckpointCommand:
    sections: tuple[DocumentSection, ...]
    latest_registry_snapshot: RegistrySnapshot


@dataclass(frozen=True, slots=True)
class RestoreWorkbenchCheckpointResult:
    node_run: ProcessingNodeRun
    input_artifact: ProcessingNodeArtifact
    output_artifact: ProcessingNodeArtifact
    completed_section_ids: tuple[str, ...]
    pending_sections: tuple[DocumentSection, ...]
    latest_registry_snapshot: RegistrySnapshot

    @property
    def pending_section_ids(self) -> tuple[str, ...]:
        return tuple(section.section_id for section in self.pending_sections)


class FaqWorkbenchRestoreCheckpointService:
    def __init__(
        self,
        repository: KnowledgeWorkbenchRestoreCheckpointRepositoryPort,
        *,
        id_factory: IdFactory,
        time_provider: TimeProvider | None = None,
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._time_provider = time_provider or SystemTimeProvider()

    async def restore_checkpoint(
        self,
        command: RestoreWorkbenchCheckpointCommand,
    ) -> RestoreWorkbenchCheckpointResult:
        self._validate_command(command)

        completed_section_ids, pending_sections = self._split_sections_by_cursor(
            sections=command.sections,
            snapshot=command.latest_registry_snapshot,
        )

        now = self._time_provider.now()
        node_run_id = self._id_factory.new_id("node-run")
        input_artifact_id = self._id_factory.new_id("artifact")
        output_artifact_id = self._id_factory.new_id("artifact")
        snapshot = command.latest_registry_snapshot

        node_run = ProcessingNodeRun(
            node_run_id=node_run_id,
            processing_run_id=snapshot.processing_run_id,
            project_id=snapshot.project_id,
            document_id=snapshot.document_id,
            node_name=ProcessingNodeName.RESTORE_CHECKPOINT,
            node_kind=ProcessingNodeKind.PERSISTENCE,
            status=ProcessingNodeStatus.COMPLETED,
            input_snapshot_id=input_artifact_id,
            output_snapshot_id=output_artifact_id,
            started_at=now,
            completed_at=now,
        )

        input_artifact = ProcessingNodeArtifact(
            artifact_id=input_artifact_id,
            node_run_id=node_run_id,
            processing_run_id=snapshot.processing_run_id,
            project_id=snapshot.project_id,
            document_id=snapshot.document_id,
            artifact_type=ProcessingNodeArtifactType.INPUT_SNAPSHOT,
            payload_json=self._input_payload(command),
            schema_version=1,
            created_at=now,
            metadata={
                "node": ProcessingNodeName.RESTORE_CHECKPOINT.value,
                "registry_snapshot_id": snapshot.snapshot_id,
            },
        )

        output_artifact = ProcessingNodeArtifact(
            artifact_id=output_artifact_id,
            node_run_id=node_run_id,
            processing_run_id=snapshot.processing_run_id,
            project_id=snapshot.project_id,
            document_id=snapshot.document_id,
            artifact_type=ProcessingNodeArtifactType.APPLIED_RESULT,
            payload_json=self._output_payload(
                snapshot=snapshot,
                completed_section_ids=completed_section_ids,
                pending_sections=pending_sections,
            ),
            schema_version=1,
            created_at=now,
            metadata={
                "node": ProcessingNodeName.RESTORE_CHECKPOINT.value,
                "registry_snapshot_id": snapshot.snapshot_id,
                "after_section_id": snapshot.after_section_id,
                "pending_section_count": len(pending_sections),
            },
        )

        await self._repository.create_processing_node_run(node_run)
        await self._repository.create_processing_node_artifact(input_artifact)
        await self._repository.create_processing_node_artifact(output_artifact)

        return RestoreWorkbenchCheckpointResult(
            node_run=node_run,
            input_artifact=input_artifact,
            output_artifact=output_artifact,
            completed_section_ids=completed_section_ids,
            pending_sections=pending_sections,
            latest_registry_snapshot=snapshot,
        )

    def _validate_command(self, command: RestoreWorkbenchCheckpointCommand) -> None:
        snapshot = command.latest_registry_snapshot
        if not snapshot.snapshot_id:
            raise DomainInvariantError("restore checkpoint requires registry snapshot")
        if snapshot.entry_count < 0:
            raise DomainInvariantError("restore checkpoint entry_count must be valid")

        for section in command.sections:
            if section.project_id != snapshot.project_id:
                raise DomainInvariantError(
                    "restore checkpoint section project mismatch"
                )
            if section.document_id != snapshot.document_id:
                raise DomainInvariantError(
                    "restore checkpoint section document mismatch"
                )

    def _split_sections_by_cursor(
        self,
        *,
        sections: tuple[DocumentSection, ...],
        snapshot: RegistrySnapshot,
    ) -> tuple[tuple[str, ...], tuple[DocumentSection, ...]]:
        if snapshot.after_section_id is None:
            return (), sections

        cursor_section = next(
            (
                section
                for section in sections
                if section.section_id == snapshot.after_section_id
            ),
            None,
        )
        if cursor_section is None:
            raise DomainInvariantError(
                "restore checkpoint after_section_id does not match document sections"
            )

        completed: list[str] = []
        pending: list[DocumentSection] = []
        for section in sorted(sections, key=lambda item: item.section_index):
            if section.section_index <= cursor_section.section_index:
                completed.append(section.section_id)
            else:
                pending.append(section)

        return tuple(completed), tuple(pending)

    def _input_payload(
        self,
        command: RestoreWorkbenchCheckpointCommand,
    ) -> JsonValue:
        snapshot = command.latest_registry_snapshot
        return {
            "node": ProcessingNodeName.RESTORE_CHECKPOINT.value,
            "registry_snapshot_id": snapshot.snapshot_id,
            "registry_id": snapshot.registry_id,
            "processing_run_id": snapshot.processing_run_id,
            "after_section_id": snapshot.after_section_id,
            "after_node_run_id": snapshot.after_node_run_id,
            "snapshot_sequence_number": snapshot.sequence_number,
            "entry_count": snapshot.entry_count,
            "section_count": len(command.sections),
            "sections": [
                {
                    "section_id": section.section_id,
                    "section_index": section.section_index,
                    "section_key": section.section_key,
                    "status": section.status.value,
                }
                for section in sorted(
                    command.sections,
                    key=lambda item: item.section_index,
                )
            ],
        }

    def _output_payload(
        self,
        *,
        snapshot: RegistrySnapshot,
        completed_section_ids: tuple[str, ...],
        pending_sections: tuple[DocumentSection, ...],
    ) -> JsonValue:
        return {
            "node": ProcessingNodeName.RESTORE_CHECKPOINT.value,
            "registry_snapshot_id": snapshot.snapshot_id,
            "resume_cursor": {
                "after_section_id": snapshot.after_section_id,
                "after_node_run_id": snapshot.after_node_run_id,
                "snapshot_sequence_number": snapshot.sequence_number,
            },
            "completed_section_ids": list(completed_section_ids),
            "pending_section_ids": [section.section_id for section in pending_sections],
            "pending_section_count": len(pending_sections),
        }
