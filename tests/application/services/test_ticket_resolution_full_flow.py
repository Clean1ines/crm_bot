from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.agent.nodes.load_state import create_load_state_node
from src.agent.nodes.response_generator import create_response_generator_node
from src.application.orchestration.manager_reply_service import ManagerReplyService
from src.application.ports.conversation_summary_port import TicketResolutionSummary
from src.application.services.ticket_resolution_service import TicketResolutionService
from src.domain.control_plane.project_configuration import ProjectConfigurationView
from src.domain.project_plane.thread_views import ThreadWithProjectView


PROJECT_ID = str(uuid4())
CLIENT_ID = str(uuid4())
OLD_THREAD_ID = str(uuid4())
NEW_THREAD_ID = str(uuid4())


class _RuntimeRepo:
    def __init__(self) -> None:
        self.resolutions: dict[str, dict[str, object]] = {}
        self.states: dict[str, dict[str, object]] = {}
        self.calls: list[dict[str, object]] = []

    async def get_ticket_resolution(self, thread_id: str):
        value = self.resolutions.get(thread_id)
        return dict(value) if value else None

    async def compare_and_update_ticket_resolution(
        self,
        thread_id: str,
        *,
        expected_version: int,
        summary: str,
        resolution: dict[str, object],
    ) -> bool:
        current = self.resolutions.get(thread_id)
        current_version = int((current or {}).get("version") or 0)
        self.calls.append(
            {
                "thread_id": thread_id,
                "expected_version": expected_version,
                "current_version": current_version,
                "status": resolution.get("status"),
                "version": resolution.get("version"),
            }
        )
        if current_version != expected_version:
            return False
        payload = dict(resolution)
        payload["summary_text"] = summary
        self.resolutions[thread_id] = payload
        self.states.setdefault(thread_id, {})["ticket_resolution"] = payload
        return True

    async def get_state_json(self, thread_id: str):
        return dict(self.states.get(thread_id, {}))

    async def get_analytics_view(self, _thread_id: str):
        return None

    async def update_analytics(self, **_kwargs) -> None:
        return None


class _ReadRepo:
    def __init__(self, runtime: _RuntimeRepo) -> None:
        self.runtime = runtime
        self.views = {
            OLD_THREAD_ID: ThreadWithProjectView(
                thread_id=OLD_THREAD_ID,
                client_id=CLIENT_ID,
                project_id=PROJECT_ID,
                status="manual",
                context_summary="Клиент спросил про цену.",
                chat_id=123,
            ),
            NEW_THREAD_ID: ThreadWithProjectView(
                thread_id=NEW_THREAD_ID,
                client_id=CLIENT_ID,
                project_id=PROJECT_ID,
                status="active",
                context_summary=None,
                chat_id=123,
            ),
        }

    async def get_thread_with_project_view(self, thread_id: str):
        return self.views.get(thread_id)

    async def list_recent_closed_ticket_resolutions(
        self,
        project_id: str,
        client_id: str,
        *,
        limit: int = 3,
        exclude_thread_id: str | None = None,
    ):
        result: list[dict[str, object]] = []
        for thread_id, resolution in self.runtime.resolutions.items():
            view = self.views.get(thread_id)
            if (
                view is None
                or view.project_id != project_id
                or view.client_id != client_id
                or view.status != "closed"
                or thread_id == exclude_thread_id
                or resolution.get("status") not in {"generated", "edited"}
                or not resolution.get("summary_text")
            ):
                continue
            result.append(
                {
                    "thread_id": thread_id,
                    "summary_text": resolution["summary_text"],
                    "closed_at": None,
                    "source": resolution.get("source"),
                    "version": resolution.get("version"),
                }
            )
        return result[:limit]


class _LifecycleRepo:
    def __init__(self, read: _ReadRepo) -> None:
        self.read = read

    async def close_manager_ticket(self, thread_id: str) -> None:
        self.read.views[thread_id].status = "closed"


class _MessagesRepo:
    def __init__(self) -> None:
        self.messages: dict[str, list[dict[str, object]]] = {}

    async def append_manager_reply_message(self, thread_id: str, content: str) -> None:
        self.messages.setdefault(thread_id, []).append(
            {"role": "manager", "content": content}
        )

    async def get_messages(self, thread_id: str, _limit: int = 30, _offset: int = 0):
        return list(self.messages.get(thread_id, []))

    async def get_messages_for_langgraph(
        self, thread_id: str, limit: int | None = None
    ):
        messages = list(self.messages.get(thread_id, []))
        return messages[-limit:] if limit else messages


