from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import asyncpg
import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_ports import (
    KnowledgeExtractionCommandEmitterPort,
)
from src.contexts.knowledge_workbench.infrastructure.postgres.postgres_knowledge_extraction_saga_reconcile_unit_of_work import (
    PostgresKnowledgeExtractionSagaReconcileUnitOfWork,
)


@dataclass(slots=True)
class FakeTransaction:
    started: bool = False
    committed: bool = False
    rolled_back: bool = False

    async def start(self) -> None:
        self.started = True

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


@dataclass(slots=True)
class FakeConnection:
    transaction_obj: FakeTransaction

    def transaction(self) -> FakeTransaction:
        return self.transaction_obj


class FakeCommandEmitter(KnowledgeExtractionCommandEmitterPort):
    async def emit_command(
        self,
        *,
        command_key: str,
        target_context: str,
        command_kind: str,
        payload: Mapping[str, object],
    ) -> None:
        return None


@pytest.mark.asyncio
async def test_postgres_reconcile_uow_owns_one_transaction() -> None:
    transaction = FakeTransaction()
    unit_of_work = PostgresKnowledgeExtractionSagaReconcileUnitOfWork(
        cast(asyncpg.Connection, FakeConnection(transaction)),
        command_emitter=FakeCommandEmitter(),
    )

    await unit_of_work.start()
    await unit_of_work.commit()

    assert transaction.started
    assert transaction.committed
    assert not transaction.rolled_back


@pytest.mark.asyncio
async def test_postgres_reconcile_uow_rolls_back_started_transaction() -> None:
    transaction = FakeTransaction()
    unit_of_work = PostgresKnowledgeExtractionSagaReconcileUnitOfWork(
        cast(asyncpg.Connection, FakeConnection(transaction)),
        command_emitter=FakeCommandEmitter(),
    )

    await unit_of_work.start()
    await unit_of_work.rollback()

    assert transaction.started
    assert transaction.rolled_back
    assert not transaction.committed


def test_postgres_reconcile_uow_constructs_same_connection_repositories() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/infrastructure/postgres/"
        "postgres_knowledge_extraction_saga_reconcile_unit_of_work.py",
    ).read_text(encoding="utf-8")

    assert "PostgresKnowledgeExtractionSagaStateRepository" in source
    assert "PostgresSourceManagementRepository" in source
    assert "PostgresWorkItemSchedulingRepository" in source
    assert "_transaction = connection.transaction()" in source
    assert "owns_transaction" not in source
