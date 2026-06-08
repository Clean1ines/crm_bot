from __future__ import annotations

from enum import StrEnum


class PublicationStatus(StrEnum):
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {
            PublicationStatus.COMPLETED,
            PublicationStatus.FAILED,
            PublicationStatus.CANCELLED,
        }
