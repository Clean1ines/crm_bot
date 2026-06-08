from __future__ import annotations

from enum import StrEnum


class ReasoningEffort(StrEnum):
    NONE = "none"
    DEFAULT = "default"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
