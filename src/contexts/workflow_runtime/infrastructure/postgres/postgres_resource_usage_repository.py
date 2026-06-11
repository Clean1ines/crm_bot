from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime

import asyncpg

from src.contexts.workflow_runtime.application.ports.resource_usage_repository_port import (
    ResourceUsageRepositoryPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_resource_usage_snapshot import (
    WorkflowResourceUsageSnapshot,
)


class PostgresResourceUsageRepository(ResourceUsageRepositoryPort):
    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def get_usage(
        self,
        workflow_run_id: str,
    ) -> WorkflowResourceUsageSnapshot | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                workflow_run_id,
                request_count,
                input_tokens,
                output_tokens,
                total_tokens,
                estimated_cost_microusd,
                duration_ms,
                provider_breakdown,
                updated_at
            FROM workflow_runtime_resource_usage_snapshots
            WHERE workflow_run_id = $1
            """,
            workflow_run_id,
        )
        if row is None:
            return None
        return _hydrate_usage(row)

    async def save_usage(
        self,
        usage: WorkflowResourceUsageSnapshot,
    ) -> WorkflowResourceUsageSnapshot:
        row = await self._connection.fetchrow(
            """
            INSERT INTO workflow_runtime_resource_usage_snapshots (
                workflow_run_id,
                request_count,
                input_tokens,
                output_tokens,
                total_tokens,
                estimated_cost_microusd,
                duration_ms,
                provider_breakdown,
                updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
            ON CONFLICT (workflow_run_id) DO UPDATE
            SET request_count = EXCLUDED.request_count,
                input_tokens = EXCLUDED.input_tokens,
                output_tokens = EXCLUDED.output_tokens,
                total_tokens = EXCLUDED.total_tokens,
                estimated_cost_microusd = EXCLUDED.estimated_cost_microusd,
                duration_ms = EXCLUDED.duration_ms,
                provider_breakdown = EXCLUDED.provider_breakdown,
                updated_at = EXCLUDED.updated_at
            RETURNING
                workflow_run_id,
                request_count,
                input_tokens,
                output_tokens,
                total_tokens,
                estimated_cost_microusd,
                duration_ms,
                provider_breakdown,
                updated_at
            """,
            usage.workflow_run_id,
            usage.request_count,
            usage.input_tokens,
            usage.output_tokens,
            usage.total_tokens,
            usage.estimated_cost_microusd,
            usage.duration_ms,
            json.dumps(
                _provider_breakdown_as_dict(usage.provider_breakdown), sort_keys=True
            ),
            usage.updated_at,
        )
        if row is None:
            raise RuntimeError("resource usage upsert did not return row")
        return _hydrate_usage(row)


def _hydrate_usage(row: Mapping[str, object]) -> WorkflowResourceUsageSnapshot:
    return WorkflowResourceUsageSnapshot(
        workflow_run_id=_required_str(row, "workflow_run_id"),
        request_count=_required_int(row, "request_count"),
        input_tokens=_required_int(row, "input_tokens"),
        output_tokens=_required_int(row, "output_tokens"),
        total_tokens=_required_int(row, "total_tokens"),
        estimated_cost_microusd=_required_int(row, "estimated_cost_microusd"),
        duration_ms=_required_int(row, "duration_ms"),
        provider_breakdown=_required_provider_breakdown(row, "provider_breakdown"),
        updated_at=_required_datetime(row, "updated_at"),
    )


def _provider_breakdown_as_dict(
    provider_breakdown: Mapping[str, Mapping[str, int]],
) -> dict[str, dict[str, int]]:
    return {
        provider_key: dict(provider_values)
        for provider_key, provider_values in provider_breakdown.items()
    }


def _required_provider_breakdown(
    row: Mapping[str, object],
    key: str,
) -> Mapping[str, Mapping[str, int]]:
    value = row[key]
    if isinstance(value, str):
        decoded = json.loads(value)
        if not isinstance(decoded, dict):
            raise TypeError(f"{key} must decode to object")
        value = decoded
    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be mapping")
    result: dict[str, dict[str, int]] = {}
    for provider_key, provider_values in value.items():
        if not isinstance(provider_key, str):
            raise TypeError("provider key must be str")
        if not isinstance(provider_values, Mapping):
            raise TypeError("provider values must be mapping")
        nested: dict[str, int] = {}
        for metric_name, metric_value in provider_values.items():
            if not isinstance(metric_name, str):
                raise TypeError("metric name must be str")
            if not isinstance(metric_value, int):
                raise TypeError("metric value must be int")
            nested[metric_name] = metric_value
        result[provider_key] = nested
    return result


def _required_str(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty string")
    return value


def _required_int(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value


def _required_datetime(row: Mapping[str, object], key: str) -> datetime:
    value = row[key]
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime")
    return value
