"""
Orchestrator service: ties together project, thread, and agent logic.

This module orchestrates message processing, event emission, and workflow
execution for the AI bot platform.
"""

import asyncio
import uuid
import json
import httpx
from typing import Optional, Dict, Any

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from src.agent.graph import create_agent
from src.database.models import ThreadStatus
from src.database.repositories.queue_repository import QueueRepository
from src.services.summarizer import SummarizerService
from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class OrchestratorService:
    """
    Service for orchestrating conversation flow and agent execution.
    
    Coordinates project settings, thread management, LangGraph agent
    execution, event emission, and escalation to human managers.
    
    Attributes:
        db: Database connection pool.
        projects: ProjectRepository instance.
        threads: ThreadRepository instance.
        queue_repo: QueueRepository instance.
        event_repo: EventRepository instance (optional for event sourcing).
        tool_registry: ToolRegistry instance (optional for dynamic tools).
        agent: Compiled LangGraph agent.
        summarizer: SummarizerService for conversation summaries.
    """
    
    # Constants for context management
    SUMMARY_THRESHOLD = 20          # Messages count before triggering summarization
    RECENT_MESSAGES_LIMIT = 10      # Recent messages to include with summary
    
    def __init__(
        self, 
        db_conn, 
        project_repo, 
        thread_repo, 
        queue_repo,
        event_repo=None,
        tool_registry=None
    ):
        """
        Initialize the OrchestratorService with required dependencies.
        
        Args:
            db_conn: Database connection pool.
            project_repo: ProjectRepository instance.
            thread_repo: ThreadRepository instance.
            queue_repo: QueueRepository instance.
            event_repo: Optional EventRepository for event sourcing.
            tool_registry: Optional ToolRegistry for dynamic tool execution.
        """
        self.db = db_conn
        self.projects = project_repo
        self.threads = thread_repo
        self.queue_repo = queue_repo
        self.event_repo = event_repo
        self.tool_registry = tool_registry
        # Pass tool_registry to agent creation for dynamic tool support
        self.agent = create_agent(tool_registry=tool_registry)
        self.summarizer = SummarizerService()
        logger.debug("OrchestratorService initialized")

    async def _emit_event(
        self,
        stream_id: str,
        project_id: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> None:
        """
        Emit an event to the event store if configured.
        
        This method is a no-op if event_repo is not set, allowing
        gradual migration to event-sourced architecture.
        
        Args:
            stream_id: Conversation/thread ID.
            project_id: Project ID for multi-tenant isolation.
            event_type: Type of event (e.g., 'message_received').
            payload: Event-specific data.
        """
        if self.event_repo is None:
            return
        
        try:
            await self.event_repo.append(
                stream_id=uuid.UUID(stream_id),
                project_id=uuid.UUID(project_id),
                event_type=event_type,
                payload=payload
            )
            logger.debug(
                "Event emitted",
                extra={"stream_id": stream_id, "event_type": event_type}
            )
        except Exception as e:
            logger.error(
                "Failed to emit event",
                extra={"stream_id": stream_id, "event_type": event_type, "error": str(e)}
            )

    async def _get_graph_for_project(self, project_id: str):
        """
        Get the appropriate LangGraph for a project.
        
        Priority order:
        1. Custom workflow (if project is in Pro mode)
        2. Template workflow (if template_slug is set)
        3. Default agent graph
        
        Args:
            project_id: UUID проекта в строковом формате.
        
        Returns:
            Compiled LangGraph or None if error.
        """
        # Check for custom workflow (Pro mode)
        is_pro = await self.projects.get_is_pro_mode(project_id)
        if is_pro:
            # TODO: Load custom workflow from workflows table
            # For now, fall through to template/default
            logger.debug("Pro mode enabled, checking for custom workflow", extra={"project_id": project_id})
        
        # Check for template
        template_slug = await self.projects.get_template_slug(project_id)
        if template_slug:
            logger.info(
                "Loading workflow from template",
                extra={"project_id": project_id, "template_slug": template_slug}
            )
            # TODO: Load graph_json from workflow_templates and build LangGraph
            # For now, use default agent
            return self.agent
        
        # Default: use the standard agent
        logger.debug("Using default agent graph", extra={"project_id": project_id})
        return self.agent

    async def process_message(self, project_id: str, chat_id: int, text: str) -> str:
        """
        Process an incoming message from a client.
        
        This is the main entry point for conversation handling:
        1. Load project settings
        2. Register client/thread
        3. Save incoming message
        4. Emit message_received event
        5. Execute agent workflow
        6. Handle escalation or return AI response
        7. Emit ai_replied or ticket_created event
        
        Args:
            project_id: UUID проекта в строковом формате.
            chat_id: Telegram chat_id клиента.
            text: Текст сообщения.
        
        Returns:
            Response text to send back to the client.
        """
        logger.info(
            "Processing message",
            extra={"project_id": project_id, "chat_id": chat_id, "text_preview": text[:50]}
        )
        
        # 1. Получаем промпт проекта
        project = await self.projects.get_project_settings(project_id)
        sys_prompt = project.get('system_prompt', "Ты помощник.")

        # 2. Регистрируем клиента/тред
        client_id = await self.threads.get_or_create_client(project_id, chat_id)
        thread_id = await self.threads.get_active_thread(client_id) or await self.threads.create_thread(client_id)
        thread_id_str = str(thread_id)

        # 3. Сохраняем входящее сообщение
        await self.threads.add_message(thread_id, role="user", content=text)

        # 4. Emit event: message_received
        await self._emit_event(
            stream_id=thread_id_str,
            project_id=project_id,
            event_type="message_received",
            payload={
                "chat_id": chat_id,
                "text": text,
                "timestamp": asyncio.get_event_loop().time()
            }
        )

        # 5. Получаем полную историю сообщений треда
        full_history = await self.threads.get_messages_for_langgraph(thread_id)

        # 6. Проверяем, нужно ли запустить фоновую суммаризацию
        if len(full_history) > self.SUMMARY_THRESHOLD:
            #asyncio.create_task(self._summarize_history(thread_id))
            logger.info("Scheduled background summarization", extra={"thread_id": thread_id_str})

        # 7. Получаем thread с summary
        thread_data = await self.threads.get_thread_with_project(thread_id)
        summary = thread_data.get("context_summary") if thread_data else None

        # 8. Формируем сообщения для агента
        messages = [SystemMessage(content=sys_prompt)]

        if summary:
            messages.append(SystemMessage(content=f"Краткое содержание предыдущего диалога:\n{summary}"))

        # Берём последние N сообщений из истории
        recent_messages = full_history[-self.RECENT_MESSAGES_LIMIT:] if full_history else []
        for m in recent_messages:
            if m['role'] == 'user':
                messages.append(HumanMessage(content=m['content']))
            elif m['role'] == 'assistant':
                messages.append(AIMessage(content=m['content']))

        # 9. Get appropriate graph for this project
        graph = await self._get_graph_for_project(project_id)
        if graph is None:
            logger.error("Failed to load graph for project", extra={"project_id": project_id})
            return "Произошла ошибка обработки запроса."

        # 10. Запускаем агента
        result = await graph.ainvoke({
            "messages": messages,
            "project_id": project_id,
            "thread_id": thread_id_str,
            "escalation_requested": False
        })

        # 11. Проверяем, нужно ли эскалировать
        if result.get("escalation_requested"):
            # Меняем статус треда на MANUAL
            await self.threads.update_status(thread_id, ThreadStatus.MANUAL)

            # Ставим задачу в очередь для уведомления менеджера
            await self.queue_repo.enqueue(
                task_type="notify_manager",
                payload={
                    "thread_id": thread_id_str,
                    "chat_id": chat_id,
                    "message": text
                }
            )

            # Emit event: ticket_created
            await self._emit_event(
                stream_id=thread_id_str,
                project_id=project_id,
                event_type="ticket_created",
                payload={
                    "reason": "User requested human help or AI could not answer",
                    "manager_notified": True
                }
            )

            # Возвращаем пользователю сообщение о передаче оператору
            response = "Ваш вопрос передан менеджеру, ожидайте ответа."
            await self.threads.add_message(thread_id, role="assistant", content=response)
            return response

        # 12. Иначе сохраняем и возвращаем ответ ассистента
        ai_text = result["messages"][-1].content
        await self.threads.add_message(thread_id, role="assistant", content=ai_text)
        
        # Emit event: ai_replied
        await self._emit_event(
            stream_id=thread_id_str,
            project_id=project_id,
            event_type="ai_replied",
            payload={
                "text": ai_text,
                "model": settings.GROQ_MODEL if hasattr(settings, 'GROQ_MODEL') else 'unknown'
            }
        )
        
        logger.info("Message processed successfully", extra={"thread_id": thread_id_str})
        return ai_text

    async def manager_reply(self, thread_id: str, manager_text: str) -> bool:
        """
        Отправляет ответ менеджера клиенту по указанному треду.
        
        Args:
            thread_id: UUID треда в строковом формате.
            manager_text: Текст ответа менеджера.
        
        Returns:
            True если ответ успешно отправлен.
        
        Raises:
            ValueError: If thread not found or status is not MANUAL.
            RuntimeError: If project has no bot token or Telegram API fails.
        """
        logger.info("Sending manager reply", extra={"thread_id": thread_id})
        
        # Получаем тред с project_id
        thread = await self.threads.get_thread_with_project(thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        if thread["status"] != ThreadStatus.MANUAL.value:
            raise ValueError(f"Thread {thread_id} status is {thread['status']}, expected MANUAL")

        project_id = thread["project_id"]

        # Транзакция: используем пул напрямую для атомарности
        async with self.threads.pool.acquire() as conn:
            async with conn.transaction():
                # Обновляем статус (оставляем MANUAL или меняем – оставим MANUAL для ясности)
                await conn.execute("""
                    UPDATE threads
                    SET updated_at = NOW()
                    WHERE id = $1
                """, uuid.UUID(thread_id))

                # Сохраняем сообщение менеджера как assistant
                await conn.execute("""
                    INSERT INTO messages (thread_id, role, content)
                    VALUES ($1, $2, $3)
                """, uuid.UUID(thread_id), "assistant", manager_text)

        # Получаем токен бота для этого проекта
        bot_token = await self.projects.get_bot_token(project_id)
        if not bot_token:
            raise RuntimeError(f"Project {project_id} has no bot token")

        # Получаем chat_id клиента
        client = await self.threads.pool.fetchrow(
            "SELECT chat_id FROM clients WHERE id = $1", uuid.UUID(thread["client_id"])
        )
        if not client:
            raise RuntimeError(f"Client not found for thread {thread_id}")

        chat_id = client["chat_id"]

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": manager_text
        }
        async with httpx.AsyncClient() as client_http:
            resp = await client_http.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(
                    "Failed to send manager reply",
                    extra={"thread_id": thread_id, "status": resp.status_code, "response": resp.text}
                )
                raise RuntimeError(f"Telegram API error: {resp.status_code}")

        # Emit event: manager_replied
        await self._emit_event(
            stream_id=thread_id,
            project_id=project_id,
            event_type="manager_replied",
            payload={
                "text": manager_text,
                "manager_chat_id": thread.get("manager_chat_id")
            }
        )

        logger.info("Manager reply sent successfully", extra={"thread_id": thread_id})
        return True

    #async def _summarize_history(self, thread_id: str) -> None:
        """
        Фоновая задача: генерирует краткое содержание диалога и сохраняет его в поле context_summary треда.
        """
        #try:
            #logger.info(f"Starting summarization for thread {thread_id}")
           # messages = await self.threads.get_messages_for_langgraph(thread_id)
            #if not messages:
                #logger.warning(f"No messages found for thread {thread_id}, skipping summarization")
               # return
            #summary = await self.summarizer.summarize(messages)
            #await self.threads.update_summary(thread_id, summary)
            #logger.info(f"Summarization completed for thread {thread_id}")
        #except Exception as e:
            #logger.exception(f"Summarization failed for thread {thread_id}: {e}")
