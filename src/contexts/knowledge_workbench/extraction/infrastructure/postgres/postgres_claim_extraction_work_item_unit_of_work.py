from __future__ import annotations

from typing import Protocol

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import (
    WorkItemAttempt,
)
from src.contexts.knowledge_workbench.extraction.application.ports.claim_extraction_work_item_unit_of_work_port import (
    ClaimExtractionRuntimeEvent,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.claim_extraction_runtime_mappers import (
    map_domain_event_to_outbox_row,
    map_llm_attempt_to_row,
    map_llm_task_to_row,
    map_pipeline_artifact_lineage_to_rows,
    map_pipeline_artifact_to_row,
    map_work_item_attempt_to_row,
    map_work_item_to_row,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask


class AsyncTransactionLike(Protocol):
    async def start(self) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class AsyncConnectionLike(Protocol):
    def transaction(self) -> AsyncTransactionLike: ...

    async def execute(self, query: str, *args: object) -> object: ...


class UnitOfWorkClosedError(RuntimeError):
    """Raised when a closed Unit of Work is used again."""


class PostgresClaimExtractionWorkItemUnitOfWork:
    """Async PostgreSQL Unit of Work for one claim-extraction work item.

    The application port is synchronous today; this infrastructure adapter is
    intentionally async because asyncpg connections are async. It is not wired
    into production process managers in this patch.
    """

    def __init__(self, connection: AsyncConnectionLike) -> None:
        self._connection = connection
        self._transaction: AsyncTransactionLike | None = None
        self._closed = False

    async def save_work_item(self, item: WorkItem) -> None:
        await self._ensure_open_transaction()
        row = map_work_item_to_row(item)
        await self._connection.execute(
            """
            INSERT INTO execution_work_items (
                work_item_id,
                work_kind,
                status,
                attempt_count,
                leased_by,
                lease_token,
                lease_expires_at,
                next_attempt_at,
                last_error_kind,
                created_at,
                updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (work_item_id) DO UPDATE SET
                work_kind = EXCLUDED.work_kind,
                status = EXCLUDED.status,
                attempt_count = EXCLUDED.attempt_count,
                leased_by = EXCLUDED.leased_by,
                lease_token = EXCLUDED.lease_token,
                lease_expires_at = EXCLUDED.lease_expires_at,
                next_attempt_at = EXCLUDED.next_attempt_at,
                last_error_kind = EXCLUDED.last_error_kind,
                updated_at = EXCLUDED.updated_at
            """,
            *row.args(),
        )

    async def save_work_item_attempt(self, attempt: WorkItemAttempt) -> None:
        await self._ensure_open_transaction()
        row = map_work_item_attempt_to_row(attempt)
        await self._connection.execute(
            """
            INSERT INTO execution_work_item_attempts (
                attempt_id,
                work_item_id,
                attempt_number,
                started_at,
                finished_at,
                outcome_status,
                error_kind,
                created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (attempt_id) DO UPDATE SET
                work_item_id = EXCLUDED.work_item_id,
                attempt_number = EXCLUDED.attempt_number,
                started_at = EXCLUDED.started_at,
                finished_at = EXCLUDED.finished_at,
                outcome_status = EXCLUDED.outcome_status,
                error_kind = EXCLUDED.error_kind
            """,
            *row.args(),
        )

    async def save_llm_task(self, task: LlmTask) -> None:
        await self._ensure_open_transaction()
        row = map_llm_task_to_row(task)
        await self._connection.execute(
            """
            INSERT INTO llm_tasks (
                task_id,
                prompt_id,
                prompt_version,
                input_ref,
                output_contract_ref,
                status,
                attempt_count,
                selected_provider_id,
                selected_model_id,
                selected_account_ref,
                wait_until,
                last_error_kind,
                created_at,
                updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT (task_id) DO UPDATE SET
                prompt_id = EXCLUDED.prompt_id,
                prompt_version = EXCLUDED.prompt_version,
                input_ref = EXCLUDED.input_ref,
                output_contract_ref = EXCLUDED.output_contract_ref,
                status = EXCLUDED.status,
                attempt_count = EXCLUDED.attempt_count,
                selected_provider_id = EXCLUDED.selected_provider_id,
                selected_model_id = EXCLUDED.selected_model_id,
                selected_account_ref = EXCLUDED.selected_account_ref,
                wait_until = EXCLUDED.wait_until,
                last_error_kind = EXCLUDED.last_error_kind,
                updated_at = EXCLUDED.updated_at
            """,
            *row.args(),
        )

    async def save_llm_attempt(self, attempt: LlmAttempt) -> None:
        await self._ensure_open_transaction()
        row = map_llm_attempt_to_row(attempt)
        await self._connection.execute(
            """
            INSERT INTO llm_attempts (
                attempt_id,
                task_id,
                attempt_number,
                provider_id,
                model_id,
                account_ref,
                started_at,
                finished_at,
                input_tokens,
                output_tokens,
                error_kind,
                created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (attempt_id) DO UPDATE SET
                task_id = EXCLUDED.task_id,
                attempt_number = EXCLUDED.attempt_number,
                provider_id = EXCLUDED.provider_id,
                model_id = EXCLUDED.model_id,
                account_ref = EXCLUDED.account_ref,
                started_at = EXCLUDED.started_at,
                finished_at = EXCLUDED.finished_at,
                input_tokens = EXCLUDED.input_tokens,
                output_tokens = EXCLUDED.output_tokens,
                error_kind = EXCLUDED.error_kind
            """,
            *row.args(),
        )

    async def save_artifact(self, artifact: PipelineArtifact) -> None:
        await self._ensure_open_transaction()
        row = map_pipeline_artifact_to_row(artifact)
        await self._connection.execute(
            """
            INSERT INTO pipeline_artifacts (
                artifact_ref,
                artifact_kind,
                status,
                visibility,
                retention_policy_kind,
                payload,
                created_at,
                updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (artifact_ref) DO UPDATE SET
                artifact_kind = EXCLUDED.artifact_kind,
                status = EXCLUDED.status,
                visibility = EXCLUDED.visibility,
                retention_policy_kind = EXCLUDED.retention_policy_kind,
                payload = EXCLUDED.payload,
                updated_at = EXCLUDED.updated_at
            """,
            *row.args(),
        )

        for lineage_row in map_pipeline_artifact_lineage_to_rows(artifact):
            await self._connection.execute(
                """
                INSERT INTO pipeline_artifact_lineage (
                    artifact_ref,
                    parent_artifact_ref
                )
                VALUES ($1, $2)
                ON CONFLICT (artifact_ref, parent_artifact_ref) DO NOTHING
                """,
                *lineage_row.args(),
            )

    async def append_event(self, event: ClaimExtractionRuntimeEvent) -> None:
        await self._ensure_open_transaction()
        row = map_domain_event_to_outbox_row(event)
        await self._connection.execute(
            """
            INSERT INTO outbox_events (
                event_id,
                event_type,
                aggregate_ref,
                payload,
                occurred_at,
                created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            *row.args(),
        )

    async def commit(self) -> None:
        if self._closed:
            raise UnitOfWorkClosedError("Claim extraction UnitOfWork is already closed")

        if self._transaction is None:
            self._closed = True
            return

        try:
            await self._transaction.commit()
        except Exception:
            await self._transaction.rollback()
            self._closed = True
            raise

        self._closed = True

    async def rollback(self) -> None:
        if self._closed:
            raise UnitOfWorkClosedError("Claim extraction UnitOfWork is already closed")

        if self._transaction is not None:
            await self._transaction.rollback()

        self._closed = True

    async def _ensure_open_transaction(self) -> None:
        if self._closed:
            raise UnitOfWorkClosedError("Claim extraction UnitOfWork is already closed")

        if self._transaction is None:
            self._transaction = self._connection.transaction()
            await self._transaction.start()
