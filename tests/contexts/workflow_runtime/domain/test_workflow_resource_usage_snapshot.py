from __future__ import annotations

from datetime import datetime, timezone
from types import MappingProxyType
from typing import cast

import pytest

from src.contexts.workflow_runtime.domain.entities.workflow_resource_usage_snapshot import (
    WorkflowResourceUsageSnapshot,
)


def _now() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


def _later() -> datetime:
    return datetime(2026, 6, 11, 12, 1, tzinfo=timezone.utc)


def test_resource_usage_rejects_negative_counters() -> None:
    with pytest.raises(ValueError, match="input_tokens must be >= 0"):
        WorkflowResourceUsageSnapshot(
            workflow_run_id="workflow-1",
            input_tokens=-1,
            updated_at=_now(),
        )


def test_resource_usage_add_usage_increments_tokens_cost_duration() -> None:
    usage = WorkflowResourceUsageSnapshot(
        workflow_run_id="workflow-1",
        updated_at=_now(),
    )

    updated = usage.add_usage(
        request_count=1,
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        estimated_cost_microusd=40,
        duration_ms=50,
        provider_key="groq:qwen",
        updated_at=_later(),
    )

    assert updated.request_count == 1
    assert updated.input_tokens == 10
    assert updated.output_tokens == 20
    assert updated.total_tokens == 30
    assert updated.estimated_cost_microusd == 40
    assert updated.duration_ms == 50


def test_provider_breakdown_increments_provider_specific_counters() -> None:
    usage = WorkflowResourceUsageSnapshot(
        workflow_run_id="workflow-1",
        updated_at=_now(),
    )

    first = usage.add_usage(
        request_count=1,
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        estimated_cost_microusd=40,
        duration_ms=50,
        provider_key="groq:qwen",
        updated_at=_later(),
    )
    second = first.add_usage(
        request_count=2,
        input_tokens=3,
        output_tokens=4,
        total_tokens=7,
        estimated_cost_microusd=8,
        duration_ms=9,
        provider_key="groq:qwen",
        updated_at=_later(),
    )

    assert second.provider_breakdown["groq:qwen"]["request_count"] == 3
    assert second.provider_breakdown["groq:qwen"]["input_tokens"] == 13
    assert isinstance(second.provider_breakdown, MappingProxyType)
    with pytest.raises(TypeError):
        cast(dict[str, object], second.provider_breakdown)["other"] = {}
