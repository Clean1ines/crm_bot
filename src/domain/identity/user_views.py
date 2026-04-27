from dataclasses import dataclass, field
from typing import SupportsInt


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None

    if not isinstance(value, str | bytes | bytearray | SupportsInt):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class UserProfileView:
    id: str
    telegram_id: int | None = None
    username: str | None = None
    full_name: str | None = None
    email: str | None = None
    is_platform_admin: bool = False

    @classmethod
    def from_record(cls, record: dict[str, object] | None) -> "UserProfileView | None":
        if not record:
            return None
        return cls(
            id=str(record["id"]),
            telegram_id=_optional_int(record.get("telegram_id")),
            username=_optional_str(record.get("username")),
            full_name=_optional_str(record.get("full_name")),
            email=_optional_str(record.get("email")),
            is_platform_admin=bool(record.get("is_platform_admin")),
        )

    def to_record(self) -> dict[str, object]:
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

    def to_record(self) -> dict[str, object]:
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

    def to_record(self) -> dict[str, object]:
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

    def to_record(self) -> dict[str, object]:
        return {"token": self.token, "expires_at": self.expires_at}


@dataclass(slots=True)
class PasswordResetTokenView:
    token: str
    expires_at: str

    def to_record(self) -> dict[str, object]:
        return {"token": self.token, "expires_at": self.expires_at}


@dataclass(slots=True)
class ConsumedEmailVerificationToken:
    user_id: str
    email: str

    def to_record(self) -> dict[str, object]:
        return {"user_id": self.user_id, "email": self.email}


@dataclass(slots=True)
class ConsumedPasswordResetToken:
    user_id: str

    def to_record(self) -> dict[str, object]:
        return {"user_id": self.user_id}
