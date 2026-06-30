from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from src.interfaces.composition.knowledge_extraction_workflow_runtime_pump import (
    DueKnowledgeExtractionWorkflow,
)


class DueWorkflowConnectionLike(Protocol):
    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]: ...


class PostgresDueKnowledgeExtractionWorkflowReader:
    """Find workflow runs that have at least one durable command due now."""

    def __init__(self, connection: DueWorkflowConnectionLike) -> None:
        self._connection = connection

    async def list_due_workflows(
        self,
        *,
        limit: int,
    ) -> tuple[DueKnowledgeExtractionWorkflow, ...]:
        if not isinstance(limit, int):
            raise TypeError("limit must be int")
        if limit <= 0:
            raise ValueError("limit must be > 0")

        rows = await self._connection.fetch(
            """
            SELECT
                run.project_id,
                command.workflow_run_id
            FROM workflow_runtime_command_log AS command
            JOIN knowledge_extraction_workflow_runs AS run
              ON run.workflow_run_id = command.workflow_run_id
            WHERE command.status = 'PENDING'
              AND command.run_after <= NOW()
            GROUP BY run.project_id, command.workflow_run_id
            ORDER BY MIN(command.run_after), command.workflow_run_id
            LIMIT $1
            """,
            limit,
        )
        return tuple(
            DueKnowledgeExtractionWorkflow(
                project_id=_required_text(row, "project_id"),
                workflow_run_id=_required_text(row, "workflow_run_id"),
            )
            for row in rows
        )


def _required_text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value
