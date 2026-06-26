from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Protocol, cast

import asyncpg

from src.contexts.capacity_admission_queue.application.build_capacity_admission_projection_candidates import (
    CapacityAdmissionLaneTarget,
)
from src.contexts.capacity_admission_queue.application.capacity_admission_lane_target_resolver import (
    CapacityAdmissionLaneTargetResolverPort,
)
from src.contexts.capacity_admission_queue.application.ports.capacity_admission_projection_writer_port import (
    CapacityAdmissionProjectionWriterPort,
)
from src.contexts.capacity_admission_queue.infrastructure.postgres.postgres_capacity_admission_projection_lifecycle_synchronizer import (
    PostgresCapacityAdmissionProjectionLifecycleSynchronizer,
)
from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservationRepositoryPort,
)
from src.contexts.capacity_runtime.infrastructure.postgres.postgres_llm_attempt_capacity_observation_repository import (
    PostgresLlmAttemptCapacityObservationRepository,
)
from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressReadRepositoryPort,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_progress_read_repository import (
    PostgresWorkItemProgressReadRepository,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_scheduling_repository import (
    PostgresWorkItemSchedulingRepository,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_split_supersede_repository import (
    PostgresWorkItemSplitSupersedeRepository,
)
from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationPort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_embedding_persistence_port import (
    DraftClaimEmbeddingPersistencePort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_embedding_read_repository_port import (
    DraftClaimEmbeddingReadRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_embedding_repository import (
    DraftClaimEmbeddingConnectionLike,
    PostgresDraftClaimEmbeddingRepository,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_plan_repository_port import (
    DraftClaimCompactionPlanRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStateRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_compaction_plan_repository import (
    DraftClaimCompactionPlanConnectionLike,
    PostgresDraftClaimCompactionPlanRepository,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_compaction_reduction_state_repository import (
    DraftClaimCompactionReductionStateConnectionLike,
    PostgresDraftClaimCompactionReductionStateRepository,
)
from src.contexts.knowledge_workbench.curation.infrastructure.postgres.postgres_draft_claim_curation_workspace_repository import (
    DraftClaimCurationWorkspaceConnectionLike,
    PostgresDraftClaimCurationWorkspaceRepository,
)
from src.contexts.knowledge_workbench.curation.infrastructure.postgres.postgres_draft_claim_curation_publication_repository import (
    PostgresDraftClaimCurationPublicationRepository,
)
from src.contexts.knowledge_workbench.infrastructure.postgres.postgres_knowledge_extraction_saga_state_repository import (
    PostgresKnowledgeExtractionSagaStateRepository,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_builder_retry_action_read_repository import (
    PostgresClaimBuilderRetryActionReadRepository,
)
from src.contexts.knowledge_workbench.application.sagas.drain_knowledge_extraction_workflow_commands import (
    DrainKnowledgeExtractionWorkflowCommands,
    DrainKnowledgeExtractionWorkflowCommandsCommand,
    DrainKnowledgeExtractionWorkflowCommandsResult,
)
from src.contexts.knowledge_workbench.application.sagas.handle_execute_claim_builder_section_command import (
    ExecutePreparedLlmDispatchAttemptPort,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_output_validation_policy import (
    ClaimBuilderOutputValidationPolicy,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_output_validator import (
    DraftClaimCompactionOutputValidator,
)
from src.contexts.knowledge_workbench.extraction.application.ports.validated_draft_claim_observation_persistence_port import (
    PersistValidatedDraftClaimObservationsPort,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_validated_draft_claim_observation_persistence import (
    PostgresValidatedDraftClaimObservationPersistence,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_observation_read_repository import (
    DraftClaimObservationReadConnectionLike,
    PostgresDraftClaimObservationReadRepository,
)
from src.contexts.knowledge_workbench.application.sagas.run_source_ingestion_first_phase import (
    RunSourceIngestionFirstPhaseCommand,
    RunSourceIngestionFirstPhaseResult,
    RunSourceIngestionFirstPhaseStatus,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_admission import (
    SourceIngestionAdmissionStatus,
)
from src.contexts.knowledge_workbench.source_management.infrastructure.postgres.postgres_source_management_repository import (
    PostgresSourceManagementRepository,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_workflow_runtime_unit_of_work import (
    PostgresWorkflowRuntimeUnitOfWork,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelRouteCatalog,
)
from src.interfaces.composition.knowledge_extraction_workflow_resume import (
    _capacity_admission_projection_writer_for_transaction,
    _capacity_window_admission_pass_for_transaction,
)
from src.contexts.knowledge_workbench.observability.application.projectors.knowledge_extraction_frontend_workflow_event_projector import (
    KnowledgeExtractionFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
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


LOGGER = logging.getLogger(__name__)


class SourceIngestionFirstPhaseRunnerPort(Protocol):
    async def execute(
        self,
        command: RunSourceIngestionFirstPhaseCommand,
    ) -> RunSourceIngestionFirstPhaseResult: ...


class _AsyncDrainPoolLike(Protocol):
    async def acquire(self) -> object: ...

    async def release(self, connection: object) -> None: ...


@dataclass(frozen=True, slots=True)
class RunKnowledgeExtractionWorkflowAfterUploadCommand:
    source_ingestion_command: RunSourceIngestionFirstPhaseCommand
    max_drain_commands: int = 10

    def __post_init__(self) -> None:
        if not isinstance(
            self.source_ingestion_command,
            RunSourceIngestionFirstPhaseCommand,
        ):
            raise TypeError(
                "source_ingestion_command must be RunSourceIngestionFirstPhaseCommand"
            )
        if not isinstance(self.max_drain_commands, int):
            raise TypeError("max_drain_commands must be int")
        if self.max_drain_commands <= 0:
            raise ValueError("max_drain_commands must be > 0")


@dataclass(frozen=True, slots=True)
class RunKnowledgeExtractionWorkflowAfterUploadResult:
    workflow_run_id: str
    source_ingestion_completed: bool
    drained_inspected_count: int
    drained_dispatched_count: int
    blocked_command_type: str | None
    blocked_reason: str | None
    source_document_ref: str | None = None
    source_unit_count: int = 0
    source_ingestion_admission_status: SourceIngestionAdmissionStatus | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_run_id, str):
            raise TypeError("workflow_run_id must be str")
        for field_name, value in (
            ("drained_inspected_count", self.drained_inspected_count),
            ("drained_dispatched_count", self.drained_dispatched_count),
        ):
            if not isinstance(value, int):
                raise TypeError(f"{field_name} must be int")
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")
        if (
            self.blocked_command_type is not None
            and not self.blocked_command_type.strip()
        ):
            raise ValueError("blocked_command_type must be non-empty when set")
        if self.blocked_reason is not None and not self.blocked_reason.strip():
            raise ValueError("blocked_reason must be non-empty when set")
        if (
            self.source_document_ref is not None
            and not self.source_document_ref.strip()
        ):
            raise ValueError("source_document_ref must be non-empty when set")
        if not isinstance(self.source_unit_count, int):
            raise TypeError("source_unit_count must be int")
        if self.source_unit_count < 0:
            raise ValueError("source_unit_count must be >= 0")
        if self.source_ingestion_admission_status is not None and not isinstance(
            self.source_ingestion_admission_status,
            SourceIngestionAdmissionStatus,
        ):
            raise TypeError(
                "source_ingestion_admission_status must be SourceIngestionAdmissionStatus"
            )
        if (
            self.source_ingestion_completed is False
            and self.source_ingestion_admission_status is None
        ):
            raise ValueError(
                "rejected source ingestion requires source_ingestion_admission_status"
            )


class RunKnowledgeExtractionWorkflowAfterUpload:
    def __init__(
        self,
        *,
        source_ingestion_runner: SourceIngestionFirstPhaseRunnerPort,
        pool: object,
        execute_prepared_llm_dispatch_attempt: (
            ExecutePreparedLlmDispatchAttemptPort | None
        ) = None,
        capacity_observation_repository: (
            LlmAttemptCapacityObservationRepositoryPort | None
        ) = None,
        work_item_progress_read_repository: (
            WorkItemProgressReadRepositoryPort | None
        ) = None,
        claim_builder_output_validation_policy: (
            ClaimBuilderOutputValidationPolicy | None
        ) = None,
        draft_claim_observation_persistence: (
            PersistValidatedDraftClaimObservationsPort | None
        ) = None,
        draft_claim_embedding_read_repository: (
            DraftClaimEmbeddingReadRepositoryPort | None
        ) = None,
        draft_claim_embedding_persistence: (
            DraftClaimEmbeddingPersistencePort | None
        ) = None,
        embedding_generation_port: EmbeddingGenerationPort | None = None,
        embedding_model_id: str | None = None,
        embedding_dimensions: int | None = None,
        draft_claim_compaction_plan_repository: (
            DraftClaimCompactionPlanRepositoryPort | None
        ) = None,
        draft_claim_compaction_reduction_state_repository: (
            DraftClaimCompactionReductionStateRepositoryPort | None
        ) = None,
        draft_claim_compaction_output_validator: (
            DraftClaimCompactionOutputValidator | None
        ) = None,
        capacity_admission_projection_writer: (
            CapacityAdmissionProjectionWriterPort | None
        ) = None,
        capacity_admission_lane_target: CapacityAdmissionLaneTarget | None = None,
        capacity_admission_lane_target_resolver: (
            CapacityAdmissionLaneTargetResolverPort | None
        ) = None,
        capacity_window_admission_route_catalog: LlmModelRouteCatalog | None = None,
    ) -> None:
        self._source_ingestion_runner = source_ingestion_runner
        self._pool = cast(_AsyncDrainPoolLike, pool)
        self._execute_prepared_llm_dispatch_attempt = (
            execute_prepared_llm_dispatch_attempt
        )
        self._capacity_observation_repository = capacity_observation_repository
        self._work_item_progress_read_repository = work_item_progress_read_repository
        self._claim_builder_output_validation_policy = (
            claim_builder_output_validation_policy
            or ClaimBuilderOutputValidationPolicy()
        )
        self._draft_claim_observation_persistence = draft_claim_observation_persistence
        self._draft_claim_embedding_read_repository = (
            draft_claim_embedding_read_repository
        )
        self._draft_claim_embedding_persistence = draft_claim_embedding_persistence
        self._embedding_generation_port = embedding_generation_port
        self._embedding_model_id = embedding_model_id
        self._embedding_dimensions = embedding_dimensions
        self._draft_claim_compaction_plan_repository = (
            draft_claim_compaction_plan_repository
        )
        self._draft_claim_compaction_reduction_state_repository = (
            draft_claim_compaction_reduction_state_repository
        )
        if capacity_admission_projection_writer is not None and (
            capacity_admission_lane_target is None
            and capacity_admission_lane_target_resolver is None
        ):
            raise ValueError(
                "capacity admission projection writer requires lane target"
            )
        self._draft_claim_compaction_output_validator = (
            draft_claim_compaction_output_validator
            or DraftClaimCompactionOutputValidator()
        )
        self._capacity_admission_projection_writer = (
            capacity_admission_projection_writer
        )
        self._capacity_admission_lane_target = capacity_admission_lane_target
        self._capacity_admission_lane_target_resolver = (
            capacity_admission_lane_target_resolver
        )
        self._capacity_window_admission_route_catalog = (
            capacity_window_admission_route_catalog
        )

    async def execute(
        self,
        command: RunKnowledgeExtractionWorkflowAfterUploadCommand,
    ) -> RunKnowledgeExtractionWorkflowAfterUploadResult:
        source_result = await self._source_ingestion_runner.execute(
            command.source_ingestion_command,
        )
        if source_result.status is not RunSourceIngestionFirstPhaseStatus.COMPLETED:
            return RunKnowledgeExtractionWorkflowAfterUploadResult(
                workflow_run_id=source_result.workflow_run_id or "",
                source_ingestion_completed=False,
                drained_inspected_count=0,
                drained_dispatched_count=0,
                blocked_command_type=None,
                blocked_reason=None,
                source_document_ref=source_result.source_document_ref,
                source_unit_count=source_result.source_unit_count,
                source_ingestion_admission_status=source_result.admission_status,
            )

        workflow_run_id = source_result.workflow_run_id
        if workflow_run_id is None or not workflow_run_id.strip():
            raise ValueError("completed source ingestion must return workflow_run_id")

        try:
            drain_result = await self._drain_until_blocked_or_idle(
                workflow_run_id=workflow_run_id,
                max_drain_commands=command.max_drain_commands,
                source_document_ref=source_result.source_document_ref,
                source_unit_count=source_result.source_unit_count,
                source_ingestion_admission_status=source_result.admission_status,
            )
        except Exception:
            LOGGER.exception(
                "knowledge_extraction_after_upload_drain_failed_after_ingestion",
                extra={
                    "workflow_run_id": workflow_run_id,
                    "source_document_ref": source_result.source_document_ref,
                },
            )
            drain_result = RunKnowledgeExtractionWorkflowAfterUploadResult(
                workflow_run_id=workflow_run_id,
                source_ingestion_completed=True,
                drained_inspected_count=0,
                drained_dispatched_count=0,
                blocked_command_type=None,
                blocked_reason="after_upload_drain_failed",
                source_document_ref=source_result.source_document_ref,
                source_unit_count=source_result.source_unit_count,
                source_ingestion_admission_status=source_result.admission_status,
            )
        return RunKnowledgeExtractionWorkflowAfterUploadResult(
            workflow_run_id=workflow_run_id,
            source_ingestion_completed=True,
            drained_inspected_count=drain_result.drained_inspected_count,
            drained_dispatched_count=drain_result.drained_dispatched_count,
            blocked_command_type=drain_result.blocked_command_type,
            blocked_reason=drain_result.blocked_reason,
            source_document_ref=source_result.source_document_ref,
            source_unit_count=source_result.source_unit_count,
            source_ingestion_admission_status=source_result.admission_status,
        )

    async def _drain_until_blocked_or_idle(
        self,
        *,
        workflow_run_id: str,
        max_drain_commands: int,
        source_document_ref: str | None,
        source_unit_count: int,
        source_ingestion_admission_status: SourceIngestionAdmissionStatus | None,
    ) -> RunKnowledgeExtractionWorkflowAfterUploadResult:
        remaining_commands = max_drain_commands
        inspected_count = 0
        dispatched_count = 0
        blocked_command_type: str | None = None
        blocked_reason: str | None = None

        while remaining_commands > 0:
            drain_result = await self._run_one_drain_transaction(
                workflow_run_id=workflow_run_id,
                max_commands=remaining_commands,
            )
            inspected_count += drain_result.inspected_count
            dispatched_count += drain_result.dispatched_count

            if drain_result.blocked_count > 0:
                blocked_command_type = drain_result.last_blocked_command_type
                blocked_reason = drain_result.last_blocked_reason
                break

            if drain_result.inspected_count == 0 or drain_result.dispatched_count == 0:
                break

            remaining_commands -= drain_result.inspected_count

        return RunKnowledgeExtractionWorkflowAfterUploadResult(
            workflow_run_id=workflow_run_id,
            source_ingestion_completed=True,
            drained_inspected_count=inspected_count,
            drained_dispatched_count=dispatched_count,
            blocked_command_type=blocked_command_type,
            blocked_reason=blocked_reason,
            source_document_ref=source_document_ref,
            source_unit_count=source_unit_count,
            source_ingestion_admission_status=source_ingestion_admission_status,
        )

    async def _run_one_drain_transaction(
        self,
        *,
        workflow_run_id: str,
        max_commands: int,
    ) -> DrainKnowledgeExtractionWorkflowCommandsResult:
        connection = await self._pool.acquire()
        workflow_unit_of_work = PostgresWorkflowRuntimeUnitOfWork(
            cast(asyncpg.Connection, connection),
        )
        await workflow_unit_of_work.start()

        draft_claim_embedding_repository = PostgresDraftClaimEmbeddingRepository(
            cast(DraftClaimEmbeddingConnectionLike, connection),
        )
        draft_claim_compaction_plan_repository = (
            self._draft_claim_compaction_plan_repository
            or PostgresDraftClaimCompactionPlanRepository(
                cast(DraftClaimCompactionPlanConnectionLike, connection)
            )
        )
        draft_claim_compaction_reduction_state_repository = (
            self._draft_claim_compaction_reduction_state_repository
            or PostgresDraftClaimCompactionReductionStateRepository(
                cast(DraftClaimCompactionReductionStateConnectionLike, connection)
            )
        )
        draft_claim_observation_read_repository = (
            PostgresDraftClaimObservationReadRepository(
                cast(DraftClaimObservationReadConnectionLike, connection)
            )
        )
        frontend_event_repository = CollectingFrontendWorkflowEventRepository(
            inner=PostgresFrontendWorkflowEventRepository(
                cast(asyncpg.Connection, connection),
            ),
        )
        frontend_event_projection_writer = ProjectFrontendWorkflowEvent(
            projector=KnowledgeExtractionFrontendWorkflowEventProjector(),
            repository=frontend_event_repository,
        )
        asyncpg_connection = cast(asyncpg.Connection, connection)
        capacity_admission_projection_writer = (
            _capacity_admission_projection_writer_for_transaction(
                connection=asyncpg_connection,
                configured_writer=self._capacity_admission_projection_writer,
                lane_target=self._capacity_admission_lane_target,
                lane_target_resolver=self._capacity_admission_lane_target_resolver,
            )
        )
        capacity_window_admission_pass = (
            _capacity_window_admission_pass_for_transaction(
                connection=asyncpg_connection,
                route_catalog=self._capacity_window_admission_route_catalog,
            )
        )

        try:
            result = await DrainKnowledgeExtractionWorkflowCommands().execute(
                DrainKnowledgeExtractionWorkflowCommandsCommand(
                    workflow_run_id=workflow_run_id,
                    max_commands=max_commands,
                ),
                source_unit_repository=PostgresSourceManagementRepository(
                    cast(asyncpg.Connection, connection),
                ),
                knowledge_unit_of_work=PostgresWorkItemSchedulingRepository(
                    cast(asyncpg.Connection, connection),
                ),
                work_item_split_supersede_repository=(
                    PostgresWorkItemSplitSupersedeRepository(
                        cast(asyncpg.Connection, connection),
                    )
                ),
                capacity_admission_projection_lifecycle_synchronizer=(
                    PostgresCapacityAdmissionProjectionLifecycleSynchronizer(
                        cast(asyncpg.Connection, connection),
                    )
                ),
                capacity_admission_projection_writer=(
                    capacity_admission_projection_writer
                ),
                capacity_admission_lane_target=self._capacity_admission_lane_target,
                capacity_admission_lane_target_resolver=(
                    self._capacity_admission_lane_target_resolver
                ),
                workflow_unit_of_work=workflow_unit_of_work,
                capacity_window_admission_pass=capacity_window_admission_pass,
                execute_prepared_llm_dispatch_attempt=(
                    self._execute_prepared_llm_dispatch_attempt
                ),
                capacity_observation_repository=(
                    self._capacity_observation_repository
                    or PostgresLlmAttemptCapacityObservationRepository(
                        cast(asyncpg.Connection, connection)
                    )
                ),
                work_item_progress_read_repository=(
                    self._work_item_progress_read_repository
                    or PostgresWorkItemProgressReadRepository(
                        cast(asyncpg.Connection, connection)
                    )
                ),
                claim_builder_retry_action_read_repository=(
                    PostgresClaimBuilderRetryActionReadRepository(
                        cast(asyncpg.Connection, connection)
                    )
                ),
                claim_builder_output_validation_policy=(
                    self._claim_builder_output_validation_policy
                ),
                draft_claim_observation_persistence=(
                    self._draft_claim_observation_persistence
                    or PostgresValidatedDraftClaimObservationPersistence(
                        cast(asyncpg.Connection, connection)
                    )
                ),
                draft_claim_observation_read_repository=(
                    draft_claim_observation_read_repository
                ),
                draft_claim_embedding_read_repository=(
                    self._draft_claim_embedding_read_repository
                    or draft_claim_embedding_repository
                ),
                draft_claim_embedding_persistence=(
                    self._draft_claim_embedding_persistence
                    or draft_claim_embedding_repository
                ),
                embedding_generation_port=self._embedding_generation_port,
                embedding_model_id=self._embedding_model_id,
                embedding_dimensions=self._embedding_dimensions,
                draft_claim_compaction_plan_repository=(
                    draft_claim_compaction_plan_repository
                ),
                draft_claim_compaction_reduction_state_repository=(
                    draft_claim_compaction_reduction_state_repository
                ),
                curation_workspace_repository=(
                    PostgresDraftClaimCurationWorkspaceRepository(
                        cast(DraftClaimCurationWorkspaceConnectionLike, connection)
                    )
                ),
                curation_publication_repository=(
                    PostgresDraftClaimCurationPublicationRepository(connection)
                ),
                draft_claim_compaction_output_validator=(
                    self._draft_claim_compaction_output_validator
                ),
                workflow_state_repository=(
                    PostgresKnowledgeExtractionSagaStateRepository(
                        cast(asyncpg.Connection, connection)
                    )
                ),
                frontend_event_projection_writer=frontend_event_projection_writer,
            )
            await workflow_unit_of_work.commit()
            await publish_frontend_workflow_events(
                frontend_event_repository.persisted_events()
            )
            return result
        except Exception:
            await workflow_unit_of_work.rollback()
            raise
        finally:
            await self._pool.release(connection)
