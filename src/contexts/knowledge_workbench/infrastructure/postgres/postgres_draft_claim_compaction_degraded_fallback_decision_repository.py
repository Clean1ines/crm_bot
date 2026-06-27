from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

from src.contexts.knowledge_workbench.application.sagas.confirm_draft_claim_compaction_degraded_fallback import (
    DraftClaimCompactionDegradedFallbackDecision,
    DraftClaimCompactionDegradedFallbackDecisionRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.domain.project_plane.json_types import JsonObject


class DraftClaimCompactionFallbackConnectionLike(Protocol):
    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> Mapping[str, object] | None: ...


class PostgresDraftClaimCompactionDegradedFallbackDecisionRepository(
    DraftClaimCompactionDegradedFallbackDecisionRepositoryPort,
):
    def __init__(
        self,
        connection: DraftClaimCompactionFallbackConnectionLike,
    ) -> None:
        self._connection = connection

    async def load_pending_decision(
        self,
        *,
        workflow_run_id: str,
        project_id: str,
    ) -> DraftClaimCompactionDegradedFallbackDecision | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                waiting.causation_command_id AS source_command_id,
                command_log.payload AS source_command_payload,
                waiting.payload AS waiting_payload,
                waiting.payload->>'degraded_candidate_model_id'
                    AS degraded_model_ref
            FROM workflow_runtime_outbox_events AS waiting
            LEFT JOIN workflow_runtime_command_log AS command_log
              ON command_log.command_id = waiting.causation_command_id
            JOIN knowledge_extraction_workflow_runs AS workflow_run
              ON workflow_run.workflow_run_id = waiting.workflow_run_id
            WHERE waiting.workflow_run_id = $1
              AND workflow_run.project_id = $2
              AND waiting.event_type = $3
              AND NOT EXISTS (
                  SELECT 1
                  FROM workflow_runtime_outbox_events AS resolved
                  WHERE resolved.workflow_run_id = waiting.workflow_run_id
                    AND resolved.event_type = $4
                    AND resolved.causation_command_id =
                        waiting.causation_command_id
              )
            ORDER BY waiting.sequence_number DESC
            LIMIT 1
            FOR UPDATE OF command_log
            """,
            workflow_run_id,
            project_id,
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_WAITING_USER_MODEL_CHOICE.value,
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_USER_MODEL_CHOICE_RESOLVED.value,
        )
        if row is None:
            return None

        source_payload_value = row.get("source_command_payload")
        source_payload = (
            cast(JsonObject, dict(source_payload_value))
            if isinstance(source_payload_value, Mapping)
            and source_payload_value.get("llm_dispatch_preparation") is not None
            else None
        )
        waiting_payload = row.get("waiting_payload")
        if not isinstance(waiting_payload, Mapping):
            waiting_payload = {}
        degraded_model_ref = row.get("degraded_model_ref")
        if not isinstance(degraded_model_ref, str) or not degraded_model_ref.strip():
            raise ValueError("waiting event degraded_candidate_model_id is missing")

        return DraftClaimCompactionDegradedFallbackDecision(
            source_command_id=WorkflowCommandId(str(row["source_command_id"])),
            degraded_model_ref=degraded_model_ref,
            source_command_payload=source_payload,
            group_ref=_optional_text(waiting_payload, "group_ref"),
            node_refs=_text_tuple(waiting_payload.get("node_refs")),
            resume_work_type=_optional_text(waiting_payload, "resume_work_type"),
            input_tokens=_optional_int(
                waiting_payload,
                "input_tokens",
            ),
            artifact_tokens=_optional_int(
                waiting_payload,
                "artifact_tokens",
            ),
        )


def _optional_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value


def _text_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TypeError("node_refs must be list")
    result = tuple(item for item in value if isinstance(item, str) and item.strip())
    if len(result) != len(value):
        raise ValueError("node_refs must contain non-empty text")
    return result


def _optional_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value
