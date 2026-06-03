from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

import pytest

from src.application.services.faq_workbench_surface_materialization_service import (
    FaqWorkbenchSurfaceMaterializationService,
    MaterializeRegistrySurfacesCommand,
    MonotonicIdFactory,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    KnowledgeSurface,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
    ProcessingNodeName,
    ProcessingNodeRun,
    QuestionRegistryEntry,
    RegistryEntryStatus,
    RegistrySnapshot,
    SurfaceCurationState,
    SurfaceKind,
    SurfaceMaterializationResult,
    SurfaceStatus,
)


@dataclass(frozen=True, slots=True)
class FixedTimeProvider:
    value: datetime

    def now(self) -> datetime:
        return self.value


@dataclass(slots=True)
class InMemorySurfaceMaterializationRepository:
    node_runs: list[ProcessingNodeRun] = field(default_factory=list)
    artifacts: list[ProcessingNodeArtifact] = field(default_factory=list)
    surfaces: list[KnowledgeSurface] = field(default_factory=list)
    materialization_results: list[SurfaceMaterializationResult] = field(
        default_factory=list
    )

    async def create_processing_node_run(self, node_run: ProcessingNodeRun) -> None:
        self.node_runs.append(node_run)

    async def create_processing_node_artifact(
        self,
        artifact: ProcessingNodeArtifact,
    ) -> None:
        self.artifacts.append(artifact)

    async def create_knowledge_surfaces(
        self,
        surfaces: tuple[KnowledgeSurface, ...],
    ) -> None:
        self.surfaces.extend(surfaces)

    async def create_surface_materialization_result(
        self,
        result: SurfaceMaterializationResult,
    ) -> None:
        self.materialization_results.append(result)


def _entry(
    *,
    entry_id: str = "registry-entry-1",
    status: RegistryEntryStatus = RegistryEntryStatus.ACTIVE,
) -> QuestionRegistryEntry:
    return QuestionRegistryEntry(
        registry_entry_id=entry_id,
        registry_id="registry-1",
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
        registry_entry_key="product_definition",
        canonical_question="Что такое продукт?",
        question_variants=("что делает продукт",),
        surface_kind=SurfaceKind.DEFINITION,
        answer="Система превращает документы бизнеса в управляемую AI-базу знаний.",
        short_answer="Управляемая AI-база знаний для бизнеса.",
        answer_scope="Описание продукта",
        question_scope="Вопросы о продукте",
        exclusion_scope="Цены и интеграции",
        evidence_quotes=(
            "Система превращает документы бизнеса в управляемую AI-базу знаний.",
        ),
        source_refs=("document-1#section-1",),
        source_section_ids=("section-1",),
        source_chunk_indexes=(0,),
        parent_entry_ids=(),
        child_entry_ids=(),
        duplicate_entry_ids=(),
        overlap_entry_ids=(),
        role_label_metadata={},
        status=status,
    )


