from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.application.services.faq_workbench_surface_curation_service import (
    FaqWorkbenchSurfaceCurationService,
    MonotonicIdFactory,
    StartSurfaceCurationSessionCommand,
    SurfaceCurationChangeRequest,
)
from src.domain.project_plane.knowledge_workbench import (
    CurationChangeOperation,
    CurationChangeStatus,
    CurationSessionStatus,
    DomainInvariantError,
    KnowledgeSurface,
    SurfaceCurationChange,
    SurfaceCurationSession,
    SurfaceCurationState,
    SurfaceKind,
    SurfaceStatus,
)


@dataclass(frozen=True, slots=True)
class FixedTimeProvider:
    value: datetime

    def now(self) -> datetime:
        return self.value


@dataclass(slots=True)
class InMemorySurfaceCurationRepository:
    sessions: list[SurfaceCurationSession] = field(default_factory=list)
    changes: list[SurfaceCurationChange] = field(default_factory=list)
    surfaces: list[KnowledgeSurface] = field(default_factory=list)

    async def create_surface_curation_session(
        self,
        session: SurfaceCurationSession,
    ) -> None:
        self.sessions.append(session)

    async def create_surface_curation_changes(
        self,
        changes: tuple[SurfaceCurationChange, ...],
    ) -> None:
        self.changes.extend(changes)

    async def update_knowledge_surfaces(
        self,
        surfaces: tuple[KnowledgeSurface, ...],
    ) -> None:
        self.surfaces = list(surfaces)


def _surface(
    *,
    surface_id: str = "surface-1",
    status: SurfaceStatus = SurfaceStatus.DRAFT,
    curation_state: SurfaceCurationState = SurfaceCurationState.CLEAN,
) -> KnowledgeSurface:
    return KnowledgeSurface(
        surface_id=surface_id,
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
        registry_entry_id="registry-entry-1",
        processing_method="faq_section_registry_v1",
        title="Product Definition",
        canonical_question="Что такое продукт?",
        question_variants=("что делает продукт",),
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
        surface_kind=SurfaceKind.DEFINITION,
        status=status,
        curation_state=curation_state,
    )


@pytest.mark.asyncio
async def test_start_curation_session_applies_answer_edit_to_draft_only() -> None:
    repository = InMemorySurfaceCurationRepository()
    service = FaqWorkbenchSurfaceCurationService(
        repository,
        id_factory=MonotonicIdFactory.create(),
        time_provider=FixedTimeProvider(datetime(2026, 5, 31, tzinfo=timezone.utc)),
    )

    result = await service.start_session(
        StartSurfaceCurationSessionCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            created_by_user_id="user-1",
            surfaces=(_surface(),),
            changes=(
                SurfaceCurationChangeRequest(
                    surface_id="surface-1",
                    operation=CurationChangeOperation.EDIT_ANSWER,
                    new_answer="Новый проверенный ответ.",
                    new_short_answer="Коротко: новый ответ.",
                    reason="manual QA correction",
                ),
            ),
        )
    )

    assert result.session.status is CurationSessionStatus.HAS_CHANGES
    assert len(result.changes) == 1
    assert result.changes[0].status is CurationChangeStatus.APPLIED_TO_DRAFT
    assert result.changes[0].operation is CurationChangeOperation.EDIT_ANSWER

    updated = result.updated_surfaces[0]
    assert updated.answer == "Новый проверенный ответ."
    assert updated.short_answer == "Коротко: новый ответ."
    assert updated.status is SurfaceStatus.EDITED
    assert updated.curation_state is SurfaceCurationState.HAS_PENDING_CHANGES

    assert repository.sessions == [result.session]
    assert repository.changes == list(result.changes)
    assert repository.surfaces == list(result.updated_surfaces)


