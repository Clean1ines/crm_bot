from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence

import pytest

from src.application.workbench_observability.document_list import (
    WorkbenchDocumentListReadService,
)


class FakeDocumentListQuery:
    def __init__(self, rows: Sequence[Mapping[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, int, int]] = []

    async def list_workbench_documents(
        self,
        *,
        project_id: str,
        limit: int,
        offset: int,
    ) -> Sequence[Mapping[str, object]]:
        self.calls.append((project_id, limit, offset))
        return self.rows


def _now() -> datetime:
    return datetime(2026, 5, 31, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_document_list_preserves_old_shape_and_adds_workbench_metadata() -> None:
    query = FakeDocumentListQuery(
        [
            {
                "document_id": "document-1",
                "project_id": "project-1",
                "file_name": "faq.md",
                "source_type": "markdown",
                "file_size_bytes": 42,
                "status": "sectioned",
                "created_at": _now(),
                "updated_at": _now(),
                "deleted_at": None,
                "processing_run_id": "processing-run-1",
                "processing_status": "running",
                "processing_trigger": "fresh_upload",
                "resume_policy": "explicit_user_action",
                "started_at": _now(),
                "finished_at": None,
                "completed_at": None,
                "section_count": 3,
                "processed_section_count": 1,
                "failed_section_count": 1,
                "pending_section_count": 1,
                "canonical_fact_count": 7,
                "runtime_entry_count": 5,
                "registry_retained": True,
                "final_registry_snapshot_id": "registry-snapshot-1",
                "uploaded_by_user_id": "user-1",
                "uploaded_by_actor_type": "web_user",
                "uploaded_by_actor_id": "user-1",
                "trusted_upload": False,
                "last_error_kind": None,
                "last_error_message": None,
                "last_error_at": None,
            }
        ]
    )

    payload = await WorkbenchDocumentListReadService(query).list_documents(
        project_id="project-1",
        limit=50,
        offset=0,
    )

    assert payload["items"] is payload["documents"]
    document = payload["documents"][0]
    assert document["document_id"] == "document-1"
    assert document["file_size_bytes"] == 42
    assert document["processing_run_id"] == "processing-run-1"
    assert document["section_count"] == 3
    assert document["progress"] == {
        "total_sections": 3,
        "processed_sections": 1,
        "failed_sections": 1,
        "pending_sections": 1,
    }
    assert document["canonical_fact_count"] == 7
    assert document["runtime_entry_count"] == 5
    assert document["registry_retained"] is True
    assert document["final_registry_snapshot_id"] == "registry-snapshot-1"
    assert document["result_metrics"] == {
        "canonical_fact_count": 7,
        "runtime_entry_count": 5,
        "registry_retained": True,
        "final_registry_snapshot_id": "registry-snapshot-1",
    }
    assert document["uploaded_by_user_id"] == "user-1"
    assert document["uploaded_by_actor_type"] == "web_user"
    assert query.calls == [("project-1", 50, 0)]


@pytest.mark.asyncio
async def test_document_list_allows_empty_result() -> None:
    query = FakeDocumentListQuery([])

    payload = await WorkbenchDocumentListReadService(query).list_documents(
        project_id="project-1",
        limit=50,
        offset=0,
    )

    assert payload == {"documents": [], "items": []}
