from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.publication.domain.value_objects.publication_run_ref import (
    PublicationRunRef,
)
from src.contexts.knowledge_workbench.publication.domain.value_objects.publication_status import (
    PublicationStatus,
)


@dataclass(frozen=True, slots=True)
class PublicationRun:
    publication_run_ref: PublicationRunRef
    status: PublicationStatus
    created_at: datetime
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("PublicationRun.created_at must be timezone-aware")

        if self.completed_at is not None:
            if (
                self.completed_at.tzinfo is None
                or self.completed_at.utcoffset() is None
            ):
                raise ValueError("PublicationRun.completed_at must be timezone-aware")
            if self.completed_at < self.created_at:
                raise ValueError("PublicationRun.completed_at must be >= created_at")
            if not self.status.is_terminal:
                raise ValueError("Only terminal PublicationRun may have completed_at")

        if self.status.is_terminal and self.completed_at is None:
            raise ValueError("Terminal PublicationRun must have completed_at")
