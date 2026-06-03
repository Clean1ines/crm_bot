from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence

import pytest

from src.application.workbench_observability.processing_overview import (
    WorkbenchProcessingOverviewReadService,
)


class FakeProcessingOverviewQuery:
    def __init__(
        self,
        *,
        documents: Sequence[Mapping[str, object]],
        node_runs: Sequence[Mapping[str, object]],
    ) -> None:
        self.documents = documents
        self.node_runs = node_runs
        self.calls: list[str] = []

    async def list_processing_overview_documents(
        self,
        *,
        project_id: str,
    ) -> Sequence[Mapping[str, object]]:
        self.calls.append(f"documents:{project_id}")
        return self.documents

    async def list_processing_overview_node_runs(
        self,
        *,
        project_id: str,
    ) -> Sequence[Mapping[str, object]]:
        self.calls.append(f"node_runs:{project_id}")
        return self.node_runs


def _now() -> datetime:
    return datetime(2026, 5, 31, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_processing_overview_summarizes_workbench_documents_and_node_runs() -> (
    None
):
    query = FakeProcessingOverviewQuery(
        documents=[
            {
                "document_id": "document-1",
                "project_id": "project-1",
                "file_name": "faq.md",
                "source_type": "markdown",
                "file_size_bytes": 42,
                "status": "sectioned",
                "processing_run_id": "run-1",
                "processing_status": "running",
                "processing_trigger": "fresh_upload",
                "resume_policy": None,
                "section_count": 3,
                "processed_section_count": 1,
                "failed_section_count": 0,
                "pending_section_count": 2,
                "created_at": _now(),
                "updated_at": _now(),
                "started_at": _now(),
                "completed_at": None,
                "last_error_kind": None,
                "last_error_message": None,
                "last_error_at": None,
            },
            {
                "document_id": "document-2",
                "project_id": "project-1",
                "file_name": "bad.md",
                "source_type": "markdown",
                "file_size_bytes": 12,
                "status": "failed",
                "processing_run_id": "run-2",
                "processing_status": "failed",
                "processing_trigger": "explicit_user_resume",
                "resume_policy": "explicit_user_action",
                "section_count": 2,
                "processed_section_count": 1,
                "failed_section_count": 1,
                "pending_section_count": 0,
                "created_at": _now(),
                "updated_at": _now(),
                "started_at": _now(),
                "completed_at": _now(),
                "last_error_kind": "provider_error",
                "last_error_message": "LLM failed",
                "last_error_at": _now(),
            },
        ],
        node_runs=[
            {
                "node_run_id": "node-1",
                "document_id": "document-1",
                "processing_run_id": "run-1",
                "node_name": "claim_observations",
                "status": "completed",
                "error_kind": None,
                "error_message": None,
            },
            {
                "node_run_id": "node-2",
                "document_id": "document-2",
                "processing_run_id": "run-2",
                "node_name": "claim_observations",
                "status": "failed",
                "error_kind": "provider_error",
                "error_message": "LLM failed",
            },
        ],
    )

    payload = await WorkbenchProcessingOverviewReadService(
        query
    ).fetch_processing_overview(project_id="project-1")

    assert payload["project_id"] == "project-1"
    assert payload["items"] is payload["documents"]
    assert payload["summary"] == {
        "documents_total": 2,
        "active_documents": 1,
        "failed_documents": 1,
        "resumable_documents": 1,
        "sections_total": 5,
        "processed_sections": 2,
        "failed_sections": 1,
        "pending_sections": 2,
        "node_runs_total": 2,
        "failed_node_runs": 1,
    }
    assert payload["status_counts"]["documents"] == {
        "failed": 1,
        "sectioned": 1,
    }
    assert payload["status_counts"]["processing_runs"] == {
        "failed": 1,
        "running": 1,
    }
    assert payload["status_counts"]["node_runs"] == {
        "completed": 1,
        "failed": 1,
    }
    assert payload["active_documents"][0]["document_id"] == "document-1"
    assert payload["failed_documents"][0]["document_id"] == "document-2"
    assert payload["resumable_documents"][0]["document_id"] == "document-2"
    assert query.calls == ["documents:project-1", "node_runs:project-1"]


@pytest.mark.asyncio
async def test_processing_overview_allows_empty_project() -> None:
    query = FakeProcessingOverviewQuery(documents=[], node_runs=[])

    payload = await WorkbenchProcessingOverviewReadService(
        query
    ).fetch_processing_overview(project_id="project-1")

    assert payload["summary"]["documents_total"] == 0
    assert payload["documents"] == []
    assert payload["status_counts"] == {
        "documents": {},
        "processing_runs": {},
        "node_runs": {},
    }
