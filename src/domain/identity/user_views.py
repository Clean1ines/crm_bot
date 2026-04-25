from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class UserProfileView:
    id: str
    telegram_id: int | None = None
    username: str | None = None
    full_name: str | None = None
    email: str | None = None
    is_platform_admin: bool = False

    @classmethod
    def from_record(cls, record: dict[str, Any] | None) -> "UserProfileView | None":
        if not record:
            return None
        telegram_id = record.get("telegram_id")
        return cls(
            id=str(record["id"]),
            telegram_id=int(telegram_id) if telegram_id is not None else None,
            username=record.get("username"),
            full_name=record.get("full_name"),
            email=record.get("email"),
            is_platform_admin=bool(record.get("is_platform_admin")),
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "telegram_id": self.telegram_id,
            "username": self.username,
            "full_name": self.full_name,
            "email": self.email,
            "is_platform_admin": self.is_platform_admin,
        }


@dataclass(slots=True)
class AuthMethodView:
    provider: str
    provider_id: str
    created_at: str | None = None
    verified: bool | None = None
    verified_at: str | None = None

    def to_record(self) -> dict[str, Any]:
        payload = {
            "provider": self.provider,
            "provider_id": self.provider_id,
            "created_at": self.created_at,
            "verified": self.verified,
            "verified_at": self.verified_at,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class AuthMethodsView:
    user_id: str
    methods: list[AuthMethodView] = field(default_factory=list)
    has_password: bool = False
    verified_email: str | None = None

    def to_record(self) -> dict[str, Any]:
        payload = {
            "user_id": self.user_id,
            "methods": [method.to_record() for method in self.methods],
            "has_password": self.has_password,
        }
        if self.verified_email is not None:
            payload["verified_email"] = self.verified_email
        return payload


@dataclass(slots=True)
class EmailVerificationTokenView:
    token: str
    expires_at: str

    def to_record(self) -> dict[str, Any]:
        return {"token": self.token, "expires_at": self.expires_at}


@dataclass(slots=True)
class PasswordResetTokenView:
    token: str
    expires_at: str

    def to_record(self) -> dict[str, Any]:
        return {"token": self.token, "expires_at": self.expires_at}


@dataclass(slots=True)
class ConsumedEmailVerificationToken:
    user_id: str
    email: str

    def to_record(self) -> dict[str, Any]:
        return {"user_id": self.user_id, "email": self.email}


@dataclass(slots=True)
class ConsumedPasswordResetToken:
    user_id: str

    def to_record(self) -> dict[str, Any]:
        return {"user_id": self.user_id}
