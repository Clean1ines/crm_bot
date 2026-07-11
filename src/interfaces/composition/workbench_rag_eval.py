from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, cast

import asyncpg

from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_scheduling_repository import (
    PostgresWorkItemSchedulingRepository,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_command_log_repository import (
    PostgresCommandLogRepository,
)
from src.contexts.embedding_runtime.infrastructure.config.embedding_runtime_settings import (
    load_embedding_runtime_settings,
)
from src.contexts.embedding_runtime.infrastructure.composition.embedding_generation_provider_factory import (
    make_embedding_generation_port,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.promoted_question_runtime_embedding_text_builder import (
    PromotedQuestionRuntimeEmbeddingTextBuilder,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalSummary,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotions_batch import (
    ApplyWorkbenchRagEvalPromotionsBatch,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotion import (
    ApplyWorkbenchRagEvalPromotion,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.approve_workbench_rag_eval_promotion_candidate import (
    ApproveWorkbenchRagEvalPromotionCandidate,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.reject_workbench_rag_eval_promotion_candidate import (
    RejectWorkbenchRagEvalPromotionCandidate,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.start_workbench_rag_eval_v2 import (
    StartWorkbenchRagEvalV2,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.llm.workbench_rag_eval_question_generator import (
    WorkbenchRagEvalQuestionGenerator,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
    PostgresWorkbenchRagEvalRepository,
)
from src.interfaces.composition.workbench_rag_eval_workflow_runtime import (
    WorkbenchRagEvalWorkflowRuntimeComposition,
    make_workbench_rag_eval_workflow_runtime,
)

__all__ = [
    "WorkbenchRagEvalWorkflowRuntimeComposition",
    "make_workbench_rag_eval_workflow_runtime",
]


class AsyncTransaction(Protocol):
    async def __aenter__(self) -> object: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...


class AsyncConnection(Protocol):
    def transaction(self) -> AsyncTransaction: ...


class AsyncPool(Protocol):
    async def acquire(self) -> AsyncConnection: ...

    async def release(self, connection: AsyncConnection) -> None: ...


@dataclass(frozen=True, slots=True)
class StartWorkbenchRagEvalV2Composition:
    pool: AsyncPool

    async def execute(
        self,
        *,
        project_id: str,
        publication_id: str | None,
        source_document_ref: str | None,
        max_entries: int,
        now: datetime,
    ) -> WorkbenchRagEvalSummary:
        connection = await self.pool.acquire()
        try:
            async with connection.transaction():
                asyncpg_connection = cast(asyncpg.Connection, connection)
                return await StartWorkbenchRagEvalV2(
                    rag_eval_repository=PostgresWorkbenchRagEvalRepository(
                        asyncpg_connection,
                    ),
                    work_item_scheduling_repository=(
                        PostgresWorkItemSchedulingRepository(asyncpg_connection)
                    ),
                    workflow_command_log=PostgresCommandLogRepository(
                        asyncpg_connection
                    ),
                    question_generator=(
                        WorkbenchRagEvalQuestionGenerator.from_prompt_file()
                    ),
                ).execute(
                    project_id=project_id,
                    publication_id=publication_id,
                    source_document_ref=source_document_ref,
                    max_entries=max_entries,
                    now=now,
                )
        finally:
            await self.pool.release(connection)


def make_start_workbench_rag_eval_v2(
    *,
    pool: object,
) -> StartWorkbenchRagEvalV2Composition:
    return StartWorkbenchRagEvalV2Composition(pool=cast(AsyncPool, pool))


def make_approve_workbench_rag_eval_promotion_candidate(
    *,
    pool: object,
) -> ApproveWorkbenchRagEvalPromotionCandidate:
    return ApproveWorkbenchRagEvalPromotionCandidate(
        repository=PostgresWorkbenchRagEvalRepository(pool),
    )


def make_reject_workbench_rag_eval_promotion_candidate(
    *,
    pool: object,
) -> RejectWorkbenchRagEvalPromotionCandidate:
    return RejectWorkbenchRagEvalPromotionCandidate(
        repository=PostgresWorkbenchRagEvalRepository(pool),
    )


def make_apply_workbench_rag_eval_promotion(
    *,
    pool: object,
) -> ApplyWorkbenchRagEvalPromotion:
    embedding_settings = load_embedding_runtime_settings()
    return ApplyWorkbenchRagEvalPromotion(
        rag_eval_repository=PostgresWorkbenchRagEvalRepository(pool),
        embedding_generation_port=make_embedding_generation_port(embedding_settings),
        embedding_model_id=embedding_settings.local_model,
        embedding_dimensions=embedding_settings.vector_dimensions,
        embedding_text_builder=PromotedQuestionRuntimeEmbeddingTextBuilder(),
    )


def make_apply_workbench_rag_eval_promotions_batch(
    *,
    pool: object,
) -> ApplyWorkbenchRagEvalPromotionsBatch:
    embedding_settings = load_embedding_runtime_settings()
    return ApplyWorkbenchRagEvalPromotionsBatch(
        rag_eval_repository=PostgresWorkbenchRagEvalRepository(pool),
        embedding_generation_port=make_embedding_generation_port(embedding_settings),
        embedding_model_id=embedding_settings.local_model,
        embedding_dimensions=embedding_settings.vector_dimensions,
        embedding_text_builder=PromotedQuestionRuntimeEmbeddingTextBuilder(),
    )
