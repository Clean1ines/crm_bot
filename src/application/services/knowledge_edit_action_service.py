from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from typing import Protocol
from uuid import uuid4

from src.application.rag_eval.failure_classification import (
    KnowledgeEditAction,
    KnowledgeEditActionType,
    knowledge_edit_actions_from_value,
)
from src.domain.project_plane.json_types import JsonObject, JsonValue


_AUTO_EXECUTABLE_ACTIONS = {
    KnowledgeEditActionType.ATTACH_QUESTION_TO_ENTRY,
    KnowledgeEditActionType.REBUILD_EMBEDDING,
    KnowledgeEditActionType.RERUN_EVAL,
}

_MANUAL_REVIEW_ACTIONS = {
    KnowledgeEditActionType.CREATE_ENTRY_FROM_FAILURE,
}

TASK_RUN_FULL_RAG_EVAL = "run_full_rag_eval"


@dataclass(frozen=True, slots=True)
class KnowledgeEditActionExecutionResult:
    source_result_id: str
    project_id: str
    document_id: str
    total_actions: int
    applied_actions: int = 0
    rejected_actions: int = 0
    failed_actions: int = 0
    skipped_actions: int = 0
    queued_rerun_job_ids: tuple[str, ...] = ()

    @property
    def has_failures(self) -> bool:
        return self.failed_actions > 0


class RagEvalActionSourcePort(Protocol):
    async def load_result_action_source(self, result_id: str) -> JsonObject | None: ...


class KnowledgeEditActionRepositoryPort(Protocol):
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
        payload: JsonObject,
    ) -> JsonObject: ...

    async def mark_knowledge_edit_action_applied(
        self,
        action_id: str,
        *,
        result_payload: JsonObject | None = None,
    ) -> None: ...

    async def mark_knowledge_edit_action_rejected(
        self,
        action_id: str,
        *,
        error: str,
        result_payload: JsonObject | None = None,
    ) -> None: ...

    async def mark_knowledge_edit_action_failed(
        self,
        action_id: str,
        *,
        error: str,
        result_payload: JsonObject | None = None,
    ) -> None: ...

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
    ) -> None: ...

    async def rebuild_entry_embedding(
        self,
        *,
        action_id: str,
        project_id: str,
        document_id: str,
        target_entry_id: str,
    ) -> None: ...


class KnowledgeEditQueuePort(Protocol):
    async def enqueue(
        self,
        task_type: str,
        payload: JsonObject | None = None,
        max_attempts: int = 3,
    ) -> str: ...


