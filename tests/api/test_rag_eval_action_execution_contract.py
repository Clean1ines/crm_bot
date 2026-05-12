from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import cast

from fastapi import HTTPException
import pytest

from src.application.rag_eval.failure_classification import (
    KnowledgeEditAction,
    KnowledgeEditActionType,
)
from src.interfaces.http import rag_eval


PROJECT_ID = "00000000-0000-0000-0000-000000000001"
DOCUMENT_ID = "00000000-0000-0000-0000-000000000002"
ENTRY_ID = "00000000-0000-0000-0000-000000000003"
RESULT_ID = "result-1"
USER_ID = "user-1"


class _Pool:
    def __init__(self, sources: Mapping[str, dict[str, object]] | None = None) -> None:
        self.sources = dict(sources or {})
        self.created_actions: list[dict[str, object]] = []
        self.applied_actions: list[dict[str, object]] = []
        self.rejected_actions: list[dict[str, object]] = []
        self.failed_actions: list[dict[str, object]] = []
        self.attached_questions: list[dict[str, object]] = []
        self.rebuilt_embeddings: list[dict[str, object]] = []


class _RagEvalRepository:
    def __init__(self, pool: _Pool) -> None:
        self._pool = pool

    async def load_result_action_source(
        self, result_id: str
    ) -> dict[str, object] | None:
        return self._pool.sources.get(result_id)


class _KnowledgeRepository:
    def __init__(self, pool: _Pool) -> None:
        self._pool = pool

    async def create_or_get_knowledge_edit_action(
        self,
        *,
        action_id: str,
        project_id: str,
        document_id: str,
        source_result_id: str,
        source_run_id: str,
        source_question_id: str,
        action_index: int,
        actor_user_id: str,
        action_type: str,
        target_entry_id: str | None,
        reason: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        stored_id = f"stored-action-{action_index}"
        self._pool.created_actions.append(
            {
                "id": stored_id,
                "project_id": project_id,
                "document_id": document_id,
                "source_result_id": source_result_id,
                "source_run_id": source_run_id,
                "source_question_id": source_question_id,
                "actor_user_id": actor_user_id,
                "action_type": action_type,
                "target_entry_id": target_entry_id,
                "reason": reason,
                "payload": payload,
            }
        )
        return {"id": stored_id, "status": "pending"}

    async def mark_knowledge_edit_action_applied(
        self,
        action_id: str,
        *,
        result_payload: dict[str, object] | None = None,
    ) -> None:
        self._pool.applied_actions.append(
            {"id": action_id, "result_payload": result_payload or {}}
        )

    async def mark_knowledge_edit_action_rejected(
        self,
        action_id: str,
        *,
        error: str,
        result_payload: dict[str, object] | None = None,
    ) -> None:
        self._pool.rejected_actions.append(
            {"id": action_id, "error": error, "result_payload": result_payload or {}}
        )

    async def mark_knowledge_edit_action_failed(
        self,
        action_id: str,
        *,
        error: str,
        result_payload: dict[str, object] | None = None,
    ) -> None:
        self._pool.failed_actions.append(
            {"id": action_id, "error": error, "result_payload": result_payload or {}}
        )

    async def attach_question_to_entry(
        self,
        *,
        action_id: str,
        project_id: str,
        document_id: str,
        target_entry_id: str,
        question: str,
        reason: str,
        actor_user_id: str,
    ) -> None:
        self._pool.attached_questions.append(
            {
                "action_id": action_id,
                "project_id": project_id,
                "document_id": document_id,
                "target_entry_id": target_entry_id,
                "question": question,
                "reason": reason,
                "actor_user_id": actor_user_id,
            }
        )

    async def rebuild_entry_embedding(
        self,
        *,
        action_id: str,
        project_id: str,
        document_id: str,
        target_entry_id: str,
    ) -> None:
        self._pool.rebuilt_embeddings.append(
            {
                "action_id": action_id,
                "project_id": project_id,
                "document_id": document_id,
                "target_entry_id": target_entry_id,
            }
        )


class _QueueRepo:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []

    async def enqueue(
        self,
        task_type: str,
        payload: dict[str, object] | None = None,
        max_attempts: int = 3,
    ) -> str:
        self.enqueued.append(
            {
                "task_type": task_type,
                "payload": payload or {},
                "max_attempts": max_attempts,
            }
        )
        return "job-1"


class _ProjectRepo:
    async def user_has_project_role(
        self,
        project_id: str,
        current_user_id: str,
        roles: list[str],
    ) -> bool:
        return (
            project_id == PROJECT_ID and current_user_id == USER_ID and "admin" in roles
        )

    async def get_project_view(self, project_id: str) -> object | None:
        return None


class _UserRepo:
    async def is_platform_admin(self, current_user_id: str) -> bool:
        return False


def _source(actions: list[dict[str, object]]) -> dict[str, object]:
    return {
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "run_id": "run-1",
        "question_id": "question-1",
        "question": "Как подключить менеджера?",
        "proposed_actions": actions,
    }


def _install_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rag_eval, "RagEvalRepository", _RagEvalRepository)

    from src.infrastructure.db.repositories import knowledge_repository

    monkeypatch.setattr(
        knowledge_repository,
        "KnowledgeRepository",
        _KnowledgeRepository,
    )


