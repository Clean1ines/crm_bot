from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.application.services.faq_workbench_restore_checkpoint_service import (
    FaqWorkbenchRestoreCheckpointService,
    RestoreWorkbenchCheckpointCommand,
)
from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    DocumentSectionStatus,
    DomainInvariantError,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
    ProcessingNodeName,
    ProcessingNodeRun,
    ProcessingNodeStatus,
    RegistrySnapshot,
)


@dataclass(frozen=True, slots=True)
class FixedTimeProvider:
    value: datetime

    def now(self) -> datetime:
        return self.value


@dataclass(slots=True)
class MonotonicIdFactory:
    current: int = 0

    def new_id(self, prefix: str) -> str:
        self.current += 1
        return f"{prefix}-{self.current}"


@dataclass(slots=True)
class InMemoryRestoreCheckpointRepository:
    node_runs: list[ProcessingNodeRun] = field(default_factory=list)
    artifacts: list[ProcessingNodeArtifact] = field(default_factory=list)

    async def create_processing_node_run(self, node_run: ProcessingNodeRun) -> None:
        self.node_runs.append(node_run)

    async def create_processing_node_artifact(
        self,
        artifact: ProcessingNodeArtifact,
    ) -> None:
        self.artifacts.append(artifact)


def _section(index: int) -> DocumentSection:
    return DocumentSection(
        section_id=f"section-{index}",
        document_id="document-1",
        project_id="project-1",
        section_index=index,
        section_key=f"s{index}",
        heading_path=(f"Section {index}",),
        title=f"Section {index}",
        raw_text=f"Raw section {index}",
        normalized_text=f"Normalized section {index}",
        source_refs=(f"document-1#section-{index}",),
        source_chunk_indexes=(index,),
        parent_section_id=None,
        status=DocumentSectionStatus.PENDING,
        metadata={},
    )


def _snapshot(after_section_id: str | None) -> RegistrySnapshot:
    return RegistrySnapshot(
        snapshot_id="snapshot-1",
        registry_id="registry-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        after_node_run_id="registry-update-application-node",
        sequence_number=3,
        entries_payload={"entries": []},
        relations_payload={"relations": []},
        entry_count=1,
        relation_count=0,
        claim_observation_count=2,
        update_count=1,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        after_section_id=after_section_id,
    )


@pytest.mark.asyncio
async def test_restore_checkpoint_persists_node_artifacts_and_returns_pending_sections() -> (
    None
):
    repository = InMemoryRestoreCheckpointRepository()
    service = FaqWorkbenchRestoreCheckpointService(
        repository,
        id_factory=MonotonicIdFactory(),
        time_provider=FixedTimeProvider(datetime(2026, 6, 1, tzinfo=timezone.utc)),
    )

    result = await service.restore_checkpoint(
        RestoreWorkbenchCheckpointCommand(
            sections=(_section(0), _section(1), _section(2)),
            latest_registry_snapshot=_snapshot(after_section_id="section-1"),
        )
    )

    assert result.node_run.node_name is ProcessingNodeName.RESTORE_CHECKPOINT
    assert result.node_run.status is ProcessingNodeStatus.COMPLETED
    assert result.node_run.input_snapshot_id == result.input_artifact.artifact_id
    assert result.node_run.output_snapshot_id == result.output_artifact.artifact_id

    assert result.completed_section_ids == ("section-0", "section-1")
    assert result.pending_section_ids == ("section-2",)

    assert repository.node_runs == [result.node_run]
    assert repository.artifacts == [result.input_artifact, result.output_artifact]
    assert (
        result.input_artifact.artifact_type is ProcessingNodeArtifactType.INPUT_SNAPSHOT
    )
    assert (
        result.output_artifact.artifact_type
        is ProcessingNodeArtifactType.APPLIED_RESULT
    )

    assert result.output_artifact.payload_json["resume_cursor"]["after_section_id"] == (
        "section-1"
    )
    assert result.output_artifact.payload_json["pending_section_ids"] == ["section-2"]


@pytest.mark.asyncio
async def test_restore_checkpoint_without_section_cursor_processes_all_sections() -> (
    None
):
    repository = InMemoryRestoreCheckpointRepository()
    service = FaqWorkbenchRestoreCheckpointService(
        repository,
        id_factory=MonotonicIdFactory(),
    )

    result = await service.restore_checkpoint(
        RestoreWorkbenchCheckpointCommand(
            sections=(_section(0), _section(1)),
            latest_registry_snapshot=_snapshot(after_section_id=None),
        )
    )

    assert result.completed_section_ids == ()
    assert result.pending_section_ids == ("section-0", "section-1")


@pytest.mark.asyncio
async def test_restore_checkpoint_rejects_unknown_after_section_id_without_persistence() -> (
    None
):
    repository = InMemoryRestoreCheckpointRepository()
    service = FaqWorkbenchRestoreCheckpointService(
        repository,
        id_factory=MonotonicIdFactory(),
    )

    with pytest.raises(DomainInvariantError, match="after_section_id"):
        await service.restore_checkpoint(
            RestoreWorkbenchCheckpointCommand(
                sections=(_section(0), _section(1)),
                latest_registry_snapshot=_snapshot(after_section_id="missing-section"),
            )
        )

    assert repository.node_runs == []
    assert repository.artifacts == []
