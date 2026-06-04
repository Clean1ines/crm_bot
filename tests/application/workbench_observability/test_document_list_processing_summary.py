from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pytest

from src.application.workbench_observability.document_list import (
    WorkbenchDocumentListReadService,
)


@dataclass(slots=True)
class FakeQuery:
    rows: Sequence[dict[str, object]]

    async def list_workbench_documents(
        self,
        *,
        project_id: str,
        limit: int,
        offset: int,
    ) -> Sequence[dict[str, object]]:
        assert project_id == "project-1"
        assert limit == 20
        assert offset == 0
        return self.rows


@pytest.mark.asyncio
async def test_document_list_uses_processing_summary_after_transient_workspace_purge() -> (
    None
):
    service = WorkbenchDocumentListReadService(
        query=FakeQuery(
            rows=[
                {
                    "document_id": "document-1",
                    "project_id": "project-1",
                    "file_name": "faq.md",
                    "source_type": "upload",
                    "file_size_bytes": 42,
                    "status": "published",
                    "section_count": 0,
                    "processed_section_count": 0,
                    "failed_section_count": 0,
                    "pending_section_count": 0,
                    "canonical_fact_count": 0,
                    "runtime_entry_count": 0,
                    "registry_retained": True,
                    "final_registry_snapshot_id": None,
                    "processing_summary": {
                        "contract": "workbench_document_processing_summary_v1",
                        "document_section_count": 3,
                        "canonical_fact_count": 2,
                        "published_runtime_fact_count": 2,
                        "final_snapshot_id": "snapshot-final",
                        "total_prompt_tokens": 100,
                        "total_completion_tokens": 50,
                        "total_tokens": 150,
                        "total_llm_calls": 5,
                        "active_elapsed_seconds": 12,
                        "wall_elapsed_seconds": 20,
                        "published_surface_count": 2,
                    },
                }
            ]
        )
    )

    payload = await service.list_documents(
        project_id="project-1",
        limit=20,
        offset=0,
    )

    document = payload["documents"][0]

    assert document["section_count"] == 3
    assert document["total_sections"] == 3
    assert document["processed_section_count"] == 3
    assert document["canonical_fact_count"] == 2
    assert document["runtime_entry_count"] == 2
    assert document["final_registry_snapshot_id"] == "snapshot-final"
    assert document["processing_summary"]["total_tokens"] == 150
    assert document["result_metrics"]["total_prompt_tokens"] == 100
    assert document["result_metrics"]["published_surface_count"] == 2


@pytest.mark.asyncio
async def test_document_list_live_counters_win_over_processing_summary_before_purge() -> (
    None
):
    service = WorkbenchDocumentListReadService(
        query=FakeQuery(
            rows=[
                {
                    "document_id": "document-1",
                    "project_id": "project-1",
                    "file_name": "faq.md",
                    "source_type": "upload",
                    "file_size_bytes": 42,
                    "status": "processing",
                    "section_count": 4,
                    "processed_section_count": 2,
                    "failed_section_count": 1,
                    "pending_section_count": 1,
                    "canonical_fact_count": 7,
                    "runtime_entry_count": 6,
                    "registry_retained": False,
                    "final_registry_snapshot_id": "live-snapshot",
                    "processing_summary": {
                        "document_section_count": 3,
                        "canonical_fact_count": 2,
                        "published_runtime_fact_count": 2,
                        "final_snapshot_id": "summary-snapshot",
                    },
                }
            ]
        )
    )

    payload = await service.list_documents(
        project_id="project-1",
        limit=20,
        offset=0,
    )

    document = payload["documents"][0]

    assert document["section_count"] == 4
    assert document["processed_section_count"] == 2
    assert document["failed_section_count"] == 1
    assert document["runtime_entry_count"] == 6
    assert document["final_registry_snapshot_id"] == "live-snapshot"
