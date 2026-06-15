from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol

from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_read_repository_port import (
    DraftClaimObservationReadModel,
    DraftClaimObservationReadRepositoryPort,
)


class DraftClaimObservationReadConnectionLike(Protocol):
    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]: ...


class PostgresDraftClaimObservationReadRepository(
    DraftClaimObservationReadRepositoryPort,
):
    """Read-only adapter for draft claim observation visibility."""

    def __init__(self, connection: DraftClaimObservationReadConnectionLike) -> None:
        self._connection = connection

    async def list_by_source_document_ref(
        self,
        *,
        source_document_ref: str,
        limit: int,
        offset: int,
    ) -> tuple[DraftClaimObservationReadModel, ...]:
        _require_non_empty_text(source_document_ref, "source_document_ref")
        _validate_page(limit=limit, offset=offset)
        rows = await self._connection.fetch(
            _DRAFT_CLAIM_OBSERVATION_SELECT
            + """
            WHERE su.document_ref = $1
            """
            + _DRAFT_CLAIM_OBSERVATION_GROUP_ORDER_PAGE,
            source_document_ref,
            limit,
            offset,
        )
        return tuple(_read_model_from_row(row) for row in rows)

    async def list_by_source_unit_ref(
        self,
        *,
        source_unit_ref: str,
        limit: int,
        offset: int,
    ) -> tuple[DraftClaimObservationReadModel, ...]:
        _require_non_empty_text(source_unit_ref, "source_unit_ref")
        _validate_page(limit=limit, offset=offset)
        rows = await self._connection.fetch(
            _DRAFT_CLAIM_OBSERVATION_SELECT
            + """
            WHERE dco.source_unit_ref = $1
            """
            + _DRAFT_CLAIM_OBSERVATION_GROUP_ORDER_PAGE,
            source_unit_ref,
            limit,
            offset,
        )
        return tuple(_read_model_from_row(row) for row in rows)

    async def list_by_observation_refs(
        self,
        *,
        observation_refs: tuple[str, ...],
    ) -> tuple[DraftClaimObservationReadModel, ...]:
        _validate_observation_refs(observation_refs)
        rows = await self._connection.fetch(
            _DRAFT_CLAIM_OBSERVATION_SELECT
            + """
            WHERE dco.observation_ref = ANY($1::text[])
            """
            + _DRAFT_CLAIM_OBSERVATION_GROUP_ORDER,
            list(observation_refs),
        )
        models = tuple(_read_model_from_row(row) for row in rows)
        models_by_ref = {model.observation_ref: model for model in models}
        return tuple(
            model
            for observation_ref in observation_refs
            for model in (models_by_ref.get(observation_ref),)
            if model is not None
        )


_DRAFT_CLAIM_OBSERVATION_SELECT = """
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
    p.workflow_run_id,
    p.stage_run_id,
    p.work_item_id,
    p.work_item_attempt_id,
    p.llm_task_id,
    p.llm_attempt_id,
    p.prompt_id,
    p.prompt_version,
    p.claim_index,
    dco.created_at,
    su.ordinal AS source_unit_ordinal
FROM draft_claim_observations AS dco
JOIN source_units AS su
    ON su.unit_ref = dco.source_unit_ref
LEFT JOIN draft_claim_observation_possible_questions AS dpq
    ON dpq.observation_ref = dco.observation_ref
LEFT JOIN draft_claim_observation_provenance AS p
    ON p.observation_ref = dco.observation_ref
"""

_DRAFT_CLAIM_OBSERVATION_GROUP_ORDER = """
GROUP BY
    dco.observation_ref,
    dco.source_unit_ref,
    dco.claim,
    dco.granularity,
    dco.exclusion_scope,
    dco.evidence_block,
    p.workflow_run_id,
    p.stage_run_id,
    p.work_item_id,
    p.work_item_attempt_id,
    p.llm_task_id,
    p.llm_attempt_id,
    p.prompt_id,
    p.prompt_version,
    p.claim_index,
    dco.created_at,
    su.ordinal
ORDER BY
    su.ordinal ASC,
    p.claim_index ASC NULLS LAST,
    dco.created_at ASC,
    dco.observation_ref ASC
"""

_DRAFT_CLAIM_OBSERVATION_GROUP_ORDER_PAGE = (
    _DRAFT_CLAIM_OBSERVATION_GROUP_ORDER
    + """
LIMIT $2 OFFSET $3
"""
)


def _validate_observation_refs(observation_refs: tuple[str, ...]) -> None:
    if not isinstance(observation_refs, tuple):
        raise TypeError("observation_refs must be tuple")
    if not observation_refs:
        raise ValueError("observation_refs must be non-empty")
    if len(set(observation_refs)) != len(observation_refs):
        raise ValueError("observation_refs must be unique")
    for observation_ref in observation_refs:
        _require_non_empty_text(observation_ref, "observation_ref")


def _validate_page(*, limit: int, offset: int) -> None:
    if not isinstance(limit, int):
        raise TypeError("limit must be int")
    if limit <= 0:
        raise ValueError("limit must be > 0")
    if not isinstance(offset, int):
        raise TypeError("offset must be int")
    if offset < 0:
        raise ValueError("offset must be >= 0")


def _read_model_from_row(row: Mapping[str, object]) -> DraftClaimObservationReadModel:
    return DraftClaimObservationReadModel(
        observation_ref=_required_str(row, "observation_ref"),
        source_unit_ref=_required_str(row, "source_unit_ref"),
        claim=_required_str(row, "claim"),
        granularity=_required_str(row, "granularity"),
        possible_questions=_str_tuple(_value(row, "possible_questions")),
        exclusion_scope=_required_str_allow_empty(row, "exclusion_scope"),
        evidence_block=_required_str(row, "evidence_block"),
        workflow_run_id=_optional_str(row, "workflow_run_id"),
        stage_run_id=_optional_str(row, "stage_run_id"),
        work_item_id=_optional_str(row, "work_item_id"),
        work_item_attempt_id=_optional_str(row, "work_item_attempt_id"),
        llm_task_id=_optional_str(row, "llm_task_id"),
        llm_attempt_id=_optional_str(row, "llm_attempt_id"),
        prompt_id=_optional_str(row, "prompt_id"),
        prompt_version=_optional_str(row, "prompt_version"),
        claim_index=_optional_int(row, "claim_index"),
        created_at=_required_datetime(row, "created_at"),
    )


def _value(row: Mapping[str, object], key: str) -> object:
    try:
        return row[key]
    except KeyError as exc:
        raise KeyError(f"Missing draft claim observation read column: {key}") from exc


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


def _optional_str(row: Mapping[str, object], key: str) -> str | None:
    value = _value(row, key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be null or non-empty str")
    return value


def _optional_int(row: Mapping[str, object], key: str) -> int | None:
    value = _value(row, key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise TypeError(f"{key} must be null or int")
    if value < 0:
        raise ValueError(f"{key} must be >= 0")
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
