from __future__ import annotations

from dataclasses import dataclass
import os
from typing import cast

import asyncpg
from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.execution_runtime.application.use_cases.record_work_item_attempt_outcome import (
    RecordWorkItemAttemptOutcome,
)
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
                return await ExecutePreparedLlmDispatchAttempt(
                    dispatch_repository=PostgresReadWorkItemAttemptDispatchRepository(
                        asyncpg_connection,
                    ),
                    llm_executor=self.llm_executor,
                    outcome_recorder=RecordWorkItemAttemptOutcome(
                        repository=outcome_repository,
                    ),
                    recorded_outcome_reader=outcome_repository,
                ).execute(command)
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
        execute_prepared_llm_dispatch_attempt=(
            _TransactionalExecutePreparedLlmDispatchAttempt(
                pool=pool,
                llm_executor=llm_executor,
            )
        ),
        claim_builder_output_validation_policy=claim_builder_output_validation_policy,
        draft_claim_compaction_output_validator=(
            draft_claim_compaction_output_validator
        ),
        embedding_generation_port=resolved_embedding_generation_port,
        embedding_model_id=embedding_settings.local_model,
        embedding_dimensions=embedding_settings.vector_dimensions,
    )
