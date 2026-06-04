from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, cast

import pytest

from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


def _workbench_repository(connection: object) -> KnowledgeWorkbenchRepository:
    factory = cast(
        Callable[[object], KnowledgeWorkbenchRepository],
        KnowledgeWorkbenchRepository,
    )
    return factory(connection)


@dataclass(slots=True)
class FakeConnection:
    row: dict[str, object] | None
    queries: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.queries.append((query, args))
        return self.row

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        raise AssertionError("fetch must not be used")

    async def execute(self, query: str, *args: object) -> str:
        raise AssertionError("execute must not be used")


@pytest.mark.asyncio
async def test_has_completed_fact_registry_canonicalization_queries_completed_parsed_prompt_c_artifact() -> (
    None
):
    connection = FakeConnection(row={"completed": True})
    repository = _workbench_repository(connection)

    completed = await repository.has_completed_fact_registry_canonicalization(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
    )

    assert completed is True
    assert len(connection.queries) == 1

    query, args = connection.queries[0]
    normalized = " ".join(query.lower().split())

    assert "select exists" in normalized
    assert (
        "from knowledge_workbench_processing_node_artifacts as artifact" in normalized
    )
    assert "join knowledge_workbench_processing_node_runs as node_run" in normalized
    assert (
        "artifact.metadata ->> 'contract' = 'fact_registry_canonicalization'"
        in normalized
    )
    assert "artifact.artifact_type = 'parsed_llm_output'" in normalized
    assert "node_run.node_name = 'faq_surface_registry_merge'" in normalized
    assert "node_run.status = 'completed'" in normalized
    assert "artifact.section_id is null" in normalized
    assert "node_run.section_id is null" in normalized
    assert args == ("project-1", "document-1", "processing-run-1")


@pytest.mark.asyncio
async def test_has_completed_fact_registry_canonicalization_returns_false_when_marker_absent() -> (
    None
):
    connection = FakeConnection(row={"completed": False})
    repository = _workbench_repository(connection)

    completed = await repository.has_completed_fact_registry_canonicalization(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
    )

    assert completed is False


@pytest.mark.asyncio
async def test_has_completed_fact_registry_canonicalization_returns_false_when_no_row() -> (
    None
):
    connection = FakeConnection(row=None)
    repository = _workbench_repository(connection)

    completed = await repository.has_completed_fact_registry_canonicalization(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
    )

    assert completed is False
