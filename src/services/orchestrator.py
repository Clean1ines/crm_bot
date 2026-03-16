"""
Orchestrator service: ties together project, thread, and agent logic.
"""

import asyncio
import uuid
import httpx
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from src.agent.graph import create_agent
from src.database.models import ThreadStatus
from src.database.repositories.queue_repository import QueueRepository
from src.services.summarizer import SummarizerService
from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

class OrchestratorService:
    # Константы для управления контекстом
    SUMMARY_THRESHOLD = 20          # Количество сообщений, после которого запускаем суммаризацию
    RECENT_MESSAGES_LIMIT = 10      # Сколько последних сообщений оставляем в истории (вместе с summary)

    def __init__(self, db_conn, project_repo, thread_repo, queue_repo):
        self.db = db_conn
        self.projects = project_repo
        self.threads = thread_repo
        self.queue_repo = queue_repo
        self.agent = create_agent()
        self.summarizer = SummarizerService()

    async def process_message(self, project_id: str, chat_id: int, text: str):
        # 1. Получаем промпт проекта
        project = await self.projects.get_project_settings(project_id)
        sys_prompt = project.get('system_prompt', "Ты помощник.")

        # 2. Регистрируем клиента/тред
        client_id = await self.threads.get_or_create_client(project_id, chat_id)
        thread_id = await self.threads.get_active_thread(client_id) or await self.threads.create_thread(client_id)

        # 3. Сохраняем входящее сообщение
        await self.threads.add_message(thread_id, role="user", content=text)

        # 4. Получаем полную историю сообщений треда
        full_history = await self.threads.get_messages_for_langgraph(thread_id)

        # 5. Проверяем, нужно ли запустить фоновую суммаризацию
        if len(full_history) > self.SUMMARY_THRESHOLD:
            #asyncio.create_task(self._summarize_history(thread_id))
            logger.info(f"Scheduled background summarization for thread {thread_id}")

        # 6. Получаем thread с summary (используем get_thread_with_project, чтобы также получить summary)
        thread_data = await self.threads.get_thread_with_project(thread_id)
        summary = thread_data.get("context_summary") if thread_data else None

        # 7. Формируем сообщения для агента:
        #    - системный промпт
        #    - summary (если есть)
        #    - последние RECENT_MESSAGES_LIMIT сообщений из истории
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
            # можно добавить поддержку tool/system, если нужно

        # 8. Запускаем агента
        result = await self.agent.ainvoke({
            "messages": messages,
            "project_id": project_id,
            "thread_id": thread_id,
            "escalation_requested": False
        })

        # 9. Проверяем, нужно ли эскалировать
        if result.get("escalation_requested"):
            # Меняем статус треда на MANUAL
            await self.threads.update_status(thread_id, ThreadStatus.MANUAL)

            # Ставим задачу в очередь для уведомления менеджера
            await self.queue_repo.enqueue(
                task_type="notify_manager",
                payload={
                    "thread_id": thread_id,
                    "chat_id": chat_id,
                    "message": text
                }
            )

            # Возвращаем пользователю сообщение о передаче оператору
            return "Ваш вопрос передан менеджеру, ожидайте ответа."

        # 10. Иначе сохраняем и возвращаем ответ ассистента
        ai_text = result["messages"][-1].content
        await self.threads.add_message(thread_id, role="assistant", content=ai_text)
        return ai_text

    async def manager_reply(self, thread_id: str, manager_text: str) -> bool:
        """
        Отправляет ответ менеджера клиенту по указанному треду.
        (Остаётся без изменений)
        """
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
                logger.error(f"Failed to send manager reply to client: {resp.text}")
                raise RuntimeError(f"Telegram API error: {resp.status_code}")

        logger.info(f"Manager reply sent for thread {thread_id}")
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
