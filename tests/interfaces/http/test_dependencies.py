from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domain.control_plane.project_configuration import ProjectConfigurationView
from src.application.services.ticket_resolution_service import TicketResolutionService
from src.interfaces.http.dependencies import get_thread_command_service


@pytest.mark.asyncio
async def test_http_thread_command_service_wires_project_language_for_regenerate():
    project_id = str(uuid4())
    thread_id = str(uuid4())
    captured_languages: list[str] = []

    class CapturingSummaryGenerator:
        async def generate_ticket_resolution(self, payload):
            captured_languages.append(payload.target_language)
            return SimpleNamespace(
                summary_text="Generated",
                discussed_questions=[],
                resolved_questions=[],
                unresolved_questions=[],
                manager_decisions=[],
                customer_facts=[],
                business_commitments=[],
            )

    runtime = AsyncMock()
    runtime.get_ticket_resolution = AsyncMock(
        return_value={"summary_text": "old", "status": "generated", "version": 2}
    )
    runtime.compare_and_update_ticket_resolution = AsyncMock(return_value=True)
    read = AsyncMock()
    read.get_thread_with_project_view = AsyncMock(
        return_value=SimpleNamespace(
            thread_id=thread_id,
            project_id=project_id,
            client_id=str(uuid4()),
            status="closed",
            context_summary="old",
        )
    )
    messages = AsyncMock()
    messages.get_messages = AsyncMock(return_value=[])
    events = AsyncMock()
    events.get_events_for_thread = AsyncMock(return_value=[])
    projects = AsyncMock()
    projects.get_project_configuration_view = AsyncMock(
        return_value=ProjectConfigurationView(
            project_id=project_id,
            settings={"target_language": "en"},
        )
    )

    with patch(
        "src.infrastructure.llm.conversation_summary_generator."
        "ResponseCompletionConversationSummaryGenerator",
        CapturingSummaryGenerator,
    ):
        service = get_thread_command_service(
            thread_lifecycle_repo=AsyncMock(),
            memory_repo=AsyncMock(),
            thread_runtime_state_repo=runtime,
            thread_read_repo=read,
            thread_message_repo=messages,
            event_repo=events,
            project_service=AsyncMock(),
            project_repo=projects,
            user_repo=AsyncMock(),
        )

    automatic_service = TicketResolutionService(
        thread_runtime_state_repo=runtime,
        thread_read_repo=read,
        thread_message_repo=messages,
        event_repo=events,
        project_configuration_repo=projects,
        summary_generator=CapturingSummaryGenerator(),
    )
    runtime.get_ticket_resolution.return_value = None
    await automatic_service.generate_after_manager_close(thread_id)

    runtime.get_ticket_resolution.return_value = {
        "summary_text": "old",
        "status": "generated",
        "version": 2,
    }
    await service.regenerate_ticket_resolution(
        thread_id=thread_id,
        actor_user_id=str(uuid4()),
    )

    assert captured_languages == ["en", "en"]
