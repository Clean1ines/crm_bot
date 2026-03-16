from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from src.agent.graph import create_agent
from src.database.models import ThreadStatus
from src.database.repositories.queue_repository import QueueRepository
import uuid

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
