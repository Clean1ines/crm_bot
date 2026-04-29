from src.application.dto.webhook_dto import WebhookAckDto
from src.application.errors import (
    InternalServiceError,
    NotFoundError,
    UnauthorizedError,
)
from src.application.ports.telegram_port import NullTelegramClient, TelegramClientPort


class WebhookDispatcher:
    def __init__(
        self,
        admin_bot_token: str,
        platform_webhook_secret: str | None = None,
        telegram_client: TelegramClientPort | None = None,
    ) -> None:
        self.admin_bot_token = admin_bot_token
        self.platform_webhook_secret = platform_webhook_secret
        self.telegram_client = telegram_client or NullTelegramClient()

    @staticmethod
    def extract_sender_chat_id(update: dict) -> int | None:
        if "message" in update:
            return update["message"].get("from", {}).get("id")
        if "callback_query" in update:
            return update["callback_query"].get("from", {}).get("id")
        return None

    @staticmethod
    def _safe_update_metadata(update: dict) -> dict[str, object]:
        top_level_keys = sorted(str(key) for key in update.keys())
        metadata: dict[str, object] = {
            "top_level_keys": top_level_keys,
            "update_id": update.get("update_id"),
            "has_message": "message" in update,
            "has_callback_query": "callback_query" in update,
        }

        message = update.get("message")
        if isinstance(message, dict):
            metadata["message_keys"] = sorted(str(key) for key in message.keys())

        callback_query = update.get("callback_query")
        if isinstance(callback_query, dict):
            metadata["callback_query_keys"] = sorted(
                str(key) for key in callback_query.keys()
            )

        return metadata

    async def verify_project_secret(
        self, project_id: str, secret_token: str | None, project_tokens
    ) -> None:
        if not secret_token:
            raise UnauthorizedError("Missing secret token")
        if secret_token != await project_tokens.get_webhook_secret(project_id):
            raise UnauthorizedError("Invalid secret token")

    async def verify_platform_secret(self, secret_token: str | None) -> None:
        if not secret_token:
            raise UnauthorizedError("Missing secret token")
        expected_secret = self.platform_webhook_secret or self.admin_bot_token
        if secret_token != expected_secret:
            raise UnauthorizedError("Invalid secret token")

    async def handle_platform_surface(
        self,
        update: dict,
        secret_token: str | None,
        *,
        pool,
        process_admin_update,
        logger,
    ):
        await self.verify_platform_secret(secret_token)
        if not self.admin_bot_token:
            raise InternalServiceError("Platform bot token is not configured")
        update["_bot_token"] = self.admin_bot_token
        logger.info("Routing to platform bot handler")
        return await process_admin_update(update, pool)

    async def handle_client_surface(
        self,
        project_id: str,
        update: dict,
        secret_token: str | None,
        *,
        orchestrator,
        project_tokens,
        process_client_update,
        logger,
    ):
        await self.verify_project_secret(project_id, secret_token, project_tokens)
        bot_token = await project_tokens.get_bot_token(project_id)
        if not bot_token:
            raise NotFoundError("Project not found")
        update["_bot_token"] = bot_token
        logger.info("Routing to client bot handler", extra={"project_id": project_id})
        return await process_client_update(update, project_id, orchestrator, bot_token)

    async def handle_manager_surface(
        self,
        project_id: str,
        update: dict,
        secret_token: str | None,
        *,
        orchestrator,
        project_tokens,
        project_members,
        process_manager_update,
        logger,
        skip_secret_validation: bool = False,
    ):
        if not secret_token:
            raise UnauthorizedError("Missing secret token")

        expected_secret = (
            secret_token
            if skip_secret_validation
            else await project_tokens.get_manager_webhook_secret(project_id)
        )
        if secret_token != expected_secret:
            logger.warning(
                "Invalid manager webhook secret", extra={"project_id": project_id}
            )
            raise UnauthorizedError("Invalid secret token")

        manager_bot_token = await project_tokens.get_manager_bot_token(project_id)
        if not manager_bot_token:
            logger.error(
                "Manager token not found after project match",
                extra={"project_id": project_id},
            )
            raise InternalServiceError("Manager token error")

        chat_id = self.extract_sender_chat_id(update)
        if not chat_id:
            logger.warning(
                "No chat_id in update",
                extra={
                    "project_id": project_id,
                    "update_metadata": self._safe_update_metadata(update),
                },
            )
            return WebhookAckDto()

        manager_user_id = await project_members.resolve_manager_user_id_by_telegram(
            project_id,
            str(chat_id),
        )
        if not manager_user_id:
            logger.info(
                "Unauthorized manager surface access attempt",
                extra={"chat_id": chat_id, "project_id": project_id},
            )
            await self.telegram_client.post_json(
                manager_bot_token,
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": "⛔ Доступ запрещён. Вы не являетесь менеджером этого проекта.",
                },
            )
            return WebhookAckDto()

        update["_bot_token"] = manager_bot_token
        update["_manager_user_id"] = manager_user_id
        logger.debug(
            "Authorized manager update",
            extra={
                "project_id": project_id,
                "manager_user_id": manager_user_id,
                "has_manager_chat_id": bool(chat_id),
            },
        )
        return await process_manager_update(
            update, project_id, orchestrator, manager_bot_token
        )
