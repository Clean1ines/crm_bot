from dataclasses import dataclass
from datetime import datetime

from src.domain.project_plane.json_types import JsonValue, json_value_from_unknown


def _memory_timestamp(value: object) -> datetime | str | None:
    if isinstance(value, (datetime, str)):
        return value
    return None


@dataclass(slots=True)
class MemoryEntryView:
    id: str
    key: str
    value: JsonValue
    type: str
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "MemoryEntryView":
        return cls(
            id=str(record["id"]),
            key=str(record["key"]),
            value=json_value_from_unknown(record.get("value")),
            type=str(record["type"]),
            created_at=_memory_timestamp(record.get("created_at")),
            updated_at=_memory_timestamp(record.get("updated_at")),
        )

    def to_record(self) -> dict[str, object]:
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "type": self.type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
