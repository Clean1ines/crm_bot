from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping

from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown


@dataclass(frozen=True, slots=True)
class QueueJobView:
    id: str
    task_type: str
    payload: JsonObject = field(default_factory=dict)
    attempts: int = 0
    max_attempts: int | None = None
    created_at: str | datetime | None = None

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "QueueJobView":
        return cls(
            id=str(record["id"]),
            task_type=str(record["task_type"]),
            payload=json_object_from_unknown(record.get("payload") or {}),
            attempts=int(record.get("attempts") or 0),
            max_attempts=(
                int(record["max_attempts"])
                if record.get("max_attempts") is not None
                else None
            ),
            created_at=record.get("created_at"),
        )

    def to_record(self) -> JsonObject:
        result: JsonObject = {
            "id": self.id,
            "task_type": self.task_type,
            "payload": self.payload,
            "attempts": self.attempts,
        }
        if self.max_attempts is not None:
            result["max_attempts"] = self.max_attempts
        if self.created_at is not None:
            result["created_at"] = (
                self.created_at.isoformat()
                if hasattr(self.created_at, "isoformat")
                else str(self.created_at)
            )
        return result
