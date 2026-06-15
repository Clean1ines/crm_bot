from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.source_management.domain.entities.source_document import (
    SourceDocument,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.heading_path import (
    HeadingPath,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_kind import (
    SourceUnitKind,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_lineage import (
    SourceUnitLineage,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_text import (
    SourceUnitText,
)
from src.contexts.knowledge_workbench.source_management.infrastructure.postgres.postgres_source_management_repository import (
    PostgresSourceManagementRepository,
)


ROOT = Path(__file__).resolve().parents[6]
ADAPTER = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "source_management"
    / "infrastructure"
    / "postgres"
    / "postgres_source_management_repository.py"
)


def _now() -> datetime:
    return datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)


def _document() -> SourceDocument:
    return SourceDocument(
        SourceDocumentRef("document-1"),
        "project-1",
        SourceFormat.MARKDOWN,
        "sha256:abc",
        _now(),
        "knowledge.md",
    )


def _unit(unit_ref: str, ordinal: int) -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef(unit_ref),
        document_ref=SourceDocumentRef("document-1"),
        unit_kind=SourceUnitKind.SECTION,
        text=SourceUnitText(f"# Section {ordinal}"),
        heading_path=HeadingPath((f"Section {ordinal}",)),
        lineage=SourceUnitLineage(),
        ordinal=ordinal,
        created_at=_now(),
    )


class _FakeConnection:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, object]] = {}
        self.units: dict[str, dict[str, object]] = {}
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        if "FROM source_documents" in query:
            return self.documents.get(_arg_str(args, 0))
        if "FROM source_units" in query:
            return self.units.get(_arg_str(args, 0))
        raise AssertionError(query)

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]:
        if "FROM source_units" not in query:
            raise AssertionError(query)
        document_ref = _arg_str(args, 0)
        rows = [
            row for row in self.units.values() if row["document_ref"] == document_ref
        ]
        return sorted(rows, key=lambda row: _row_int(row, "ordinal"))

    async def execute(self, query: str, *args: object) -> object:
        self.execute_calls.append((query, args))
        if "INSERT INTO source_documents" in query:
            self.documents[_arg_str(args, 0)] = {
                "document_ref": args[0],
                "project_id": args[1],
                "source_format": args[2],
                "content_hash": args[3],
                "original_filename": args[4],
                "created_at": args[5],
            }
            return "OK"
        if "INSERT INTO source_units" in query:
            self.units[_arg_str(args, 0)] = {
                "unit_ref": args[0],
                "document_ref": args[1],
                "unit_kind": args[2],
                "text": args[3],
                "heading_path": args[4],
                "lineage": args[5],
                "ordinal": args[6],
                "created_at": args[7],
            }
            return "OK"
        raise AssertionError(query)


def _arg_str(args: tuple[object, ...], index: int) -> str:
    value = args[index]
    if not isinstance(value, str):
        raise TypeError("expected string argument")
    return value


def _row_int(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if not isinstance(value, int):
        raise TypeError("expected int row value")
    return value


@pytest.mark.asyncio
async def test_saves_and_loads_source_document() -> None:
    connection = _FakeConnection()
    repository = PostgresSourceManagementRepository(connection)
    document = _document()

    await repository.save_source_document(document)
    loaded = await repository.load_source_document(SourceDocumentRef("document-1"))

    assert loaded == document


@pytest.mark.asyncio
async def test_returns_none_for_missing_source_document() -> None:
    repository = PostgresSourceManagementRepository(_FakeConnection())

    assert (
        await repository.load_source_document(SourceDocumentRef("missing-document"))
        is None
    )


@pytest.mark.asyncio
async def test_saves_and_lists_source_units_ordered_by_ordinal() -> None:
    connection = _FakeConnection()
    repository = PostgresSourceManagementRepository(connection)
    second = _unit("document-1.unit.1", 1)
    first = _unit("document-1.unit.0", 0)

    await repository.save_source_units((second, first))
    loaded = await repository.list_source_units_for_document(
        SourceDocumentRef("document-1")
    )

    assert loaded == (first, second)


@pytest.mark.asyncio
async def test_load_source_unit_returns_single_unit_or_none() -> None:
    connection = _FakeConnection()
    repository = PostgresSourceManagementRepository(connection)
    unit = _unit("document-1.unit.0", 0)

    await repository.save_source_units((unit,))

    assert await repository.load_source_unit(SourceUnitRef("document-1.unit.0")) == unit
    assert await repository.load_source_unit(SourceUnitRef("missing-unit")) is None


@pytest.mark.asyncio
async def test_empty_save_source_units_is_no_op() -> None:
    connection = _FakeConnection()
    repository = PostgresSourceManagementRepository(connection)

    await repository.save_source_units(())

    assert connection.execute_calls == []


def test_source_guard() -> None:
    text = ADAPTER.read_text(encoding="utf-8")
    required_markers = (
        "PostgresSourceManagementRepository",
        "AsyncSourceManagementConnectionLike",
        "SourceManagementRepositoryPort",
        "source_documents",
        "source_units",
        "ON CONFLICT",
        "ORDER BY ordinal ASC",
    )
    forbidden_markers = (
        "asyncpg",
        "src.infrastructure",
        "JobDispatcher",
        "worker_loop",
        "outbox_events",
        "published_at",
        "Groq",
        "Qwen",
        "knowledge_workbench_documents",
        "knowledge_workbench_document_sections",
        "knowledge_workbench_processing_runs",
        "SectionBatchQueueItem",
        "workbench_parallel_processing",
        "process_" + "workbench_document",
        "RunClaimExtractionStageAsync",
        "RecordClaimExtractionSuccess",
        "ProcessClaimExtractionWorkItem",
        "KnowledgeExtractionSaga",
    )

    missing = [marker for marker in required_markers if marker not in text]
    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)
