from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import os
from typing import Protocol, cast

import asyncpg

from src.contexts.capacity_admission_queue.application.build_capacity_admission_projection_candidates import (
    CapacityAdmissionLaneTarget,
)
from src.contexts.capacity_admission_queue.application.capacity_admission_lane_target_resolver import (
    CapacityAdmissionLaneTargetRegistry,
)
from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.execution_runtime.application.use_cases.record_work_item_attempt_outcome import (
    RecordWorkItemAttemptOutcome,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationPort,
)
from src.contexts.embedding_runtime.infrastructure.config.embedding_runtime_settings import (
    load_embedding_runtime_settings,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_attempt_dispatch_read_repository import (
    PostgresReadWorkItemAttemptDispatchRepository,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_attempt_outcome_repository import (
    PostgresWorkItemAttemptOutcomeRepository,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_output_validation_policy import (
    ClaimBuilderOutputValidationPolicy,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_output_validator import (
    DraftClaimCompactionOutputValidator,
)
from src.contexts.knowledge_workbench.application.sagas.handle_execute_claim_builder_section_command import (
    ExecutePreparedLlmDispatchAttemptPort,
)
from src.contexts.llm_runtime.application.capacity.project_llm_capacity_to_capacity_runtime import (
    ProjectLlmCapacityToCapacityRuntime,
)
from src.contexts.llm_runtime.application.capacity.select_active_llm_model_capacity import (
    SelectActiveLlmModelCapacity,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutorPort,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    default_groq_llm_model_route_catalog,
)
from src.contexts.llm_runtime.infrastructure.config.llm_runtime_settings import (
    LlmRuntimeSettings,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    build_groq_free_plan_model_profiles,
)
from src.contexts.llm_runtime.infrastructure.postgres.postgres_llm_route_capacity_reservation_repository import (
    PostgresLlmRouteCapacityReservationRepository,
    actual_tokens_from_capacity_observation,
)
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt import (
    ExecutePreparedLlmDispatchAttempt,
    ExecutePreparedLlmDispatchAttemptCommand,
    ExecutePreparedLlmDispatchAttemptResult,
)
from src.interfaces.composition.knowledge_extraction_workflow_after_upload import (
    RunKnowledgeExtractionWorkflowAfterUpload,
)
from src.interfaces.composition.knowledge_extraction_workflow_resume import (
    _sync_capacity_admission_projection_lifecycle,
)
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    PrepareLlmDispatchBatch,
)
from src.interfaces.composition.source_ingestion_first_phase import (
    make_source_ingestion_first_phase,
)


class AsyncPool(Protocol):
    async def acquire(self) -> asyncpg.Connection: ...

    async def release(self, connection: asyncpg.Connection) -> None: ...


@dataclass(frozen=True, slots=True)
class _ConnectionBoundExecutePreparedLlmDispatchAttempt:
    connection: asyncpg.Connection
    llm_executor: LlmDispatchExecutorPort

    async def execute(
        self,
        command: ExecutePreparedLlmDispatchAttemptCommand,
    ) -> ExecutePreparedLlmDispatchAttemptResult:
        outcome_repository = PostgresWorkItemAttemptOutcomeRepository(
            self.connection,
        )
        result = await ExecutePreparedLlmDispatchAttempt(
            dispatch_repository=PostgresReadWorkItemAttemptDispatchRepository(
                self.connection,
            ),
            llm_executor=self.llm_executor,
            outcome_recorder=RecordWorkItemAttemptOutcome(
                repository=outcome_repository,
            ),
            recorded_outcome_reader=outcome_repository,
        ).execute(command)

        actual_tokens = actual_tokens_from_capacity_observation(
            result.llm_result.capacity_observation
        )
        await PostgresLlmRouteCapacityReservationRepository(self.connection).finalize(
            attempt_id=result.dispatch.attempt_id,
            final_status="committed" if actual_tokens is not None else "released",
            actual_tokens=actual_tokens,
            finalized_at=result.llm_result.finished_at,
        )
        await _sync_capacity_admission_projection_lifecycle(
            self.connection,
            work_item=result.outcome_result.work_item,
            changed_at=result.llm_result.finished_at,
        )
        return result

    async def complete_work_item_after_domain_apply(
        self,
        *,
        work_item_id: str,
        lease_token: LeaseToken,
    ) -> object:
        work_item = await PostgresWorkItemAttemptOutcomeRepository(
            self.connection,
        ).complete_work_item_after_domain_apply(
            work_item_id=work_item_id,
            lease_token=lease_token,
        )
        await _sync_capacity_admission_projection_lifecycle(
            self.connection,
            work_item=work_item,
            changed_at=datetime.now(UTC),
        )
        return work_item


@dataclass(frozen=True, slots=True)
class _TransactionalExecutePreparedLlmDispatchAttempt:
    pool: AsyncPool
    llm_executor: LlmDispatchExecutorPort

    def for_connection(
        self,
        connection: asyncpg.Connection,
    ) -> ExecutePreparedLlmDispatchAttemptPort:
        return _ConnectionBoundExecutePreparedLlmDispatchAttempt(
            connection=connection,
            llm_executor=self.llm_executor,
        )

    async def execute(
        self,
        command: ExecutePreparedLlmDispatchAttemptCommand,
    ) -> ExecutePreparedLlmDispatchAttemptResult:
        connection = await self.pool.acquire()
        try:
            async with connection.transaction():
                asyncpg_connection = cast(asyncpg.Connection, connection)
                outcome_repository = PostgresWorkItemAttemptOutcomeRepository(
                    asyncpg_connection,
                )
                result = await ExecutePreparedLlmDispatchAttempt(
                    dispatch_repository=PostgresReadWorkItemAttemptDispatchRepository(
                        asyncpg_connection,
                    ),
                    llm_executor=self.llm_executor,
                    outcome_recorder=RecordWorkItemAttemptOutcome(
                        repository=outcome_repository,
                    ),
                    recorded_outcome_reader=outcome_repository,
                ).execute(command)
                actual_tokens = actual_tokens_from_capacity_observation(
                    result.llm_result.capacity_observation
                )
                await PostgresLlmRouteCapacityReservationRepository(
                    asyncpg_connection
                ).finalize(
                    attempt_id=result.dispatch.attempt_id,
                    final_status="committed"
                    if actual_tokens is not None
                    else "released",
                    actual_tokens=actual_tokens,
                    finalized_at=result.llm_result.finished_at,
                )
                await _sync_capacity_admission_projection_lifecycle(
                    asyncpg_connection,
                    work_item=result.outcome_result.work_item,
                    changed_at=result.llm_result.finished_at,
                )
                return result
        finally:
            await self.pool.release(connection)

    async def complete_work_item_after_domain_apply(
        self,
        *,
        work_item_id: str,
        lease_token: LeaseToken,
    ) -> object:
        connection = await self.pool.acquire()
        try:
            async with connection.transaction():
                asyncpg_connection = cast(asyncpg.Connection, connection)
                work_item = await PostgresWorkItemAttemptOutcomeRepository(
                    asyncpg_connection,
                ).complete_work_item_after_domain_apply(
                    work_item_id=work_item_id,
                    lease_token=lease_token,
                )
                await _sync_capacity_admission_projection_lifecycle(
                    asyncpg_connection,
                    work_item=work_item,
                    changed_at=datetime.now(UTC),
                )
                return work_item
        finally:
            await self.pool.release(connection)


def make_knowledge_extraction_workflow_after_upload(
    *,
    pool: AsyncPool,
    project_repo: object,
    user_repo: UserRepository,
    llm_executor: LlmDispatchExecutorPort | None = None,
    embedding_generation_port: EmbeddingGenerationPort | None = None,
) -> RunKnowledgeExtractionWorkflowAfterUpload:
    """Build the after-upload composition root for the upload → claim-builder path.

    Without an LLM executor, upload remains safe and explicit: it can ingest source
    documents, create source units, schedule claim-builder work, and then return the
    workflow blocker from the drain loop. With an executor, the same factory injects
    the prepare/execute/capacity/validation ports required for the current claim
    builder vertical.
    """

    source_ingestion_runner = make_source_ingestion_first_phase(
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    claim_builder_output_validation_policy = ClaimBuilderOutputValidationPolicy()
    draft_claim_compaction_output_validator = DraftClaimCompactionOutputValidator()
    from src.contexts.embedding_runtime.infrastructure.composition.embedding_generation_provider_factory import (
        make_embedding_generation_port,
    )

    embedding_settings = load_embedding_runtime_settings()
    resolved_embedding_generation_port = (
        embedding_generation_port
        if embedding_generation_port is not None
        else make_embedding_generation_port(embedding_settings)
    )

    if llm_executor is None:
        return RunKnowledgeExtractionWorkflowAfterUpload(
            source_ingestion_runner=source_ingestion_runner,
            pool=pool,
            claim_builder_output_validation_policy=claim_builder_output_validation_policy,
            draft_claim_compaction_output_validator=(
                draft_claim_compaction_output_validator
            ),
            embedding_generation_port=resolved_embedding_generation_port,
            embedding_model_id=embedding_settings.local_model,
            embedding_dimensions=embedding_settings.vector_dimensions,
        )

    route_catalog = default_groq_llm_model_route_catalog()
    groq_env_config = LlmRuntimeSettings.from_env_mapping(
        os.environ,
    ).to_groq_env_config()

    return RunKnowledgeExtractionWorkflowAfterUpload(
        source_ingestion_runner=source_ingestion_runner,
        pool=pool,
        prepare_llm_dispatch_batch=PrepareLlmDispatchBatch(
            pool=pool,
            capacity_policy=CapacityAdmissionPolicy(),
            active_model_capacity_selector=SelectActiveLlmModelCapacity(
                projector=ProjectLlmCapacityToCapacityRuntime(),
            ),
            route_catalog=route_catalog,
            provider_account_refs=tuple(
                account.account_seed.account_ref for account in groq_env_config.accounts
            ),
            model_profiles=build_groq_free_plan_model_profiles(),
        ),
        capacity_admission_lane_target_resolver=CapacityAdmissionLaneTargetRegistry(
            targets_by_work_kind={
                "knowledge_workbench.claim_builder.section_extraction": CapacityAdmissionLaneTarget(
                    provider="groq",
                    account_ref=None,
                    model_ref=route_catalog.primary_model_ref(),
                ),
                "knowledge_workbench.draft_claim_compaction": CapacityAdmissionLaneTarget(
                    provider="groq",
                    account_ref=None,
                    model_ref=route_catalog.highest_input_limit_automatic_route_model_ref(),
                ),
            }
        ),
        execute_prepared_llm_dispatch_attempt=(
            _TransactionalExecutePreparedLlmDispatchAttempt(
                pool=pool,
                llm_executor=llm_executor,
            )
        ),
        capacity_window_admission_route_catalog=route_catalog,
        claim_builder_output_validation_policy=claim_builder_output_validation_policy,
        draft_claim_compaction_output_validator=(
            draft_claim_compaction_output_validator
        ),
        embedding_generation_port=resolved_embedding_generation_port,
        embedding_model_id=embedding_settings.local_model,
        embedding_dimensions=embedding_settings.vector_dimensions,
    )
