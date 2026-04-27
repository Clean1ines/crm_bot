from typing import Protocol

from src.domain.project_plane.json_types import JsonObject


class TelegramClientPort(Protocol):
    async def post_json(
        self,
        bot_token: str,
        method: str,
        payload: JsonObject,
    ) -> JsonObject: ...


class NullTelegramClient:
    async def post_json(
        self,
        bot_token: str,
        method: str,
        payload: JsonObject,
    ) -> JsonObject:
        return {"ok": False}
