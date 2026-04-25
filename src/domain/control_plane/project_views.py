from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ProjectSummaryView:
    id: str
    name: str
    is_pro_mode: bool
    user_id: str | None = None
    client_bot_username: str | None = None
    manager_bot_username: str | None = None
    access_role: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ProjectSummaryView":
        return cls(
            id=str(record["id"]),
            name=str(record["name"]),
            is_pro_mode=bool(record.get("is_pro_mode")),
            user_id=str(record["user_id"]) if record.get("user_id") is not None else None,
            client_bot_username=record.get("client_bot_username"),
            manager_bot_username=record.get("manager_bot_username"),
            access_role=record.get("access_role"),
            created_at=record.get("created_at"),
            updated_at=record.get("updated_at"),
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "is_pro_mode": self.is_pro_mode,
            "user_id": self.user_id,
            "client_bot_username": self.client_bot_username,
            "manager_bot_username": self.manager_bot_username,
            "access_role": self.access_role,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class ProjectMemberView:
    user_id: str
    role: str
    telegram_id: int | None = None
    username: str | None = None
    full_name: str | None = None
    email: str | None = None
    project_id: str | None = None
    created_at: datetime | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ProjectMemberView":
        return cls(
            user_id=str(record["user_id"]),
            role=str(record["role"]),
            telegram_id=record.get("telegram_id"),
            username=record.get("username"),
            full_name=record.get("full_name"),
            email=record.get("email"),
            project_id=str(record["project_id"]) if record.get("project_id") is not None else None,
            created_at=record.get("created_at"),
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "role": self.role,
            "telegram_id": self.telegram_id,
            "username": self.username,
            "full_name": self.full_name,
            "email": self.email,
            "project_id": self.project_id,
            "created_at": self.created_at,
        }
