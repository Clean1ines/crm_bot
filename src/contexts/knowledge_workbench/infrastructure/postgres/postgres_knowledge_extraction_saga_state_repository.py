from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from src.contexts.knowledge_workbench.application.sagas import (
    KnowledgeExtractionCommandLogPort,
    KnowledgeExtractionCommandRecord,
    KnowledgeExtractionEventCursorPort,
    KnowledgeExtractionEventCursorRecord,
    KnowledgeExtractionPhaseCheckpoint,
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionPhaseStatus,
    KnowledgeExtractionSagaStateRepositoryPort,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)


class AsyncKnowledgeExtractionSagaConnectionLike(Protocol):
    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> Mapping[str, object] | None: ...

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]: ...

    async def execute(self, query: str, *args: object) -> object: ...

    async def fetchval(self, query: str, *args: object) -> object: ...


class PostgresKnowledgeExtractionSagaStateRepository(
    KnowledgeExtractionSagaStateRepositoryPort,
    KnowledgeExtractionCommandLogPort,
    KnowledgeExtractionEventCursorPort,
):
    def __init__(self, connection: AsyncKnowledgeExtractionSagaConnectionLike) -> None:
        self._connection = connection

    async def load_workflow_state(
        self,
        workflow_run_id: str,
    ) -> KnowledgeExtractionWorkflowState | None:
        workflow_row = await self._connection.fetchrow(
            """
            SELECT
                workflow_run_id,
                project_id,
                source_document_ref,
                status,
                current_phase,
                pause_reason,
                failure_kind,
                failure_message,
                review_status,
                publication_ref,
                cleanup_status,
                created_at,
                updated_at,
                completed_at,
                cancelled_at
            FROM knowledge_extraction_workflow_runs
            WHERE workflow_run_id = $1
            """,
            workflow_run_id,
        )
        if workflow_row is None:
            return None

        checkpoint_rows = await self._connection.fetch(
            """
            SELECT
                workflow_run_id,
                phase_key,
                phase_status,
                expected_count,
                completed_count,
                failed_count,
                blocked_count,
                idempotency_key,
                last_event_ref,
                checkpoint_payload,
                updated_at
            FROM knowledge_extraction_phase_checkpoints
            WHERE workflow_run_id = $1
            ORDER BY updated_at ASC, phase_key ASC
            """,
            workflow_run_id,
        )

        return _workflow_state_from_row(
            workflow_row,
            tuple(_phase_checkpoint_from_row(row) for row in checkpoint_rows),
        )

    async def save_workflow_state(
        self,
        state: KnowledgeExtractionWorkflowState,
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO knowledge_extraction_workflow_runs (
                workflow_run_id,
                project_id,
                source_document_ref,
                status,
                current_phase,
                pause_reason,
                failure_kind,
                failure_message,
                review_status,
                publication_ref,
                cleanup_status,
                created_at,
                updated_at,
                completed_at,
                cancelled_at
            )
            VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15
            )
            ON CONFLICT (workflow_run_id) DO UPDATE SET
                project_id = EXCLUDED.project_id,
                source_document_ref = EXCLUDED.source_document_ref,
                status = EXCLUDED.status,
                current_phase = EXCLUDED.current_phase,
                pause_reason = EXCLUDED.pause_reason,
                failure_kind = EXCLUDED.failure_kind,
                failure_message = EXCLUDED.failure_message,
                review_status = EXCLUDED.review_status,
                publication_ref = EXCLUDED.publication_ref,
                cleanup_status = EXCLUDED.cleanup_status,
                created_at = EXCLUDED.created_at,
                updated_at = EXCLUDED.updated_at,
                completed_at = EXCLUDED.completed_at,
                cancelled_at = EXCLUDED.cancelled_at
            """,
            state.workflow_run_id,
            state.project_id,
            state.source_document_ref,
            state.status.value,
            state.current_phase.value,
            state.pause_reason,
            state.failure_kind,
            state.failure_message,
            state.review_status,
            state.publication_ref,
            state.cleanup_status,
            state.created_at,
            state.updated_at,
            state.completed_at,
            state.cancelled_at,
        )
        await self._connection.execute(
            """
            UPDATE knowledge_workbench_documents
            SET current_processing_run_id = $1,
                status = CASE
                    WHEN $5 = 'PAUSED'
                    THEN 'paused'
                    WHEN $5 = 'CANCELLED'
                    THEN 'cancelled'
                    WHEN $5 = 'FAILED'
                    THEN 'failed'
                    WHEN $5 = 'COMPLETED'
                    THEN CASE
                        WHEN $6 IS NOT NULL
                        THEN 'published'
                        ELSE 'processed'
                    END
                    WHEN $5 = 'WAITING_FOR_REVIEW'
                    THEN 'processed'
                    ELSE 'processing'
                END,
                updated_at = $2
            WHERE document_id = $3
              AND project_id = $4::uuid
              AND deleted_at IS NULL
            """,
            state.workflow_run_id,
            state.updated_at,
            state.source_document_ref,
            state.project_id,
            state.status.value,
            state.publication_ref,
        )

    async def save_phase_checkpoint(
        self,
        checkpoint: KnowledgeExtractionPhaseCheckpoint,
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO knowledge_extraction_phase_checkpoints (
                workflow_run_id,
                phase_key,
                phase_status,
                expected_count,
                completed_count,
                failed_count,
                blocked_count,
                idempotency_key,
                last_event_ref,
                checkpoint_payload,
                updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (workflow_run_id, phase_key) DO UPDATE SET
                phase_status = EXCLUDED.phase_status,
                expected_count = EXCLUDED.expected_count,
                completed_count = EXCLUDED.completed_count,
                failed_count = EXCLUDED.failed_count,
                blocked_count = EXCLUDED.blocked_count,
                idempotency_key = EXCLUDED.idempotency_key,
                last_event_ref = EXCLUDED.last_event_ref,
                checkpoint_payload = EXCLUDED.checkpoint_payload,
                updated_at = EXCLUDED.updated_at
            """,
            checkpoint.workflow_run_id,
            checkpoint.phase_key.value,
            checkpoint.phase_status.value,
            checkpoint.expected_count,
            checkpoint.completed_count,
            checkpoint.failed_count,
            checkpoint.blocked_count,
            checkpoint.idempotency_key,
            checkpoint.last_event_ref,
            json.dumps(dict(checkpoint.checkpoint_payload)),
            checkpoint.updated_at,
        )

    async def command_exists(self, command_key: str) -> bool:
        value = await self._connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM knowledge_extraction_command_log
                WHERE command_key = $1
            )
            """,
            command_key,
        )
        return _bool_value(value, "command_exists")

    async def record_command(
        self,
        command: KnowledgeExtractionCommandRecord,
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO knowledge_extraction_command_log (
                command_key,
                workflow_run_id,
                phase_key,
                target_context,
                command_kind,
                command_payload_hash,
                status,
                emitted_at,
                completed_at,
                result_ref
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (command_key) DO NOTHING
            """,
            command.command_key,
            command.workflow_run_id,
            command.phase_key.value,
            command.target_context,
            command.command_kind,
            command.command_payload_hash,
            command.status,
            command.emitted_at,
            command.completed_at,
            command.result_ref,
        )

    async def event_was_processed(
        self,
        *,
        consumer_name: str,
        event_id: str,
    ) -> bool:
        value = await self._connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM knowledge_extraction_event_cursor
                WHERE consumer_name = $1
                  AND event_id = $2
            )
            """,
            consumer_name,
            event_id,
        )
        return _bool_value(value, "event_was_processed")

    async def record_processed_event(
        self,
        record: KnowledgeExtractionEventCursorRecord,
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO knowledge_extraction_event_cursor (
                consumer_name,
                event_id,
                workflow_run_id,
                event_type,
                processed_at,
                handler_result
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """,
            record.consumer_name,
            record.event_id,
            record.workflow_run_id,
            record.event_type,
            record.processed_at,
            record.handler_result,
        )


