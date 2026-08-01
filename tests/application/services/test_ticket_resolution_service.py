from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.errors import ConflictError, ValidationError
from src.application.ports.conversation_summary_port import TicketResolutionSummary
from src.application.services.ticket_resolution_service import TicketResolutionService
from src.domain.control_plane.project_configuration import ProjectConfigurationView
from src.infrastructure.llm.conversation_summary_generator import (
    ResponseCompletionConversationSummaryGenerator,
)


THREAD_ID = str(uuid4())
PROJECT_ID = str(uuid4())
CLIENT_ID = str(uuid4())


def _thread(status: str = "closed"):
    return SimpleNamespace(
        thread_id=THREAD_ID,
        project_id=PROJECT_ID,
        client_id=CLIENT_ID,
        status=status,
        context_summary="old summary",
    )


def _project_config(
    *,
    target_language: str | None = None,
    default_language: str | None = None,
) -> ProjectConfigurationView:
    settings = {}
    if target_language is not None:
        settings["target_language"] = target_language
    if default_language is not None:
        settings["default_language"] = default_language
    return ProjectConfigurationView(project_id=PROJECT_ID, settings=settings)


@pytest.mark.asyncio
async def test_ticket_resolution_edit_preserves_structured_fields_and_uses_cas():
    runtime = AsyncMock()
    runtime.get_ticket_resolution = AsyncMock(
        return_value={
            "summary_text": "old",
            "status": "generated",
            "source": "llm",
            "version": 2,
            "generated_at": "2026-01-01T00:00:00+00:00",
            "resolved_questions": ["old answer"],
            "manager_decisions": ["old decision"],
        }
    )
    runtime.compare_and_update_ticket_resolution = AsyncMock(return_value=True)
    read = AsyncMock()
    read.get_thread_with_project_view = AsyncMock(return_value=_thread())
    events = AsyncMock()

    service = TicketResolutionService(
        thread_runtime_state_repo=runtime,
        thread_read_repo=read,
        event_repo=events,
    )

    result = await service.edit(
        thread_id=THREAD_ID,
        summary_text=" updated summary ",
        expected_version=2,
        actor_user_id="user-1",
    )

    assert result["summary_text"] == "updated summary"
    assert result["status"] == "edited"
    assert result["source"] == "manager"
    assert result["version"] == 3
    assert result["generated_at"] == "2026-01-01T00:00:00+00:00"
    assert result["resolved_questions"] == ["old answer"]
    assert result["manager_decisions"] == ["old decision"]
    runtime.compare_and_update_ticket_resolution.assert_awaited_once()


@pytest.mark.asyncio
async def test_ticket_resolution_edit_conflict_when_cas_returns_no_row():
    runtime = AsyncMock()
    runtime.get_ticket_resolution = AsyncMock(
        return_value={"summary_text": "old", "status": "generated", "version": 2}
    )
    runtime.compare_and_update_ticket_resolution = AsyncMock(return_value=False)
    read = AsyncMock()
    read.get_thread_with_project_view = AsyncMock(return_value=_thread())

    service = TicketResolutionService(
        thread_runtime_state_repo=runtime,
        thread_read_repo=read,
    )

    with pytest.raises(ConflictError):
        await service.edit(
            thread_id=THREAD_ID,
            summary_text="new",
            expected_version=2,
            actor_user_id="user-1",
        )


@pytest.mark.asyncio
async def test_ticket_resolution_edit_rejects_active_or_non_resolution_thread():
    runtime = AsyncMock()
    runtime.get_ticket_resolution = AsyncMock(return_value=None)
    read = AsyncMock()
    read.get_thread_with_project_view = AsyncMock(return_value=_thread(status="active"))

    service = TicketResolutionService(
        thread_runtime_state_repo=runtime,
        thread_read_repo=read,
    )

    with pytest.raises(ValidationError):
        await service.edit(
            thread_id=THREAD_ID,
            summary_text="new",
            expected_version=0,
            actor_user_id="user-1",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "status"),
    [
        ("edit", "pending"),
        ("edit", "missing"),
        ("regenerate", "pending"),
    ],
)
async def test_ticket_resolution_manual_mutations_reject_forbidden_statuses(
    method,
    status,
):
    runtime = AsyncMock()
    runtime.get_ticket_resolution = AsyncMock(
        return_value={"summary_text": "old", "status": status, "version": 1}
    )
    read = AsyncMock()
    read.get_thread_with_project_view = AsyncMock(return_value=_thread())

    service = TicketResolutionService(
        thread_runtime_state_repo=runtime,
        thread_read_repo=read,
        summary_generator=AsyncMock(),
    )

    with pytest.raises(ValidationError):
        if method == "edit":
            await service.edit(
                thread_id=THREAD_ID,
                summary_text="new",
                expected_version=1,
                actor_user_id="user-1",
            )
        else:
            await service.regenerate(thread_id=THREAD_ID, actor_user_id="user-1")


