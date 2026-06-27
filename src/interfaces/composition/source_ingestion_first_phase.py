from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from src.contexts.knowledge_workbench.application.sagas.apply_source_ingestion_workflow_effects import (
    ApplySourceIngestionWorkflowEffects,
    ApplySourceIngestionWorkflowEffectsCommand,
)
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
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_token_estimation import (
    RoughWorkbenchTokenEstimator,
    SourceIngestionPromptTokenEstimationService,
    WorkbenchPromptText,
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
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.projectors.source_ingestion_frontend_workflow_event_projector import (
    SourceIngestionFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.infrastructure.postgres.postgres_frontend_workflow_event_repository import (
    PostgresFrontendWorkflowEventRepository,
)
from src.interfaces.realtime.collecting_frontend_workflow_event_repository import (
    CollectingFrontendWorkflowEventRepository,
)
from src.interfaces.realtime.redis_frontend_workflow_event_bus import (
    publish_frontend_workflow_events,
)
from src.contexts.knowledge_workbench.source_management.infrastructure.postgres.postgres_source_management_repository import (
    AsyncSourceManagementConnectionLike,
    PostgresSourceManagementRepository,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_command_log_repository import (
    PostgresCommandLogRepository,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_event_cursor_repository import (
    PostgresEventCursorRepository,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_outbox_repository import (
    PostgresOutboxRepository,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_progress_snapshot_repository import (
    PostgresProgressSnapshotRepository,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_resource_usage_repository import (
    PostgresResourceUsageRepository,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_timeline_repository import (
    PostgresTimelineRepository,
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
    segmentation_input_safety_gap_tokens: int
    char_to_token_multiplier: Decimal

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
        if not isinstance(self.segmentation_input_safety_gap_tokens, int):
            raise TypeError("segmentation_input_safety_gap_tokens must be int")
        if self.segmentation_input_safety_gap_tokens < 0:
            raise ValueError("segmentation_input_safety_gap_tokens must be >= 0")
        if not isinstance(self.char_to_token_multiplier, Decimal):
            raise TypeError("char_to_token_multiplier must be Decimal")
        if self.char_to_token_multiplier <= 0:
            raise ValueError("char_to_token_multiplier must be > 0")
        if (
            self.prompt_token_count + self.segmentation_input_safety_gap_tokens
            >= self.max_request_input_tokens
        ):
            raise ValueError(
                "prompt_token_count + segmentation_input_safety_gap_tokens must be "
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
                segmentation_input_safety_gap_tokens=self.segmentation_input_safety_gap_tokens,
                char_to_token_multiplier=self.char_to_token_multiplier,
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
        segmentation_input_safety_gap_tokens=profile.primary_model.segmentation_input_safety_gap_tokens,
        char_to_token_multiplier=profile.primary_model.char_to_token_multiplier,
    )


def _load_workbench_prompt_text(
    profile: SourceIngestionSegmentationProfile,
    *,
    repo_root: Path | None = None,
) -> WorkbenchPromptText:
    prompt_path = Path(profile.prompt.prompt_path)
    resolved_prompt_path = (
        prompt_path
        if prompt_path.is_absolute()
        else (repo_root or Path.cwd()) / prompt_path
    )
    prompt_text = resolved_prompt_path.read_text(encoding="utf-8")
    return WorkbenchPromptText(
        prompt_name=profile.prompt.prompt_name,
        node_id=profile.prompt.node_id,
        prompt_path=profile.prompt.prompt_path,
        text=prompt_text,
    )


def source_ingestion_segmentation_profile_with_input_tokens(
    *,
    profile: SourceIngestionSegmentationProfile | None = None,
    repo_root: Path | None = None,
) -> SourceIngestionSegmentationProfile:
    base_profile = profile or default_source_ingestion_segmentation_profile()
    prompt_text = _load_workbench_prompt_text(
        base_profile,
        repo_root=repo_root,
    )
    service = SourceIngestionPromptTokenEstimationService(
        token_estimator=RoughWorkbenchTokenEstimator(),
    )
    return service.with_input_tokens(
        profile=base_profile,
        prompt_text=prompt_text,
    )


def default_source_ingestion_first_phase_segmentation_config(
    *,
    repo_root: Path | None = None,
) -> SourceIngestionFirstPhaseSegmentationConfig:
    return segmentation_config_from_profile(
        source_ingestion_segmentation_profile_with_input_tokens(
            repo_root=repo_root,
        )
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


class _WorkflowRuntimeDeferredUnitOfWork(WorkflowRuntimeUnitOfWorkPort):
    """Workflow runtime repositories bound to the outer source-ingestion transaction."""

    def __init__(
        self,
        *,
        command_log: PostgresCommandLogRepository,
        outbox: PostgresOutboxRepository,
        event_cursors: PostgresEventCursorRepository,
        progress_snapshots: PostgresProgressSnapshotRepository,
        timeline: PostgresTimelineRepository,
        resource_usage: PostgresResourceUsageRepository,
    ) -> None:
        self._command_log = command_log
        self._outbox = outbox
        self._event_cursors = event_cursors
        self._progress_snapshots = progress_snapshots
        self._timeline = timeline
        self._resource_usage = resource_usage
        self.commit_request_count = 0
        self.rollback_request_count = 0

    @property
    def command_log(self) -> PostgresCommandLogRepository:
        return self._command_log

    @property
    def outbox(self) -> PostgresOutboxRepository:
        return self._outbox

    @property
    def event_cursors(self) -> PostgresEventCursorRepository:
        return self._event_cursors

    @property
    def progress_snapshots(self) -> PostgresProgressSnapshotRepository:
        return self._progress_snapshots

    @property
    def timeline(self) -> PostgresTimelineRepository:
        return self._timeline

    @property
    def resource_usage(self) -> PostgresResourceUsageRepository:
        return self._resource_usage

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
            workflow_runtime_unit_of_work = _WorkflowRuntimeDeferredUnitOfWork(
                command_log=PostgresCommandLogRepository(connection),
                outbox=PostgresOutboxRepository(connection),
                event_cursors=PostgresEventCursorRepository(connection),
                progress_snapshots=PostgresProgressSnapshotRepository(connection),
                timeline=PostgresTimelineRepository(connection),
                resource_usage=PostgresResourceUsageRepository(connection),
            )
            frontend_event_repository = CollectingFrontendWorkflowEventRepository(
                inner=PostgresFrontendWorkflowEventRepository(connection),
            )
            frontend_event_projection_writer = ProjectFrontendWorkflowEvent(
                projector=SourceIngestionFrontendWorkflowEventProjector(),
                repository=frontend_event_repository,
            )
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
            if result.workflow_effects is not None:
                await ApplySourceIngestionWorkflowEffects().execute(
                    ApplySourceIngestionWorkflowEffectsCommand(
                        effects=result.workflow_effects,
                    ),
                    unit_of_work=workflow_runtime_unit_of_work,
                    frontend_event_projection_writer=(frontend_event_projection_writer),
                )
            await transaction.commit()
            await publish_frontend_workflow_events(
                frontend_event_repository.persisted_events()
            )
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
    repo_root: Path | None = None,
) -> SourceIngestionFirstPhaseRunnerPort:
    project_access = _ProjectAccessAdapter(
        project_repo=project_repo,
        user_repo=user_repo,
    )
    admission_policy = SourceIngestionAdmissionPolicy(project_access=project_access)
    starter = StartSourceIngestionWorkflow(admission_policy=admission_policy)

    effective_segmentation_config = segmentation_config
    if effective_segmentation_config is None:
        effective_segmentation_config = (
            default_source_ingestion_first_phase_segmentation_config(
                repo_root=repo_root,
            )
        )

    return _TransactionalSourceIngestionFirstPhaseRunner(
        pool=cast(_AsyncSourceIngestionPoolLike, pool),
        starter=starter,
        segmentation_budget=effective_segmentation_config.to_document_segmentation_budget(),
    )
