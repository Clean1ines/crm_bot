from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RepositoryRecordView(Mapping[str, Any]):
    """
    Typed boundary object for repository records whose exact public shape is
    owned by application/API adapters.

    Repositories must not expose raw dict/list[dict] contracts. This wrapper
    keeps existing read behavior compatible while making the repository return
    a typed view object with explicit boundary serialization.
    """

    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: Mapping[str, Any] | None) -> "RepositoryRecordView":
        return cls(dict(record or {}))

    def to_record(self) -> dict[str, Any]:
        return dict(self.payload)

    def __getitem__(self, key: str) -> Any:
        return self.payload[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.payload)

    def __len__(self) -> int:
        return len(self.payload)

    def get(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, RepositoryRecordView):
            return self.payload == other.payload
        if isinstance(other, Mapping):
            return self.payload == dict(other)
        return False