class _Events:
    def __init__(self) -> None:
        self.events: dict[str, list[dict[str, object]]] = {}

    async def emit_event(
        self,
        *,
        stream_id: str,
        project_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        self.events.setdefault(stream_id, []).append(
            {"project_id": project_id, "event_type": event_type, "payload": payload}
        )

    async def get_events_for_thread(
        self, thread_id: str, _limit: int = 30, _offset: int = 0
    ):
        return list(self.events.get(thread_id, []))


class _Projects:
    def __init__(self, *, target_language: str = "ru") -> None:
        self.target_language = target_language

    async def get_bot_token(self, _project_id: str) -> str:
        return "telegram-token"

    async def get_user_display_name(self, _user_id: str) -> str:
        return "Manager"

    async def get_project_configuration_view(self, project_id: str):
        return ProjectConfigurationView(
            project_id=project_id,
            settings={"target_language": self.target_language},
        )


class _Telegram:
    async def post_json(self, *_args, **_kwargs):
        return {"ok": True}


class _Response:
    content = (
        '{"answer":"Менеджер уже обещал отправить расчёт.",'
        '"answerability":"supported","supporting_evidence_refs":[],'
        '"unsupported_aspects":[]}'
    )


class _CapturingLlm:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def ainvoke(self, messages):
        self.prompts.append(messages[-1][1])
        return _Response()


class _Generator:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.payloads = []

    async def generate_ticket_resolution(self, payload):
        if self.fail:
            raise RuntimeError("summary failed")
        assert payload.messages
        self.payloads.append(payload)
        if payload.target_language == "en":
            return TicketResolutionSummary(
                summary_text="The manager promised to send a price estimate.",
                discussed_questions=["Price"],
                resolved_questions=["The manager will send an estimate"],
                manager_decisions=["Send the estimate to the customer"],
            )
        return TicketResolutionSummary(
            summary_text="Менеджер пообещал отправить расчёт цены.",
            discussed_questions=["Цена"],
            resolved_questions=["Менеджер отправит расчёт"],
            manager_decisions=["Отправить расчёт клиенту"],
        )


async def _run_close_flow(*, fail: bool = False, target_language: str = "ru"):
    runtime = _RuntimeRepo()
    read = _ReadRepo(runtime)
    messages = _MessagesRepo()
    events = _Events()
    projects = _Projects(target_language=target_language)
    generator = _Generator(fail=fail)
    resolution_service = TicketResolutionService(
        thread_runtime_state_repo=runtime,
        thread_read_repo=read,
        thread_message_repo=messages,
        event_repo=events,
        project_configuration_repo=projects,
        summary_generator=generator,
    )
    manager_service = ManagerReplyService(
        projects=projects,
        threads=_LifecycleRepo(read),
        thread_messages=messages,
        thread_read=read,
        thread_runtime_state=runtime,
        ticket_resolution_service=resolution_service,
        telegram_client=_Telegram(),
        event_emitter=events,
        logger=SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None),
    )

    await manager_service.manager_reply(
        OLD_THREAD_ID,
        "Отправлю расчёт цены после уточнения.",
        manager_user_id=str(uuid4()),
    )
    await manager_service.close_thread_for_manager(OLD_THREAD_ID)
    return runtime, read, messages, generator


@pytest.mark.asyncio
async def test_manager_close_generates_resolution_loaded_into_next_response_prompt():
    runtime, read, messages, generator = await _run_close_flow()

    assert [(call["status"], call["version"]) for call in runtime.calls] == [
        ("pending", 1),
        ("generated", 2),
    ]
    assert generator.payloads[0].target_language == "ru"

    load_state = create_load_state_node(
        thread_read_repo=read,
        thread_message_repo=messages,
        thread_runtime_state_repo=runtime,
        project_repo=SimpleNamespace(),
    )
    state = await load_state({"thread_id": NEW_THREAD_ID})

    assert state["recent_ticket_resolutions"][0]["summary_text"] == (
        "Менеджер пообещал отправить расчёт цены."
    )
    llm = _CapturingLlm()
    response_node = create_response_generator_node(llm=llm, model_name="base-model")
    await response_node(
        {
            **state,
            "decision": "LLM_GENERATE",
            "generation_mode": "CONVERSATIONAL_RESPONSE",
            "user_input": "Что с ценой?",
            "knowledge_chunks": [],
            "knowledge_retrieval_status": "skipped",
            "project_configuration": {"settings": {"target_language": "ru"}},
        }
    )
    assert "Менеджер пообещал отправить расчёт цены." in llm.prompts[0]


@pytest.mark.asyncio
async def test_failed_resolution_is_not_loaded_as_resolved_case_for_new_thread():
    runtime, read, messages, _generator = await _run_close_flow(fail=True)

    assert [(call["status"], call["version"]) for call in runtime.calls] == [
        ("pending", 1),
        ("failed", 2),
    ]

    load_state = create_load_state_node(
        thread_read_repo=read,
        thread_message_repo=messages,
        thread_runtime_state_repo=runtime,
        project_repo=SimpleNamespace(),
    )
    state = await load_state({"thread_id": NEW_THREAD_ID})

    assert state["recent_ticket_resolutions"] == []


@pytest.mark.asyncio
async def test_manager_close_generates_english_resolution_for_english_project():
    runtime, _read, _messages, generator = await _run_close_flow(target_language="en")

    assert generator.payloads[0].target_language == "en"
    assert runtime.resolutions[OLD_THREAD_ID]["status"] == "generated"
    assert runtime.resolutions[OLD_THREAD_ID]["summary_text"] == (
        "The manager promised to send a price estimate."
    )
