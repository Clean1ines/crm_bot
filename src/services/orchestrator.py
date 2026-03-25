"""
Orchestrator service: ties together project, thread, and agent logic.

This module orchestrates message processing, event emission, and workflow
execution for the AI bot platform.
"""

import asyncio
import uuid
import json
import httpx
import re
from typing import Optional, Dict, Any, List, Union

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END

from src.agent.graph import create_agent as create_default_agent
from src.agent.state import AgentState
from src.database.models import ThreadStatus
from src.database.repositories.queue_repository import QueueRepository
from src.services.lock import acquire_thread_lock, release_thread_lock
from src.services.redis_client import get_redis_client
from src.core.config import settings
from src.core.logging import get_logger
from src.utils.uuid_utils import ensure_uuid

logger = get_logger(__name__)


def split_questions(text: str) -> List[str]:
    """
    Разбивает текст на отдельные вопросы по разделителям: . ? ! и переносам строк.
    Возвращает список непустых строк.
    """
    # Разделяем по границам предложений (точка, вопросительный, восклицательный знак, перевод строки)
    parts = re.split(r'[.?!\n]+', text)
    # Убираем пустые и обрезаем пробелы
    questions = [p.strip() for p in parts if p.strip()]
    return questions


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
        template_repo: TemplateRepository instance (for template-based workflows).
        workflow_repo: WorkflowRepository instance (for custom workflows).
        tool_registry: ToolRegistry instance (optional for dynamic tools).
        memory_repo: MemoryRepository instance (optional for long-term memory).
        agent: Compiled LangGraph agent (default fallback).
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
        template_repo=None,
        workflow_repo=None,
        tool_registry=None,
        memory_repo=None
    ):
        """
        Initialize the OrchestratorService with required dependencies.
        
        Args:
            db_conn: Database connection pool.
            project_repo: ProjectRepository instance.
            thread_repo: ThreadRepository instance.
            queue_repo: QueueRepository instance.
            event_repo: Optional EventRepository for event sourcing.
            template_repo: Optional TemplateRepository for template workflows.
            workflow_repo: Optional WorkflowRepository for custom workflows.
            tool_registry: Optional ToolRegistry for dynamic tool execution.
            memory_repo: Optional MemoryRepository for long-term memory.
        """
        self.db = db_conn
        self.projects = project_repo
        self.threads = thread_repo
        self.queue_repo = queue_repo
        self.event_repo = event_repo
        self.template_repo = template_repo
        self.workflow_repo = workflow_repo
        self.tool_registry = tool_registry
        self.memory_repo = memory_repo
        # Create default agent (now the new state machine graph)
        self.agent = create_default_agent(
            tool_registry=tool_registry,
            thread_repo=thread_repo,
            queue_repo=queue_repo,
            event_repo=event_repo,
            project_repo=project_repo,
            memory_repo=memory_repo
        )
        
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
        
        # Ensure stream_id is string
        stream_id = str(stream_id)
        
        try:
            await self.event_repo.append(
                stream_id=ensure_uuid(stream_id),
                project_id=ensure_uuid(project_id),
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

    def _build_graph_from_json(self, graph_json: Union[str, Dict[str, Any]]) -> Any:
        """
        Build a LangGraph instance from JSON definition.
        
        FIXED: Handles both string (from DB) and dict inputs.
        
        Args:
            graph_json: Graph definition with nodes and edges (can be JSON string or dict).
        
        Returns:
            Compiled LangGraph instance.
        """
        # FIX: Parse JSON string if necessary
        if isinstance(graph_json, str):
            try:
                graph_dict = json.loads(graph_json)
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON in graph definition", extra={"error": str(e)})
                return self.agent
        else:
            graph_dict = graph_json
        
        # For MVP: return default agent if graph is simple or invalid
        if not graph_dict or "nodes" not in graph_dict:
            logger.warning("Invalid or empty graph_json, using default agent")
            return self.agent
        
        # Simple graph with default flow: message → AI → reply
        # In production: resolve nodes from registry, build dynamic graph
        logger.debug("Building graph from JSON", extra={"node_count": len(graph_dict.get("nodes", []))})
        return self.agent

    async def _get_graph_for_project(self, project_id: str) -> Any:
        """
        Get the appropriate LangGraph for a project.
        
        Priority order:
        1. Custom workflow (if project is in Pro mode AND has workflow_id)
        2. Template workflow (if project has template_slug)
        3. Default agent graph (fallback)
        
        Args:
            project_id: UUID of the project in string format.
        
        Returns:
            Compiled LangGraph instance.
        """
        logger.debug("Loading graph for project", extra={"project_id": project_id})
        
        # Check for custom workflow (Pro mode)
        if self.workflow_repo:
            is_pro = await self.projects.get_is_pro_mode(project_id)
            if is_pro:
                # Try to load active workflow for project
                workflows = await self.workflow_repo.get_for_project(project_id, active_only=True)
                if workflows:
                    # Use latest version
                    latest = max(workflows, key=lambda w: w.get("version", 0))
                    workflow_id = latest.get("id")
                    logger.info(
                        "Loading custom workflow",
                        extra={"project_id": project_id, "workflow_id": workflow_id}
                    )
                    workflow_data = await self.workflow_repo.get_by_id(
                        ensure_uuid(workflow_id), include_graph=True
                    )
                    if workflow_data and "graph_json" in workflow_data:
                        return self._build_graph_from_json(workflow_data["graph_json"])
        
        # Check for template
        if self.template_repo:
            template_slug = await self.projects.get_template_slug(project_id)
            if template_slug:
                logger.info(
                    "Loading workflow from template",
                    extra={"project_id": project_id, "template_slug": template_slug}
                )
                template_data = await self.template_repo.get_by_slug(template_slug)
                if template_data and "graph_json" in template_data:
                    return self._build_graph_from_json(template_data["graph_json"])
        
        # Default: use the standard agent
        logger.debug("Using default agent graph", extra={"project_id": project_id})
        return self.agent

    async def process_message(self, project_id: str, chat_id: int, text: str) -> str:
        """
        Process an incoming message from a client.
        
        This is the main entry point for conversation handling.
        Steps:
          1. Register client/thread.
          2. Save user message and emit message_received event.
          3. Acquire thread lock to prevent concurrent processing.
          4. Check if manager is currently in a reply session for this thread.
          5. If yes, redirect the message to the manager (enqueue notification).
          6. Otherwise, split message into questions and invoke graph.
          7. Collect responses and combine them.
          8. Release lock.
        
        Args:
            project_id: UUID проекта в строковом формате.
            chat_id: Telegram chat_id клиента.
            text: Текст сообщения.
        
        Returns:
            Response text to send back to the client, or empty string if already sent.
        """
        logger.info(
            "Processing message",
            extra={"project_id": project_id, "chat_id": chat_id, "text_preview": text[:50]}
        )
        
        # 1. Register client and thread
        client_id = await self.threads.get_or_create_client(project_id, chat_id)
        thread_id = await self.threads.get_active_thread(client_id) or await self.threads.create_thread(client_id)
        thread_id_str = str(thread_id)
        
        # 2. Acquire Redis lock for this thread
        lock_acquired = await acquire_thread_lock(thread_id_str)
        if not lock_acquired:
            logger.warning("Could not acquire lock for thread", extra={"thread_id": thread_id_str})
            return "⏳ Ваш запрос уже обрабатывается, пожалуйста, подождите."

        try:
            # 3. Check if manager is in reply session for this thread
            redis = await get_redis_client()
            awaiting_reply_key = f"awaiting_reply_thread:{thread_id_str}"
            manager_chat_id = await redis.get(awaiting_reply_key)
            
            if manager_chat_id:
                # Also check thread status – if ACTIVE, ignore the key
                thread_data = await self.threads.get_thread_with_project(thread_id_str)
                if thread_data and thread_data.get("status") == ThreadStatus.ACTIVE.value:
                    # Key is stale, delete it and continue
                    await redis.delete(awaiting_reply_key)
                    logger.info("Stale awaiting_reply key deleted for thread", extra={"thread_id": thread_id_str})
                    manager_chat_id = None
            
            if manager_chat_id:
                # Manager has claimed the ticket – redirect all future messages to manager
                logger.info("Message redirected to manager (thread in reply session)", extra={"thread_id": thread_id_str})
                await self.queue_repo.enqueue(
                    task_type="notify_manager",
                    payload={
                        "thread_id": thread_id_str,
                        "project_id": project_id,
                        "message": text,
                        "manager_chat_id": manager_chat_id.decode() if isinstance(manager_chat_id, bytes) else manager_chat_id
                    }
                )
                return "Ваш вопрос передан менеджеру. Ожидайте ответа."

            # 4. Save user message (whole text, will be split later)
            await self.threads.add_message(thread_id, role="user", content=text)
            
            # Emit message_received event
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

            # 5. Split message into questions
            questions = split_questions(text)
            if not questions:
                questions = [text]  # fallback to whole text
            
            logger.debug(f"Split message into {len(questions)} questions", extra={"thread_id": thread_id_str})
            
            # 6. For each question, call graph and collect responses
            responses = []
            for q in questions:
                # Load context for state
                recent_messages = await self.threads.get_messages_for_langgraph(thread_id)
                if len(recent_messages) > self.RECENT_MESSAGES_LIMIT:
                    recent_messages = recent_messages[-self.RECENT_MESSAGES_LIMIT:]
                
                conversation_summary = None
                if hasattr(self.threads, 'get_summary'):
                    conversation_summary = await self.threads.get_summary(thread_id)
                
                saved_state = await self.threads.get_state_json(thread_id_str)

                # Generate trace_id for this graph execution
                trace_id = uuid.uuid4().hex

                # Build initial AgentState
                state = AgentState(
                    messages=[],
                    project_id=project_id,
                    thread_id=thread_id_str,
                    escalation_requested=False,
                    tool_calls=None,
                    user_input=q,
                    client_profile=None,
                    conversation_summary=conversation_summary,
                    history=recent_messages,
                    knowledge_chunks=None,
                    decision=None,
                    tool_name=None,
                    tool_args=None,
                    tool_result=None,
                    response_text=None,
                    requires_human=False,
                    confidence=None,
                    chat_id=chat_id,
                    trace_id=trace_id,
                )

                # Get graph for project
                graph = await self._get_graph_for_project(project_id)
                if graph is None:
                    logger.error("Failed to load graph for project", extra={"project_id": project_id})
                    responses.append("Произошла ошибка обработки запроса.")
                    continue

                # Execute graph
                result_state = await graph.ainvoke(state)

                # Determine if message was already sent by the graph
                if result_state.get("message_sent"):
                    logger.debug(f"Message sent for question: {q[:30]}...", extra={"thread_id": thread_id_str})
                    continue

                # Otherwise, get response_text
                response_text = result_state.get("response_text")
                if response_text:
                    responses.append(response_text)
                else:
                    logger.warning(f"Graph did not produce response_text for question: {q[:30]}...",
                                   extra={"thread_id": thread_id_str})
                    responses.append("Извините, не удалось сформировать ответ.")

            # 7. Combine responses
            if not responses:
                return ""
            
            combined_response = "\n\n".join(responses)
            logger.info("All questions processed", extra={"thread_id": thread_id_str, "response_count": len(responses)})
            return combined_response

        finally:
            # Always release lock
            await release_thread_lock(thread_id_str)

    async def manager_reply(self, thread_id: str, manager_text: str, manager_chat_id: str) -> bool:
        """
        Отправляет ответ менеджера клиенту по указанному треду.
        
        Args:
            thread_id: UUID треда в строковом формате.
            manager_text: Текст ответа менеджера.
            manager_chat_id: Telegram chat_id менеджера (для идентификации).
        
        Returns:
            True если ответ успешно отправлен.
        
        Raises:
            ValueError: If thread not found or status is not MANUAL.
            RuntimeError: If project has no bot token or Telegram API fails.
        """
        logger.info("Sending manager reply", extra={"thread_id": thread_id, "manager_chat_id": manager_chat_id})
        
        # Получаем тред с project_id
        thread = await self.threads.get_thread_with_project(thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        # Check that thread is in MANUAL state (manager has taken the ticket)
        if thread["status"] != ThreadStatus.MANUAL.value:
            raise ValueError(f"Thread {thread_id} status is {thread['status']}, expected MANUAL")

        project_id = thread["project_id"]

        # Get manager info (username) from Telegram
        manager_name = None
        try:
            # Get manager bot token
            project_settings = await self.projects.get_project_settings(project_id)
            manager_bot_token = project_settings.get("manager_bot_token")
            if manager_bot_token:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"https://api.telegram.org/bot{manager_bot_token}/getChat",
                        params={"chat_id": manager_chat_id}
                    )
                    if resp.status_code == 200 and resp.json().get("ok"):
                        chat_data = resp.json()["result"]
                        manager_name = chat_data.get("first_name") or chat_data.get("username") or "Менеджер"
        except Exception as e:
            logger.warning("Failed to fetch manager name", extra={"error": str(e)})
            manager_name = "Менеджер"

        # Prepend manager indicator to the text
        prefixed_text = f"[{manager_name}]: {manager_text}"

        # Транзакция: используем пул напрямую для атомарности
        async with self.threads.pool.acquire() as conn:
            async with conn.transaction():
                # Обновляем статус (оставляем MANUAL)
                await conn.execute("""
                    UPDATE threads
                    SET updated_at = NOW()
                    WHERE id = $1
                """, ensure_uuid(thread_id))

                # Сохраняем сообщение менеджера как assistant с префиксом
                await conn.execute("""
                    INSERT INTO messages (thread_id, role, content)
                    VALUES ($1, $2, $3)
                """, ensure_uuid(thread_id), "assistant", prefixed_text)

        # Получаем токен бота для этого проекта
        bot_token = await self.projects.get_bot_token(project_id)
        if not bot_token:
            raise RuntimeError(f"Project {project_id} has no bot token")

        # Получаем chat_id клиента
        client = await self.threads.pool.fetchrow(
            "SELECT chat_id FROM clients WHERE id = $1", thread["client_id"]
        )
        if not client:
            raise RuntimeError(f"Client not found for thread {thread_id}")

        chat_id = client["chat_id"]

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": prefixed_text
        }
        async with httpx.AsyncClient() as client_http:
            resp = await client_http.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(
                    "Failed to send manager reply",
                    extra={"thread_id": thread_id, "status": resp.status_code, "response": resp.text}
                )
                raise RuntimeError(f"Telegram API error: {resp.status_code}")

        # Emit event: manager_replied – convert thread_id to string to avoid UUID issues
        await self._emit_event(
            stream_id=str(thread_id),
            project_id=project_id,
            event_type="manager_replied",
            payload={
                "text": manager_text,
                "manager_chat_id": manager_chat_id
            }
        )

        logger.info("Manager reply sent successfully", extra={"thread_id": thread_id})
        return True
