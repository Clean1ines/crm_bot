from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.domain.project_plane.knowledge_workbench import (
    FactRegistry,
    FactRegistryStatus,
)
from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


@dataclass(slots=True)
class CapturingConnection:
    execute_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append((" ".join(query.lower().split()), args))
        return "INSERT 0 1"

    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> Mapping[str, object] | None:
        raise AssertionError(f"unexpected fetchrow: {query} {args}")

    async def fetch(
        self,
        query: str,
        *args: object,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError(f"unexpected fetch: {query} {args}")


def _registry() -> FactRegistry:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return FactRegistry(
        registry_id="registry-1",
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        processing_run_id="run-1",
        status=FactRegistryStatus.BUILDING,
        version=1,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_create_fact_registry_inserts_parent_registry_id_before_snapshot_fk_can_reference_it() -> (
    None
):
    connection = CapturingConnection()
    repository = KnowledgeWorkbenchRepository(connection)

    await repository.create_fact_registry(_registry())

    assert len(connection.execute_calls) == 1
    query, args = connection.execute_calls[0]

    assert "insert into knowledge_workbench_fact_registries" in query
    assert "registry_id" in query
    assert "fact_registry_id" not in query
    assert "on conflict (registry_id) do update set" in query

    assert args[0] == "registry-1"
    assert args[1] == "00000000-0000-0000-0000-000000000001"
    assert args[2] == "document-1"
    assert args[3] == "run-1"
    assert args[4] == "building"
