from __future__ import annotations

import asyncpg

from src.contexts.workflow_runtime.application.ports.command_log_repository_port import (
    CommandLogRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.event_cursor_repository_port import (
    EventCursorRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.outbox_repository_port import (
    OutboxRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_command_log_repository import (
    PostgresCommandLogRepository,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_event_cursor_repository import (
    PostgresEventCursorRepository,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_outbox_repository import (
    PostgresOutboxRepository,
)


class PostgresWorkflowRuntimeUnitOfWork(WorkflowRuntimeUnitOfWorkPort):
    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection
        self._transaction = connection.transaction()
        self._started = False
        self._closed = False
        self._command_log: PostgresCommandLogRepository | None = None
        self._outbox: PostgresOutboxRepository | None = None
        self._event_cursors: PostgresEventCursorRepository | None = None

    async def start(self) -> None:
        self._ensure_not_closed()
        if not self._started:
            await self._transaction.start()
            self._started = True

    @property
    def command_log(self) -> CommandLogRepositoryPort:
        self._ensure_started()
        if self._command_log is None:
            self._command_log = PostgresCommandLogRepository(self._connection)
        return self._command_log

    @property
    def outbox(self) -> OutboxRepositoryPort:
        self._ensure_started()
        if self._outbox is None:
            self._outbox = PostgresOutboxRepository(self._connection)
        return self._outbox

    @property
    def event_cursors(self) -> EventCursorRepositoryPort:
        self._ensure_started()
        if self._event_cursors is None:
            self._event_cursors = PostgresEventCursorRepository(self._connection)
        return self._event_cursors

    async def commit(self) -> None:
        self._ensure_not_closed()
        if not self._started:
            raise RuntimeError("cannot commit before transaction start")
        await self._transaction.commit()
        self._closed = True

    async def rollback(self) -> None:
        self._ensure_not_closed()
        if self._started:
            await self._transaction.rollback()
        self._closed = True

    def _ensure_started(self) -> None:
        self._ensure_not_closed()
        if not self._started:
            raise RuntimeError(
                "PostgresWorkflowRuntimeUnitOfWork.start() must be awaited before use"
            )

    def _ensure_not_closed(self) -> None:
        if self._closed:
            raise RuntimeError("PostgresWorkflowRuntimeUnitOfWork is already closed")
