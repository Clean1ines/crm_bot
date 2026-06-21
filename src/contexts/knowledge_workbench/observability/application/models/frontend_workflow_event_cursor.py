from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass

from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)

_CURSOR_VERSION = 1


@dataclass(frozen=True, slots=True)
class FrontendWorkflowEventCursor:
    """Lexicographic replay cursor for frontend workflow projection events."""

    source_sequence_number: int
    projection_type: str
    projection_version: int
    projection_event_id: str
    sequence_only: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_sequence_number, int)
            or isinstance(self.source_sequence_number, bool)
            or self.source_sequence_number < 0
        ):
            raise ValueError("source_sequence_number must be a non-negative int")
        if not isinstance(self.projection_type, str):
            raise TypeError("projection_type must be str")
        if (
            not isinstance(self.projection_version, int)
            or isinstance(self.projection_version, bool)
            or self.projection_version < 0
        ):
            raise ValueError("projection_version must be a non-negative int")
        if not isinstance(self.projection_event_id, str):
            raise TypeError("projection_event_id must be str")

    @classmethod
    def beginning(cls) -> FrontendWorkflowEventCursor:
        return cls(
            source_sequence_number=0,
            projection_type="",
            projection_version=0,
            projection_event_id="",
        )

    @classmethod
    def from_legacy_source_sequence(
        cls,
        after_source_sequence: int,
    ) -> FrontendWorkflowEventCursor:
        if (
            not isinstance(after_source_sequence, int)
            or isinstance(after_source_sequence, bool)
            or after_source_sequence < 0
        ):
            raise ValueError("after_source_sequence must be a non-negative int")
        return cls(
            source_sequence_number=after_source_sequence,
            projection_type="",
            projection_version=0,
            projection_event_id="",
            sequence_only=True,
        )

    @classmethod
    def from_event(cls, event: FrontendWorkflowEvent) -> FrontendWorkflowEventCursor:
        return cls(
            source_sequence_number=event.source_sequence_number,
            projection_type=event.projection_type,
            projection_version=event.projection_version,
            projection_event_id=event.projection_event_id,
        )

    def serialize(self) -> str:
        if self.sequence_only:
            raise ValueError("sequence-only cursors cannot be serialized")
        payload = {
            "v": _CURSOR_VERSION,
            "s": self.source_sequence_number,
            "t": self.projection_type,
            "pv": self.projection_version,
            "id": self.projection_event_id,
        }
        raw = json.dumps(
            payload,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @classmethod
    def parse(cls, value: str) -> FrontendWorkflowEventCursor:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("after_cursor must be a non-empty string")
        padded = value + ("=" * (-len(value) % 4))
        try:
            decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        except (ValueError, binascii.Error) as exc:
            raise ValueError("after_cursor is not valid base64url") from exc
        try:
            payload = json.loads(decoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("after_cursor is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("after_cursor payload must be an object")
        version = payload.get("v")
        if version != _CURSOR_VERSION:
            raise ValueError("after_cursor version is unsupported")
        return cls(
            source_sequence_number=_required_non_negative_int(
                payload.get("s"),
                field_name="source_sequence_number",
            ),
            projection_type=_required_str(
                payload.get("t"), field_name="projection_type"
            ),
            projection_version=_required_non_negative_int(
                payload.get("pv"),
                field_name="projection_version",
            ),
            projection_event_id=_required_str(
                payload.get("id"),
                field_name="projection_event_id",
            ),
        )


def _required_str(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be str")
    return value


def _required_non_negative_int(value: object, *, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value
