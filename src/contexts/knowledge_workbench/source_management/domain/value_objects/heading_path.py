from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HeadingPath:
    parts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        copied_parts = tuple(self.parts)
        for part in copied_parts:
            if not part or not part.strip():
                raise ValueError("HeadingPath.parts must not contain empty parts")
        object.__setattr__(self, "parts", copied_parts)
