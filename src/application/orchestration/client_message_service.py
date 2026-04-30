"""
Client message orchestration.
"""

import asyncio
import re
import uuid

from src.application.ports.cache_port import NullCache
from src.domain.project_plane.manager_assignments import ManagerReplySession
from src.domain.project_plane.thread_runtime import ThreadRuntimeSnapshot
from src.domain.project_plane.thread_status import ThreadStatus

THREAD_ALREADY_PROCESSING_TEXT = (
    "Your request is already being processed. Please wait a moment."
)
PROJECT_RATE_LIMIT_TEXT = (
    "This project is receiving too many messages right now. Please try again later."
)
PROJECT_CONCURRENCY_LIMIT_TEXT = "This project already has too many active conversations in progress. Please try again later."
MANAGER_HANDOFF_TEXT = (
    "Your message has been handed off to a manager. Please wait for a reply."
)
GRAPH_FAILURE_TEXT = "Something went wrong while processing the request."


def split_questions(text: str) -> list[str]:
    parts = re.split(r"[?!\n]+", text)
    return [part.strip() for part in parts if part.strip()]


class ClientMessageService:
    def __init__(
        self,
        *,
        threads,
        thread_messages=None,
        thread_read=None,
        queue_repo,
        runtime_guards,
        runtime_loader,
        graph_factory,
        graph_executor,
        thread_lock,
        cache_factory,
        event_emitter,
        logger,
    ) -> None:
        self.threads = threads
        self.thread_messages = thread_messages or threads
        self.thread_read = thread_read or threads
        self.queue_repo = queue_repo
        self.runtime_guards = runtime_guards
        self.runtime_loader = runtime_loader
        self.graph_factory = graph_factory
        self.graph_executor = graph_executor
        self.thread_lock = thread_lock
        self.cache_factory = cache_factory
        self.event_emitter = event_emitter
        self.logger = logger

    async def cache(self):
        if self.cache_factory is None:
            return NullCache()
        return await self.cache_factory()

    async def process_message(
        self,
        project_id: str,
        chat_id: int,
        text: str,
        username: str | None = None,
        full_name: str | None = None,
        source: str = "telegram",
    ) -> str:
        self._log_processing_started(project_id, chat_id, text)

        client_id = await self._get_or_create_client(
            project_id,
            chat_id,
            username=username,
            full_name=full_name,
            source=source,
        )
        thread_id = await self._get_or_create_thread(client_id)
        thread_id_str = str(thread_id)

        lock_acquired = await self.thread_lock.acquire_thread_lock(thread_id_str)
        if not lock_acquired:
            return self._locked_response(thread_id_str)

        try:
            return await self._process_locked_message(
                project_id=project_id,
                chat_id=chat_id,
                text=text,
                thread_id=thread_id,
                thread_id_str=thread_id_str,
            )
        finally:
            await self.thread_lock.release_thread_lock(thread_id_str)

    def _log_processing_started(self, project_id: str, chat_id: int, text: str) -> None:
        self.logger.info(
            "Processing message",
            extra={
                "project_id": project_id,
                "chat_id": chat_id,
                "text_preview": text[:50],
            },
        )

    async def _get_or_create_client(
        self,
        project_id: str,
        chat_id: int,
        *,
        username: str | None,
        full_name: str | None,
        source: str,
    ):
        return await self.threads.get_or_create_client(
            project_id,
            chat_id,
            username=username,
            source=source,
            full_name=full_name,
        )

    async def _get_or_create_thread(self, client_id):
        return await self.threads.get_active_thread(
            client_id
        ) or await self.threads.create_thread(client_id)

    def _locked_response(self, thread_id: str) -> str:
        self.logger.warning(
            "Could not acquire lock for thread",
            extra={"thread_id": thread_id},
        )
        return self.graph_executor.outcome(THREAD_ALREADY_PROCESSING_TEXT).text

    async def _process_locked_message(
        self,
        *,
        project_id: str,
        chat_id: int,
        text: str,
        thread_id,
        thread_id_str: str,
    ) -> str:
        runtime_context = await self.runtime_loader.load_project_configuration(
            project_id
        )
        runtime_payload = runtime_context.to_dict()

        if not await self._request_allowed(project_id, thread_id_str, runtime_payload):
            return self.graph_executor.outcome(PROJECT_RATE_LIMIT_TEXT).text

        slot_acquired = await self._acquire_thread_slot(
            project_id, thread_id_str, runtime_payload
        )
        if not slot_acquired:
            return self.graph_executor.outcome(PROJECT_CONCURRENCY_LIMIT_TEXT).text

        try:
            return await self._process_with_thread_slot(
                project_id=project_id,
                chat_id=chat_id,
                text=text,
                thread_id=thread_id,
                thread_id_str=thread_id_str,
                runtime_context=runtime_context,
            )
        finally:
            await self.runtime_guards.release_thread_slot(project_id, thread_id_str)

    async def _request_allowed(
        self, project_id: str, thread_id: str, runtime_payload: dict[str, object]
    ) -> bool:
        allowed = await self.runtime_guards.allow_request(project_id, runtime_payload)
        if not allowed:
            self.logger.warning(
                "Project request limit exceeded",
                extra={"project_id": project_id, "thread_id": thread_id},
            )
        return bool(allowed)

    async def _acquire_thread_slot(
        self, project_id: str, thread_id: str, runtime_payload: dict[str, object]
    ) -> bool:
        acquired = await self.runtime_guards.try_acquire_thread_slot(
            project_id,
            thread_id,
            runtime_payload,
        )
        if not acquired:
            self.logger.warning(
                "Project concurrent thread limit exceeded",
                extra={"project_id": project_id, "thread_id": thread_id},
            )
        return bool(acquired)

    async def _process_with_thread_slot(
        self,
        *,
        project_id: str,
        chat_id: int,
        text: str,
        thread_id,
        thread_id_str: str,
        runtime_context,
    ) -> str:
        manager_response = await self._try_redirect_to_manager(
            project_id=project_id,
            thread_id_str=thread_id_str,
            text=text,
        )
        if manager_response is not None:
            return manager_response

        await self._record_user_message(
            project_id=project_id,
            chat_id=chat_id,
            text=text,
            thread_id=thread_id,
            thread_id_str=thread_id_str,
        )
        return await self._process_questions(
            project_id=project_id,
            chat_id=chat_id,
            text=text,
            thread_id=thread_id,
            thread_id_str=thread_id_str,
            runtime_context=runtime_context,
        )

    async def _try_redirect_to_manager(
        self, *, project_id: str, thread_id_str: str, text: str
    ) -> str | None:
        redis = await self.cache()
        awaiting_reply_key = f"awaiting_reply_thread:{thread_id_str}"
        raw_session = await redis.get(awaiting_reply_key)
        manager_session = ManagerReplySession.from_redis_value(
            thread_id=thread_id_str,
            raw_value=raw_session,
        )

        manager_session = await self._clear_stale_manager_session(
            redis=redis,
            awaiting_reply_key=awaiting_reply_key,
            thread_id_str=thread_id_str,
            manager_session=manager_session,
        )
        if not manager_session or not manager_session.manager_chat_id:
            return None

        await self._enqueue_manager_notification(
            project_id=project_id,
            thread_id_str=thread_id_str,
            text=text,
            manager_session=manager_session,
        )
        return self.graph_executor.outcome(MANAGER_HANDOFF_TEXT).text

    async def _clear_stale_manager_session(
        self,
        *,
        redis,
        awaiting_reply_key: str,
        thread_id_str: str,
        manager_session: ManagerReplySession | None,
    ) -> ManagerReplySession | None:
        if not manager_session or not manager_session.manager_chat_id:
            return manager_session

        thread_view = await self.thread_read.get_thread_with_project_view(thread_id_str)
        thread_snapshot = ThreadRuntimeSnapshot.from_record(
            thread_view.to_record() if thread_view else None
        )
        if not thread_snapshot or thread_snapshot.status != ThreadStatus.ACTIVE.value:
            return manager_session

        await redis.delete(awaiting_reply_key)
        self.logger.info(
            "Stale awaiting_reply key deleted for thread",
            extra={"thread_id": thread_id_str},
        )
        return None

    async def _enqueue_manager_notification(
        self,
        *,
        project_id: str,
        thread_id_str: str,
        text: str,
        manager_session: ManagerReplySession,
    ) -> None:
        self.logger.info(
            "Message redirected to manager (thread in reply session)",
            extra={"thread_id": thread_id_str},
        )
        await self.queue_repo.enqueue(
            task_type="notify_manager",
            payload={
                "thread_id": thread_id_str,
                "project_id": project_id,
                "message": text,
                "target_manager_telegram_chat_id": manager_session.manager_chat_id,
                "manager_user_id": manager_session.manager_user_id or None,
            },
        )

    async def _record_user_message(
        self,
        *,
        project_id: str,
        chat_id: int,
        text: str,
        thread_id,
        thread_id_str: str,
    ) -> None:
        await self.thread_messages.add_message(thread_id, role="user", content=text)
        await self.event_emitter.emit_event(
            stream_id=thread_id_str,
            project_id=project_id,
            event_type="message_received",
            payload={
                "chat_id": chat_id,
                "text": text,
                "timestamp": asyncio.get_event_loop().time(),
            },
        )

    async def _process_questions(
        self,
        *,
        project_id: str,
        chat_id: int,
        text: str,
        thread_id,
        thread_id_str: str,
        runtime_context,
    ) -> str:
        questions = split_questions(text) or [text]
        self.logger.debug(
            f"Split message into {len(questions)} questions",
            extra={"thread_id": thread_id_str},
        )

        responses = await self._collect_question_responses(
            project_id=project_id,
            chat_id=chat_id,
            thread_id=thread_id,
            thread_id_str=thread_id_str,
            runtime_context=runtime_context,
            questions=questions,
        )
        return self._final_response(thread_id_str, responses)

    async def _collect_question_responses(
        self,
        *,
        project_id: str,
        chat_id: int,
        thread_id,
        thread_id_str: str,
        runtime_context,
        questions: list[str],
    ) -> list[str]:
        responses: list[str] = []
        for question in questions:
            response = await self._process_single_question(
                project_id=project_id,
                chat_id=chat_id,
                thread_id=thread_id,
                thread_id_str=thread_id_str,
                runtime_context=runtime_context,
                question=question,
            )
            if response is not None:
                responses.append(response)
        return responses

    async def _process_single_question(
        self,
        *,
        project_id: str,
        chat_id: int,
        thread_id,
        thread_id_str: str,
        runtime_context,
        question: str,
    ) -> str | None:
        graph = await self.graph_factory.get_graph_for_project(project_id)
        if graph is None:
            self.logger.error(
                "Failed to load graph for project", extra={"project_id": project_id}
            )
            return GRAPH_FAILURE_TEXT

        graph_request = await self._create_graph_request(
            project_id=project_id,
            chat_id=chat_id,
            thread_id=thread_id,
            thread_id_str=thread_id_str,
            runtime_context=runtime_context,
            question=question,
        )
        graph_outcome = await self.graph_executor.invoke_graph(
            graph=graph,
            request=graph_request,
        )
        return None if graph_outcome.delivered else graph_outcome.text

    async def _create_graph_request(
        self,
        *,
        project_id: str,
        chat_id: int,
        thread_id,
        thread_id_str: str,
        runtime_context,
        question: str,
    ):
        recent_messages = self.graph_executor.trim_recent_history(
            await self.thread_messages.get_messages_for_langgraph(thread_id)
        )
        return self.graph_executor.create_graph_execution_request(
            project_id=project_id,
            thread_id=thread_id_str,
            chat_id=chat_id,
            question=question,
            recent_history=recent_messages,
            runtime_context=runtime_context,
            trace_id=uuid.uuid4().hex,
        )

    def _final_response(self, thread_id: str, responses: list[str]) -> str:
        if not responses:
            return self.graph_executor.outcome("", delivered=True).text

        combined_response = "\n\n".join(responses)
        self.logger.info(
            "All questions processed",
            extra={"thread_id": thread_id, "response_count": len(responses)},
        )
        return self.graph_executor.outcome(combined_response).text
