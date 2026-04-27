from src.application.dto.webhook_dto import WebhookAckDto
from src.application.ports.cache_port import CachePort
from src.application.ports.logger_port import LoggerPort, NullLogger
from src.application.ports.manager_bot_port import ManagerBotOrchestratorPort
from src.application.ports.telegram_port import TelegramClientPort
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.manager_assignments import ManagerActor, ManagerReplySession
from src.domain.runtime.dialog_state import default_dialog_state


class ManagerBotService:
    def __init__(
        self,
        orchestrator: ManagerBotOrchestratorPort,
        redis: CachePort,
        bot_token: str,
        project_id: str,
        *,
        telegram_client: TelegramClientPort | None = None,
        logger: LoggerPort | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.redis = redis
        self.bot_token = bot_token
        self.project_id = project_id
        self.telegram_client = telegram_client
        self.logger = logger or NullLogger()

    async def _post_telegram(self, method: str, payload: JsonObject) -> None:
        if self.telegram_client is not None:
            await self.telegram_client.post_json(self.bot_token, method, payload)
            return

        httpx_mod = __import__("httpx")
        async with httpx_mod.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/{method}",
                json=payload,
            )

    async def _deny_unauthorized_manager(self, chat_id: str) -> WebhookAckDto:
        await self._post_telegram(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "⛔ Доступ запрещён. Вы не являетесь менеджером этого проекта.",
            },
        )
        return WebhookAckDto()

    async def claim_thread(
        self,
        *,
        callback_id: str,
        thread_id: str,
        manager_chat_id: str,
        manager_user_id: str | None = None,
    ) -> WebhookAckDto:
        manager_user_id = manager_user_id or await self.orchestrator.resolve_manager_user_id_by_telegram(
            self.project_id,
            manager_chat_id,
        )
        if not manager_user_id:
            self.logger.info(
                "Manager claim denied because Telegram chat is not a project member",
                extra={"project_id": self.project_id, "manager_chat_id": manager_chat_id},
            )
            return await self._deny_unauthorized_manager(manager_chat_id)

        session = ManagerReplySession.for_telegram_manager(
            thread_id=thread_id,
            manager_user_id=manager_user_id,
            manager_chat_id=manager_chat_id,
        )

        await self.redis.setex(
            session.thread_key,
            600,
            session.to_redis_value(),
        )
        if session.manager_key:
            await self.redis.setex(session.manager_key, 600, thread_id)

        await self.orchestrator.threads.claim_for_manager(
            thread_id,
            manager=ManagerActor(
                user_id=manager_user_id,
                telegram_chat_id=manager_chat_id,
            ),
        )

        await self._post_telegram(
            "answerCallbackQuery",
            {
                "callback_query_id": callback_id,
                "text": "Тикет взят в работу. Теперь все сообщения клиента будут направлены вам.",
                "show_alert": False,
            },
        )
        await self._post_telegram(
            "sendMessage",
            {
                "chat_id": manager_chat_id,
                "text": f"Тикет {thread_id} взят в работу. Чтобы вернуть диалог AI, нажмите «Закрыть тикет».",
                "reply_markup": {
                    "inline_keyboard": [[{"text": "✅ Закрыть тикет", "callback_data": f"close:{thread_id}"}]],
                },
            },
        )
        return WebhookAckDto()

    async def close_thread(
        self,
        *,
        callback_id: str,
        thread_id: str,
        manager_chat_id: str,
        manager_user_id: str | None = None,
    ) -> WebhookAckDto:
        manager_user_id = manager_user_id or await self.orchestrator.resolve_manager_user_id_by_telegram(
            self.project_id,
            manager_chat_id,
        )
        if not manager_user_id:
            self.logger.info(
                "Manager close denied because Telegram chat is not a project member",
                extra={"project_id": self.project_id, "manager_chat_id": manager_chat_id},
            )
            return await self._deny_unauthorized_manager(manager_chat_id)

        session = ManagerReplySession.for_telegram_manager(
            thread_id=thread_id,
            manager_user_id=manager_user_id,
            manager_chat_id=manager_chat_id,
        )

        await self.redis.delete(session.thread_key)
        if session.manager_key:
            await self.redis.delete(session.manager_key)

        await self.orchestrator.threads.release_manager_assignment(thread_id)

        try:
            await self.orchestrator.threads.update_analytics(
                thread_id=thread_id,
                lifecycle="active_client",
                decision=None,
                intent=None,
                cta=None,
            )
            self.logger.info("Thread analytics reset after ticket closure", extra={"thread_id": thread_id})
        except Exception as exc:
            self.logger.warning("Failed to reset thread analytics", extra={"error": str(exc)})

        try:
            thread = await self.orchestrator.threads.get_thread_with_project_view(thread_id)
            if thread and self.orchestrator.memory_repo:
                client_id = thread.client_id
                project_id = thread.project_id
                if client_id and project_id:
                    await self.orchestrator.memory_repo.set_lifecycle(project_id, client_id, "active_client")
                    await self.orchestrator.memory_repo.set(
                        project_id,
                        client_id,
                        "dialog_state",
                        default_dialog_state(lifecycle="active_client"),
                        "dialog_state",
                    )
                    self.logger.info("User memory reset after ticket closure", extra={"client_id": client_id})
        except Exception as exc:
            self.logger.warning("Failed to reset user memory after ticket closure", extra={"error": str(exc)})

        await self._post_telegram(
            "answerCallbackQuery",
            {
                "callback_query_id": callback_id,
                "text": "Тикет закрыт. AI снова будет отвечать клиенту.",
                "show_alert": False,
            },
        )
        return WebhookAckDto()

    async def reply_from_manager(
        self,
        *,
        manager_chat_id: str,
        text: str,
        manager_user_id: str | None = None,
    ) -> WebhookAckDto:
        manager_user_id = manager_user_id or await self.orchestrator.resolve_manager_user_id_by_telegram(
            self.project_id,
            manager_chat_id,
        )
        if not manager_user_id:
            self.logger.info(
                "Manager reply denied because Telegram chat is not a project member",
                extra={"project_id": self.project_id, "manager_chat_id": manager_chat_id},
            )
            return await self._deny_unauthorized_manager(manager_chat_id)

        key = ManagerReplySession(
            thread_id="",
            manager_user_id=manager_user_id,
            manager_chat_id=manager_chat_id,
        ).manager_key
        thread_id = await self.redis.get(key) if key else None

        if not thread_id:
            await self._post_telegram(
                "sendMessage",
                {
                    "chat_id": manager_chat_id,
                    "text": "Нет активного ожидания ответа. Пожалуйста, нажмите кнопку ✏️ Ответить под уведомлением.",
                },
            )
            return WebhookAckDto()

        if isinstance(thread_id, bytes):
            thread_id = thread_id.decode()

        try:
            success = await self.orchestrator.manager_reply(
                thread_id,
                text,
                manager_chat_id,
                manager_user_id=manager_user_id,
            )
            await self._post_telegram(
                "sendMessage",
                {
                    "chat_id": manager_chat_id,
                    "text": "✅ Ответ успешно отправлен клиенту." if success else "❌ Не удалось отправить ответ.",
                },
            )
        except Exception as exc:
            self.logger.exception("Error sending manager reply")
            await self._post_telegram(
                "sendMessage",
                {"chat_id": manager_chat_id, "text": f"❌ Ошибка: {str(exc)}"},
            )

        return WebhookAckDto()
