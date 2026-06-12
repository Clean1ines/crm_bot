from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Protocol

from src.contexts.knowledge_workbench.extraction.application.ports.validated_draft_claim_observation_persistence_port import (
    PersistValidatedDraftClaimObservationsPort,
    PersistValidatedDraftClaimObservationsResult,
    ValidatedDraftClaimObservationCandidate,
)


class ValidatedDraftClaimObservationPersistenceConnectionLike(Protocol):
    async def execute(self, query: str, *args: object) -> object: ...


class PostgresValidatedDraftClaimObservationPersistence(
    PersistValidatedDraftClaimObservationsPort,
):
    """Postgres adapter for validated claim observations produced by execute flow.

    Uses the existing draft_claim_observations persistence tables. Transaction
    ownership stays at the composition boundary.
    """

    def __init__(
        self,
        connection: ValidatedDraftClaimObservationPersistenceConnectionLike,
    ) -> None:
        self._connection = connection

    async def persist_validated_claims(
        self,
        candidates: tuple[ValidatedDraftClaimObservationCandidate, ...],
    ) -> PersistValidatedDraftClaimObservationsResult:
        if not isinstance(candidates, tuple):
            raise TypeError("candidates must be tuple")
        if not candidates:
            return PersistValidatedDraftClaimObservationsResult(persisted_count=0)

        created_at = _utc_now()
        for candidate in candidates:
            if not isinstance(candidate, ValidatedDraftClaimObservationCandidate):
                raise TypeError(
                    "candidates must contain ValidatedDraftClaimObservationCandidate"
                )
            await self._persist_candidate(candidate, created_at=created_at)

        return PersistValidatedDraftClaimObservationsResult(
            persisted_count=len(candidates),
        )

    async def _persist_candidate(
        self,
        candidate: ValidatedDraftClaimObservationCandidate,
        *,
        created_at: datetime,
    ) -> None:
        observation_ref = _observation_ref(candidate)

        await self._connection.execute(
            """
            INSERT INTO draft_claim_observations (
                observation_ref,
                source_unit_ref,
                claim,
                granularity,
                exclusion_scope,
                evidence_block,
                created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (observation_ref) DO UPDATE SET
                source_unit_ref = EXCLUDED.source_unit_ref,
                claim = EXCLUDED.claim,
                granularity = EXCLUDED.granularity,
                exclusion_scope = EXCLUDED.exclusion_scope,
                evidence_block = EXCLUDED.evidence_block,
                created_at = EXCLUDED.created_at
            """,
            observation_ref,
            candidate.source_unit_ref,
            candidate.claim,
            candidate.granularity.value,
            candidate.exclusion_scope,
            candidate.evidence_block,
            created_at,
        )

        await self._connection.execute(
            """
            DELETE FROM draft_claim_observation_possible_questions
            WHERE observation_ref = $1
            """,
            observation_ref,
        )

        for ordinal, question in enumerate(candidate.possible_questions):
            await self._connection.execute(
                """
                INSERT INTO draft_claim_observation_possible_questions (
                    observation_ref,
                    ordinal,
                    question
                )
                VALUES ($1, $2, $3)
                ON CONFLICT (observation_ref, ordinal) DO UPDATE SET
                    question = EXCLUDED.question
                """,
                observation_ref,
                ordinal,
                question,
            )

        await self._connection.execute(
            """
            INSERT INTO draft_claim_observation_provenance (
                observation_ref,
                source_unit_ref,
                workflow_run_id,
                stage_run_id,
                work_item_id,
                work_item_attempt_id,
                llm_task_id,
                llm_attempt_id,
                prompt_id,
                prompt_version,
                raw_artifact_ref,
                parsed_artifact_ref,
                claim_index,
                created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT (observation_ref) DO UPDATE SET
                source_unit_ref = EXCLUDED.source_unit_ref,
                workflow_run_id = EXCLUDED.workflow_run_id,
                stage_run_id = EXCLUDED.stage_run_id,
                work_item_id = EXCLUDED.work_item_id,
                work_item_attempt_id = EXCLUDED.work_item_attempt_id,
                llm_task_id = EXCLUDED.llm_task_id,
                llm_attempt_id = EXCLUDED.llm_attempt_id,
                prompt_id = EXCLUDED.prompt_id,
                prompt_version = EXCLUDED.prompt_version,
                raw_artifact_ref = EXCLUDED.raw_artifact_ref,
                parsed_artifact_ref = EXCLUDED.parsed_artifact_ref,
                claim_index = EXCLUDED.claim_index,
                created_at = EXCLUDED.created_at
            """,
            observation_ref,
            candidate.source_unit_ref,
            candidate.workflow_run_id,
            candidate.workflow_run_id,
            candidate.work_item_id,
            candidate.dispatch_attempt_id,
            candidate.work_item_id,
            candidate.dispatch_attempt_id,
            f"{candidate.provider}:claim_builder_section_extraction",
            candidate.model_ref,
            None,
            None,
            candidate.claim_index,
            created_at,
        )


def _observation_ref(candidate: ValidatedDraftClaimObservationCandidate) -> str:
    digest = sha256(
        (
            f"{candidate.workflow_run_id}:"
            f"{candidate.source_unit_ref}:"
            f"{candidate.work_item_id}:"
            f"{candidate.dispatch_attempt_id}:"
            f"{candidate.claim_index}:"
            f"{candidate.claim}"
        ).encode("utf-8"),
    ).hexdigest()
    return f"draft-claim-observation:{digest}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
