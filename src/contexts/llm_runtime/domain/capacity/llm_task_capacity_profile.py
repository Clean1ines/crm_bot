from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LlmTaskCapacityProfile:
    profile_id: str
    input_tokens: int
    artifact_tokens: int
    request_count: int = 1

    def __post_init__(self) -> None:
        _require_non_empty_text(self.profile_id, field_name="profile_id")
        _require_positive_int(self.input_tokens, field_name="input_tokens")
        _require_non_negative_int(self.artifact_tokens, field_name="artifact_tokens")
        _require_positive_int(self.request_count, field_name="request_count")

    @property
    def required_window_tokens(self) -> int:
        return self.input_tokens + self.artifact_tokens


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_positive_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
