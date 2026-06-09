from __future__ import annotations

from datetime import datetime, timezone
from types import MappingProxyType
from typing import Protocol, TypeAlias
from uuid import uuid4

from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_provenance_candidate_builder import DraftClaimObservationProvenanceCandidate
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_application_unit_of_work_port import (
    AsyncDraftClaimObservationApplicationUnitOfWorkPort,
    DraftClaimObservationApplicationEvent,
)
from src.contexts.knowledge_workbench.extraction.domain.entities.draft_claim_observation import DraftClaimObservation
from src.contexts.knowledge_workbench.extraction.domain.events.draft_claim_observation_events import DraftClaimObservationsApplied


JsonScalar: TypeAlias = None | bool | int | float | str
JsonObject: TypeAlias = dict[str, "JsonCompatible"]
JsonArray: TypeAlias = list["JsonCompatible"]
JsonCompatible: TypeAlias = JsonScalar | JsonObject | JsonArray


class AsyncTransactionLike(Protocol):
    async def start(self) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class AsyncConnectionLike(Protocol):
    def transaction(self) -> AsyncTransactionLike: ...

    async def execute(self, query: str, *args: object) -> object: ...


class DraftClaimObservationUnitOfWorkClosedError(RuntimeError):
    """Raised when a closed draft claim observation Unit of Work is reused."""


class PostgresDraftClaimObservationApplicationUnitOfWork(
    AsyncDraftClaimObservationApplicationUnitOfWorkPort,
):
    """Async PostgreSQL Unit of Work for applying Prompt A draft claims."""

    def __init__(self, connection: AsyncConnectionLike) -> None:
        self._connection = connection
        self._transaction: AsyncTransactionLike | None = None
        self._closed = False

    async def save_draft_claim_observations(
        self,
        observations: tuple[DraftClaimObservation, ...],
    ) -> None:
        if not observations:
            return

        await self._ensure_open_transaction()
        for observation in observations:
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
                observation.observation_ref.value,
                observation.source_unit_ref.value,
                observation.claim.value,
                observation.granularity.value,
                observation.exclusion_scope.value,
                observation.evidence_block.value,
                observation.created_at,
            )
            await self._connection.execute(
                """
                DELETE FROM draft_claim_observation_possible_questions
                WHERE observation_ref = $1
                """,
                observation.observation_ref.value,
            )
            for ordinal, question in enumerate(observation.possible_questions):
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
                    observation.observation_ref.value,
                    ordinal,
                    question.value,
                )

    async def save_draft_claim_observation_provenance_candidates(
        self,
        candidates: tuple[DraftClaimObservationProvenanceCandidate, ...],
    ) -> None:
        if not candidates:
            return

        await self._ensure_open_transaction()
        for candidate in candidates:
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
                candidate.observation_ref.value,
                candidate.source_unit_ref.value,
                candidate.workflow_run_id,
                candidate.stage_run_id,
                candidate.work_item_id,
                candidate.work_item_attempt_id,
                candidate.llm_task_id,
                candidate.llm_attempt_id,
                candidate.prompt_id,
                candidate.prompt_version,
                candidate.raw_artifact_ref.value,
                candidate.parsed_artifact_ref.value,
                candidate.claim_index,
                candidate.created_at,
            )

    async def append_event(self, event: DraftClaimObservationApplicationEvent) -> None:
        await self._ensure_open_transaction()
        event_type, aggregate_ref, payload, occurred_at = _map_event(event)
        await self._connection.execute(
            """
            INSERT INTO outbox_events (
                event_id,
                event_type,
                aggregate_ref,
                payload,
                occurred_at,
                created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            str(uuid4()),
            event_type,
            aggregate_ref,
            payload,
            occurred_at,
            _utc_now(),
        )

    async def commit(self) -> None:
        if self._closed:
            raise DraftClaimObservationUnitOfWorkClosedError(
                "Draft claim observation UnitOfWork is already closed",
            )

        if self._transaction is None:
            self._closed = True
            return

        try:
            await self._transaction.commit()
        except Exception:
            await self._transaction.rollback()
            self._closed = True
            raise

        self._closed = True

    async def rollback(self) -> None:
        if self._closed:
            raise DraftClaimObservationUnitOfWorkClosedError(
                "Draft claim observation UnitOfWork is already closed",
            )

        if self._transaction is not None:
            await self._transaction.rollback()

        self._closed = True

    async def _ensure_open_transaction(self) -> None:
        if self._closed:
            raise DraftClaimObservationUnitOfWorkClosedError(
                "Draft claim observation UnitOfWork is already closed",
            )

        if self._transaction is None:
            self._transaction = self._connection.transaction()
            await self._transaction.start()


def _map_event(
    event: DraftClaimObservationApplicationEvent,
) -> tuple[str, str, JsonObject, datetime]:
    if isinstance(event, DraftClaimObservationsApplied):
        return (
            "knowledge_workbench.extraction.draft_claim_observations_applied",
            event.artifact_ref.value,
            {
                "artifact_ref": event.artifact_ref.value,
                "source_unit_ref": event.source_unit_ref.value,
                "observation_count": event.observation_count,
                "occurred_at": event.occurred_at.isoformat(),
            },
            event.occurred_at,
        )
    raise TypeError(f"Unsupported draft claim observation event: {type(event).__name__}")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
