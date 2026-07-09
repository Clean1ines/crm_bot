from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import asyncpg
import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.pause_knowledge_extraction_workflow import (
    PauseKnowledgeExtractionWorkflowCommand,
)
from src.contexts.knowledge_workbench.application.sagas.resume_knowledge_extraction_workflow import (
    ResumeKnowledgeExtractionWorkflowCommand,
)
from src.contexts.knowledge_workbench.infrastructure.postgres.postgres_knowledge_extraction_saga_state_repository import (
    PostgresKnowledgeExtractionSagaStateRepository,
)
from src.contexts.knowledge_workbench.observability.application.projectors.knowledge_extraction_frontend_workflow_event_projector import (
    KnowledgeExtractionFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)
from src.interfaces.composition import knowledge_extraction_workflow_pause_resume
from src.interfaces.composition.knowledge_extraction_workflow_pause_resume import (
    RunPauseKnowledgeExtractionWorkflow,
    RunResumeKnowledgeExtractionWorkflowTransition,
)
from src.interfaces.http import dependencies
from src.interfaces.http import knowledge


def _now() -> datetime:
    return datetime(2026, 7, 9, 20, 23, 48, tzinfo=timezone.utc)


@dataclass(slots=True)
class _AllowingProjectRepository:
    async def project_exists(self, project_id: str) -> bool:
        return bool(project_id)

    async def user_has_project_role(
        self,
        project_id: str,
        user_id: str,
        allowed_roles: tuple[str, ...],
    ) -> bool:
        del project_id, user_id
        return allowed_roles == ("owner", "admin", "manager")


@dataclass(slots=True)
class _NonAdminUserRepository:
    async def is_platform_admin(self, user_id: str) -> bool:
        del user_id
        return False


def _running_state(
    *,
    project_id: str,
    workflow_run_id: str,
    source_document_ref: str,
) -> KnowledgeExtractionWorkflowState:
    return KnowledgeExtractionWorkflowState(
        workflow_run_id=workflow_run_id,
        project_id=project_id,
        source_document_ref=source_document_ref,
        status=KnowledgeExtractionWorkflowStatus.RUNNING,
        current_phase=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        created_at=_now(),
        updated_at=_now(),
    )


