from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domain.project_plane.model_usage_views import ModelUsageEventCreate
from src.infrastructure.db.repositories.model_usage_repository import (
    ModelUsageRepository,
)


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_conn
    mock_cm.__aexit__.return_value = None
    pool.acquire = MagicMock(return_value=mock_cm)
    pool.mock_conn = mock_conn
    return pool


@pytest.mark.asyncio
async def test_record_event_persists_usage_event(mock_pool):
    repo = ModelUsageRepository(mock_pool)
    event = ModelUsageEventCreate(
        project_id=str(uuid4()),
        provider="voyage",
        model="voyage-4-lite",
        usage_type="embedding",
        source="knowledge_upload",
        tokens_input=10,
        tokens_output=None,
        tokens_total=10,
        estimated_cost_usd=None,
        document_id=str(uuid4()),
        metadata={"is_estimated": False},
    )

    await repo.record_event(event)

    mock_pool.mock_conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_project_usage_summary_aggregates_usage(mock_pool):
    repo = ModelUsageRepository(mock_pool)
    mock_pool.mock_conn.fetchrow = AsyncMock(
        side_effect=[
            {
                "tokens_month_total": 1400,
                "estimated_cost_month_usd": 2.5,
            },
            {
                "tokens_today_total": 250,
            },
        ]
    )
    mock_pool.mock_conn.fetch = AsyncMock(
        side_effect=[
            [
                {
                    "provider": "voyage",
                    "model": "voyage-4-lite",
                    "usage_type": "embedding",
                    "source": "knowledge_upload",
                    "tokens_input": 1000,
                    "tokens_output": 0,
                    "tokens_total": 1000,
                    "estimated_cost_usd": 1.0,
                    "events_count": 3,
                },
                {
                    "provider": "voyage",
                    "model": "voyage-4-lite",
                    "usage_type": "embedding",
                    "source": "rag_search",
                    "tokens_input": 400,
                    "tokens_output": 0,
                    "tokens_total": 400,
                    "estimated_cost_usd": 1.5,
                    "events_count": 8,
                },
            ],
            [
                {
                    "day": datetime(2026, 5, 2, tzinfo=UTC).date(),
                    "tokens_total": 250,
                    "estimated_cost_usd": 0.75,
                }
            ],
        ]
    )

    summary = await repo.get_project_usage_summary(
        project_id=str(uuid4()),
        month_start_utc=datetime(2026, 5, 1, tzinfo=UTC),
        month_end_utc=datetime(2026, 6, 1, tzinfo=UTC),
        today_start_utc=datetime(2026, 5, 2, tzinfo=UTC),
        monthly_budget_tokens=2000,
    )

    assert summary.tokens_month_total == 1400
    assert summary.tokens_today_total == 250
    assert summary.remaining_tokens == 600
    assert len(summary.breakdown) == 2
    assert summary.breakdown[0].source == "knowledge_upload"
    assert len(summary.daily) == 1
