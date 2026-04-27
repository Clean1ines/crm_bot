from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import SupportsInt

from src.domain.identity.user_views import (
    AuthMethodView,
    AuthMethodsView,
    UserProfileView,
)


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_bool(value: object) -> bool | None:
    return bool(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None

    if not isinstance(value, str | bytes | bytearray | SupportsInt):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _record_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


@dataclass(slots=True)
class AuthMethodDto:
    provider: str
    provider_id: str
    created_at: str | None = None
    verified: bool | None = None
    verified_at: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "AuthMethodDto":
        return cls(
            provider=str(record["provider"]),
            provider_id=str(record["provider_id"]),
            created_at=_optional_str(record.get("created_at")),
            verified=_optional_bool(record.get("verified")),
            verified_at=_optional_str(record.get("verified_at")),
        )

    @classmethod
    def from_view(cls, view: AuthMethodView) -> "AuthMethodDto":
        return cls(
            provider=str(view.provider),
            provider_id=str(view.provider_id),
            created_at=view.created_at,
            verified=view.verified,
            verified_at=view.verified_at,
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class AuthMethodsDto:
    user_id: str
    methods: list[AuthMethodDto]
    has_password: bool
    verified_email: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "AuthMethodsDto":
        return cls(
            user_id=str(record["user_id"]),
            methods=[
                AuthMethodDto.from_record(item)
                for item in _record_list(record.get("methods", []))
            ],
            has_password=bool(record.get("has_password")),
            verified_email=_optional_str(record.get("verified_email")),
        )

    @classmethod
    def from_view(
        cls, view: AuthMethodsView, *, verified_email: str | None = None
    ) -> "AuthMethodsDto":
        return cls(
            user_id=str(view.user_id),
            methods=[AuthMethodDto.from_view(method) for method in view.methods],
            has_password=bool(view.has_password),
            verified_email=verified_email,
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "user_id": self.user_id,
            "methods": [method.to_dict() for method in self.methods],
            "has_password": self.has_password,
        }
        if self.verified_email is not None:
            payload["verified_email"] = self.verified_email
        return payload


@dataclass(slots=True)
class AuthSessionDto:
    access_token: str
    user_id: str
    username: str | None = None
    full_name: str | None = None

    @classmethod
    def create(
        cls,
        *,
        access_token: str,
        user_id: str,
        username: str | None = None,
        full_name: str | None = None,
    ) -> "AuthSessionDto":
        return cls(
            access_token=access_token,
            user_id=user_id,
            username=username,
            full_name=full_name,
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class AuthActionDto:
    status: str
    delivery: str | None = None
    expires_at: str | None = None
    token: str | None = None
    url: str | None = None
    user_id: str | None = None

    @classmethod
    def create(
        cls,
        *,
        status: str,
        delivery: str | None = None,
        expires_at: str | None = None,
        token: str | None = None,
        url: str | None = None,
        user_id: str | None = None,
    ) -> "AuthActionDto":
        return cls(
            status=status,
            delivery=delivery,
            expires_at=expires_at,
            token=token,
            url=url,
            user_id=user_id,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class UserProfileDto:
    id: str
    telegram_id: int | None = None
    username: str | None = None
    full_name: str | None = None
    email: str | None = None
    is_platform_admin: bool | None = None

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "UserProfileDto":
        return cls(
            id=str(record["id"]),
            telegram_id=_optional_int(record.get("telegram_id")),
            username=_optional_str(record.get("username")),
            full_name=_optional_str(record.get("full_name")),
            email=_optional_str(record.get("email")),
            is_platform_admin=_optional_bool(record.get("is_platform_admin")),
        )

    @classmethod
    def from_view(cls, view: UserProfileView) -> "UserProfileDto":
        return cls(
            id=str(view.id),
            telegram_id=view.telegram_id,
            username=view.username,
            full_name=view.full_name,
            email=view.email,
            is_platform_admin=view.is_platform_admin,
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}
