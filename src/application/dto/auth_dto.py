from dataclasses import asdict, dataclass


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
            created_at=record.get("created_at"),
            verified=record.get("verified"),
            verified_at=record.get("verified_at"),
        )

    @classmethod
    def from_view(cls, view: object) -> "AuthMethodDto":
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
                AuthMethodDto.from_record(item) for item in record.get("methods", [])
            ],
            has_password=bool(record.get("has_password")),
            verified_email=record.get("verified_email"),
        )

    @classmethod
    def from_view(
        cls, view: object, *, verified_email: str | None = None
    ) -> "AuthMethodsDto":
        return cls(
            user_id=str(view.user_id),
            methods=[AuthMethodDto.from_view(method) for method in view.methods],
            has_password=bool(view.has_password),
            verified_email=verified_email,
        )

    def to_dict(self) -> dict[str, object]:
        payload = {
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
        telegram_id = record.get("telegram_id")
        return cls(
            id=str(record["id"]),
            telegram_id=int(telegram_id) if telegram_id is not None else None,
            username=record.get("username"),
            full_name=record.get("full_name"),
            email=record.get("email"),
            is_platform_admin=record.get("is_platform_admin"),
        )

    @classmethod
    def from_view(cls, view: object) -> "UserProfileDto":
        return cls(
            id=str(view.id),
            telegram_id=int(view.telegram_id) if view.telegram_id is not None else None,
            username=view.username,
            full_name=view.full_name,
            email=view.email,
            is_platform_admin=view.is_platform_admin,
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}
