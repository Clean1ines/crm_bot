from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.domain.project_plane.knowledge_workbench import FactRegistryStatus
from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


@dataclass(slots=True)
class CapturingConnection:
    fetchrow_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    row: Mapping[str, object] | None = None

    async def execute(self, query: str, *args: object) -> str:
        raise AssertionError(f"unexpected execute: {query} {args}")

    async def fetch(
        self,
        query: str,
        *args: object,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError(f"unexpected fetch: {query} {args}")

    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> Mapping[str, object] | None:
        self.fetchrow_calls.append((" ".join(query.lower().split()), args))
        return self.row


@pytest.mark.asyncio
async def test_get_fact_registry_for_run_reads_current_registry_id_parent_row() -> None:
    now = datetime(2026, 6, 4, tzinfo=timezone.utc)
    connection = CapturingConnection(
        row={
            "registry_id": "registry-1",
            "project_id": "00000000-0000-0000-0000-000000000001",
            "document_id": "document-1",
            "processing_run_id": "run-1",
            "status": "building",
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
    )
    repository = KnowledgeWorkbenchRepository(connection)

    registry = await repository.get_fact_registry_for_run(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        processing_run_id="run-1",
    )

    assert registry is not None
    assert registry.registry_id == "registry-1"
    assert registry.status is FactRegistryStatus.BUILDING
    assert registry.version == 1

    assert len(connection.fetchrow_calls) == 1
    query, args = connection.fetchrow_calls[0]
    assert "from knowledge_workbench_fact_registries" in query
    assert "registry_id" in query
    assert "fact_registry_id" not in query
    assert "processing_run_id = $3" in query
    assert args == (
        "00000000-0000-0000-0000-000000000001",
        "document-1",
        "run-1",
    )


@pytest.mark.asyncio
async def test_get_fact_registry_for_run_returns_none_when_parent_row_missing() -> None:
    repository = KnowledgeWorkbenchRepository(CapturingConnection(row=None))

    registry = await repository.get_fact_registry_for_run(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        processing_run_id="run-1",
    )

    assert registry is None
