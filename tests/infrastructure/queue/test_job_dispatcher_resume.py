from unittest.mock import AsyncMock

import pytest

from src.infrastructure.queue import job_dispatcher as dispatcher_module
from src.infrastructure.queue.job_dispatcher import JobDispatcher
from src.infrastructure.queue.job_types import TASK_RESUME_KNOWLEDGE_PROCESSING


@pytest.mark.asyncio
async def test_dispatcher_routes_resume_task(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = AsyncMock()
    monkeypatch.setattr(
        dispatcher_module, "handle_resume_knowledge_processing", handler
    )
    dispatcher = JobDispatcher(db_pool=object())
    await dispatcher.dispatch(
        {"type": TASK_RESUME_KNOWLEDGE_PROCESSING, "payload": {}}, worker_id="worker-1"
    )
    handler.assert_awaited_once()
