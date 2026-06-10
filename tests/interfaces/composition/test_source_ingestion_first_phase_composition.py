from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest

from src.contexts.knowledge_workbench.application.sagas.run_source_ingestion_first_phase import (
    RunSourceIngestionFirstPhaseCommand,
    RunSourceIngestionFirstPhaseResult,
    RunSourceIngestionFirstPhaseStatus,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_admission import (
    SourceIngestionActor,
    SourceIngestionAdmissionStatus,
)
from src.contexts.knowledge_workbench.document_segmentation.domain import (
    DocumentSegmentationBudget,
    SegmentationModelBudgetProfile,
    SegmentationPromptProfile,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.interfaces.composition import source_ingestion_first_phase as composition
from src.interfaces.composition.source_ingestion_first_phase import (
    SourceIngestionFirstPhaseSegmentationConfig,
    _ProjectAccessAdapter,
    _SourceIngestionFirstPhaseUnitOfWork,
    default_source_ingestion_first_phase_segmentation_config,
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


class FakeTransaction:
    def __init__(self) -> None:
        self.start_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    async def start(self) -> None:
        self.start_count += 1

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


class FakeConnection:
    def __init__(self, transaction: FakeTransaction) -> None:
        self._transaction = transaction
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.fetchrow_results: list[Mapping[str, object] | None] = []
        self.fetch_results: list[list[Mapping[str, object]]] = []
        self.fetchval_results: list[object] = []

    def transaction(self) -> FakeTransaction:
        return self._transaction

    async def execute(self, query: str, *args: object) -> object:
        self.executed.append((query, args))
        return "OK"

    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> Mapping[str, object] | None:
        if self.fetchrow_results:
            return self.fetchrow_results.pop(0)
        return None

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]:
        if self.fetch_results:
            return self.fetch_results.pop(0)
        return []

    async def fetchval(self, query: str, *args: object) -> object:
        if self.fetchval_results:
            return self.fetchval_results.pop(0)
        return False


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.acquire_count = 0
        self.released_connections: list[FakeConnection] = []

    async def acquire(self) -> FakeConnection:
        self.acquire_count += 1
        return self.connection

    async def release(self, connection: FakeConnection) -> None:
        self.released_connections.append(connection)


class FakeSourceRepository:
    constructed_with: list[FakeConnection] = []

    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        FakeSourceRepository.constructed_with.append(connection)


class FakeSagaRepository:
    constructed_with: list[FakeConnection] = []

    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        FakeSagaRepository.constructed_with.append(connection)


class FakeDocumentPersister:
    constructed_uows: list[_SourceIngestionFirstPhaseUnitOfWork] = []

    def __init__(self, *, unit_of_work: _SourceIngestionFirstPhaseUnitOfWork) -> None:
        self.unit_of_work = unit_of_work
        FakeDocumentPersister.constructed_uows.append(unit_of_work)


class FakeSourceUnitCreator:
    constructed_uows: list[_SourceIngestionFirstPhaseUnitOfWork] = []

    def __init__(self, *, unit_of_work: _SourceIngestionFirstPhaseUnitOfWork) -> None:
        self.unit_of_work = unit_of_work
        FakeSourceUnitCreator.constructed_uows.append(unit_of_work)


class FakeInnerRunner:
    should_fail = False
    calls: list[RunSourceIngestionFirstPhaseCommand] = []

    def __init__(
        self,
        *,
        starter: object,
        document_persister: object,
        source_unit_creator: object,
    ) -> None:
        self.starter = starter
        self.document_persister = document_persister
        self.source_unit_creator = source_unit_creator

    async def execute(
        self,
        command: RunSourceIngestionFirstPhaseCommand,
    ) -> RunSourceIngestionFirstPhaseResult:
        FakeInnerRunner.calls.append(command)
        if FakeInnerRunner.should_fail:
            raise RuntimeError("first phase failed")
        return RunSourceIngestionFirstPhaseResult(
            status=RunSourceIngestionFirstPhaseStatus.COMPLETED,
            admission_status=SourceIngestionAdmissionStatus.ALLOWED,
            workflow_run_id="knowledge-extraction:source-document:project-1:abc",
            source_document_ref="source-document:project-1:abc",
            source_unit_count=3,
        )


def _custom_segmentation_budget() -> DocumentSegmentationBudget:
    return DocumentSegmentationBudget(
        prompt=SegmentationPromptProfile(
            prompt_name="custom_prompt",
            prompt_token_count=3,
        ),
        model=SegmentationModelBudgetProfile(
            profile_name="custom_primary_model",
            max_request_input_tokens=55,
            reserved_output_tokens=5,
        ),
    )


def _reset_fake_classes() -> None:
    FakeSourceRepository.constructed_with = []
    FakeSagaRepository.constructed_with = []
    FakeDocumentPersister.constructed_uows = []
    FakeSourceUnitCreator.constructed_uows = []
    FakeInnerRunner.should_fail = False
    FakeInnerRunner.calls = []


def _user_repo() -> UserRepository:
    return cast(UserRepository, object())


def _command(
    *,
    segmentation_budget: DocumentSegmentationBudget | None = None,
) -> RunSourceIngestionFirstPhaseCommand:
    return RunSourceIngestionFirstPhaseCommand(
        project_id="project-1",
        actor=SourceIngestionActor(actor_user_id="owner-1"),
        original_filename="knowledge.md",
        source_format=SourceFormat.MARKDOWN,
        content_bytes=b"# Knowledge",
        raw_text="# Knowledge\n\nText",
        occurred_at=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
        segmentation_budget=segmentation_budget,
    )


def _patch_transactional_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_fake_classes()
    monkeypatch.setattr(
        composition,
        "PostgresSourceManagementRepository",
        FakeSourceRepository,
    )
    monkeypatch.setattr(
        composition,
        "PostgresKnowledgeExtractionSagaStateRepository",
        FakeSagaRepository,
    )
    monkeypatch.setattr(
        composition,
        "PersistAcceptedSourceIngestionPlan",
        FakeDocumentPersister,
    )
    monkeypatch.setattr(
        composition,
        "CreateSourceUnitsForIngestion",
        FakeSourceUnitCreator,
    )
    monkeypatch.setattr(
        composition,
        "RunSourceIngestionFirstPhase",
        FakeInnerRunner,
    )


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


@pytest.mark.asyncio
async def test_factory_runner_commits_and_releases_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transactional_dependencies(monkeypatch)
    transaction = FakeTransaction()
    connection = FakeConnection(transaction)
    pool = FakePool(connection)

    runner = make_source_ingestion_first_phase(
        pool=pool,
        project_repo=ProjectMemberRoleRepo(role="owner"),
        user_repo=_user_repo(),
    )
    result = await runner.execute(_command())

    assert result.status is RunSourceIngestionFirstPhaseStatus.COMPLETED
    assert transaction.start_count == 1
    assert transaction.commit_count == 1
    assert transaction.rollback_count == 0
    assert pool.released_connections == [connection]
    assert FakeSourceRepository.constructed_with == [connection]
    assert FakeSagaRepository.constructed_with == [connection]


@pytest.mark.asyncio
async def test_factory_runner_rollbacks_and_releases_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transactional_dependencies(monkeypatch)
    FakeInnerRunner.should_fail = True
    transaction = FakeTransaction()
    connection = FakeConnection(transaction)
    pool = FakePool(connection)

    runner = make_source_ingestion_first_phase(
        pool=pool,
        project_repo=ProjectMemberRoleRepo(role="owner"),
        user_repo=_user_repo(),
    )

    with pytest.raises(RuntimeError, match="first phase failed"):
        await runner.execute(_command())

    assert transaction.start_count == 1
    assert transaction.commit_count == 0
    assert transaction.rollback_count == 1
    assert pool.released_connections == [connection]


@pytest.mark.asyncio
async def test_lower_use_cases_receive_shared_unit_of_work_repositories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transactional_dependencies(monkeypatch)
    transaction = FakeTransaction()
    connection = FakeConnection(transaction)
    pool = FakePool(connection)

    runner = make_source_ingestion_first_phase(
        pool=pool,
        project_repo=ProjectMemberRoleRepo(role="owner"),
        user_repo=_user_repo(),
    )
    await runner.execute(_command())

    assert len(FakeDocumentPersister.constructed_uows) == 1
    assert len(FakeSourceUnitCreator.constructed_uows) == 1
    assert (
        FakeDocumentPersister.constructed_uows[0]
        is FakeSourceUnitCreator.constructed_uows[0]
    )

    unit_of_work = FakeDocumentPersister.constructed_uows[0]
    assert isinstance(unit_of_work.source_management, FakeSourceRepository)
    assert isinstance(unit_of_work.saga_state, FakeSagaRepository)
    assert unit_of_work.source_management.connection is connection
    assert unit_of_work.saga_state.connection is connection


def test_source_ingestion_first_phase_composition_source_guard() -> None:
    source = "src/interfaces/composition/source_ingestion_first_phase.py"
    text = __import__("pathlib").Path(source).read_text(encoding="utf-8")

    required_markers = [
        "transaction",
        "commit",
        "rollback",
        "release",
        "PostgresSourceManagementRepository",
        "PostgresKnowledgeExtractionSagaStateRepository",
        "make_source_ingestion_first_phase",
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


def test_segmentation_config_converts_to_document_segmentation_budget() -> None:
    config = SourceIngestionFirstPhaseSegmentationConfig(
        prompt_name="custom_prompt",
        prompt_token_count=12,
        primary_model_profile_name="custom_primary_model",
        max_request_input_tokens=100,
        reserved_output_tokens=20,
    )

    budget = config.to_document_segmentation_budget()

    assert budget.prompt.prompt_name == "custom_prompt"
    assert budget.prompt.prompt_token_count == 12
    assert budget.model.profile_name == "custom_primary_model"
    assert budget.model.max_request_input_tokens == 100
    assert budget.model.reserved_output_tokens == 20
    assert budget.max_source_segment_tokens == 68


def test_default_segmentation_config_is_request_budget_without_provider_names() -> None:
    config = default_source_ingestion_first_phase_segmentation_config()
    budget = config.to_document_segmentation_budget()

    assert budget.prompt.prompt_name == "draft_observation_extraction"
    assert budget.prompt.prompt_token_count == 2_000
    assert budget.model.profile_name == "primary_model"
    assert budget.model.max_request_input_tokens == 6_000
    assert budget.model.reserved_output_tokens == 1_000
    assert budget.max_source_segment_tokens == 3_000


@pytest.mark.asyncio
async def test_factory_runner_injects_default_segmentation_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transactional_dependencies(monkeypatch)
    transaction = FakeTransaction()
    connection = FakeConnection(transaction)
    pool = FakePool(connection)

    runner = make_source_ingestion_first_phase(
        pool=pool,
        project_repo=ProjectMemberRoleRepo(role="owner"),
        user_repo=_user_repo(),
    )
    await runner.execute(_command())

    assert len(FakeInnerRunner.calls) == 1
    budget = FakeInnerRunner.calls[0].segmentation_budget
    assert budget is not None
    assert budget.prompt.prompt_name == "draft_observation_extraction"
    assert budget.model.profile_name == "primary_model"


@pytest.mark.asyncio
async def test_explicit_command_budget_overrides_factory_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transactional_dependencies(monkeypatch)
    transaction = FakeTransaction()
    connection = FakeConnection(transaction)
    pool = FakePool(connection)
    custom_budget = _custom_segmentation_budget()

    runner = make_source_ingestion_first_phase(
        pool=pool,
        project_repo=ProjectMemberRoleRepo(role="owner"),
        user_repo=_user_repo(),
    )
    await runner.execute(_command(segmentation_budget=custom_budget))

    assert len(FakeInnerRunner.calls) == 1
    assert FakeInnerRunner.calls[0].segmentation_budget is custom_budget


def test_invalid_segmentation_config_is_rejected() -> None:
    with pytest.raises(ValueError, match="prompt_name must be non-empty"):
        SourceIngestionFirstPhaseSegmentationConfig(
            prompt_name=" ",
            prompt_token_count=0,
            primary_model_profile_name="primary_model",
            max_request_input_tokens=10,
            reserved_output_tokens=1,
        )

    with pytest.raises(ValueError, match="prompt_token_count must be >= 0"):
        SourceIngestionFirstPhaseSegmentationConfig(
            prompt_name="prompt",
            prompt_token_count=-1,
            primary_model_profile_name="primary_model",
            max_request_input_tokens=10,
            reserved_output_tokens=1,
        )

    with pytest.raises(ValueError, match="primary_model_profile_name must be"):
        SourceIngestionFirstPhaseSegmentationConfig(
            prompt_name="prompt",
            prompt_token_count=0,
            primary_model_profile_name=" ",
            max_request_input_tokens=10,
            reserved_output_tokens=1,
        )

    with pytest.raises(ValueError, match="must be < max_request_input_tokens"):
        SourceIngestionFirstPhaseSegmentationConfig(
            prompt_name="prompt",
            prompt_token_count=9,
            primary_model_profile_name="primary_model",
            max_request_input_tokens=10,
            reserved_output_tokens=1,
        )


def test_composition_segmentation_budget_source_guard() -> None:
    source = Path(
        "src/interfaces/composition/source_ingestion_first_phase.py"
    ).read_text(encoding="utf-8")

    required_markers = [
        "SourceIngestionFirstPhaseSegmentationConfig",
        "default_source_ingestion_first_phase_segmentation_config",
        "to_document_segmentation_budget",
        "SegmentationPromptProfile",
        "SegmentationModelBudgetProfile",
        "replace",
    ]
    forbidden_markers = [
        "qwen",
        "Qwen",
        "Groq",
        "context_window_tokens",
        "ModelProfile",
        "RateLimitProfile",
        "src.contexts.llm_runtime",
        "capacity_runtime",
        "execution_runtime",
        "artifact_runtime",
        "DraftObservationExtractionSchedulingReconciler",
        "PROMPT_A_WORK_SCHEDULED",
        "worker_loop",
        "JobDispatcher",
        "queue",
    ]

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source
