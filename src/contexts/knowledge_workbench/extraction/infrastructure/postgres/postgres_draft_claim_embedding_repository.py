from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from hashlib import sha256
from typing import Protocol

from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_embedding_persistence_port import (
    DraftClaimEmbeddingCandidate,
    DraftClaimEmbeddingPersistencePort,
    PersistDraftClaimEmbeddingsResult,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_embedding_read_repository_port import (
    DraftClaimEmbeddingReadRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.domain.entities.draft_claim_observation import (
    DraftClaimObservation,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_granularity import (
    DraftClaimGranularity,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_observation_ref import (
    DraftClaimObservationRef,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_text import (
    DraftClaimText,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.evidence_block import (
    EvidenceBlock,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.exclusion_scope import (
    ExclusionScope,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.possible_question import (
    PossibleQuestion,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


class DraftClaimEmbeddingConnectionLike(Protocol):
    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]: ...

    async def execute(self, query: str, *args: object) -> object: ...


class PostgresDraftClaimEmbeddingRepository(
    DraftClaimEmbeddingReadRepositoryPort,
    DraftClaimEmbeddingPersistencePort,
):
    def __init__(self, connection: DraftClaimEmbeddingConnectionLike) -> None:
        self._connection = connection

    async def list_unembedded_claim_observations_by_workflow_run_id(
        self,
        *,
        workflow_run_id: str,
        embedding_model_id: str,
        limit: int,
    ) -> tuple[DraftClaimObservation, ...]:
        _require_non_empty_text(workflow_run_id, "workflow_run_id")
        _require_non_empty_text(embedding_model_id, "embedding_model_id")
        if not isinstance(limit, int):
            raise TypeError("limit must be int")
        if limit <= 0:
            raise ValueError("limit must be > 0")

        rows = await self._connection.fetch(
            """
            SELECT
                dco.observation_ref,
                dco.source_unit_ref,
                dco.claim,
                dco.granularity,
                COALESCE(
                    array_agg(dpq.question ORDER BY dpq.ordinal)
                        FILTER (WHERE dpq.question IS NOT NULL),
                    ARRAY[]::text[]
                ) AS possible_questions,
                dco.exclusion_scope,
                dco.evidence_block,
                dco.created_at,
                su.ordinal AS source_unit_ordinal,
                p.claim_index
            FROM draft_claim_observations AS dco
            JOIN draft_claim_observation_provenance AS p
                ON p.observation_ref = dco.observation_ref
            JOIN source_units AS su
                ON su.unit_ref = dco.source_unit_ref
            LEFT JOIN draft_claim_observation_possible_questions AS dpq
                ON dpq.observation_ref = dco.observation_ref
            LEFT JOIN draft_claim_embeddings AS existing
                ON existing.observation_ref = dco.observation_ref
               AND existing.embedding_model_id = $2
            WHERE p.workflow_run_id = $1
              AND existing.embedding_ref IS NULL
            GROUP BY
                dco.observation_ref,
                dco.source_unit_ref,
                dco.claim,
                dco.granularity,
                dco.exclusion_scope,
                dco.evidence_block,
                dco.created_at,
                su.ordinal,
                p.claim_index
            ORDER BY
                su.ordinal ASC,
                p.claim_index ASC NULLS LAST,
                dco.created_at ASC,
                dco.observation_ref ASC
            LIMIT $3
            """,
            workflow_run_id,
            embedding_model_id,
            limit,
        )
        return tuple(_observation_from_row(row) for row in rows)

    async def persist_draft_claim_embeddings(
        self,
        candidates: tuple[DraftClaimEmbeddingCandidate, ...],
    ) -> PersistDraftClaimEmbeddingsResult:
        if not isinstance(candidates, tuple):
            raise TypeError("candidates must be tuple")
        inserted_count = 0
        for candidate in candidates:
            if not isinstance(candidate, DraftClaimEmbeddingCandidate):
                raise TypeError("candidates must contain DraftClaimEmbeddingCandidate")
            status = await self._connection.execute(
                """
                INSERT INTO draft_claim_embeddings (
                    embedding_ref,
                    workflow_run_id,
                    source_document_ref,
                    source_unit_ref,
                    observation_ref,
                    embedding_text,
                    embedding_text_hash,
                    embedding_model_id,
                    dimensions,
                    embedding,
                    created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::vector, $11)
                ON CONFLICT (observation_ref, embedding_model_id, embedding_text_hash)
                    DO NOTHING
                """,
                _embedding_ref(candidate),
                candidate.workflow_run_id,
                candidate.source_document_ref,
                candidate.source_unit_ref,
                candidate.observation_ref,
                candidate.embedding_text,
                candidate.embedding_text_hash,
                candidate.embedding_model_id,
                candidate.dimensions,
                _pg_vector_text(candidate.vector),
                candidate.created_at,
            )
            if _inserted(status):
                inserted_count += 1

        return PersistDraftClaimEmbeddingsResult(
            requested_count=len(candidates),
            inserted_count=inserted_count,
            already_exists_count=len(candidates) - inserted_count,
        )


def _observation_from_row(row: Mapping[str, object]) -> DraftClaimObservation:
    return DraftClaimObservation(
        observation_ref=DraftClaimObservationRef(_required_str(row, "observation_ref")),
        source_unit_ref=SourceUnitRef(_required_str(row, "source_unit_ref")),
        claim=DraftClaimText(_required_str(row, "claim")),
        granularity=DraftClaimGranularity(_required_str(row, "granularity")),
        possible_questions=tuple(
            PossibleQuestion(question)
            for question in _str_tuple(_value(row, "possible_questions"))
        ),
        exclusion_scope=ExclusionScope(
            _required_str_allow_empty(row, "exclusion_scope")
        ),
        evidence_block=EvidenceBlock(_required_str(row, "evidence_block")),
        created_at=_required_datetime(row, "created_at"),
    )


def _embedding_ref(candidate: DraftClaimEmbeddingCandidate) -> str:
    digest = sha256(
        (
            f"{candidate.workflow_run_id}:"
            f"{candidate.observation_ref}:"
            f"{candidate.embedding_model_id}:"
            f"{candidate.embedding_text_hash}"
        ).encode("utf-8"),
    ).hexdigest()
    return f"draft-claim-embedding:{digest}"


def _pg_vector_text(vector: tuple[float, ...]) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def _inserted(status: object) -> bool:
    text = str(status)
    return text.endswith(" 1") or text == "INSERT 1"


def _value(row: Mapping[str, object], key: str) -> object:
    try:
        return row[key]
    except KeyError as exc:
        raise KeyError(f"Missing draft claim embedding row column: {key}") from exc


def _required_str(row: Mapping[str, object], key: str) -> str:
    value = _value(row, key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty str")
    return value


def _required_str_allow_empty(row: Mapping[str, object], key: str) -> str:
    value = _value(row, key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be str")
    return value


def _required_datetime(row: Mapping[str, object], key: str) -> datetime:
    value = _value(row, key)
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime")
    return value


def _str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise TypeError("possible_questions must be sequence")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise TypeError("possible_questions must contain non-empty strings")
        result.append(item)
    return tuple(result)


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
