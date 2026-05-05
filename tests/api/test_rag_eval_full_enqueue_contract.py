from __future__ import annotations

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

    monkeypatch.setattr(rag_eval.settings, "GROQ_API_KEY", "test-groq-key")

    queue_repo = _QueueRepo()

    response = await enqueue_full_rag_eval_for_document(
        document_id="00000000-0000-0000-0000-000000000002",
        questions_per_chunk=1,
        max_questions=None,
        current_user_id="user-1",
        pool=_Pool(),  # type: ignore[arg-type]
        project_repo=_ProjectRepo(),  # type: ignore[arg-type]
        user_repo=_UserRepo(),  # type: ignore[arg-type]
        queue_repo=queue_repo,  # type: ignore[arg-type]
    )

    assert response["ok"] is True
    assert response["queued"] is True
    assert response["job_id"] == "job-1"
    assert response["mode"] == "full_document"
    assert response["target_questions"] == 17

    queue_repo.enqueue.assert_awaited_once()
    task_type, payload = queue_repo.enqueue.await_args.args[:2]
    assert task_type == TASK_RUN_FULL_RAG_EVAL
    assert payload["mode"] == "full_document"
    assert payload["questions_per_chunk"] == 1
    assert payload["document_id"] == "00000000-0000-0000-0000-000000000002"
    assert queue_repo.enqueue.await_args.kwargs["max_attempts"] == 20
