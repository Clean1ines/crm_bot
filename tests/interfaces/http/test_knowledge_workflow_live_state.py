from __future__ import annotations

import pytest
from fastapi import HTTPException

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
            authorization="Bearer valid-token",
            pool=object(),
            project_repo=_FakeProjectRepo(has_role=False),
            user_repo=_user_repo(platform_admin=False),
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
                "section_lanes": [],
                "llm_attempts": [],
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

    response = await knowledge.knowledge_workflow_live_state(
        project_id="project-1",
        document_id="source-document:project-1:abc",
        authorization="Bearer valid-token",
        pool=object(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    assert response["workflow"]["workflow_run_id"] == "workflow-1"
    assert response["workflow"]["curation"]["available"] is True
    assert response["workflow"]["timer"]["active_elapsed_seconds"] == 10
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
            authorization="Bearer valid-token",
            pool=object(),
            project_repo=_FakeProjectRepo(has_role=True),
            user_repo=_user_repo(),
        )

    assert exc_info.value.status_code == 404
