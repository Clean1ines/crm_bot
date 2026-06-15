from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Protocol, cast

from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalQuery,
    PublishedWorkbenchRetrievalResult,
    PublishedWorkbenchRetrievalSourceRef,
)
from src.contexts.knowledge_workbench.retrieval.application.ports.published_workbench_retrieval_port import (
    PublishedWorkbenchRetrievalPort,
)


PUBLISHED_WORKBENCH_VECTOR_SEARCH_SQL = """
SELECT
    entry.runtime_entry_id,
    CASE
        WHEN entry.source_refs ? 'workflow_run_id'
        THEN 'draft-claim-curation-publication:' || (entry.source_refs->>'workflow_run_id')
        ELSE NULL
    END AS publication_id,
    entry.project_id::text AS project_id,
    entry.fact_id,
    entry.claim,
    entry.answer_text,
    entry.possible_questions,
    entry.embedding_text,
    entry.source_refs,
    entry.source_refs->>'workflow_run_id' AS workflow_run_id,
    entry.source_refs->>'source_document_ref' AS source_document_ref,
    entry.source_refs->>'curation_item_ref' AS curation_item_ref,
    entry.source_refs->'source_claim_refs' AS source_claim_refs,
    fact.exclusion_scope,
    NULL::text AS evidence_block,
    (1 - (emb.embedding <=> $4::vector)) AS score,
    row_number() OVER (ORDER BY emb.embedding <=> $4::vector) AS rank
FROM knowledge_workbench_runtime_retrieval_entry_embeddings AS emb
JOIN knowledge_workbench_runtime_retrieval_entries AS entry
  ON entry.runtime_entry_id = emb.runtime_entry_id
JOIN knowledge_workbench_canonical_facts AS fact
  ON fact.fact_id = entry.fact_id
WHERE entry.project_id = $1::uuid
  AND entry.visibility = 'published'
  AND entry.status = 'active'
  AND fact.status = 'published'
  AND emb.embedding_model_id = $2
  AND emb.dimensions = $3
ORDER BY emb.embedding <=> $4::vector
LIMIT $5
"""


class PublishedWorkbenchRetrievalConnectionLike(Protocol):
    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]: ...


class PublishedWorkbenchRetrievalAcquireContextLike(Protocol):
    async def __aenter__(self) -> PublishedWorkbenchRetrievalConnectionLike: ...

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> bool | None: ...


class PublishedWorkbenchRetrievalPoolLike(Protocol):
    def acquire(self) -> PublishedWorkbenchRetrievalAcquireContextLike: ...


class PostgresPublishedWorkbenchRetrievalRepository(PublishedWorkbenchRetrievalPort):
    def __init__(self, connection_or_pool: object) -> None:
        self._connection_or_pool = connection_or_pool

    async def search(
        self,
        *,
        project_id: str,
        query_text: str,
        query_embedding: Sequence[float],
        embedding_model_id: str,
        dimensions: int,
        limit: int,
    ) -> tuple[PublishedWorkbenchRetrievalResult, ...]:
        query = PublishedWorkbenchRetrievalQuery.from_sequence(
            project_id=project_id,
            query_text=query_text,
            query_embedding=query_embedding,
            embedding_model_id=embedding_model_id,
            dimensions=dimensions,
            limit=limit,
        )

        if _has_acquire(self._connection_or_pool):
            async with cast(
                PublishedWorkbenchRetrievalPoolLike,
                self._connection_or_pool,
            ).acquire() as connection:
                return await _search_with_connection(connection, query)

        return await _search_with_connection(
            cast(PublishedWorkbenchRetrievalConnectionLike, self._connection_or_pool),
            query,
        )


async def _search_with_connection(
    connection: PublishedWorkbenchRetrievalConnectionLike,
    query: PublishedWorkbenchRetrievalQuery,
) -> tuple[PublishedWorkbenchRetrievalResult, ...]:
    rows = await connection.fetch(
        PUBLISHED_WORKBENCH_VECTOR_SEARCH_SQL,
        query.project_id,
        query.embedding_model_id,
        query.dimensions,
        _pg_vector_text(query.query_embedding),
        query.limit,
    )
    return tuple(_result_from_row(row) for row in rows)


def _result_from_row(row: Mapping[str, object]) -> PublishedWorkbenchRetrievalResult:
    source_ref = _source_ref_from_row(row)
    return PublishedWorkbenchRetrievalResult(
        runtime_entry_id=_text(row, "runtime_entry_id"),
        publication_id=_optional_text(row.get("publication_id")),
        project_id=_text(row, "project_id"),
        source_document_ref=source_ref.source_document_ref,
        fact_id=_text(row, "fact_id"),
        curation_item_ref=source_ref.curation_item_ref,
        claim=_text(row, "claim"),
        answer_text=_text(row, "answer_text"),
        possible_questions=_text_tuple(row.get("possible_questions")),
        exclusion_scope=_optional_text(row.get("exclusion_scope")),
        evidence_block=_optional_text(row.get("evidence_block")),
        source_claim_refs=source_ref.source_claim_refs,
        embedding_text=_text(row, "embedding_text"),
        score=_float(row, "score"),
        rank=_int(row, "rank"),
        source_ref=source_ref,
    )


def _source_ref_from_row(
    row: Mapping[str, object],
) -> PublishedWorkbenchRetrievalSourceRef:
    source_refs = _mapping(row.get("source_refs"))
    source_claim_refs = _text_tuple(
        row.get("source_claim_refs") or source_refs.get("source_claim_refs")
    )
    return PublishedWorkbenchRetrievalSourceRef(
        workflow_run_id=_optional_text(
            row.get("workflow_run_id") or source_refs.get("workflow_run_id")
        ),
        source_document_ref=_optional_text(
            row.get("source_document_ref") or source_refs.get("source_document_ref")
        ),
        curation_item_ref=_optional_text(
            row.get("curation_item_ref") or source_refs.get("curation_item_ref")
        ),
        source_claim_refs=source_claim_refs,
    )


def _has_acquire(value: object) -> bool:
    return callable(getattr(value, "acquire", None))


def _pg_vector_text(vector: tuple[float, ...]) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def _text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("optional text value must be str or None")
    stripped = value.strip()
    return stripped or None


def _text_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parsed = json.loads(value)
        return _text_tuple(parsed)
    if not isinstance(value, list):
        raise TypeError("value must be list")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise TypeError(f"value[{index}] must be text")
        stripped = item.strip()
        if stripped:
            result.append(stripped)
    return tuple(result)


def _mapping(value: object) -> Mapping[str, object]:
    if value is None:
        return {}
    if isinstance(value, str):
        parsed = json.loads(value)
        return _mapping(parsed)
    if not isinstance(value, Mapping):
        raise TypeError("source_refs must be object")
    return value


def _float(row: Mapping[str, object], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be numeric")
    return float(value)


def _int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value
