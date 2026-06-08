from __future__ import annotations

from enum import StrEnum


class ArtifactStatus(StrEnum):
    """Generic lifecycle status for stored pipeline artifacts."""

    STORED = "stored"
    VALIDATED = "validated"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"

    @property
    def is_terminal(self) -> bool:
        return self in {
            ArtifactStatus.REJECTED,
            ArtifactStatus.SUPERSEDED,
            ArtifactStatus.EXPIRED,
        }
