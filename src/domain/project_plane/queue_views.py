from dataclasses import dataclass, field
from datetime import datetime

from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown


def _queue_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return default
        try:
            return int(normalized)
        except ValueError:
            return default
    return default


def _queue_optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _queue_int(value)


def _queue_timestamp(value: object) -> str | datetime | None:
    if isinstance(value, (str, datetime)):
        return value
    return None


@dataclass(frozen=True, slots=True)
class QueueJobView:
    id: str
    task_type: str
    payload: JsonObject = field(default_factory=dict)
    attempts: int = 0
    max_attempts: int | None = None
    created_at: str | datetime | None = None

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "QueueJobView":
        return cls(
            id=str(record["id"]),
            task_type=str(record["task_type"]),
            payload=json_object_from_unknown(record.get("payload") or {}),
            attempts=_queue_int(record.get("attempts")),
            max_attempts=_queue_optional_int(record.get("max_attempts")),
            created_at=_queue_timestamp(record.get("created_at")),
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
