from typing import cast

import pytest

from src.contexts.knowledge_workbench.application.sagas.run_source_ingestion_first_phase import (
    RunSourceIngestionFirstPhase,
)
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.interfaces.composition.source_ingestion_first_phase import (
    _ProjectAccessAdapter,
    _SourceIngestionFirstPhaseUnitOfWork,
    make_source_ingestion_first_phase,
)


class EmptyProjectRepo:
    pass


class ProjectExistsRepo:
    def __init__(self, exists: bool) -> None:
        self.exists = exists
        self.called_with: list[str] = []

    async def project_exists(self, project_id: str) -> bool:
        self.called_with.append(project_id)
        return self.exists


class ProjectViewRepo:
    def __init__(self, view: object | None) -> None:
        self.view = view
        self.called_with: list[str] = []

    async def get_project_view(self, project_id: str) -> object | None:
        self.called_with.append(project_id)
        return self.view


class ProjectMemberRoleRepo:
    def __init__(self, role: str | None) -> None:
        self.role = role
        self.called_with: list[tuple[str, str]] = []

    async def get_project_view(self, project_id: str) -> object | None:
        return {"project_id": project_id}

    async def get_project_member_role(
        self,
        project_id: str,
        user_id: str,
    ) -> str | None:
        self.called_with.append((project_id, user_id))
        return self.role


class FakePool:
    pass


class FakeRepository:
    pass


def _user_repo() -> UserRepository:
    return cast(UserRepository, object())


@pytest.mark.asyncio
async def test_project_access_adapter_fails_closed_for_unknown_project_repo_shape() -> (
    None
):
    adapter = _ProjectAccessAdapter(
        project_repo=EmptyProjectRepo(),
        user_repo=_user_repo(),
    )

    assert await adapter.project_exists("project-1") is False


@pytest.mark.asyncio
async def test_project_exists_uses_project_exists_when_available() -> None:
    repo = ProjectExistsRepo(exists=True)
    adapter = _ProjectAccessAdapter(project_repo=repo, user_repo=_user_repo())

    assert await adapter.project_exists("project-1") is True
    assert repo.called_with == ["project-1"]


@pytest.mark.asyncio
async def test_project_exists_falls_back_to_get_project_view() -> None:
    existing_repo = ProjectViewRepo(view={"id": "project-1"})
    missing_repo = ProjectViewRepo(view=None)

    existing_adapter = _ProjectAccessAdapter(
        project_repo=existing_repo,
        user_repo=_user_repo(),
    )
    missing_adapter = _ProjectAccessAdapter(
        project_repo=missing_repo,
        user_repo=_user_repo(),
    )

    assert await existing_adapter.project_exists("project-1") is True
    assert await missing_adapter.project_exists("project-1") is False
    assert existing_repo.called_with == ["project-1"]
    assert missing_repo.called_with == ["project-1"]


@pytest.mark.asyncio
async def test_actor_project_role_uses_get_project_member_role() -> None:
    repo = ProjectMemberRoleRepo(role="owner")
    adapter = _ProjectAccessAdapter(project_repo=repo, user_repo=_user_repo())

    role = await adapter.actor_project_role(
        project_id="project-1",
        actor_user_id="user-1",
    )

    assert role == "owner"
    assert repo.called_with == [("project-1", "user-1")]


def test_factory_returns_run_source_ingestion_first_phase() -> None:
    use_case = make_source_ingestion_first_phase(
        pool=FakePool(),
        project_repo=ProjectMemberRoleRepo(role="owner"),
        user_repo=_user_repo(),
    )

    assert isinstance(use_case, RunSourceIngestionFirstPhase)


@pytest.mark.asyncio
async def test_noop_unit_of_work_delegates_repositories_and_methods_are_awaitable() -> (
    None
):
    source_management = FakeRepository()
    saga_state = FakeRepository()
    unit_of_work = _SourceIngestionFirstPhaseUnitOfWork(
        source_management=source_management,
        saga_state=saga_state,
    )

    assert unit_of_work.source_management is source_management
    assert unit_of_work.saga_state is saga_state

    await unit_of_work.commit()
    await unit_of_work.rollback()


def test_source_ingestion_first_phase_composition_source_guard() -> None:
    source = "src/interfaces/composition/source_ingestion_first_phase.py"
    text = __import__("pathlib").Path(source).read_text(encoding="utf-8")

    required_markers = [
        "make_source_ingestion_first_phase",
        "_ProjectAccessAdapter",
        "_SourceIngestionFirstPhaseUnitOfWork",
        "SourceIngestionAdmissionPolicy",
        "StartSourceIngestionWorkflow",
        "PersistAcceptedSourceIngestionPlan",
        "CreateSourceUnitsForIngestion",
        "RunSourceIngestionFirstPhase",
        "PostgresSourceManagementRepository",
        "PostgresKnowledgeExtractionSagaStateRepository",
        "project_exists",
        "get_project_view",
        "get_project_member_role",
    ]
    forbidden_markers = [
        "fastapi",
        "HTTPException",
        "Depends",
        "Header",
        "Request",
        "get_current_user_id",
        "authorization",
        "RunClaimExtractionStageAsync",
        "DraftObservationExtractionSchedulingReconciler",
        "PROMPT_A",
        "capacity_runtime",
        "execution_runtime",
        "llm_runtime",
        "artifact_runtime",
        "worker_loop",
        "JobDispatcher",
        "outbox_events",
        "queue",
        "Queue",
        "pdf",
        "Pdf",
        "openpyxl",
        "pandas",
        "markdown",
        "BeautifulSoup",
    ]

    for marker in required_markers:
        assert marker in text

    for marker in forbidden_markers:
        assert marker not in text