@pytest.mark.asyncio
async def test_ticket_resolution_regenerate_saves_full_structured_payload():
    runtime = AsyncMock()
    runtime.get_ticket_resolution = AsyncMock(
        return_value={"summary_text": "old", "status": "generated", "version": 1}
    )
    runtime.compare_and_update_ticket_resolution = AsyncMock(return_value=True)
    read = AsyncMock()
    read.get_thread_with_project_view = AsyncMock(return_value=_thread())
    messages = AsyncMock()
    messages.get_messages = AsyncMock(return_value=[])
    events = AsyncMock()
    events.get_events_for_thread = AsyncMock(return_value=[])
    generator = AsyncMock()
    generator.generate_ticket_resolution = AsyncMock(
        return_value=TicketResolutionSummary(
            summary_text="resolved",
            discussed_questions=["question"],
            resolved_questions=["resolved question"],
            unresolved_questions=["missing"],
            manager_decisions=["decision"],
            customer_facts=["fact"],
            business_commitments=["commitment"],
        )
    )

    service = TicketResolutionService(
        thread_runtime_state_repo=runtime,
        thread_read_repo=read,
        thread_message_repo=messages,
        event_repo=events,
        summary_generator=generator,
    )

    result = await service.regenerate(thread_id=THREAD_ID, actor_user_id="user-1")

    assert result["status"] == "generated"
    assert result["version"] == 2
    assert result["resolved_questions"] == ["resolved question"]
    assert result["business_commitments"] == ["commitment"]


@pytest.mark.asyncio
async def test_ticket_resolution_regenerate_missing_becomes_generated():
    runtime = AsyncMock()
    runtime.get_ticket_resolution = AsyncMock(
        return_value={"summary_text": "", "status": "missing", "version": 1}
    )
    runtime.compare_and_update_ticket_resolution = AsyncMock(return_value=True)
    read = AsyncMock()
    read.get_thread_with_project_view = AsyncMock(return_value=_thread())
    generator = AsyncMock()
    generator.generate_ticket_resolution = AsyncMock(
        return_value=TicketResolutionSummary(summary_text="generated after missing")
    )

    service = TicketResolutionService(
        thread_runtime_state_repo=runtime,
        thread_read_repo=read,
        summary_generator=generator,
    )

    result = await service.regenerate(thread_id=THREAD_ID, actor_user_id="user-1")

    assert result["status"] == "generated"
    assert result["summary_text"] == "generated after missing"


@pytest.mark.asyncio
async def test_ticket_resolution_generation_failure_persists_failed_result():
    runtime = AsyncMock()
    runtime.get_ticket_resolution = AsyncMock(return_value=None)
    runtime.compare_and_update_ticket_resolution = AsyncMock(return_value=True)
    read = AsyncMock()
    read.get_thread_with_project_view = AsyncMock(return_value=_thread())
    generator = AsyncMock()
    generator.generate_ticket_resolution = AsyncMock(side_effect=RuntimeError("boom"))

    service = TicketResolutionService(
        thread_runtime_state_repo=runtime,
        thread_read_repo=read,
        summary_generator=generator,
        logger=MagicMock(),
    )

    result = await service.generate_after_manager_close(THREAD_ID)

    assert result is not None
    assert result["status"] == "failed"
    assert result["error_type"] == "RuntimeError"
    assert runtime.compare_and_update_ticket_resolution.await_count == 2
    assert [
        call.kwargs["resolution"]["version"]
        for call in runtime.compare_and_update_ticket_resolution.await_args_list
    ] == [1, 2]


