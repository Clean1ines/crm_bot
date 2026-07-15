from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, cast

import asyncpg

from src.contexts.embedding_runtime.infrastructure.composition.embedding_generation_provider_factory import (
    make_embedding_generation_port,
)
from src.contexts.embedding_runtime.infrastructure.config.embedding_runtime_settings import (
    load_embedding_runtime_settings,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_scheduling_repository import (
    PostgresWorkItemSchedulingRepository,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalSummary,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.promoted_question_runtime_embedding_text_builder import (
    PromotedQuestionRuntimeEmbeddingTextBuilder,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_promotion_application_policy import (
    WorkbenchRagEvalPromotionApplicationPolicy,
    WorkbenchRagEvalPromotionApplicationPolicyConfig,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotion import (
    ApplyWorkbenchRagEvalPromotion,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotions_batch import (
    ApplyWorkbenchRagEvalPromotionsBatch,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.accept_workbench_rag_eval_embedding_revision import (
    AcceptWorkbenchRagEvalEmbeddingRevision,
    AcceptWorkbenchRagEvalEmbeddingRevisionCommand,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.approve_workbench_rag_eval_promotion_candidate import (
    ApproveWorkbenchRagEvalPromotionCandidate,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.reject_workbench_rag_eval_promotion_candidate import (
    RejectWorkbenchRagEvalPromotionCandidate,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.rollback_workbench_rag_eval_embedding_revision import (
    RollbackWorkbenchRagEvalEmbeddingRevision,
    RollbackWorkbenchRagEvalEmbeddingRevisionCommand,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WorkbenchRagEvalEmbeddingRevisionReadModel,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
    WorkbenchRagEvalWorkflowEventType,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.projectors.workbench_rag_eval_frontend_workflow_event_projector import (
    WorkbenchRagEvalFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.infrastructure.postgres.postgres_frontend_workflow_event_repository import (
    PostgresFrontendWorkflowEventRepository,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.start_workbench_rag_eval_v2 import (
    StartWorkbenchRagEvalV2,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.llm.workbench_rag_eval_question_generator import (
    WorkbenchRagEvalQuestionGenerator,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    model_budget_profile_for_ref,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
    PostgresWorkbenchRagEvalRepository,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_command_log_repository import (
    PostgresCommandLogRepository,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)
from src.interfaces.composition.workbench_rag_eval_workflow_runtime import (
    WorkbenchRagEvalWorkflowRuntimeComposition,
    make_workbench_rag_eval_workflow_runtime,
)
from src.interfaces.realtime.collecting_frontend_workflow_event_repository import (
    CollectingFrontendWorkflowEventRepository,
)
from src.interfaces.realtime.redis_frontend_workflow_event_bus import (
    publish_frontend_workflow_events,
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
                question_generator = (
                    WorkbenchRagEvalQuestionGenerator.from_prompt_file()
                )
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
                    question_generator=question_generator,
                    question_generation_model_profile=(
                        model_budget_profile_for_ref(
                            question_generator.generation_model
                        )
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


def make_apply_workbench_rag_eval_promotions_batch(
    *,
    pool: object,
) -> ApplyWorkbenchRagEvalPromotionsBatch:
    embedding_settings = load_embedding_runtime_settings()
    if embedding_settings.vector_dimensions != WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS:
        raise RuntimeError(
            "Workbench runtime embedding dimensions must equal "
            f"{WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS}; got "
            f"{embedding_settings.vector_dimensions}"
        )
    return ApplyWorkbenchRagEvalPromotionsBatch(
        rag_eval_repository=PostgresWorkbenchRagEvalRepository(pool),
        embedding_generation_port=make_embedding_generation_port(embedding_settings),
        embedding_model_id=embedding_settings.local_model,
        embedding_dimensions=embedding_settings.vector_dimensions,
        embedding_text_builder=PromotedQuestionRuntimeEmbeddingTextBuilder(),
        application_policy=WorkbenchRagEvalPromotionApplicationPolicy(
            config=WorkbenchRagEvalPromotionApplicationPolicyConfig()
        ),
    )


def make_apply_workbench_rag_eval_promotion(
    *,
    pool: object,
) -> ApplyWorkbenchRagEvalPromotion:
    return ApplyWorkbenchRagEvalPromotion(
        grouped_application=make_apply_workbench_rag_eval_promotions_batch(pool=pool),
    )


def make_accept_workbench_rag_eval_embedding_revision(
    *,
    pool: object,
) -> AcceptWorkbenchRagEvalEmbeddingRevisionComposition:
    return AcceptWorkbenchRagEvalEmbeddingRevisionComposition(
        pool=cast(AsyncPool, pool)
    )


def make_rollback_workbench_rag_eval_embedding_revision(
    *,
    pool: object,
) -> RollbackWorkbenchRagEvalEmbeddingRevisionComposition:
    return RollbackWorkbenchRagEvalEmbeddingRevisionComposition(
        pool=cast(AsyncPool, pool)
    )


@dataclass(frozen=True, slots=True)
class AcceptWorkbenchRagEvalEmbeddingRevisionComposition:
    pool: AsyncPool

    async def execute(
        self,
        command: AcceptWorkbenchRagEvalEmbeddingRevisionCommand,
    ) -> WorkbenchRagEvalEmbeddingRevisionReadModel:
        connection = await self.pool.acquire()
        frontend_event_repository: CollectingFrontendWorkflowEventRepository | None = (
            None
        )
        try:
            async with connection.transaction():
                asyncpg_connection = cast(asyncpg.Connection, connection)
                frontend_event_repository = CollectingFrontendWorkflowEventRepository(
                    PostgresFrontendWorkflowEventRepository(asyncpg_connection)
                )
                revision = await AcceptWorkbenchRagEvalEmbeddingRevision(
                    repository=PostgresWorkbenchRagEvalRepository(asyncpg_connection),
                ).execute(command)
                await _project_revision_event(
                    connection=asyncpg_connection,
                    revision=revision,
                    event_type=(
                        WorkbenchRagEvalWorkflowEventType.EMBEDDING_REVISION_ACCEPTED.value
                    ),
                    frontend_event_repository=frontend_event_repository,
                )
            if frontend_event_repository is not None:
                await publish_frontend_workflow_events(
                    frontend_event_repository.persisted_events()
                )
            return revision
        finally:
            await self.pool.release(connection)


@dataclass(frozen=True, slots=True)
class RollbackWorkbenchRagEvalEmbeddingRevisionComposition:
    pool: AsyncPool

    async def execute(
        self,
        command: RollbackWorkbenchRagEvalEmbeddingRevisionCommand,
    ) -> WorkbenchRagEvalEmbeddingRevisionReadModel:
        connection = await self.pool.acquire()
        frontend_event_repository: CollectingFrontendWorkflowEventRepository | None = (
            None
        )
        try:
            async with connection.transaction():
                asyncpg_connection = cast(asyncpg.Connection, connection)
                frontend_event_repository = CollectingFrontendWorkflowEventRepository(
                    PostgresFrontendWorkflowEventRepository(asyncpg_connection)
                )
                revision = await RollbackWorkbenchRagEvalEmbeddingRevision(
                    repository=PostgresWorkbenchRagEvalRepository(asyncpg_connection),
                ).execute(command)
                await _project_revision_event(
                    connection=asyncpg_connection,
                    revision=revision,
                    event_type=(
                        WorkbenchRagEvalWorkflowEventType.EMBEDDING_REVISION_ROLLED_BACK.value
                    ),
                    frontend_event_repository=frontend_event_repository,
                )
            if frontend_event_repository is not None:
                await publish_frontend_workflow_events(
                    frontend_event_repository.persisted_events()
                )
            return revision
        finally:
            await self.pool.release(connection)


async def _project_revision_event(
    *,
    connection: asyncpg.Connection,
    revision: WorkbenchRagEvalEmbeddingRevisionReadModel,
    event_type: str,
    frontend_event_repository: CollectingFrontendWorkflowEventRepository,
) -> None:
    event = await _load_revision_workflow_event(
        connection=connection,
        workflow_run_id=revision.source_rag_eval_run_id,
        event_type=event_type,
        revision_id=revision.revision_id,
    )
    if event is None:
        return
    await ProjectFrontendWorkflowEvent(
        projector=WorkbenchRagEvalFrontendWorkflowEventProjector(),
        repository=frontend_event_repository,
    ).execute(event)


async def _load_revision_workflow_event(
    *,
    connection: asyncpg.Connection,
    workflow_run_id: str,
    event_type: str,
    revision_id: str,
) -> WorkflowEvent | None:
    event_id = f"workflow-event:{workflow_run_id}:{event_type}:{revision_id}"
    row = await connection.fetchrow(
        """
        SELECT
            event_id,
            event_type,
            workflow_run_id,
            payload,
            occurred_at,
            causation_command_id,
            correlation_id,
            sequence_number
        FROM workflow_runtime_outbox_events
        WHERE event_id = $1
        """,
        event_id,
    )
    if row is None:
        return None
    payload = _json_payload(row.get("payload"))
    causation_command_id = row.get("causation_command_id")
    return WorkflowEvent(
        event_id=WorkflowEventId(_text_from_row(row, "event_id")),
        event_type=_text_from_row(row, "event_type"),
        workflow_run_id=_text_from_row(row, "workflow_run_id"),
        payload=payload,
        occurred_at=_datetime_from_row(row, "occurred_at"),
        causation_command_id=WorkflowCommandId(causation_command_id)
        if isinstance(causation_command_id, str) and causation_command_id.strip()
        else None,
        correlation_id=_optional_text_from_row(row, "correlation_id"),
        sequence_number=_int_from_row(row, "sequence_number"),
    )


def _json_payload(value: object) -> Mapping[str, object]:
    if isinstance(value, str):
        decoded = json.loads(value)
        if isinstance(decoded, Mapping):
            return decoded
    if isinstance(value, Mapping):
        return value
    raise TypeError("workflow event payload must be a JSON object")


def _text_from_row(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value.strip()


def _optional_text_from_row(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be text or None")
    stripped = value.strip()
    return stripped or None


def _int_from_row(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value


def _datetime_from_row(row: Mapping[str, object], key: str) -> datetime:
    value = row.get(key)
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime")
    return value
