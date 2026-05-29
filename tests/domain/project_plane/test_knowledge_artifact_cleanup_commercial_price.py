from __future__ import annotations

import pytest

from src.domain.project_plane.knowledge_artifact_cleanup import (
    DELETE_DOCUMENT_TABLES,
    KnowledgeArtifactCleanupCounters,
    build_document_delete_cleanup_plan,
)
from src.infrastructure.db.repositories.knowledge_artifact_cleanup import (
    cleanup_document_artifacts,
)


PROJECT_ID = "11111111-1111-1111-1111-111111111111"
DOCUMENT_ID = "22222222-2222-2222-2222-222222222222"


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> bool:
        return False


class FakeConnection:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def execute(self, query: str, *args: object) -> str:
        self.queries.append(query)
        if "commercial_price_" in query:
            return "DELETE 1"
        if query.lstrip().upper().startswith("UPDATE"):
            return "UPDATE 0"
        return "DELETE 0"


class FakeAcquire:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn

    async def __aenter__(self) -> FakeConnection:
        return self.conn

    async def __aexit__(self, *args: object) -> bool:
        return False


class FakePool:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self.conn)


def test_document_delete_plan_declares_commercial_price_tables() -> None:
    plan = build_document_delete_cleanup_plan(
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
    )

    assert "commercial_price_documents" in DELETE_DOCUMENT_TABLES
    assert "commercial_price_source_units" in DELETE_DOCUMENT_TABLES
    assert "commercial_price_source_rows" in DELETE_DOCUMENT_TABLES
    assert "commercial_price_facts" in DELETE_DOCUMENT_TABLES
    assert "commercial_price_documents" in plan.affected_tables


def test_commercial_price_counter_is_included_in_total() -> None:
    counters = KnowledgeArtifactCleanupCounters(commercial_price_artifacts=4)

    assert counters.total == 4


@pytest.mark.asyncio
async def test_cleanup_document_artifacts_deletes_commercial_price_artifacts() -> None:
    conn = FakeConnection()
    plan = build_document_delete_cleanup_plan(
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
    )

    result = await cleanup_document_artifacts(
        FakePool(conn),
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        plan=plan,
    )

    executed_sql = "\n".join(conn.queries)
    assert "DELETE FROM commercial_price_facts" in executed_sql
    assert "DELETE FROM commercial_price_source_rows" in executed_sql
    assert "DELETE FROM commercial_price_source_units" in executed_sql
    assert "DELETE FROM commercial_price_documents" in executed_sql
    assert result.counters.commercial_price_artifacts == 4