@pytest.mark.asyncio
async def test_ticket_resolution_generation_persists_pending_then_generated():
    runtime = AsyncMock()
    runtime.get_ticket_resolution = AsyncMock(return_value=None)
    runtime.compare_and_update_ticket_resolution = AsyncMock(return_value=True)
    read = AsyncMock()
    read.get_thread_with_project_view = AsyncMock(return_value=_thread())
    generator = AsyncMock()
    generator.generate_ticket_resolution = AsyncMock(
        return_value=TicketResolutionSummary(
            summary_text="done",
            discussed_questions=["question"],
            resolved_questions=["resolved"],
        )
    )

    service = TicketResolutionService(
        thread_runtime_state_repo=runtime,
        thread_read_repo=read,
        summary_generator=generator,
    )

    result = await service.generate_after_manager_close(THREAD_ID)

    assert result is not None
    assert result["status"] == "generated"
    first_call = runtime.compare_and_update_ticket_resolution.await_args_list[0]
    assert first_call.kwargs["expected_version"] == 0
    assert first_call.kwargs["resolution"]["status"] == "pending"
    assert first_call.kwargs["resolution"]["version"] == 1
    second_call = runtime.compare_and_update_ticket_resolution.await_args_list[1]
    assert second_call.kwargs["expected_version"] == 1
    assert second_call.kwargs["resolution"]["status"] == "generated"
    assert second_call.kwargs["resolution"]["version"] == 2


@pytest.mark.asyncio
async def test_ticket_resolution_input_orders_production_desc_events_chronologically():
    runtime = AsyncMock()
    runtime.get_ticket_resolution = AsyncMock(return_value=None)
    runtime.compare_and_update_ticket_resolution = AsyncMock(return_value=True)
    read = AsyncMock()
    read.get_thread_with_project_view = AsyncMock(return_value=_thread())
    messages = AsyncMock()
    messages.get_messages = AsyncMock(
        return_value=[
            {"id": "message-old", "created_at": "2026-01-01T00:00:00+00:00"},
            {"id": "message-new", "created_at": "2026-01-01T00:01:00+00:00"},
        ]
    )
    events = AsyncMock()
    events.get_events_for_thread = AsyncMock(
        return_value=[
            {
                "id": f"event-{index}",
                "event_type": "manager_note" if index == 34 else "status_changed",
                "created_at": f"2026-01-01T00:{index:02d}:00+00:00",
            }
            for index in range(34, -1, -1)
        ]
    )
    generator = AsyncMock()
    generator.generate_ticket_resolution = AsyncMock(
        return_value=TicketResolutionSummary(summary_text="done")
    )

    service = TicketResolutionService(
        thread_runtime_state_repo=runtime,
        thread_read_repo=read,
        thread_message_repo=messages,
        event_repo=events,
        summary_generator=generator,
    )

    await service.generate_after_manager_close(THREAD_ID)

    resolution_input = generator.generate_ticket_resolution.await_args.args[0]
    assert [message["id"] for message in resolution_input.messages] == [
        "message-old",
        "message-new",
    ]
    assert len(resolution_input.events) == 30
    assert resolution_input.events[0]["id"] == "event-5"
    assert resolution_input.events[-1]["id"] == "event-34"
    assert resolution_input.events[-1]["event_type"] == "manager_note"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("settings", "expected_language"),
    [
        ({"target_language": "ru"}, "ru"),
        ({"target_language": "en"}, "en"),
        ({"target_language": "de"}, "de"),
        ({"target_language": "es"}, "es"),
        ({"default_language": "de"}, "de"),
        ({"target_language": "it"}, "ru"),
    ],
)
async def test_ticket_resolution_input_uses_project_language(
    settings,
    expected_language,
):
    runtime = AsyncMock()
    runtime.get_ticket_resolution = AsyncMock(return_value=None)
    runtime.compare_and_update_ticket_resolution = AsyncMock(return_value=True)
    read = AsyncMock()
    read.get_thread_with_project_view = AsyncMock(return_value=_thread())
    projects = AsyncMock()
    projects.get_project_configuration_view = AsyncMock(
        return_value=ProjectConfigurationView(project_id=PROJECT_ID, settings=settings)
    )
    generator = AsyncMock()
    generator.generate_ticket_resolution = AsyncMock(
        return_value=TicketResolutionSummary(summary_text="done")
    )

    service = TicketResolutionService(
        thread_runtime_state_repo=runtime,
        thread_read_repo=read,
        project_configuration_repo=projects,
        summary_generator=generator,
    )

    await service.generate_after_manager_close(THREAD_ID)

    resolution_input = generator.generate_ticket_resolution.await_args.args[0]
    assert resolution_input.target_language == expected_language


