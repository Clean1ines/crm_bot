from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class MemoryEntryView:
    id: str
    key: str
    value: Any
    type: str
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "MemoryEntryView":
        return cls(
            id=str(record["id"]),
            key=str(record["key"]),
            value=record.get("value"),
            type=str(record["type"]),
            created_at=record.get("created_at"),
            updated_at=record.get("updated_at"),
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "type": self.type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
