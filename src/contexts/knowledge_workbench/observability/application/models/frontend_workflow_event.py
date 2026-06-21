from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class FrontendWorkflowEvent:
    """Versioned, frontend-safe projection of one durable workflow event."""

    projection_event_id: str
    source_event_id: str
    source_sequence_number: int
    projection_version: int
    projection_type: str
    event_type: str
    operation_key: str | None
    canonical_phase: str
    workflow_run_id: str
    project_id: str
    document_id: str
    payload: Mapping[str, object]
    occurred_at: datetime
    projected_at: datetime
    causation_command_id: str | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("projection_event_id", self.projection_event_id),
            ("source_event_id", self.source_event_id),
            ("projection_type", self.projection_type),
            ("event_type", self.event_type),
            ("canonical_phase", self.canonical_phase),
            ("workflow_run_id", self.workflow_run_id),
            ("project_id", self.project_id),
            ("document_id", self.document_id),
        ):
            _require_non_empty_text(value, field_name=field_name)
        if self.operation_key is not None:
            _require_non_empty_text(self.operation_key, field_name="operation_key")
        if self.causation_command_id is not None:
            _require_non_empty_text(
                self.causation_command_id,
                field_name="causation_command_id",
            )
        if self.correlation_id is not None:
            _require_non_empty_text(self.correlation_id, field_name="correlation_id")
        _require_positive_int(
            self.source_sequence_number,
            field_name="source_sequence_number",
        )
        _require_positive_int(
            self.projection_version,
            field_name="projection_version",
        )
        _require_timezone_aware(self.occurred_at, field_name="occurred_at")
        _require_timezone_aware(self.projected_at, field_name="projected_at")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_positive_int(value: int, *, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