def _snapshot(entry_count: int = 1) -> RegistrySnapshot:
    return RegistrySnapshot(
        snapshot_id="registry-snapshot-1",
        registry_id="registry-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        after_node_run_id="registry-update-application",
        sequence_number=2,
        entries_payload={"entries": []},
        relations_payload={"relations": []},
        entry_count=entry_count,
        relation_count=0,
        finding_count=1,
        update_count=1,
        created_at=datetime(2026, 5, 31, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_materializes_active_registry_entry_into_draft_surface() -> None:
    repository = InMemorySurfaceMaterializationRepository()
    service = FaqWorkbenchSurfaceMaterializationService(
        repository,
        id_factory=MonotonicIdFactory.create(),
        time_provider=FixedTimeProvider(datetime(2026, 5, 31, tzinfo=timezone.utc)),
    )

    result = await service.materialize_surfaces(
        MaterializeRegistrySurfacesCommand(
            registry_snapshot=_snapshot(entry_count=1),
            registry_entries=(_entry(),),
        )
    )

    assert result.node_run.node_name is ProcessingNodeName.SURFACE_MATERIALIZATION
    assert (
        result.input_artifact.artifact_type is ProcessingNodeArtifactType.INPUT_SNAPSHOT
    )
    assert (
        result.output_artifact.artifact_type
        is ProcessingNodeArtifactType.APPLIED_RESULT
    )

    assert len(result.surfaces) == 1
    surface = result.surfaces[0]
    assert surface.registry_entry_id == "registry-entry-1"
    assert surface.status is SurfaceStatus.DRAFT
    assert surface.curation_state is SurfaceCurationState.CLEAN
    assert surface.canonical_question == "Что такое продукт?"

    assert result.materialization_result.created_surface_ids == (surface.surface_id,)
    assert result.materialization_result.rejected_registry_entry_ids == ()

    assert repository.node_runs == [result.node_run]
    assert repository.artifacts == [result.input_artifact, result.output_artifact]
    assert repository.surfaces == list(result.surfaces)
    assert repository.materialization_results == [result.materialization_result]


@pytest.mark.asyncio
async def test_materialization_records_rejected_registry_entries_without_surface() -> (
    None
):
    repository = InMemorySurfaceMaterializationRepository()
    service = FaqWorkbenchSurfaceMaterializationService(
        repository,
        id_factory=MonotonicIdFactory.create(),
    )

    result = await service.materialize_surfaces(
        MaterializeRegistrySurfacesCommand(
            registry_snapshot=_snapshot(entry_count=1),
            registry_entries=(_entry(status=RegistryEntryStatus.REJECTED),),
        )
    )

    assert result.surfaces == ()
    assert result.materialization_result.created_surface_ids == ()
    assert result.materialization_result.rejected_registry_entry_ids == (
        "registry-entry-1",
    )
    assert repository.surfaces == []


@pytest.mark.asyncio
async def test_materialization_rejects_snapshot_entry_count_mismatch() -> None:
    repository = InMemorySurfaceMaterializationRepository()
    service = FaqWorkbenchSurfaceMaterializationService(
        repository,
        id_factory=MonotonicIdFactory.create(),
    )

    with pytest.raises(DomainInvariantError):
        await service.materialize_surfaces(
            MaterializeRegistrySurfacesCommand(
                registry_snapshot=_snapshot(entry_count=2),
                registry_entries=(_entry(),),
            )
        )

    assert repository.node_runs == []
    assert repository.surfaces == []


@pytest.mark.asyncio
async def test_materialization_rejects_registry_mismatch() -> None:
    repository = InMemorySurfaceMaterializationRepository()
    service = FaqWorkbenchSurfaceMaterializationService(
        repository,
        id_factory=MonotonicIdFactory.create(),
    )

    bad_entry = QuestionRegistryEntry(
        registry_entry_id="registry-entry-bad",
        registry_id="other-registry",
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
        registry_entry_key="bad",
        canonical_question="Bad?",
        question_variants=(),
        surface_kind=SurfaceKind.OTHER,
        answer="Bad",
        short_answer="Bad",
        answer_scope="Bad",
        question_scope="Bad",
        exclusion_scope="Bad",
        evidence_quotes=("Bad",),
        source_refs=("document-1#section-1",),
        source_section_ids=("section-1",),
        source_chunk_indexes=(0,),
        parent_entry_ids=(),
        child_entry_ids=(),
        duplicate_entry_ids=(),
        overlap_entry_ids=(),
        role_label_metadata={},
        status=RegistryEntryStatus.ACTIVE,
    )

    with pytest.raises(DomainInvariantError):
        await service.materialize_surfaces(
            MaterializeRegistrySurfacesCommand(
                registry_snapshot=_snapshot(entry_count=1),
                registry_entries=(bad_entry,),
            )
        )

    assert repository.materialization_results == []


async def test_materialization_dedupes_grounded_evidence_refs() -> None:
    repository = InMemorySurfaceMaterializationRepository()
    service = FaqWorkbenchSurfaceMaterializationService(
        repository, id_factory=MonotonicIdFactory.create()
    )

    entry = replace(
        _entry(),
        evidence_quotes=(
            "  System turns docs into knowledge. ",
            "System   turns docs into knowledge.",
        ),
        source_refs=(
            "document-1#section-1",
            "document-1#section-1",
        ),
        source_section_ids=(
            "section-1",
            "section-1",
        ),
        source_chunk_indexes=(0, 0),
    )

    result = await service.materialize_surfaces(
        MaterializeRegistrySurfacesCommand(
            registry_snapshot=_snapshot(entry_count=1),
            registry_entries=(entry,),
        )
    )

    assert result.surfaces[0].evidence_quotes == ("System turns docs into knowledge.",)
    assert result.surfaces[0].source_refs == ("section-1",)
    assert result.surfaces[0].source_section_ids == ("section-1",)


async def test_materialization_rejects_surface_without_grounded_evidence() -> None:
    repository = InMemorySurfaceMaterializationRepository()
    service = FaqWorkbenchSurfaceMaterializationService(
        repository, id_factory=MonotonicIdFactory.create()
    )

    entry = replace(
        _entry(),
        evidence_quotes=("",),
        source_refs=("document-1#section-1",),
        source_section_ids=("section-1",),
        source_chunk_indexes=(0,),
    )

    with pytest.raises(
        ValueError, match="must have at least one evidence ref|ungrounded"
    ):
        await service.materialize_surfaces(
            MaterializeRegistrySurfacesCommand(
                registry_snapshot=_snapshot(entry_count=1),
                registry_entries=(entry,),
            )
        )

    assert not repository.surfaces