@pytest.mark.asyncio
async def test_start_curation_session_can_add_variant_without_runtime_publication() -> (
    None
):
    repository = InMemorySurfaceCurationRepository()
    service = FaqWorkbenchSurfaceCurationService(
        repository,
        id_factory=MonotonicIdFactory.create(),
    )

    result = await service.start_session(
        StartSurfaceCurationSessionCommand(
            project_id="project-1",
            created_by_user_id="user-1",
            surfaces=(_surface(),),
            changes=(
                SurfaceCurationChangeRequest(
                    surface_id="surface-1",
                    operation=CurationChangeOperation.ADD_VARIANT,
                    variant="зачем нужна платформа",
                ),
            ),
        )
    )

    updated = result.updated_surfaces[0]
    assert "зачем нужна платформа" in updated.question_variants
    assert updated.curation_state is SurfaceCurationState.HAS_PENDING_CHANGES
    assert repository.sessions[0].status is CurationSessionStatus.HAS_CHANGES


@pytest.mark.asyncio
async def test_start_curation_session_can_mark_surface_rejected() -> None:
    repository = InMemorySurfaceCurationRepository()
    service = FaqWorkbenchSurfaceCurationService(
        repository,
        id_factory=MonotonicIdFactory.create(),
    )

    result = await service.start_session(
        StartSurfaceCurationSessionCommand(
            project_id="project-1",
            created_by_user_id="user-1",
            surfaces=(_surface(),),
            changes=(
                SurfaceCurationChangeRequest(
                    surface_id="surface-1",
                    operation=CurationChangeOperation.REJECT,
                    reason="not useful",
                ),
            ),
        )
    )

    assert result.updated_surfaces[0].status is SurfaceStatus.REJECTED
    assert (
        result.updated_surfaces[0].curation_state
        is SurfaceCurationState.HAS_PENDING_CHANGES
    )


@pytest.mark.asyncio
async def test_start_curation_session_rejects_published_surface_edit() -> None:
    repository = InMemorySurfaceCurationRepository()
    service = FaqWorkbenchSurfaceCurationService(
        repository,
        id_factory=MonotonicIdFactory.create(),
    )

    with pytest.raises(DomainInvariantError):
        await service.start_session(
            StartSurfaceCurationSessionCommand(
                project_id="project-1",
                created_by_user_id="user-1",
                surfaces=(
                    _surface(
                        status=SurfaceStatus.PUBLISHED,
                        curation_state=SurfaceCurationState.PUBLISHED,
                    ),
                ),
                changes=(
                    SurfaceCurationChangeRequest(
                        surface_id="surface-1",
                        operation=CurationChangeOperation.EDIT_ANSWER,
                        new_answer="Should fail",
                    ),
                ),
            )
        )

    assert repository.sessions == []
    assert repository.changes == []


@pytest.mark.asyncio
async def test_start_curation_session_rejects_surface_from_other_project() -> None:
    repository = InMemorySurfaceCurationRepository()
    service = FaqWorkbenchSurfaceCurationService(
        repository,
        id_factory=MonotonicIdFactory.create(),
    )
    surface = _surface()

    with pytest.raises(DomainInvariantError):
        await service.start_session(
            StartSurfaceCurationSessionCommand(
                project_id="other-project",
                created_by_user_id="user-1",
                surfaces=(surface,),
                changes=(),
            )
        )

    assert repository.sessions == []


@pytest.mark.asyncio
async def test_open_curation_session_without_changes_does_not_modify_surface() -> None:
    repository = InMemorySurfaceCurationRepository()
    service = FaqWorkbenchSurfaceCurationService(
        repository,
        id_factory=MonotonicIdFactory.create(),
    )
    surface = _surface()

    result = await service.start_session(
        StartSurfaceCurationSessionCommand(
            project_id="project-1",
            created_by_user_id="user-1",
            surfaces=(surface,),
            changes=(),
        )
    )

    assert result.session.status is CurationSessionStatus.OPEN
    assert result.changes == ()
    assert result.updated_surfaces == (surface,)
    assert repository.surfaces == [surface]


