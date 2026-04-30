from unittest.mock import AsyncMock

import pytest

from src.infrastructure.queue.handlers.metrics import handle_update_metrics


@pytest.mark.asyncio
async def test_handle_update_metrics_skips_missing_thread_without_updating_metrics():
    metrics_repo = AsyncMock()
    thread_read_repo = AsyncMock()
    thread_read_repo.get_thread_with_project_view.return_value = None

    await handle_update_metrics(
        {
            "id": "job-1",
            "payload": {
                "thread_id": "thread-1",
                "total_messages": 3,
            },
        },
        metrics_repo=metrics_repo,
        thread_read_repo=thread_read_repo,
    )

    metrics_repo.update_thread_metrics.assert_not_awaited()
