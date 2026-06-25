from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Protocol, cast

import asyncpg

from src.contexts.capacity_admission_queue.application.build_capacity_admission_projection_candidates import (
    CapacityAdmissionLaneTarget,
)
from src.contexts.capacity_admission_queue.application.capacity_admission_lane_target_resolver import (
    CapacityAdmissionLaneTargetRegistry,
)
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
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutorPort,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    default_groq_llm_model_route_catalog,
)
from src.contexts.llm_runtime.infrastructure.config.llm_runtime_settings import (
    LlmRuntimeSettings,
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
from src.interfaces.composition.source_ingestion_first_phase import (
    make_source_ingestion_first_phase,
)


class AsyncPool(Protocol):
    async def acquire(self) -> asyncpg.Connection: ...

    async def release(self, connection: asyncpg.Connection) -> None: ...


@dataclass(frozen=True, slots=True)
class _TransactionalExecutePreparedLlmDispatchAttempt:
    pool: AsyncPool
    llm_executor: LlmDispatchExecutorPort

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
                return await PostgresWorkItemAttemptOutcomeRepository(
                    cast(asyncpg.Connection, connection),
                ).complete_work_item_after_domain_apply(
                    work_item_id=work_item_id,
                    lease_token=lease_token,
                )
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
    _ = LlmRuntimeSettings.from_env_mapping(
        os.environ,
    ).to_groq_env_config()

    return RunKnowledgeExtractionWorkflowAfterUpload(
        source_ingestion_runner=source_ingestion_runner,
        pool=pool,
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
