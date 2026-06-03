from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from src.application.workbench_observability.evidence_trace import (
    WorkbenchEvidenceTraceNotFoundError,
    WorkbenchEvidenceTraceReadService,
)
from src.application.workbench_observability.import_quality import (
    WorkbenchImportQualityNotFoundError,
    WorkbenchImportQualityReadService,
)
from src.application.workbench_observability.progress import (
    WorkbenchProgressNotFoundError,
    WorkbenchProgressReadService,
)
from src.application.workbench_observability.surface_cards import (
    WorkbenchSurfaceCardsNotFoundError,
    WorkbenchSurfaceCardsReadService,
)
from src.application.workbench_observability.tombstone import (
    is_deleted_workbench_document,
)


DELETED_DOCUMENT = {
    "project_id": "project-1",
    "document_id": "document-1",
    "file_name": "faq.md",
    "status": "deleted",
    "deleted_at": "2026-05-31T12:00:00+00:00",
}


class DeletedProgressQuery:
    async def fetch_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None:
        del project_id, document_id
        return DELETED_DOCUMENT

    async def fetch_latest_processing_run(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None:
        raise AssertionError("deleted document must stop before loading run")

    async def fetch_section_status_counts(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, int]:
        raise AssertionError("deleted document must stop before loading sections")

    async def fetch_node_runs(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError("deleted document must stop before loading node runs")


class DeletedEvidenceTraceQuery:
    async def get_evidence_trace_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None:
        del project_id, document_id
        return DELETED_DOCUMENT

    async def list_evidence_trace_sections(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError("deleted document must stop before evidence sections")

    async def list_evidence_trace_findings(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError("deleted document must stop before evidence findings")

    async def list_evidence_trace_canonical_facts(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError("deleted document must stop before canonical facts")

    async def list_evidence_trace_surfaces(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError("deleted document must stop before surfaces")


class DeletedSurfaceCardsQuery:
    async def get_surface_cards_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None:
        del project_id, document_id
        return DELETED_DOCUMENT

    async def list_workbench_surface_cards(
        self,
        *,
        project_id: str,
        document_id: str,
        limit: int,
        offset: int,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError("deleted document must stop before surface cards")


class DeletedImportQualityQuery:
    async def get_import_quality_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None:
        del project_id, document_id
        return DELETED_DOCUMENT

    async def list_import_quality_sections(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError("deleted document must stop before import sections")

    async def list_import_quality_findings(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError("deleted document must stop before import findings")

    async def list_import_quality_canonical_facts(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError("deleted document must stop before import registry")

    async def list_import_quality_surfaces(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError("deleted document must stop before import surfaces")

    async def list_import_quality_node_runs(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError("deleted document must stop before import node runs")


def test_deleted_tombstone_helper_accepts_status_or_deleted_at() -> None:
    assert is_deleted_workbench_document({"status": "deleted"}) is True
    assert (
        is_deleted_workbench_document({"status": "processed", "deleted_at": "x"})
        is True
    )
    assert (
        is_deleted_workbench_document({"status": "processed", "deleted_at": None})
        is False
    )


@pytest.mark.asyncio
async def test_progress_read_side_treats_deleted_document_as_not_found() -> None:
    with pytest.raises(WorkbenchProgressNotFoundError):
        await WorkbenchProgressReadService(DeletedProgressQuery()).get_progress(
            project_id="project-1",
            document_id="document-1",
        )


@pytest.mark.asyncio
async def test_evidence_trace_read_side_treats_deleted_document_as_not_found() -> None:
    with pytest.raises(WorkbenchEvidenceTraceNotFoundError):
        await WorkbenchEvidenceTraceReadService(
            DeletedEvidenceTraceQuery()
        ).fetch_document_evidence_trace(
            project_id="project-1",
            document_id="document-1",
        )


@pytest.mark.asyncio
async def test_surface_cards_read_side_treats_deleted_document_as_not_found() -> None:
    with pytest.raises(WorkbenchSurfaceCardsNotFoundError):
        await WorkbenchSurfaceCardsReadService(
            DeletedSurfaceCardsQuery()
        ).fetch_document_surface_cards(
            project_id="project-1",
            document_id="document-1",
            limit=100,
            offset=0,
        )


@pytest.mark.asyncio
async def test_import_quality_read_side_treats_deleted_document_as_not_found() -> None:
    with pytest.raises(WorkbenchImportQualityNotFoundError):
        await WorkbenchImportQualityReadService(
            DeletedImportQualityQuery()
        ).fetch_import_quality_report(
            project_id="project-1",
            document_id="document-1",
        )
