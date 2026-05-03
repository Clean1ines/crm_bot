from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast

import asyncpg

from src.domain.project_plane.model_usage_views import (
    ModelUsageSource,
    ModelUsageBreakdownView,
    ModelUsageDailyView,
    ModelUsageEventCreate,
    ModelUsageSummaryView,
    ModelUsageType,
)
from src.infrastructure.config.settings import settings
from src.utils.uuid_utils import ensure_uuid


class ModelUsageRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def record_event(self, event: ModelUsageEventCreate) -> None:
        if not settings.MODEL_USAGE_COUNTER_ENABLED:
            return

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO model_usage_events (
                    project_id,
                    provider,
                    model,
                    usage_type,
                    source,
                    tokens_input,
                    tokens_output,
                    tokens_total,
                    estimated_cost_usd,
                    document_id,
                    thread_id,
                    metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb)
                """,
                ensure_uuid(event.project_id),
                event.provider,
                event.model,
                event.usage_type,
                event.source,
                event.tokens_input,
                event.tokens_output,
                event.tokens_total,
                event.estimated_cost_usd,
                ensure_uuid(event.document_id) if event.document_id else None,
                ensure_uuid(event.thread_id) if event.thread_id else None,
                json.dumps(event.metadata, ensure_ascii=False),
            )

    async def get_project_usage_summary(
        self,
        *,
        project_id: str,
        month_start_utc: datetime,
        month_end_utc: datetime,
        today_start_utc: datetime,
        monthly_budget_tokens: int,
    ) -> ModelUsageSummaryView:
        project_uuid = ensure_uuid(project_id)

        async with self.pool.acquire() as conn:
            month_row = await conn.fetchrow(
                """
                SELECT
                    COALESCE(SUM(tokens_total), 0)::bigint AS tokens_month_total,
                    COALESCE(SUM(estimated_cost_usd), 0)::double precision AS estimated_cost_month_usd
                FROM model_usage_events
                WHERE project_id = $1
                  AND created_at >= $2
                  AND created_at < $3
                """,
                project_uuid,
                month_start_utc,
                month_end_utc,
            )
            today_row = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(tokens_total), 0)::bigint AS tokens_today_total
                FROM model_usage_events
                WHERE project_id = $1
                  AND created_at >= $2
                  AND created_at < $3
                """,
                project_uuid,
                today_start_utc,
                month_end_utc,
            )
            breakdown_rows = await conn.fetch(
                """
                SELECT
                    provider,
                    model,
                    usage_type,
                    source,
                    COALESCE(SUM(tokens_input), 0)::bigint AS tokens_input,
                    COALESCE(SUM(tokens_output), 0)::bigint AS tokens_output,
                    COALESCE(SUM(tokens_total), 0)::bigint AS tokens_total,
                    COALESCE(SUM(estimated_cost_usd), 0)::double precision AS estimated_cost_usd,
                    COUNT(*)::int AS events_count
                FROM model_usage_events
                WHERE project_id = $1
                  AND created_at >= $2
                  AND created_at < $3
                GROUP BY provider, model, usage_type, source
                ORDER BY tokens_total DESC, provider ASC, model ASC
                """,
                project_uuid,
                month_start_utc,
                month_end_utc,
            )
            daily_rows = await conn.fetch(
                """
                SELECT
                    DATE(created_at AT TIME ZONE 'UTC') AS day,
                    COALESCE(SUM(tokens_total), 0)::bigint AS tokens_total,
                    COALESCE(SUM(estimated_cost_usd), 0)::double precision AS estimated_cost_usd
                FROM model_usage_events
                WHERE project_id = $1
                  AND created_at >= $2
                  AND created_at < $3
                GROUP BY day
                ORDER BY day ASC
                """,
                project_uuid,
                month_start_utc,
                month_end_utc,
            )

        tokens_month_total = (
            int(month_row["tokens_month_total"]) if month_row is not None else 0
        )
        estimated_cost_month_usd = (
            float(month_row["estimated_cost_month_usd"])
            if month_row is not None
            else 0.0
        )
        tokens_today_total = (
            int(today_row["tokens_today_total"]) if today_row is not None else 0
        )
        remaining_tokens = max(0, int(monthly_budget_tokens) - tokens_month_total)

        breakdown = tuple(
            ModelUsageBreakdownView(
                provider=str(row["provider"]),
                model=str(row["model"]),
                usage_type=_coerce_usage_type(row["usage_type"]),
                source=_coerce_usage_source(row["source"]),
                tokens_input=int(row["tokens_input"]),
                tokens_output=int(row["tokens_output"]),
                tokens_total=int(row["tokens_total"]),
                estimated_cost_usd=float(row["estimated_cost_usd"]),
                events_count=int(row["events_count"]),
            )
            for row in breakdown_rows
        )
        daily = tuple(
            ModelUsageDailyView(
                day=row["day"],
                tokens_total=int(row["tokens_total"]),
                estimated_cost_usd=float(row["estimated_cost_usd"]),
            )
            for row in daily_rows
        )

        return ModelUsageSummaryView(
            project_id=project_id,
            month_start=month_start_utc,
            month_end=month_end_utc,
            today_start=today_start_utc,
            tokens_month_total=tokens_month_total,
            tokens_today_total=tokens_today_total,
            estimated_cost_month_usd=estimated_cost_month_usd,
            monthly_budget_tokens=int(monthly_budget_tokens),
            remaining_tokens=remaining_tokens,
            breakdown=breakdown,
            daily=daily,
        )


def _coerce_usage_type(value: object) -> ModelUsageType:
    text = str(value)
    if text not in {"embedding", "llm"}:
        raise ValueError(f"Unsupported usage type in ledger row: {text}")
    return cast(ModelUsageType, text)


def _coerce_usage_source(value: object) -> ModelUsageSource:
    text = str(value)
    if text not in {"knowledge_upload", "knowledge_preprocessing", "rag_search"}:
        raise ValueError(f"Unsupported usage source in ledger row: {text}")
    return cast(ModelUsageSource, text)


def current_month_window_utc(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or datetime.now(UTC)
    month_start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    return month_start, next_month


def today_start_utc(now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    return current.replace(hour=0, minute=0, second=0, microsecond=0)
