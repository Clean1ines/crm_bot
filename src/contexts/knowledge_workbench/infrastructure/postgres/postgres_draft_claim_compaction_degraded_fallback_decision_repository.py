from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

from src.contexts.knowledge_workbench.application.sagas.confirm_draft_claim_compaction_degraded_fallback import (
    DraftClaimCompactionDegradedFallbackDecision,
    DraftClaimCompactionDegradedFallbackDecisionRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
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
                waiting.payload->>'degraded_candidate_model_id'
                    AS degraded_model_ref
            FROM workflow_runtime_outbox_events AS waiting
            JOIN workflow_runtime_command_log AS command_log
              ON command_log.command_id = waiting.causation_command_id
            JOIN knowledge_extraction_workflow_runs AS workflow_run
              ON workflow_run.workflow_run_id = waiting.workflow_run_id
            WHERE waiting.workflow_run_id = $1
              AND workflow_run.project_id = $2
              AND waiting.event_type = $3
              AND waiting.payload->>'reason' =
                  'primary_model_daily_capacity_exhausted'
              AND command_log.command_type = $4
              AND NOT EXISTS (
                  SELECT 1
                  FROM workflow_runtime_outbox_events AS resolved
                  WHERE resolved.workflow_run_id = waiting.workflow_run_id
                    AND resolved.event_type = $5
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
            KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value,
            KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_USER_MODEL_CHOICE_RESOLVED.value,
        )
        if row is None:
            return None

        payload = row.get("source_command_payload")
        if not isinstance(payload, Mapping):
            raise TypeError("source_command_payload must be object")
        degraded_model_ref = row.get("degraded_model_ref")
        if not isinstance(degraded_model_ref, str) or not degraded_model_ref.strip():
            raise ValueError("waiting event degraded_candidate_model_id is missing")

        return DraftClaimCompactionDegradedFallbackDecision(
            source_command_id=WorkflowCommandId(str(row["source_command_id"])),
            source_command_payload=cast(JsonObject, dict(payload)),
            degraded_model_ref=degraded_model_ref,
        )
