import asyncio

import pytest

from src.infrastructure.queue import runtime


class _DummyQueueRepo:
    pass


class _DummyDispatcher:
    pass


@pytest.mark.asyncio
async def test_run_configured_worker_loops_uses_configured_concurrency(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[str] = []
    shutdown_event = asyncio.Event()

    async def fake_run_worker_loop(**kwargs: object) -> None:
        worker_id = kwargs["worker_id"]
        assert isinstance(worker_id, str)
        calls.append(worker_id)

    monkeypatch.setattr(runtime.settings, "WORKER_CONCURRENCY", 3)
    monkeypatch.setattr(runtime, "run_worker_loop", fake_run_worker_loop)

    await runtime._run_configured_worker_loops(
        queue_repo=_DummyQueueRepo(),
        dispatcher=_DummyDispatcher(),
        shutdown_event=shutdown_event,
    )

    assert calls == ["worker-1", "worker-2", "worker-3"]
