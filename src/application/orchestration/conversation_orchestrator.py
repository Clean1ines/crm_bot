"""
Conversation orchestrator composition root.

The heavy logic lives in small orchestration services. This class remains the
public application service used by existing HTTP/Telegram entrypoints.
"""

from src.application.ports.cache_port import CacheFactoryPort
from src.application.ports.lock_port import NullThreadLock, ThreadLockPort
from src.application.ports.agent_runtime_port import AgentFactoryPort
from src.application.ports.logger_port import LoggerPort, NullLogger
from src.application.services.project_runtime_guards import ProjectRuntimeGuards
from src.utils.uuid_utils import ensure_uuid

from src.application.orchestration.client_message_service import ClientMessageService
from src.application.orchestration.graph_factory import GraphExecutor, GraphFactory
from src.domain.runtime.state_contracts import RuntimeHistoryMessage
from src.application.orchestration.manager_reply_service import ManagerReplyService
from src.application.orchestration.project_runtime_loader import ProjectRuntimeLoader
from src.application.orchestration.transport_sender_port import (
    NullTelegramClient,
    TelegramClientPort,
)


class EventEmitter:
    def __init__(self, *, event_repo=None, logger=None) -> None:
        self.event_repo = event_repo
        self.logger = logger or NullLogger()

    async def emit_event(
        self,
        stream_id: str,
        project_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        if self.event_repo is None:
            return

        stream_id = str(stream_id)
        try:
            await self.event_repo.append(
                stream_id=ensure_uuid(stream_id),
                project_id=ensure_uuid(project_id),
                event_type=event_type,
                payload=payload,
            )
            self.logger.debug(
                "Event emitted",
                extra={"stream_id": stream_id, "event_type": event_type},
            )
        except Exception as exc:
            self.logger.error(
                "Failed to emit event",
                extra={
                    "stream_id": stream_id,
                    "event_type": event_type,
                    "error": str(exc),
                },
            )


class ConversationOrchestrator:
    SUMMARY_THRESHOLD = 20
    RECENT_MESSAGES_LIMIT = 10

    def __init__(
        self,
        db_conn,
        project_repo,
        thread_lifecycle_repo,
        thread_message_repo,
        thread_runtime_state_repo,
        thread_read_repo,
        queue_repo,
        event_repo=None,
        tool_registry=None,
        memory_repo=None,
        *,
        cache_factory: CacheFactoryPort | None = None,
        thread_lock: ThreadLockPort | None = None,
        telegram_client: TelegramClientPort | None = None,
        logger: LoggerPort | None = None,
        agent_factory: AgentFactoryPort | None = None,
    ):
        self.db = db_conn
        self.projects = project_repo
        self.queue_repo = queue_repo
        self.event_repo = event_repo
        self.tool_registry = tool_registry
        self.memory_repo = memory_repo
        self.cache_factory = cache_factory
        self.thread_lock = thread_lock or NullThreadLock()
        self.telegram_client = telegram_client or NullTelegramClient()
        self.logger = logger or NullLogger()

        self.runtime_guards = ProjectRuntimeGuards(
            cache_factory=cache_factory, logger=self.logger
        )
        self.event_emitter = EventEmitter(event_repo=event_repo, logger=self.logger)
        self.runtime_loader = ProjectRuntimeLoader(
            projects=project_repo, logger=self.logger
        )
        if agent_factory is None:
            raise ValueError("agent_factory is required")

        self.graph_factory = GraphFactory(
            agent_factory=agent_factory,
            tool_registry=tool_registry,
            thread_lifecycle_repo=thread_lifecycle_repo,
            thread_message_repo=thread_message_repo,
            thread_runtime_state_repo=thread_runtime_state_repo,
            thread_read_repo=thread_read_repo,
            queue_repo=queue_repo,
            event_repo=event_repo,
            project_repo=project_repo,
            memory_repo=memory_repo,
            logger=self.logger,
        )
        self.graph_executor = GraphExecutor(logger=self.logger)
        self.client_messages = ClientMessageService(
            threads=thread_lifecycle_repo,
            queue_repo=queue_repo,
            runtime_guards=self.runtime_guards,
            runtime_loader=self.runtime_loader,
            graph_factory=self.graph_factory,
            graph_executor=self.graph_executor,
            thread_lock=self.thread_lock,
            cache_factory=cache_factory,
            event_emitter=self.event_emitter,
            logger=self.logger,
        )
        self.manager_replies = ManagerReplyService(
            projects=project_repo,
            threads=thread_lifecycle_repo,
            telegram_client=self.telegram_client,
            event_emitter=self.event_emitter,
            logger=self.logger,
        )

        # Backward-compatible attribute used by tests and older call sites.
        self.agent = self.graph_factory.agent

        self.logger.debug("ConversationOrchestrator initialized")

    async def _emit_event(
        self,
        stream_id: str,
        project_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        await self.event_emitter.emit_event(stream_id, project_id, event_type, payload)

    def _build_graph_from_json(self, graph_json):
        return self.graph_factory.build_graph_from_json(graph_json)

    async def _get_graph_for_project(self, project_id: str):
        return await self.graph_factory.get_graph_for_project(project_id)

    async def _load_project_configuration(self, project_id: str):
        return await self.runtime_loader.load_project_configuration(project_id)

    @staticmethod
    def _outcome(text: str, *, delivered: bool = False):
        return GraphExecutor.outcome(text, delivered=delivered)

    def _trim_recent_history(
        self, recent_messages: list[RuntimeHistoryMessage]
    ) -> list[RuntimeHistoryMessage]:
        return self.graph_executor.trim_recent_history(recent_messages)

    def _create_graph_execution_request(self, **kwargs):
        return self.graph_executor.create_graph_execution_request(**kwargs)

    def _build_agent_state(self, *, request):
        return self.graph_executor.build_agent_state(request=request)

    def _extract_graph_result(self, result_state, *, question: str, thread_id: str):
        return self.graph_executor.extract_graph_result(
            result_state, question=question, thread_id=thread_id
        )

    async def _invoke_graph(self, *, graph, request):
        return await self.graph_executor.invoke_graph(graph=graph, request=request)

    async def _cache(self):
        return await self.client_messages.cache()

    async def process_message(
        self,
        project_id: str,
        chat_id: int,
        text: str,
        username: str | None = None,
        full_name: str | None = None,
        source: str = "telegram",
    ) -> str:
        return await self.client_messages.process_message(
            project_id=project_id,
            chat_id=chat_id,
            text=text,
            username=username,
            full_name=full_name,
            source=source,
        )

    async def resolve_manager_user_id_by_telegram(
        self,
        project_id: str,
        manager_chat_id: str,
    ) -> str | None:
        return await self.manager_replies.resolve_manager_user_id_by_telegram(
            project_id, manager_chat_id
        )

    async def _resolve_manager_display_name(
        self,
        *,
        project_id: str,
        manager_chat_id: str | None,
        manager_user_id: str | None,
    ) -> str:
        return await self.manager_replies.resolve_manager_display_name(
            project_id=project_id,
            manager_chat_id=manager_chat_id,
            manager_user_id=manager_user_id,
        )

    async def manager_reply(
        self,
        thread_id: str,
        manager_text: str,
        manager_chat_id: str | None = None,
        manager_user_id: str | None = None,
    ) -> bool:
        return await self.manager_replies.manager_reply(
            thread_id=thread_id,
            manager_text=manager_text,
            manager_chat_id=manager_chat_id,
            manager_user_id=manager_user_id,
        )