def _workflow_state_from_row(
    row: Mapping[str, object],
    checkpoints: tuple[KnowledgeExtractionPhaseCheckpoint, ...],
) -> KnowledgeExtractionWorkflowState:
    return KnowledgeExtractionWorkflowState(
        workflow_run_id=_required_str(row, "workflow_run_id"),
        project_id=_required_str(row, "project_id"),
        source_document_ref=_required_str(row, "source_document_ref"),
        status=KnowledgeExtractionWorkflowStatus(_required_str(row, "status")),
        current_phase=KnowledgeExtractionPhaseKey(_required_str(row, "current_phase")),
        checkpoints=checkpoints,
        pause_reason=_optional_str(row, "pause_reason"),
        failure_kind=_optional_str(row, "failure_kind"),
        failure_message=_optional_str(row, "failure_message"),
        review_status=_optional_str(row, "review_status"),
        publication_ref=_optional_str(row, "publication_ref"),
        cleanup_status=_optional_str(row, "cleanup_status"),
        created_at=_optional_datetime(row, "created_at"),
        updated_at=_optional_datetime(row, "updated_at"),
        completed_at=_optional_datetime(row, "completed_at"),
        cancelled_at=_optional_datetime(row, "cancelled_at"),
    )


def _phase_checkpoint_from_row(
    row: Mapping[str, object],
) -> KnowledgeExtractionPhaseCheckpoint:
    payload = _required_mapping(row, "checkpoint_payload")
    return KnowledgeExtractionPhaseCheckpoint(
        workflow_run_id=_required_str(row, "workflow_run_id"),
        phase_key=KnowledgeExtractionPhaseKey(_required_str(row, "phase_key")),
        phase_status=KnowledgeExtractionPhaseStatus(_required_str(row, "phase_status")),
        expected_count=_required_int(row, "expected_count"),
        completed_count=_required_int(row, "completed_count"),
        failed_count=_required_int(row, "failed_count"),
        blocked_count=_required_int(row, "blocked_count"),
        idempotency_key=_required_str_allow_empty(row, "idempotency_key"),
        last_event_ref=_optional_str(row, "last_event_ref"),
        checkpoint_payload=payload,
        updated_at=_optional_datetime(row, "updated_at"),
    )