@pytest.mark.asyncio
async def test_start_curation_session_can_delete_surface() -> None:
    repository = InMemorySurfaceCurationRepository()
    service = FaqWorkbenchSurfaceCurationService(
        repository,
        id_factory=MonotonicIdFactory.create(),
    )

    result = await service.start_session(
        StartSurfaceCurationSessionCommand(
            project_id="project-1",
            created_by_user_id="user-1",
            surfaces=(_surface(),),
            changes=(
                SurfaceCurationChangeRequest(
                    surface_id="surface-1",
                    operation=CurationChangeOperation.DELETE,
                    reason="obsolete answer card",
                ),
            ),
        )
    )

    updated = result.updated_surfaces[0]
    assert updated.status is SurfaceStatus.DELETED
    assert updated.curation_state is SurfaceCurationState.HAS_PENDING_CHANGES
    assert result.changes[0].operation is CurationChangeOperation.DELETE


@pytest.mark.asyncio
async def test_start_curation_session_can_restore_surface_to_draft() -> None:
    repository = InMemorySurfaceCurationRepository()
    service = FaqWorkbenchSurfaceCurationService(
        repository,
        id_factory=MonotonicIdFactory.create(),
    )

    result = await service.start_session(
        StartSurfaceCurationSessionCommand(
            project_id="project-1",
            created_by_user_id="user-1",
            surfaces=(
                _surface(
                    status=SurfaceStatus.REJECTED,
                    curation_state=SurfaceCurationState.HAS_PENDING_CHANGES,
                ),
            ),
            changes=(
                SurfaceCurationChangeRequest(
                    surface_id="surface-1",
                    operation=CurationChangeOperation.RESTORE,
                    reason="reviewed again",
                ),
            ),
        )
    )

    updated = result.updated_surfaces[0]
    assert updated.status is SurfaceStatus.DRAFT
    assert updated.curation_state is SurfaceCurationState.HAS_PENDING_CHANGES
    assert result.changes[0].operation is CurationChangeOperation.RESTORE


@pytest.mark.asyncio
async def test_start_curation_session_marks_merge_pending_with_target_surface() -> None:
    repository = InMemorySurfaceCurationRepository()
    service = FaqWorkbenchSurfaceCurationService(
        repository,
        id_factory=MonotonicIdFactory.create(),
    )

    result = await service.start_session(
        StartSurfaceCurationSessionCommand(
            project_id="project-1",
            created_by_user_id="user-1",
            surfaces=(
                _surface(surface_id="surface-1"),
                _surface(surface_id="surface-2"),
            ),
            changes=(
                SurfaceCurationChangeRequest(
                    surface_id="surface-1",
                    operation=CurationChangeOperation.MERGE,
                    merge_target_surface_id="surface-2",
                    reason="duplicate answer card",
                ),
            ),
        )
    )

    updated = result.updated_surfaces[0]
    assert updated.status is SurfaceStatus.MERGE_PENDING
    assert updated.curation_state is SurfaceCurationState.HAS_PENDING_CHANGES

    after_payload = result.changes[0].after_payload
    assert isinstance(after_payload, dict)
    assert after_payload["merge_target_surface_id"] == "surface-2"


@pytest.mark.asyncio
async def test_start_curation_session_rejects_merge_without_target_surface() -> None:
    repository = InMemorySurfaceCurationRepository()
    service = FaqWorkbenchSurfaceCurationService(
        repository,
        id_factory=MonotonicIdFactory.create(),
    )

    with pytest.raises(
        DomainInvariantError,
        match="merge requires merge_target_surface_id",
    ):
        await service.start_session(
            StartSurfaceCurationSessionCommand(
                project_id="project-1",
                created_by_user_id="user-1",
                surfaces=(_surface(),),
                changes=(
                    SurfaceCurationChangeRequest(
                        surface_id="surface-1",
                        operation=CurationChangeOperation.MERGE,
                    ),
                ),
            )
        )

    assert repository.sessions == []
    assert repository.changes == []
