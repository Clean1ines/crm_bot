from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

ALIAS_PATTERN = re.compile(r"^E[1-9][0-9]*$")


class UnknownEvidenceReference(ValueError):
    def __init__(self, unknown_aliases: Sequence[str]) -> None:
        self.unknown_aliases = tuple(unknown_aliases)
        aliases = ", ".join(self.unknown_aliases)
        super().__init__(f"unknown evidence reference aliases: {aliases}")


@dataclass(frozen=True, slots=True)
class EvidenceReferenceIndex:
    alias_to_entry_id: Mapping[str, str]
    entry_id_to_alias: Mapping[str, str]

    @classmethod
    def from_knowledge_chunks(
        cls,
        chunks: Sequence[object],
        *,
        limit: int,
    ) -> "EvidenceReferenceIndex":
        alias_to_entry_id: dict[str, str] = {}
        entry_id_to_alias: dict[str, str] = {}
        for item in chunks:
            entry_id = _chunk_text_field(item, "id")
            content = _chunk_text_field(item, "content")
            if not entry_id or not content:
                continue
            if entry_id in entry_id_to_alias:
                continue
            alias = f"E{len(alias_to_entry_id) + 1}"
            alias_to_entry_id[alias] = entry_id
            entry_id_to_alias[entry_id] = alias
            if len(alias_to_entry_id) >= limit:
                break
        return cls(
            alias_to_entry_id=alias_to_entry_id,
            entry_id_to_alias=entry_id_to_alias,
        )

    def resolve_aliases(self, aliases: Sequence[str]) -> list[str]:
        resolved: list[str] = []
        seen: set[str] = set()
        unknown: list[str] = []
        for alias in aliases:
            if alias in seen:
                continue
            seen.add(alias)
            if not ALIAS_PATTERN.match(alias) or alias not in self.alias_to_entry_id:
                unknown.append(alias)
                continue
            resolved.append(self.alias_to_entry_id[alias])
        if unknown:
            raise UnknownEvidenceReference(unknown)
        return resolved

    def known_aliases(self) -> tuple[str, ...]:
        return tuple(self.alias_to_entry_id)


def _chunk_text_field(item: object, field: str) -> str | None:
    if not isinstance(item, Mapping):
        return None
    value = item.get(field)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
