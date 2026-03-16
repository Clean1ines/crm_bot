"""
Orchestrator service: ties together project, thread, and agent logic.
"""

import httpx
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from src.agent.graph import create_agent
from src.database.models import ThreadStatus
from src.database.repositories.queue_repository import QueueRepository
from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

class OrchestratorService:
    def __init__(self, db_conn, project_repo, thread_repo, queue_repo):
        self.db = db_conn
        self.projects = project_repo
        self.threads = thread_repo
        self.queue_repo = queue_repo
        self.agent = create_agent()

    async def process_message(self, project_id: str, chat_id: int, text: str):
        # 1. Тянем промпт проекта
        project = await self.projects.get_project_settings(project_id)
        sys_prompt = project.get('system_prompt', "Ты помощник.")

        # 2. Регаем клиента/тред
        client_id = await self.threads.get_or_create_client(project_id, chat_id)
        thread_id = await self.threads.get_active_thread(client_id) or await self.threads.create_thread(client_id)

        # 3. Сохраняем входящее
        await self.threads.add_message(thread_id, role="user", content=text)

        # 4. Формируем историю для LangGraph
        history = await self.threads.get_messages_for_langgraph(thread_id)
        messages = [SystemMessage(content=sys_prompt)]
        for m in history:
            if m['role'] == 'user': messages.append(HumanMessage(content=m['content']))
            elif m['role'] == 'assistant': messages.append(AIMessage(content=m['content']))

        # 5. Пуск
        result = await self.agent.ainvoke({
            "messages": messages,
            "project_id": project_id,
            "thread_id": thread_id,
            "escalation_requested": False
        })

        # 6. Проверяем, нужно ли эскалировать
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

        # 7. Иначе сохраняем и возвращаем ответ ассистента
        ai_text = result["messages"][-1].content
        await self.threads.add_message(thread_id, role="assistant", content=ai_text)
        return ai_text

    # NEW METHOD
    async def manager_reply(self, thread_id: str, manager_text: str) -> bool:
        """
        Отправляет ответ менеджера клиенту по указанному треду.

        Алгоритм:
        1. Получить данные треда (с project_id) через репозиторий.
        2. Проверить, что статус треда = MANUAL.
        3. В транзакции:
           - обновить статус (опционально можно оставить MANUAL)
           - сохранить сообщение менеджера как 'assistant'.
        4. Получить bot_token проекта.
        5. Отправить сообщение клиенту через Telegram Bot API.
        6. Вернуть True при успехе.

        Args:
            thread_id: UUID треда.
            manager_text: Текст ответа менеджера.

        Returns:
            True, если сообщение успешно отправлено клиенту.

        Raises:
            ValueError: если тред не найден или его статус не MANUAL.
            Exception: при ошибках отправки через Telegram.
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

        # Отправляем сообщение клиенту
        client_chat_id = thread.get("client_id")  # client_id не равен chat_id
        # Нам нужен chat_id клиента. У нас есть thread["client_id"], но это UUID, не chat_id.
        # Нужно получить chat_id из таблицы clients.
        # Сделаем запрос отдельно или добавим в get_thread_with_project поле chat_id.
        # Проще: добавить в get_thread_with_project также chat_id клиента.
        # Но мы можем получить его через репозиторий отдельно.
        # Временно упростим: будем считать, что thread["chat_id"] есть (если мы добавили его в запрос).
        # Модифицируем get_thread_with_project, чтобы возвращал chat_id.
        # Для этого нужно обновить запрос.
        # Вместо этого получим клиента отдельно.
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
