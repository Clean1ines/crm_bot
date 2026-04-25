from typing import Protocol, Any


class UserAuthPort(Protocol):
    async def get_or_create_by_telegram(
        self,
        telegram_chat_id: int,
        first_name: str,
        username: str | None,
    ) -> tuple[str, bool]: ...


UserRepositoryPort = UserAuthPort
