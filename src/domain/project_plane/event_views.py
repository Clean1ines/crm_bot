from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown


@dataclass(frozen=True, slots=True)
class EventTimelineItemView(Mapping[str, object]):
    id: int
    type: str
    payload: JsonObject = field(default_factory=dict)
    ts: datetime | str | None = None
    stream_id: UUID | str | None = None
    project_id: UUID | str | None = None

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "EventTimelineItemView":
        timestamp = record.get("ts")
        if timestamp is None:
            timestamp = record.get("created_at")

        return cls(
            id=int(record.get("id") or 0),
            type=str(record.get("type") or record.get("event_type") or ""),
            payload=json_object_from_unknown(record.get("payload")),
            ts=timestamp if isinstance(timestamp, (datetime, str)) else None,
            stream_id=record.get("stream_id") if isinstance(record.get("stream_id"), (UUID, str)) else None,
            project_id=record.get("project_id") if isinstance(record.get("project_id"), (UUID, str)) else None,
        )

    def to_record(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": self.type,
            "payload": dict(self.payload),
            "ts": self.ts,
            "stream_id": self.stream_id,
            "project_id": self.project_id,
        }

    def __getitem__(self, key: str) -> object:
        return self.to_record()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_record())

    def __len__(self) -> int:
        return len(self.to_record())

    def get(self, key: str, default: object = None) -> object:
        return self.to_record().get(key, default)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, EventTimelineItemView):
            return self.to_record() == other.to_record()

        if isinstance(other, Mapping):
            return self.to_record() == dict(other)

        return False
