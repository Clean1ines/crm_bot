from typing import Protocol, Any, Mapping


class TelegramClientPort(Protocol):
    async def post_json(self, bot_token: str, method: str, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


class NullTelegramClient:
    async def post_json(self, bot_token: str, method: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"ok": True, "result": {}}
