from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RetentionPolicyKind(StrEnum):
    """Generic artifact retention policy kind."""

    TEMPORARY = "temporary"
    DURABLE = "durable"
    UNTIL_SUPERSEDED = "until_superseded"


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    kind: RetentionPolicyKind

    @classmethod
    def temporary(cls) -> "RetentionPolicy":
        return cls(RetentionPolicyKind.TEMPORARY)

    @classmethod
    def durable(cls) -> "RetentionPolicy":
        return cls(RetentionPolicyKind.DURABLE)

    @classmethod
    def until_superseded(cls) -> "RetentionPolicy":
        return cls(RetentionPolicyKind.UNTIL_SUPERSEDED)
