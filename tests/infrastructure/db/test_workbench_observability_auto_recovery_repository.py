from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import pytest

from src.infrastructure.db.workbench_observability_repository import (
    WorkbenchObservabilityRepository,
)


@dataclass(slots=True)
class CapturedFetch:
    query: str
    args: tuple[object, ...]


class FakeObservabilityPool:
    def __init__(self) -> None:
        self.fetch_calls: list[CapturedFetch] = []

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.fetch_calls.append(CapturedFetch(query=query, args=args))
        return [
            {
                "document_id": "document-1",
                "project_id": "project-1",
                "file_name": "faq.md",
                "source_type": "faq",
                "file_size_bytes": 123,
                "status": "paused_quota",
                "retention_state": "active_processing",
                "current_processing_run_id": "processing-run-1",
                "uploaded_by_user_id": None,
                "uploaded_by_actor_type": "user",
                "uploaded_by_actor_id": "user-1",
                "trusted_upload": True,
                "last_error_kind": "quota",
                "last_error_message": "quota exceeded",
                "last_error_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "deleted_at": None,
                "processing_run_id": "processing-run-1",
                "processing_status": "paused_quota",
                "processing_trigger": "fresh_upload",
                "resume_policy": "auto_allowed",
                "started_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "finished_at": None,
                "completed_at": None,
                "active_elapsed_seconds": 0,
                "wall_elapsed_seconds": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "llm_call_count": 0,
                "processing_last_error_kind": "quota",
                "last_error_report_id": None,
                "processing_last_user_message": "quota exceeded",
                "section_count": 1,
                "processed_section_count": 0,
                "failed_section_count": 0,
                "pending_section_count": 1,
                "canonical_fact_count": 0,
                "final_registry_snapshot_id": None,
                "registry_retained": False,
                "surface_draft_count": 0,
                "surface_ready_count": 0,
                "surface_published_count": 0,
                "surface_rejected_count": 0,
                "curation_session_id": None,
                "curation_session_status": None,
                "publication_id": None,
                "runtime_entry_count": 0,
                "auto_resume_scheduled_at": datetime(
                    2026, 1, 1, 1, tzinfo=timezone.utc
                ),
            }
        ]

    async def fetchrow(self, query: str, *args: object) -> object | None:
        raise AssertionError("fetchrow must not be used by list_workbench_documents")


@pytest.mark.asyncio
async def test_list_workbench_documents_auto_recovery_reads_parallel_task_type() -> (
    None
):
    pool = FakeObservabilityPool()
    repository = WorkbenchObservabilityRepository(pool)

    rows = await repository.list_workbench_documents(
        project_id="project-1",
        limit=20,
        offset=0,
    )

    assert len(rows) == 1
    assert rows[0]["auto_resume_scheduled_at"] == datetime(
        2026, 1, 1, 1, tzinfo=timezone.utc
    )

    assert len(pool.fetch_calls) == 1
    query = pool.fetch_calls[0].query

    assert "q.task_type = 'process_workbench_parallel_processing'" in query
    assert "q.task_type = 'process_workbench_document'" not in query
    assert "q.next_attempt_at IS NOT NULL" in query
    assert "q.status IN ('pending', 'queued', 'scheduled', 'retry')" in query
