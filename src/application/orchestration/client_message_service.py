"""
Client message orchestration.
"""

import asyncio
import re
import uuid
from typing import Optional

from src.application.ports.cache_port import NullCache
from src.domain.project_plane.manager_assignments import ManagerReplySession
from src.domain.project_plane.thread_runtime import ThreadRuntimeSnapshot
from src.domain.project_plane.thread_status import ThreadStatus

THREAD_ALREADY_PROCESSING_TEXT = "Your request is already being processed. Please wait a moment."
PROJECT_RATE_LIMIT_TEXT = "This project is receiving too many messages right now. Please try again later."
PROJECT_CONCURRENCY_LIMIT_TEXT = (
    "This project already has too many active conversations in progress. Please try again later."
)
MANAGER_HANDOFF_TEXT = "Your message has been handed off to a manager. Please wait for a reply."


def split_questions(text: str) -> list[str]:
    parts = re.split(r"[?!\n]+", text)
    return [part.strip() for part in parts if part.strip()]


class ClientMessageService:
    def __init__(
        self,
        *,
        threads,
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
        username: Optional[str] = None,
        full_name: Optional[str] = None,
        source: str = "telegram",
    ) -> str:
        self.logger.info(
            "Processing message",
            extra={"project_id": project_id, "chat_id": chat_id, "text_preview": text[:50]},
        )

        client_id = await self.threads.get_or_create_client(
            project_id,
            chat_id,
            username=username,
            source=source,
            full_name=full_name,
        )
        thread_id = await self.threads.get_active_thread(client_id) or await self.threads.create_thread(client_id)
        thread_id_str = str(thread_id)

        lock_acquired = await self.thread_lock.acquire_thread_lock(thread_id_str)
        if not lock_acquired:
            self.logger.warning("Could not acquire lock for thread", extra={"thread_id": thread_id_str})
            return self.graph_executor.outcome(THREAD_ALREADY_PROCESSING_TEXT).text

        try:
            project_runtime_context = await self.runtime_loader.load_project_configuration(project_id)

            if not await self.runtime_guards.allow_request(project_id, project_runtime_context.to_dict()):
                self.logger.warning(
                    "Project request limit exceeded",
                    extra={"project_id": project_id, "thread_id": thread_id_str},
                )
                return self.graph_executor.outcome(PROJECT_RATE_LIMIT_TEXT).text

            thread_slot_acquired = await self.runtime_guards.try_acquire_thread_slot(
                project_id,
                thread_id_str,
                project_runtime_context.to_dict(),
            )
            if not thread_slot_acquired:
                self.logger.warning(
                    "Project concurrent thread limit exceeded",
                    extra={"project_id": project_id, "thread_id": thread_id_str},
                )
                return self.graph_executor.outcome(PROJECT_CONCURRENCY_LIMIT_TEXT).text

            redis = await self.cache()
            awaiting_reply_key = f"awaiting_reply_thread:{thread_id_str}"
            awaiting_reply_session = await redis.get(awaiting_reply_key)
            manager_session = ManagerReplySession.from_redis_value(
                thread_id=thread_id_str,
                raw_value=awaiting_reply_session,
            )

            if manager_session and manager_session.manager_chat_id:
                thread_view = await self.threads.get_thread_with_project_view(thread_id_str)
                thread_snapshot = ThreadRuntimeSnapshot.from_record(
                    thread_view.to_record() if thread_view else None
                )
                if thread_snapshot and thread_snapshot.status == ThreadStatus.ACTIVE.value:
                    await redis.delete(awaiting_reply_key)
                    self.logger.info("Stale awaiting_reply key deleted for thread", extra={"thread_id": thread_id_str})
                    manager_session = None

            if manager_session and manager_session.manager_chat_id:
                self.logger.info("Message redirected to manager (thread in reply session)", extra={"thread_id": thread_id_str})
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
                return self.graph_executor.outcome(MANAGER_HANDOFF_TEXT).text

            await self.threads.add_message(thread_id, role="user", content=text)

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

            questions = split_questions(text) or [text]
            self.logger.debug(f"Split message into {len(questions)} questions", extra={"thread_id": thread_id_str})

            responses = []
            for question in questions:
                recent_messages = self.graph_executor.trim_recent_history(
                    await self.threads.get_messages_for_langgraph(thread_id)
                )
                graph_request = self.graph_executor.create_graph_execution_request(
                    project_id=project_id,
                    thread_id=thread_id_str,
                    chat_id=chat_id,
                    question=question,
                    recent_history=recent_messages,
                    runtime_context=project_runtime_context,
                    trace_id=uuid.uuid4().hex,
                )

                graph = await self.graph_factory.get_graph_for_project(project_id)
                if graph is None:
                    self.logger.error("Failed to load graph for project", extra={"project_id": project_id})
                    responses.append("Something went wrong while processing the request.")
                    continue

                graph_outcome = await self.graph_executor.invoke_graph(
                    graph=graph,
                    request=graph_request,
                )
                if graph_outcome.delivered:
                    continue
                responses.append(graph_outcome.text)

            if not responses:
                return self.graph_executor.outcome("", delivered=True).text

            combined_response = "\n\n".join(responses)
            self.logger.info(
                "All questions processed",
                extra={"thread_id": thread_id_str, "response_count": len(responses)},
            )
            return self.graph_executor.outcome(combined_response).text

        finally:
            await self.runtime_guards.release_thread_slot(project_id, thread_id_str)
            await self.thread_lock.release_thread_lock(thread_id_str)
