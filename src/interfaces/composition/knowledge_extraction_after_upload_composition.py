from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import asyncpg

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
    LlmAttemptCapacityObservationRepositoryPort,
)
from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.execution_runtime.application.use_cases.record_work_item_attempt_outcome import (
    RecordWorkItemAttemptOutcome,
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
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt import (
    ExecutePreparedLlmDispatchAttempt,
    ExecutePreparedLlmDispatchAttemptCommand,
    ExecutePreparedLlmDispatchAttemptResult,
)
from src.interfaces.composition.knowledge_extraction_workflow_after_upload import (
    RunKnowledgeExtractionWorkflowAfterUpload,
)
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    AsyncPool,
    PrepareLlmDispatchBatch,
)
from src.interfaces.composition.source_ingestion_first_phase import (
    make_source_ingestion_first_phase,
)


@dataclass(frozen=True, slots=True)
class _NoopLlmAttemptCapacityObservationRepository(
    LlmAttemptCapacityObservationRepositoryPort,
):
    """Explicit temporary capacity sink.

    There is no Postgres capacity-observation adapter in main yet. The after-upload
    composition still injects a concrete port so ExecuteClaimBuilderSection is not
    blocked by missing dependencies when tests provide an LLM executor. Once
    capacity_runtime grows a persistence adapter, this is the single composition
    point to replace.
    """

    async def record_observation(
        self,
        observation: LlmAttemptCapacityObservation,
    ) -> None:
        del observation


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
                return await ExecutePreparedLlmDispatchAttempt(
                    dispatch_repository=PostgresReadWorkItemAttemptDispatchRepository(
                        asyncpg_connection,
                    ),
                    llm_executor=self.llm_executor,
                    outcome_recorder=RecordWorkItemAttemptOutcome(
                        repository=PostgresWorkItemAttemptOutcomeRepository(
                            asyncpg_connection,
                        ),
                    ),
                ).execute(command)
        finally:
            await self.pool.release(connection)


def make_knowledge_extraction_workflow_after_upload(
    *,
    pool: AsyncPool,
    project_repo: object,
    user_repo: UserRepository,
    llm_executor: LlmDispatchExecutorPort | None = None,
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

    if llm_executor is None:
        return RunKnowledgeExtractionWorkflowAfterUpload(
            source_ingestion_runner=source_ingestion_runner,
            pool=pool,
            claim_builder_output_validation_policy=claim_builder_output_validation_policy,
        )

    route_catalog = default_groq_llm_model_route_catalog()

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
        ),
        execute_prepared_llm_dispatch_attempt=(
            _TransactionalExecutePreparedLlmDispatchAttempt(
                pool=pool,
                llm_executor=llm_executor,
            )
        ),
        capacity_observation_repository=_NoopLlmAttemptCapacityObservationRepository(),
        claim_builder_output_validation_policy=claim_builder_output_validation_policy,
    )
