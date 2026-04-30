from src.application.dto.webhook_dto import WebhookAckDto
from src.application.ports.cache_port import CachePort
from src.application.ports.logger_port import LoggerPort, NullLogger
from src.application.ports.manager_bot_port import ManagerBotOrchestratorPort
from src.application.ports.telegram_port import TelegramClientPort
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.manager_assignments import (
    ManagerActor,
    ManagerReplySession,
)

MANAGER_REPLY_FAILED_TEXT = "❌ Не удалось отправить ответ. Попробуйте ещё раз позже."


class ManagerBotService:
    def __init__(
        self,
        orchestrator: ManagerBotOrchestratorPort,
        redis: CachePort,
        bot_token: str,
        project_id: str,
        *,
        telegram_client: TelegramClientPort,
        logger: LoggerPort | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.redis = redis
        self.bot_token = bot_token
        self.project_id = project_id
        self.telegram_client = telegram_client
        self.logger = logger or NullLogger()

    async def _post_telegram(self, method: str, payload: JsonObject) -> None:
        await self.telegram_client.post_json(self.bot_token, method, payload)

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
        manager_user_id = (
            manager_user_id
            or await self.orchestrator.resolve_manager_user_id_by_telegram(
                self.project_id,
                manager_chat_id,
            )
        )
        if not manager_user_id:
            self.logger.info(
                "Manager claim denied because Telegram chat is not a project member",
                extra={
                    "project_id": self.project_id,
                    "manager_chat_id": manager_chat_id,
                },
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

        await self.orchestrator.claim_thread_for_manager(
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
                    "inline_keyboard": [
                        [
                            {
                                "text": "✅ Закрыть тикет",
                                "callback_data": f"close:{thread_id}",
                            }
                        ]
                    ],
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
        manager_user_id = (
            manager_user_id
            or await self.orchestrator.resolve_manager_user_id_by_telegram(
                self.project_id,
                manager_chat_id,
            )
        )
        if not manager_user_id:
            self.logger.info(
                "Manager close denied because Telegram chat is not a project member",
                extra={
                    "project_id": self.project_id,
                    "manager_chat_id": manager_chat_id,
                },
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

        await self.orchestrator.close_thread_for_manager(thread_id)

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
        manager_user_id = (
            manager_user_id
            or await self.orchestrator.resolve_manager_user_id_by_telegram(
                self.project_id,
                manager_chat_id,
            )
        )
        if not manager_user_id:
            self.logger.info(
                "Manager reply denied because Telegram chat is not a project member",
                extra={
                    "project_id": self.project_id,
                    "manager_chat_id": manager_chat_id,
                },
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
                    "text": "✅ Ответ успешно отправлен клиенту."
                    if success
                    else "❌ Не удалось отправить ответ.",
                },
            )
        except Exception as exc:
            self.logger.exception(
                "Error sending manager reply",
                extra={
                    "project_id": self.project_id,
                    "manager_chat_id": manager_chat_id,
                    "error_type": type(exc).__name__,
                },
            )
            await self._post_telegram(
                "sendMessage",
                {"chat_id": manager_chat_id, "text": MANAGER_REPLY_FAILED_TEXT},
            )

        return WebhookAckDto()