def _value(row: Mapping[str, object], key: str) -> object:
    try:
        return row[key]
    except KeyError as exc:
        raise KeyError(f"Missing knowledge extraction saga row column: {key}") from exc


def _required_str(row: Mapping[str, object], key: str) -> str:
    value = _value(row, key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be a non-empty string")
    return value


def _required_str_allow_empty(row: Mapping[str, object], key: str) -> str:
    value = _value(row, key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _optional_str(row: Mapping[str, object], key: str) -> str | None:
    value = _value(row, key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be null or a non-empty string")
    return value


def _required_int(row: Mapping[str, object], key: str) -> int:
    value = _value(row, key)
    if not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value


def _optional_datetime(row: Mapping[str, object], key: str) -> datetime | None:
    value = _value(row, key)
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime or null")
    return value


def _required_mapping(row: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = _value(row, key)
    if isinstance(value, Mapping):
        return value

    if isinstance(value, str):
        try:
            decoded: object = json.loads(value)
        except json.JSONDecodeError as exc:
            raise TypeError(f"{key} must be mapping or JSON object string") from exc

        if not isinstance(decoded, Mapping):
            raise TypeError(f"{key} must decode to mapping")

        normalized: dict[str, object] = {}
        for raw_key, raw_value in decoded.items():
            if not isinstance(raw_key, str):
                raise TypeError(f"{key} JSON object keys must be strings")
            normalized[raw_key] = raw_value
        return normalized

    raise TypeError(f"{key} must be mapping or JSON object string")


def _bool_value(value: object, query_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{query_name} query must return bool")
    return value
