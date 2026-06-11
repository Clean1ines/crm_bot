from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType


def _missing_updated_at() -> datetime:
    raise ValueError("updated_at is required")


@dataclass(frozen=True, slots=True)
class WorkflowResourceUsageSnapshot:
    workflow_run_id: str
    request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_microusd: int = 0
    duration_ms: int = 0
    provider_breakdown: Mapping[str, Mapping[str, int]] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=_missing_updated_at)

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        for field_name, value in (
            ("request_count", self.request_count),
            ("input_tokens", self.input_tokens),
            ("output_tokens", self.output_tokens),
            ("total_tokens", self.total_tokens),
            ("estimated_cost_microusd", self.estimated_cost_microusd),
            ("duration_ms", self.duration_ms),
        ):
            _require_non_negative_int(value, field_name)
        _require_timezone_aware(self.updated_at, "updated_at")
        object.__setattr__(
            self,
            "provider_breakdown",
            _freeze_provider_breakdown(self.provider_breakdown),
        )

    def add_usage(
        self,
        *,
        request_count: int,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        estimated_cost_microusd: int,
        duration_ms: int,
        provider_key: str | None,
        updated_at: datetime,
    ) -> WorkflowResourceUsageSnapshot:
        usage_delta = {
            "request_count": request_count,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_microusd": estimated_cost_microusd,
            "duration_ms": duration_ms,
        }
        for field_name, value in usage_delta.items():
            _require_non_negative_int(value, field_name)
        if provider_key is not None:
            _require_non_empty_text(provider_key, "provider_key")
        _require_timezone_aware(updated_at, "updated_at")

        provider_breakdown = _mutable_provider_breakdown(self.provider_breakdown)
        if provider_key is not None:
            provider_values = provider_breakdown.setdefault(
                provider_key,
                _zero_provider_values(),
            )
            for field_name, value in usage_delta.items():
                provider_values[field_name] += value

        return WorkflowResourceUsageSnapshot(
            workflow_run_id=self.workflow_run_id,
            request_count=self.request_count + request_count,
            input_tokens=self.input_tokens + input_tokens,
            output_tokens=self.output_tokens + output_tokens,
            total_tokens=self.total_tokens + total_tokens,
            estimated_cost_microusd=(
                self.estimated_cost_microusd + estimated_cost_microusd
            ),
            duration_ms=self.duration_ms + duration_ms,
            provider_breakdown=provider_breakdown,
            updated_at=updated_at,
        )


def _zero_provider_values() -> dict[str, int]:
    return {
        "request_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_microusd": 0,
        "duration_ms": 0,
    }


def _mutable_provider_breakdown(
    provider_breakdown: Mapping[str, Mapping[str, int]],
) -> dict[str, dict[str, int]]:
    return {
        provider_key: dict(provider_values)
        for provider_key, provider_values in provider_breakdown.items()
    }


def _freeze_provider_breakdown(
    provider_breakdown: Mapping[str, Mapping[str, int]],
) -> Mapping[str, Mapping[str, int]]:
    frozen: dict[str, Mapping[str, int]] = {}
    for provider_key, provider_values in provider_breakdown.items():
        _require_non_empty_text(provider_key, "provider_key")
        provider_result: dict[str, int] = {}
        for field_name, value in provider_values.items():
            _require_non_empty_text(field_name, "provider metric")
            _require_non_negative_int(value, f"{provider_key}.{field_name}")
            provider_result[field_name] = value
        frozen[provider_key] = MappingProxyType(provider_result)
    return MappingProxyType(frozen)


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
