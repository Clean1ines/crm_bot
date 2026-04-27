from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown


def _event_int(value: object, default: int = 0) -> int:
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


def _event_timestamp(value: object) -> datetime | str | None:
    if isinstance(value, (datetime, str)):
        return value
    return None


@dataclass(frozen=True, slots=True)
class EventTimelineItemView:
    id: int
    type: str
    payload: JsonObject
    ts: datetime | str | None = None
    stream_id: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "EventTimelineItemView":
        stream_id = record.get("stream_id")
        return cls(
            id=_event_int(record.get("id")),
            type=str(record["type"]),
            payload=json_object_from_unknown(record.get("payload")),
            ts=_event_timestamp(record.get("ts")),
            stream_id=str(stream_id) if isinstance(stream_id, (str, UUID)) else None,
        )

    def to_record(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "type": self.type,
            "payload": dict(self.payload),
            "ts": self.ts,
        }
        if self.stream_id is not None:
            payload["stream_id"] = self.stream_id
        return payload