class KnowledgeEditActionService:
    """Executes safe Stage H KnowledgeEditAction proposals from stored RAG eval results."""

    def __init__(
        self,
        *,
        action_source: RagEvalActionSourcePort,
        knowledge_repo: KnowledgeEditActionRepositoryPort,
        queue_repo: KnowledgeEditQueuePort,
        rerun_eval_task_type: str = TASK_RUN_FULL_RAG_EVAL,
    ) -> None:
        self._action_source = action_source
        self._knowledge_repo = knowledge_repo
        self._queue_repo = queue_repo
        self._rerun_eval_task_type = rerun_eval_task_type

    async def execute_result_actions(
        self,
        *,
        result_id: str,
        actor_user_id: str,
    ) -> KnowledgeEditActionExecutionResult:
        source = await self._action_source.load_result_action_source(result_id)
        if source is None:
            raise ValueError(f"RAG eval result not found: {result_id}")

        project_id = _required_text(source.get("project_id"), "project_id")
        document_id = _required_text(source.get("document_id"), "document_id")
        run_id = _required_text(source.get("run_id"), "run_id")
        question_id = _required_text(source.get("question_id"), "question_id")
        question_text = _optional_text(source.get("question"))

        actions = knowledge_edit_actions_from_value(
            _json_or_native(source.get("proposed_actions"))
        )

        applied = 0
        rejected = 0
        failed = 0
        skipped = 0
        queued_job_ids: list[str] = []

        for index, action in enumerate(actions):
            stored = await self._knowledge_repo.create_or_get_knowledge_edit_action(
                action_id=_action_id(result_id=result_id, index=index),
                project_id=project_id,
                document_id=document_id,
                source_result_id=result_id,
                source_run_id=run_id,
                source_question_id=question_id,
                action_index=index,
                actor_user_id=actor_user_id,
                action_type=action.action_type.value,
                target_entry_id=action.target_entry_id,
                reason=action.reason,
                payload=_json_object_from_mapping(action.payload),
            )
            action_record_id = _required_text(stored.get("id"), "action_id")
            status = _optional_text(stored.get("status"))

            if status in {"applied", "rejected"}:
                skipped += 1
                continue

            if action.action_type in _MANUAL_REVIEW_ACTIONS:
                await self._knowledge_repo.mark_knowledge_edit_action_rejected(
                    action_record_id,
                    error=(
                        "Stage H does not auto-execute create_entry_from_failure yet; "
                        "manual canonical entry creation/review is required."
                    ),
                    result_payload={"action_type": action.action_type.value},
                )
                rejected += 1
                continue

            if action.action_type not in _AUTO_EXECUTABLE_ACTIONS:
                await self._knowledge_repo.mark_knowledge_edit_action_rejected(
                    action_record_id,
                    error=(
                        "Stage H does not auto-execute this action type yet; "
                        "manual review is required."
                    ),
                    result_payload={"action_type": action.action_type.value},
                )
                rejected += 1
                continue

            try:
                job_id = await self._execute_action(
                    action_id=action_record_id,
                    action=action,
                    project_id=project_id,
                    document_id=document_id,
                    question=question_text,
                    actor_user_id=actor_user_id,
                )
            except Exception as exc:
                await self._knowledge_repo.mark_knowledge_edit_action_failed(
                    action_record_id,
                    error=str(exc),
                    result_payload={"action_type": action.action_type.value},
                )
                failed += 1
                continue

            result_payload: JsonObject = {"action_type": action.action_type.value}
            if job_id:
                result_payload["queued_job_id"] = job_id
                queued_job_ids.append(job_id)

            await self._knowledge_repo.mark_knowledge_edit_action_applied(
                action_record_id,
                result_payload=result_payload,
            )
            applied += 1

        return KnowledgeEditActionExecutionResult(
            source_result_id=result_id,
            project_id=project_id,
            document_id=document_id,
            total_actions=len(actions),
            applied_actions=applied,
            rejected_actions=rejected,
            failed_actions=failed,
            skipped_actions=skipped,
            queued_rerun_job_ids=tuple(queued_job_ids),
        )

    async def _execute_action(
        self,
        *,
        action_id: str,
        action: KnowledgeEditAction,
        project_id: str,
        document_id: str,
        question: str,
        actor_user_id: str,
    ) -> str | None:
        if action.action_type == KnowledgeEditActionType.ATTACH_QUESTION_TO_ENTRY:
            target_entry_id = _required_text(
                action.target_entry_id,
                "target_entry_id",
            )
            payload_question = _optional_text(action.payload.get("question"))
            await self._knowledge_repo.attach_question_to_entry(
                action_id=action_id,
                project_id=project_id,
                document_id=document_id,
                target_entry_id=target_entry_id,
                question=payload_question or question,
                reason=action.reason,
                actor_user_id=actor_user_id,
            )
            return None

        if action.action_type == KnowledgeEditActionType.REBUILD_EMBEDDING:
            target_entry_id = _required_text(
                action.target_entry_id,
                "target_entry_id",
            )
            await self._knowledge_repo.rebuild_entry_embedding(
                action_id=action_id,
                project_id=project_id,
                document_id=document_id,
                target_entry_id=target_entry_id,
            )
            return None

        if action.action_type == KnowledgeEditActionType.RERUN_EVAL:
            return await self._queue_repo.enqueue(
                self._rerun_eval_task_type,
                {
                    "project_id": project_id,
                    "document_id": document_id,
                    "requested_by": actor_user_id,
                    "mode": "full_document",
                    "retrieval_limit": 5,
                    "source": "knowledge_edit_action",
                    "source_action_id": action_id,
                },
                max_attempts=20,
            )

        raise ValueError(f"Unsupported Stage H action: {action.action_type.value}")


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_value(item) for item in value]
    return str(value)


def _json_object_from_mapping(value: Mapping[str, object]) -> JsonObject:
    return {str(key): _json_value(item) for key, item in value.items()}


def _json_or_native(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _action_id(*, result_id: str, index: int) -> str:
    safe_result = "".join(ch if ch.isalnum() else "_" for ch in result_id)[:80]
    return f"kedit_{safe_result}_{index}_{uuid4().hex[:12]}"


def _optional_text(value: object) -> str:
    return str(value or "").strip()


def _required_text(value: object, field_name: str) -> str:
    text = _optional_text(value)
    if not text:
        raise ValueError(f"Stage H action source missing {field_name}")
    return text