@pytest.mark.asyncio
async def test_pause_resume_composition_persists_manual_control_frontend_events(
    db_pool: asyncpg.Pool,
    test_project: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = test_project
    suffix = uuid4().hex
    source_document_ref = f"source-document:{project_id}:{suffix}"
    workflow_run_id = f"knowledge-extraction:{source_document_ref}"

    async def no_publish(events: tuple[object, ...]) -> None:
        del events

    async def fake_current_user_id(authorization: str | None) -> str:
        assert authorization == "Bearer test"
        return "owner-1"

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge_extraction_workflow_pause_resume,
        "publish_frontend_workflow_events",
        no_publish,
        raising=False,
    )

    async with db_pool.acquire() as connection:
        await PostgresKnowledgeExtractionSagaStateRepository(
            connection
        ).save_workflow_state(
            _running_state(
                project_id=project_id,
                workflow_run_id=workflow_run_id,
                source_document_ref=source_document_ref,
            )
        )

    try:
        result = await RunPauseKnowledgeExtractionWorkflow(pool=db_pool).execute(
            PauseKnowledgeExtractionWorkflowCommand(
                workflow_run_id=workflow_run_id,
                project_id=project_id,
                actor_user_id="owner-1",
                occurred_at=_now(),
                reason="manual_stop",
            )
        )

        assert result.status == "manually_paused"

        async with db_pool.acquire() as connection:
            outbox_row = await connection.fetchrow(
                """
                SELECT sequence_number, event_id, event_type, workflow_run_id,
                       payload, occurred_at, causation_command_id, correlation_id
                FROM workflow_runtime_outbox_events
                WHERE workflow_run_id = $1
                  AND event_type = 'WorkflowManuallyPaused'
                """,
                workflow_run_id,
            )
            assert outbox_row is not None
            assert outbox_row["event_type"] == "WorkflowManuallyPaused"
            assert outbox_row["sequence_number"] is not None

            paused_event = WorkflowEvent(
                event_id=WorkflowEventId(outbox_row["event_id"]),
                event_type=outbox_row["event_type"],
                workflow_run_id=outbox_row["workflow_run_id"],
                payload=_json_payload(outbox_row["payload"]),
                occurred_at=outbox_row["occurred_at"],
                causation_command_id=None,
                correlation_id=outbox_row["correlation_id"],
                sequence_number=outbox_row["sequence_number"],
            )
            projected = KnowledgeExtractionFrontendWorkflowEventProjector().project(
                paused_event
            )
            assert projected is not None
            assert projected.projection_type == "workflow_manually_paused"

            frontend_row = await connection.fetchrow(
                """
                SELECT projection_type, event_type, source_sequence_number,
                       workflow_run_id, project_id, document_id, payload
                FROM frontend_workflow_events
                WHERE workflow_run_id = $1
                  AND projection_type = 'workflow_manually_paused'
                """,
                workflow_run_id,
            )
            assert frontend_row is not None
            assert frontend_row["event_type"] == "WorkflowManuallyPaused"
            assert (
                frontend_row["source_sequence_number"] == outbox_row["sequence_number"]
            )
            assert frontend_row["project_id"] == project_id
            assert frontend_row["document_id"] == source_document_ref

        response = await knowledge.list_knowledge_frontend_workflow_events(
            project_id=project_id,
            document_id=source_document_ref,
            workflow_run_id=workflow_run_id,
            after_source_sequence=0,
            after_cursor=None,
            limit=200,
            authorization="Bearer test",
            pool=db_pool,
            project_repo=_AllowingProjectRepository(),
            user_repo=_NonAdminUserRepository(),
        )

        events = response["events"]
        assert isinstance(events, list)
        assert [event["projection_type"] for event in events] == [
            "workflow_manually_paused"
        ]

        resume_result = await RunResumeKnowledgeExtractionWorkflowTransition(
            pool=db_pool
        ).execute(
            ResumeKnowledgeExtractionWorkflowCommand(
                workflow_run_id=workflow_run_id,
                project_id=project_id,
                actor_user_id="owner-1",
                occurred_at=_now(),
            )
        )

        assert resume_result.status == "running"

        async with db_pool.acquire() as connection:
            resume_outbox_row = await connection.fetchrow(
                """
                SELECT sequence_number, event_id, event_type, workflow_run_id,
                       payload, occurred_at, causation_command_id, correlation_id
                FROM workflow_runtime_outbox_events
                WHERE workflow_run_id = $1
                  AND event_type = 'WorkflowManuallyResumed'
                """,
                workflow_run_id,
            )
            assert resume_outbox_row is not None
            assert resume_outbox_row["event_type"] == "WorkflowManuallyResumed"
            assert resume_outbox_row["sequence_number"] is not None

            resumed_event = WorkflowEvent(
                event_id=WorkflowEventId(resume_outbox_row["event_id"]),
                event_type=resume_outbox_row["event_type"],
                workflow_run_id=resume_outbox_row["workflow_run_id"],
                payload=_json_payload(resume_outbox_row["payload"]),
                occurred_at=resume_outbox_row["occurred_at"],
                causation_command_id=None,
                correlation_id=resume_outbox_row["correlation_id"],
                sequence_number=resume_outbox_row["sequence_number"],
            )
            resumed_projected = (
                KnowledgeExtractionFrontendWorkflowEventProjector().project(
                    resumed_event
                )
            )
            assert resumed_projected is not None
            assert resumed_projected.projection_type == "workflow_manually_resumed"

            resume_frontend_row = await connection.fetchrow(
                """
                SELECT projection_type, event_type, source_sequence_number,
                       workflow_run_id, project_id, document_id, payload
                FROM frontend_workflow_events
                WHERE workflow_run_id = $1
                  AND projection_type = 'workflow_manually_resumed'
                """,
                workflow_run_id,
            )
            assert resume_frontend_row is not None
            assert resume_frontend_row["event_type"] == "WorkflowManuallyResumed"
            assert (
                resume_frontend_row["source_sequence_number"]
                == resume_outbox_row["sequence_number"]
            )
            assert resume_frontend_row["project_id"] == project_id
            assert resume_frontend_row["document_id"] == source_document_ref

        resumed_response = await knowledge.list_knowledge_frontend_workflow_events(
            project_id=project_id,
            document_id=source_document_ref,
            workflow_run_id=workflow_run_id,
            after_source_sequence=0,
            after_cursor=None,
            limit=200,
            authorization="Bearer test",
            pool=db_pool,
            project_repo=_AllowingProjectRepository(),
            user_repo=_NonAdminUserRepository(),
        )
        resumed_events = resumed_response["events"]
        assert isinstance(resumed_events, list)
        assert [event["projection_type"] for event in resumed_events] == [
            "workflow_manually_paused",
            "workflow_manually_resumed",
        ]
    finally:
        async with db_pool.acquire() as connection:
            await connection.execute(
                "DELETE FROM frontend_workflow_events WHERE workflow_run_id = $1",
                workflow_run_id,
            )
            await connection.execute(
                "DELETE FROM workflow_runtime_timeline_entries WHERE workflow_run_id = $1",
                workflow_run_id,
            )
            await connection.execute(
                "DELETE FROM workflow_runtime_outbox_events WHERE workflow_run_id = $1",
                workflow_run_id,
            )
            await connection.execute(
                "DELETE FROM knowledge_extraction_workflow_runs WHERE workflow_run_id = $1",
                workflow_run_id,
            )


def _json_payload(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        decoded = json.loads(value)
        if isinstance(decoded, dict):
            return decoded
    raise TypeError("payload must be a JSON object")
