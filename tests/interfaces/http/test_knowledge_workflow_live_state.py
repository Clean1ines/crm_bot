from __future__ import annotations

import pytest
from fastapi import BackgroundTasks, HTTPException

from src.interfaces.http import dependencies, knowledge
from tests.api.test_knowledge import _FakeProjectRepo, _user_repo


@pytest.mark.asyncio
async def test_workflow_live_state_endpoint_requires_project_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetch_called = False

    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    async def fake_fetch_workbench_workflow_live_state(
        *,
        pool: object,
        project_id: str,
        document_id: str,
    ) -> dict[str, object]:
        nonlocal fetch_called
        fetch_called = True
        return {}

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge,
        "fetch_workbench_workflow_live_state",
        fake_fetch_workbench_workflow_live_state,
    )

    with pytest.raises(HTTPException) as exc_info:
        await knowledge.knowledge_workflow_live_state(
            project_id="project-1",
            document_id="document-1",
            background_tasks=BackgroundTasks(),
            authorization="Bearer valid-token",
            pool=object(),
            project_repo=_FakeProjectRepo(has_role=False),
            user_repo=_user_repo(platform_admin=False),
            llm_executor=object(),
        )

    assert exc_info.value.status_code == 403
    assert fetch_called is False


@pytest.mark.asyncio
async def test_workflow_live_state_endpoint_returns_frontend_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    async def fake_fetch_workbench_workflow_live_state(
        *,
        pool: object,
        project_id: str,
        document_id: str,
    ) -> dict[str, object]:
        assert project_id == "project-1"
        assert document_id == "source-document:project-1:abc"
        return {
            "document_id": document_id,
            "project_id": project_id,
            "file_name": "faq.md",
            "document_status": "processing",
            "current_processing_run_id": "run-1",
            "workflow": {
                "workflow_run_id": "workflow-1",
                "source_document_ref": document_id,
                "workflow_status": "RUNNING",
                "current_phase": "PROMPT_A_WORK_SCHEDULED",
                "timer": {
                    "mode": "running",
                    "active_elapsed_seconds": 10,
                    "wall_elapsed_seconds": 30,
                    "current_active_started_at": "2026-06-15T12:00:00+00:00",
                    "started_at": "2026-06-15T12:00:00+00:00",
                    "completed_at": None,
                    "is_live": True,
                },
                "usage": {
                    "total_prompt_tokens": 100,
                    "total_completion_tokens": 50,
                    "total_tokens": 150,
                    "total_llm_calls": 1,
                    "model_summaries": [],
                },
                "stages": [],
                "section_lanes": [
                    {
                        "lane_index": 0,
                        "lane_id": "execution-runtime",
                        "ready_count": 0,
                        "leased_count": 0,
                        "done_count": 0,
                        "failed_count": 0,
                        "waiting_count": 1,
                        "total_attempt_count": 1,
                        "max_attempt_count": 1,
                        "items": [
                            {
                                "queue_item_id": "work-item-1",
                                "section_id": "section-1",
                                "section_index": 0,
                                "section_key": "section-1",
                                "status": "user_action_required",
                                "attempt_count": 1,
                                "lease_expires_at": None,
                                "next_attempt_at": None,
                                "claimed_by_worker_id": None,
                                "error_kind": "primary_model_daily_capacity_exhausted",
                                "retry_plan": None,
                                "user_action_required": True,
                                "blocked_reason": "primary_model_daily_capacity_exhausted",
                                "retry_timer": {
                                    "retry_available_at": None,
                                    "seconds_until_retry": None,
                                },
                            }
                        ],
                    }
                ],
                "llm_attempts": [
                    {
                        "node_run_id": "attempt-1",
                        "section_id": "section-1",
                        "node_name": "knowledge_workbench.claim_builder",
                        "node_kind": "execution_work_item",
                        "status": "retryable_failed",
                        "started_at": "2026-06-15T12:00:00+00:00",
                        "completed_at": "2026-06-15T12:00:05+00:00",
                        "duration_ms": 5000,
                        "model_provider": "groq",
                        "model_name": "openai/gpt-oss-120b",
                        "account_ref": "groq_org_primary",
                        "prompt_tokens": 100,
                        "completion_tokens": 0,
                        "total_tokens": 100,
                        "remaining_minute_requests": 0,
                        "remaining_minute_tokens": 0,
                        "minute_reset_at": "2026-06-15T12:01:00+00:00",
                        "remaining_daily_requests": 0,
                        "remaining_daily_tokens": 0,
                        "daily_reset_at": "2026-06-16T00:00:00+00:00",
                        "error_kind": "minute_limit",
                        "error_message_user": "primary_model_daily_capacity_exhausted",
                        "next_attempt_at": "2026-06-15T12:01:00+00:00",
                        "retry_plan": "wait_nearest_admission_window",
                        "user_action_required": False,
                        "blocked_reason": None,
                    }
                ],
                "timeline": [
                    {
                        "timeline_entry_id": "timeline-1",
                        "event_type": "SourceUnitsCreated",
                        "phase": "SOURCE_INGESTION",
                        "severity": "info",
                        "message": "Source units created",
                        "occurred_at": "2026-06-15T12:00:00+00:00",
                        "source_ref": document_id,
                        "work_item_id": None,
                        "attempt_id": None,
                    }
                ],
                "curation": {
                    "available": True,
                    "reason_code": "ready_to_open",
                    "workflow_run_id": "workflow-1",
                    "workspace_ref": None,
                    "workspace_status": None,
                    "item_count": 0,
                    "excluded_item_count": 0,
                },
                "actions": [],
            },
        }

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge,
        "fetch_workbench_workflow_live_state",
        fake_fetch_workbench_workflow_live_state,
    )

    background_tasks = BackgroundTasks()

    response = await knowledge.knowledge_workflow_live_state(
        project_id="project-1",
        document_id="source-document:project-1:abc",
        background_tasks=background_tasks,
        authorization="Bearer valid-token",
        pool=object(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
        llm_executor=object(),
    )

    assert len(background_tasks.tasks) == 1
    assert response["workflow"]["workflow_run_id"] == "workflow-1"
    assert response["workflow"]["curation"]["available"] is True
    assert response["workflow"]["timer"]["active_elapsed_seconds"] == 10
    assert (
        response["workflow"]["section_lanes"][0]["items"][0]["user_action_required"]
        is True
    )
    assert response["workflow"]["llm_attempts"][0]["account_ref"] == "groq_org_primary"
    assert (
        response["workflow"]["llm_attempts"][0]["retry_plan"]
        == "wait_nearest_admission_window"
    )
    assert response["workflow"]["timeline"][0]["event_type"] == "SourceUnitsCreated"


@pytest.mark.asyncio
async def test_workflow_live_state_endpoint_maps_missing_document_to_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.interfaces.composition.faq_workbench_workflow_live_state import (
        WorkbenchWorkflowLiveStateNotFoundError,
    )

    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    async def fake_fetch_workbench_workflow_live_state(
        *,
        pool: object,
        project_id: str,
        document_id: str,
    ) -> dict[str, object]:
        del pool, project_id, document_id
        raise WorkbenchWorkflowLiveStateNotFoundError("missing")

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge,
        "fetch_workbench_workflow_live_state",
        fake_fetch_workbench_workflow_live_state,
    )

    with pytest.raises(HTTPException) as exc_info:
        await knowledge.knowledge_workflow_live_state(
            project_id="project-1",
            document_id="missing-document",
            background_tasks=BackgroundTasks(),
            authorization="Bearer valid-token",
            pool=object(),
            project_repo=_FakeProjectRepo(has_role=True),
            user_repo=_user_repo(),
            llm_executor=object(),
        )

    assert exc_info.value.status_code == 404