async def _execute(
    *,
    result_id: str,
    pool: _Pool,
    queue_repo: _QueueRepo,
) -> dict[str, object]:
    endpoint = cast(
        Callable[..., Awaitable[dict[str, object]]],
        rag_eval.execute_rag_eval_result_actions,
    )
    return await endpoint(
        result_id=result_id,
        current_user_id=USER_ID,
        pool=pool,
        project_repo=_ProjectRepo(),
        user_repo=_UserRepo(),
        queue_repo=queue_repo,
    )


@pytest.mark.asyncio
async def test_execute_result_actions_applies_safe_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)

    actions = [
        KnowledgeEditAction(
            action_type=KnowledgeEditActionType.ATTACH_QUESTION_TO_ENTRY,
            target_entry_id=ENTRY_ID,
            reason="User phrasing should enrich the canonical entry.",
            payload={
                "question": "Как подключить менеджера к проекту?",
                "embedding_text": "INTERNAL_RAW_EMBEDDING_TEXT_SHOULD_NOT_LEAK",
            },
        ).to_json(),
        KnowledgeEditAction(
            action_type=KnowledgeEditActionType.RERUN_EVAL,
            target_entry_id=None,
            reason="Verify retrieval after safe edit.",
            payload={},
        ).to_json(),
    ]
    pool = _Pool({RESULT_ID: _source(actions)})
    queue_repo = _QueueRepo()

    response = await _execute(result_id=RESULT_ID, pool=pool, queue_repo=queue_repo)

    assert response == {
        "ok": True,
        "source_result_id": RESULT_ID,
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "total_actions": 2,
        "applied_actions": 2,
        "rejected_actions": 0,
        "failed_actions": 0,
        "skipped_actions": 0,
        "queued_rerun_job_ids": ["job-1"],
    }
    assert len(pool.attached_questions) == 1
    assert pool.attached_questions[0]["target_entry_id"] == ENTRY_ID
    assert (
        pool.attached_questions[0]["question"] == "Как подключить менеджера к проекту?"
    )
    assert len(pool.applied_actions) == 2
    assert queue_repo.enqueued[0]["task_type"] == "run_full_rag_eval"
    assert queue_repo.enqueued[0]["max_attempts"] == 20

    rendered_response = repr(response)
    assert "embedding_text" not in rendered_response
    assert "INTERNAL_RAW_EMBEDDING_TEXT_SHOULD_NOT_LEAK" not in rendered_response


@pytest.mark.asyncio
async def test_execute_result_actions_rejects_manual_review_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)

    actions = [
        KnowledgeEditAction(
            action_type=KnowledgeEditActionType.CREATE_ENTRY_FROM_FAILURE,
            target_entry_id=None,
            reason="Missing answer requires manual canonical entry review.",
            payload={"draft_answer": "manual-only"},
        ).to_json(),
    ]
    pool = _Pool({RESULT_ID: _source(actions)})
    queue_repo = _QueueRepo()

    response = await _execute(result_id=RESULT_ID, pool=pool, queue_repo=queue_repo)

    assert response["ok"] is True
    assert response["total_actions"] == 1
    assert response["applied_actions"] == 0
    assert response["rejected_actions"] == 1
    assert response["failed_actions"] == 0
    assert response["queued_rerun_job_ids"] == []
    assert len(pool.rejected_actions) == 1
    assert "manual canonical entry creation" in str(pool.rejected_actions[0]["error"])
    assert queue_repo.enqueued == []


@pytest.mark.asyncio
async def test_execute_result_actions_missing_result_returns_clean_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)

    pool = _Pool()
    queue_repo = _QueueRepo()

    with pytest.raises(HTTPException) as exc_info:
        await _execute(result_id="missing-result", pool=pool, queue_repo=queue_repo)

    assert exc_info.value.status_code == 404
    assert "RAG eval result not found" in str(exc_info.value.detail)
    assert pool.created_actions == []
    assert queue_repo.enqueued == []
