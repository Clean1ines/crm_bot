from typing import Protocol


class UserAuthPort(Protocol):
    async def get_or_create_by_telegram(
        self,
        telegram_chat_id: int,
        first_name: str,
        username: str | None,
    ) -> tuple[str, bool]: ...


class UserAdminPort(Protocol):
    async def is_platform_admin(self, user_id: str) -> bool: ...


UserRepositoryPort = UserAuthPort
