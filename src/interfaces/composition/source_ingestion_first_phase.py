from dataclasses import dataclass, replace
from typing import Protocol, cast, runtime_checkable

from src.contexts.knowledge_workbench.application.sagas.create_source_units_for_ingestion import (
    CreateSourceUnitsForIngestion,
    CreateSourceUnitsForIngestionUnitOfWorkPort,
)
from src.contexts.knowledge_workbench.application.sagas.persist_accepted_source_ingestion_plan import (
    PersistAcceptedSourceIngestionPlan,
    PersistAcceptedSourceIngestionPlanUnitOfWorkPort,
)
from src.contexts.knowledge_workbench.application.sagas.run_source_ingestion_first_phase import (
    RunSourceIngestionFirstPhase,
    RunSourceIngestionFirstPhaseCommand,
    RunSourceIngestionFirstPhaseResult,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_admission import (
    SourceIngestionAdmissionPolicy,
    SourceIngestionProjectAccessPort,
)
from src.contexts.knowledge_workbench.application.sagas.start_source_ingestion_workflow import (
    StartSourceIngestionWorkflow,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_segmentation_profiles import (
    SourceIngestionSegmentationProfile,
    default_source_ingestion_segmentation_profile,
)
from src.contexts.knowledge_workbench.document_segmentation.domain import (
    DocumentSegmentationBudget,
    SegmentationModelBudgetProfile,
    SegmentationPromptProfile,
)
from src.contexts.knowledge_workbench.infrastructure.postgres.postgres_knowledge_extraction_saga_state_repository import (
    AsyncKnowledgeExtractionSagaConnectionLike,
    PostgresKnowledgeExtractionSagaStateRepository,
)
from src.contexts.knowledge_workbench.source_management.infrastructure.postgres.postgres_source_management_repository import (
    AsyncSourceManagementConnectionLike,
    PostgresSourceManagementRepository,
)
from src.infrastructure.db.repositories.user_repository import UserRepository


class SourceIngestionFirstPhaseRunnerPort(Protocol):
    async def execute(
        self,
        command: RunSourceIngestionFirstPhaseCommand,
    ) -> RunSourceIngestionFirstPhaseResult: ...


@dataclass(frozen=True, slots=True)
class SourceIngestionFirstPhaseSegmentationConfig:
    prompt_name: str
    prompt_token_count: int
    primary_model_profile_name: str
    max_request_input_tokens: int
    reserved_output_tokens: int

    def __post_init__(self) -> None:
        if not isinstance(self.prompt_name, str) or not self.prompt_name.strip():
            raise ValueError("prompt_name must be non-empty")
        if not isinstance(self.prompt_token_count, int):
            raise TypeError("prompt_token_count must be int")
        if self.prompt_token_count < 0:
            raise ValueError("prompt_token_count must be >= 0")
        if (
            not isinstance(self.primary_model_profile_name, str)
            or not self.primary_model_profile_name.strip()
        ):
            raise ValueError("primary_model_profile_name must be non-empty")
        if not isinstance(self.max_request_input_tokens, int):
            raise TypeError("max_request_input_tokens must be int")
        if self.max_request_input_tokens <= 0:
            raise ValueError("max_request_input_tokens must be > 0")
        if not isinstance(self.reserved_output_tokens, int):
            raise TypeError("reserved_output_tokens must be int")
        if self.reserved_output_tokens < 0:
            raise ValueError("reserved_output_tokens must be >= 0")
        if (
            self.prompt_token_count + self.reserved_output_tokens
            >= self.max_request_input_tokens
        ):
            raise ValueError(
                "prompt_token_count + reserved_output_tokens must be "
                "< max_request_input_tokens"
            )

    def to_document_segmentation_budget(self) -> DocumentSegmentationBudget:
        return DocumentSegmentationBudget(
            prompt=SegmentationPromptProfile(
                prompt_name=self.prompt_name,
                prompt_token_count=self.prompt_token_count,
            ),
            model=SegmentationModelBudgetProfile(
                profile_name=self.primary_model_profile_name,
                max_request_input_tokens=self.max_request_input_tokens,
                reserved_output_tokens=self.reserved_output_tokens,
            ),
        )


def segmentation_config_from_profile(
    profile: SourceIngestionSegmentationProfile,
) -> SourceIngestionFirstPhaseSegmentationConfig:
    return SourceIngestionFirstPhaseSegmentationConfig(
        prompt_name=profile.prompt.prompt_name,
        prompt_token_count=profile.prompt.prompt_token_count,
        primary_model_profile_name=profile.primary_model.profile_name,
        max_request_input_tokens=profile.primary_model.max_request_input_tokens,
        reserved_output_tokens=profile.primary_model.reserved_output_tokens,
    )


def default_source_ingestion_first_phase_segmentation_config() -> (
    SourceIngestionFirstPhaseSegmentationConfig
):
    return segmentation_config_from_profile(
        default_source_ingestion_segmentation_profile()
    )


class _AsyncTransactionLike(Protocol):
    async def start(self) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class _AsyncSourceIngestionConnectionLike(
    AsyncSourceManagementConnectionLike,
    AsyncKnowledgeExtractionSagaConnectionLike,
    Protocol,
):
    def transaction(self) -> _AsyncTransactionLike: ...


class _AsyncSourceIngestionPoolLike(Protocol):
    async def acquire(self) -> _AsyncSourceIngestionConnectionLike: ...

    async def release(
        self, connection: _AsyncSourceIngestionConnectionLike
    ) -> None: ...


@runtime_checkable
class _ProjectExistsRepository(Protocol):
    async def project_exists(self, project_id: str) -> bool: ...


@runtime_checkable
class _ProjectViewRepository(Protocol):
    async def get_project_view(self, project_id: str) -> object | None: ...


@runtime_checkable
class _ProjectMemberRoleRepository(Protocol):
    async def get_project_member_role(
        self,
        project_id: str,
        user_id: str,
    ) -> str | None: ...


class _ProjectAccessAdapter(SourceIngestionProjectAccessPort):
    def __init__(
        self,
        *,
        project_repo: object,
        user_repo: UserRepository,
    ) -> None:
        self._project_repo = project_repo
        self._user_repo = user_repo

    async def project_exists(self, project_id: str) -> bool:
        if isinstance(self._project_repo, _ProjectExistsRepository):
            return await self._project_repo.project_exists(project_id)

        if isinstance(self._project_repo, _ProjectViewRepository):
            return await self._project_repo.get_project_view(project_id) is not None

        return False

    async def actor_project_role(
        self,
        *,
        project_id: str,
        actor_user_id: str,
    ) -> str | None:
        if not isinstance(self._project_repo, _ProjectMemberRoleRepository):
            return None

        role = await self._project_repo.get_project_member_role(
            project_id,
            actor_user_id,
        )
        if not isinstance(role, str) or not role.strip():
            return None
        return role


class _SourceIngestionFirstPhaseUnitOfWork:
    """Deferred UoW used inside one shared source-ingestion transaction.

    Lower application use cases call commit()/rollback(), but actual database
    transaction lifecycle is owned by _TransactionalSourceIngestionFirstPhaseRunner
    so source document, workflow checkpoints, and source units share one boundary.
    """

    def __init__(
        self,
        *,
        source_management: PostgresSourceManagementRepository,
        saga_state: PostgresKnowledgeExtractionSagaStateRepository,
    ) -> None:
        self.source_management = source_management
        self.saga_state = saga_state
        self.commit_request_count = 0
        self.rollback_request_count = 0

    async def commit(self) -> None:
        self.commit_request_count += 1

    async def rollback(self) -> None:
        self.rollback_request_count += 1


class _TransactionalSourceIngestionFirstPhaseRunner(
    SourceIngestionFirstPhaseRunnerPort
):
    def __init__(
        self,
        *,
        pool: _AsyncSourceIngestionPoolLike,
        starter: StartSourceIngestionWorkflow,
        segmentation_budget: DocumentSegmentationBudget,
    ) -> None:
        self._pool = pool
        self._starter = starter
        self._segmentation_budget = segmentation_budget

    async def execute(
        self,
        command: RunSourceIngestionFirstPhaseCommand,
    ) -> RunSourceIngestionFirstPhaseResult:
        connection = await self._pool.acquire()
        transaction = connection.transaction()
        await transaction.start()

        try:
            source_management = PostgresSourceManagementRepository(connection)
            saga_state = PostgresKnowledgeExtractionSagaStateRepository(connection)
            unit_of_work = _SourceIngestionFirstPhaseUnitOfWork(
                source_management=source_management,
                saga_state=saga_state,
            )

            document_persister = PersistAcceptedSourceIngestionPlan(
                unit_of_work=cast(
                    PersistAcceptedSourceIngestionPlanUnitOfWorkPort,
                    unit_of_work,
                ),
            )
            source_unit_creator = CreateSourceUnitsForIngestion(
                unit_of_work=cast(
                    CreateSourceUnitsForIngestionUnitOfWorkPort,
                    unit_of_work,
                ),
            )
            runner = RunSourceIngestionFirstPhase(
                starter=self._starter,
                document_persister=document_persister,
                source_unit_creator=source_unit_creator,
            )

            effective_command = replace(
                command,
                segmentation_budget=(
                    command.segmentation_budget or self._segmentation_budget
                ),
            )
            result = await runner.execute(effective_command)
            await transaction.commit()
            return result
        except Exception:
            await transaction.rollback()
            raise
        finally:
            await self._pool.release(connection)


def make_source_ingestion_first_phase(
    *,
    pool: object,
    project_repo: object,
    user_repo: UserRepository,
    segmentation_config: SourceIngestionFirstPhaseSegmentationConfig | None = None,
) -> SourceIngestionFirstPhaseRunnerPort:
    project_access = _ProjectAccessAdapter(
        project_repo=project_repo,
        user_repo=user_repo,
    )
    admission_policy = SourceIngestionAdmissionPolicy(project_access=project_access)
    starter = StartSourceIngestionWorkflow(admission_policy=admission_policy)

    effective_segmentation_config = (
        segmentation_config
        or default_source_ingestion_first_phase_segmentation_config()
    )

    return _TransactionalSourceIngestionFirstPhaseRunner(
        pool=cast(_AsyncSourceIngestionPoolLike, pool),
        starter=starter,
        segmentation_budget=effective_segmentation_config.to_document_segmentation_budget(),
    )
