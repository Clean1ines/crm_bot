from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast
from unittest.mock import AsyncMock

import pytest

from src.interfaces.http.rag_eval import enqueue_full_rag_eval_for_document
from src.infrastructure.queue.job_types import TASK_RUN_FULL_RAG_EVAL


class _QueueRepo:
    def __init__(self) -> None:
        self.enqueue = AsyncMock(return_value="job-1")


class _ProjectRepo:
    async def user_has_project_role(
        self,
        project_id: str,
        current_user_id: str,
        roles: list[str],
    ) -> bool:
        return True


class _UserRepo:
    async def is_platform_admin(self, current_user_id: str) -> bool:
        return False


class _Conn:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        return {
            "id": "00000000-0000-0000-0000-000000000002",
            "project_id": "00000000-0000-0000-0000-000000000001",
            "status": "processed",
            "file_name": "full-doc.md",
            "chunk_count": 17,
        }


class _AcquireContext:
    async def __aenter__(self) -> _Conn:
        return _Conn()

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _Pool:
    def acquire(self) -> _AcquireContext:
        return _AcquireContext()


@pytest.mark.asyncio
async def test_enqueue_full_rag_eval_queues_full_document_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.interfaces.http import rag_eval

    monkeypatch.setattr(rag_eval, "has_configured_groq_api_key", lambda: True)

    queue_repo = _QueueRepo()

    enqueue = cast(
        Callable[..., Awaitable[dict[str, object]]],
        enqueue_full_rag_eval_for_document,
    )

    response = await enqueue(
        document_id="00000000-0000-0000-0000-000000000002",
        current_user_id="user-1",
        pool=_Pool(),
        project_repo=_ProjectRepo(),
        user_repo=_UserRepo(),
        queue_repo=queue_repo,
    )

    assert response["ok"] is True
    assert response["queued"] is True
    assert response["job_id"] == "job-1"
    assert response["mode"] == "full_document"
    assert "target_questions" not in response

    queue_repo.enqueue.assert_awaited_once()
    awaited = queue_repo.enqueue.await_args
    assert awaited is not None

    task_type, payload = awaited.args[:2]
    assert task_type == TASK_RUN_FULL_RAG_EVAL
    assert payload["mode"] == "full_document"
    assert payload["document_id"] == "00000000-0000-0000-0000-000000000002"
    legacy_density_key = "questions" + "_per_chunk"
    assert legacy_density_key not in payload
    assert "max_questions" not in payload
    assert "target_questions" not in payload
    assert awaited.kwargs["max_attempts"] == 20
