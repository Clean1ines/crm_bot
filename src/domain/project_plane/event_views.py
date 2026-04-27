from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown


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
            id=int(record["id"]),
            type=str(record["type"]),
            payload=json_object_from_unknown(record.get("payload")),
            ts=record.get("ts"),
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
