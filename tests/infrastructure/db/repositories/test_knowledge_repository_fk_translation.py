from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from types import TracebackType

import asyncpg
import pytest

from src.application.errors import KnowledgeDocumentDeletedDuringProcessingError
from src.infrastructure.db.repositories import knowledge_repository as kr


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        del exc_type, exc, tb
        return False


class FakeConnection:
    def transaction(self) -> FakeTransaction:
        return FakeTransaction()


class FakeAcquire:
    async def __aenter__(self) -> FakeConnection:
        return FakeConnection()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        del exc_type, exc, tb
        return False


class FakePool:
    def acquire(self) -> FakeAcquire:
        return FakeAcquire()


@pytest.mark.asyncio
async def test_add_source_chunks_translates_fk_violation_to_application_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def raise_fk(
        _conn: FakeConnection,
        *,
        project_id: str,
        document_id: str,
        chunks: Sequence[object],
    ) -> int:
        del _conn, project_id, document_id, chunks
        raise asyncpg.ForeignKeyViolationError("document disappeared")

    monkeypatch.setattr(kr, "replace_document_source_chunks", raise_fk)

    repo = kr.KnowledgeRepository(FakePool())

    with pytest.raises(KnowledgeDocumentDeletedDuringProcessingError):
        await repo.add_source_chunks(
            project_id="00000000-0000-0000-0000-000000000001",
            document_id="00000000-0000-0000-0000-000000000002",
            chunks=(object(),),
        )


def test_repository_translates_fk_violations_in_processing_persistence_methods() -> (
    None
):
    source_path = Path(kr.__file__ or "")
    source = source_path.read_text(encoding="utf-8")

    for method in (
        "add_source_chunks",
        "add_answer_candidates",
        "add_candidate_clusters",
        "add_canonical_entries",
        "complete_compiler_run",
    ):
        assert f"async def {method}(" in source

    assert source.count("except asyncpg.ForeignKeyViolationError as exc:") >= 5
    assert "KnowledgeDocumentDeletedDuringProcessingError" in source
    assert "_raise_document_deleted_during_processing(exc)" in source