class _Completion:
    def __init__(self, content: str) -> None:
        self.content = content

    async def complete(self, *_args, **_kwargs) -> str:
        return self.content


class _CasRuntime:
    def __init__(self, initial: dict[str, object] | None = None) -> None:
        self.resolution = dict(initial or {})
        self.calls: list[dict[str, object]] = []

    async def get_ticket_resolution(self, _thread_id: str):
        return dict(self.resolution) if self.resolution else None

    async def compare_and_update_ticket_resolution(
        self,
        _thread_id: str,
        *,
        expected_version: int,
        summary: str,
        resolution: dict[str, object],
    ) -> bool:
        current_version = int(self.resolution.get("version") or 0)
        self.calls.append(
            {
                "expected_version": expected_version,
                "current_version": current_version,
                "resolution": dict(resolution),
            }
        )
        if current_version != expected_version:
            return False
        self.resolution = dict(resolution)
        self.resolution["summary_text"] = summary
        return True


@pytest.mark.asyncio
async def test_old_generation_final_cannot_overwrite_manual_edit_after_pending():
    runtime = _CasRuntime()
    read = AsyncMock()
    read.get_thread_with_project_view = AsyncMock(return_value=_thread())

    class EditingGenerator:
        async def generate_ticket_resolution(self, _payload):
            runtime.resolution = {
                "summary_text": "manual edit",
                "status": "edited",
                "source": "manager",
                "version": 2,
            }
            return TicketResolutionSummary(summary_text="stale generated")

    service = TicketResolutionService(
        thread_runtime_state_repo=runtime,
        thread_read_repo=read,
        summary_generator=EditingGenerator(),
        logger=MagicMock(),
    )

    result = await service.generate_after_manager_close(THREAD_ID)

    assert result is not None
    assert result["status"] == "edited"
    assert result["summary_text"] == "manual edit"
    assert runtime.resolution["status"] == "edited"
    assert [call["expected_version"] for call in runtime.calls] == [0, 1]
    assert runtime.calls[0]["resolution"]["status"] == "pending"
    assert runtime.calls[1]["resolution"]["status"] == "generated"


def _valid_summary_json() -> str:
    return """
    {
      "summary_text": "Менеджер закрыл обращение.",
      "discussed_questions": ["Цена"],
      "resolved_questions": ["Расчёт отправят"],
      "unresolved_questions": [],
      "manager_decisions": ["Отправить расчёт"],
      "customer_facts": ["Клиент интересуется ценой"],
      "business_commitments": ["Отправить расчёт"]
    }
    """


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "expected_status"),
    [
        (_valid_summary_json(), "generated"),
        ("not json", "failed"),
        ("[]", "failed"),
        ('{"discussed_questions":[]}', "failed"),
        (
            '{"summary_text":"ok","discussed_questions":"bad","resolved_questions":[],"unresolved_questions":[],"manager_decisions":[],"customer_facts":[],"business_commitments":[]}',
            "failed",
        ),
        (f"```json\n{_valid_summary_json()}\n```", "generated"),
    ],
)
async def test_ticket_resolution_generation_status_follows_strict_summary_parser(
    content,
    expected_status,
):
    runtime = AsyncMock()
    runtime.get_ticket_resolution = AsyncMock(return_value=None)
    runtime.compare_and_update_ticket_resolution = AsyncMock(return_value=True)
    read = AsyncMock()
    read.get_thread_with_project_view = AsyncMock(return_value=_thread())
    generator = ResponseCompletionConversationSummaryGenerator(
        completion_client=_Completion(content)
    )

    service = TicketResolutionService(
        thread_runtime_state_repo=runtime,
        thread_read_repo=read,
        summary_generator=generator,
    )

    result = await service.generate_after_manager_close(THREAD_ID)

    assert result is not None
    assert result["status"] == expected_status
    assert runtime.compare_and_update_ticket_resolution.await_count == 2
