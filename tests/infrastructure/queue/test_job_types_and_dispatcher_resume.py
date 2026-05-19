from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.infrastructure.queue.job_dispatcher import JobDispatcher
from src.infrastructure.queue.job_types import (
    KNOWN_TASK_TYPES,
    TASK_RESUME_KNOWLEDGE_PROCESSING,
)


def test_resume_task_is_known_task_type():
    assert TASK_RESUME_KNOWLEDGE_PROCESSING in KNOWN_TASK_TYPES


@pytest.mark.asyncio
async def test_dispatcher_routes_resume_task_to_handler():
    dispatcher = JobDispatcher(
        thread_read_repo=Mock(),
        db_pool=object(),
        project_repo=Mock(),
        metrics_repo=Mock(),
        telegram_sender=Mock(),
        redis_getter=Mock(),
    )
    job = {"task_type": TASK_RESUME_KNOWLEDGE_PROCESSING, "payload": {}}

    with patch(
        "src.infrastructure.queue.job_dispatcher.handle_resume_knowledge_processing",
        new=AsyncMock(),
    ) as resume_handler:
        await dispatcher.dispatch(job, worker_id="w-1")

    resume_handler.assert_awaited_once_with(job, db_pool=dispatcher.db_pool)
