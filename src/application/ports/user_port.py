from typing import Protocol

from src.domain.identity.user_views import (
    AuthMethodsView,
    ConsumedEmailVerificationToken,
    ConsumedPasswordResetToken,
    EmailVerificationTokenView,
    PasswordResetTokenView,
    UserProfileView,
)


class UserAuthPort(Protocol):
    async def get_or_create_by_telegram(
        self,
        telegram_chat_id: int,
        first_name: str,
        username: str | None,
    ) -> tuple[str, bool]: ...


class UserAdminPort(Protocol):
    async def is_platform_admin(self, user_id: str) -> bool: ...


class UserRepositoryPort(UserAuthPort, Protocol):
    async def get_or_create_by_email(
        self,
        email: str,
        full_name: str | None = None,
    ) -> tuple[str, bool]: ...

    async def create_user(
        self,
        full_name: str | None = None,
        email: str | None = None,
        username: str | None = None,
    ) -> str: ...

    async def link_identity(
        self,
        user_id: str,
        provider: str,
        provider_id: str,
    ) -> bool: ...

    async def unlink_identity(self, user_id: str, provider: str) -> bool: ...

    async def get_user_by_identity_view(
        self,
        provider: str,
        provider_id: str,
    ) -> UserProfileView | None: ...

    async def get_user_by_id_view(self, user_id: str) -> UserProfileView | None: ...

    async def get_user_by_email_view(self, email: str) -> UserProfileView | None: ...

    async def list_auth_methods_view(self, user_id: str) -> AuthMethodsView: ...

    async def count_auth_methods(self, user_id: str) -> int: ...

    async def has_auth_method(self, user_id: str, provider: str) -> bool: ...

    async def set_password(self, user_id: str, password: str) -> None: ...

    async def link_email_auth(
        self,
        user_id: str,
        email: str,
        password: str,
    ) -> None: ...

    async def verify_password(self, user_id: str, password: str) -> bool: ...

    async def has_password(self, user_id: str) -> bool: ...

    async def update_user(self, user_id: str, data: dict[str, object]) -> bool: ...

    async def create_email_verification_token(
        self,
        user_id: str,
        email: str,
        ttl_hours: int = 24,
    ) -> EmailVerificationTokenView: ...

    async def consume_email_verification_token(
        self,
        token: str,
    ) -> ConsumedEmailVerificationToken | None: ...

    async def mark_email_verified(self, user_id: str, email: str) -> None: ...

    async def create_password_reset_token(
        self,
        user_id: str,
        ttl_hours: int = 2,
    ) -> PasswordResetTokenView: ...

    async def consume_password_reset_token(
        self,
        token: str,
    ) -> ConsumedPasswordResetToken | None: ...
