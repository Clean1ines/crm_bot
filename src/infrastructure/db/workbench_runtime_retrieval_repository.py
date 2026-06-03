from __future__ import annotations

import math
import re
from dataclasses import dataclass
import json
from typing import Any

import asyncpg

from src.domain.project_plane.knowledge_views import (
    KnowledgeSearchResultView,
    KnowledgeSearchTraceView,
)
from src.utils.uuid_utils import ensure_uuid


_RUNTIME_SEARCH_SQL = """
SELECT
    runtime_entry_id,
    fact_id,
    claim,
    possible_questions,
    answer_text,
    embedding_text,
    source_refs
FROM knowledge_workbench_runtime_retrieval_entries
WHERE project_id = $1
  AND status = 'published'
  AND visibility = 'runtime'
  AND (
      claim ILIKE $2
      OR answer_text ILIKE $2
      OR embedding_text ILIKE $2
      OR possible_questions::text ILIKE $2
      OR source_refs::text ILIKE $2
  )
ORDER BY created_at DESC
LIMIT $3
"""


_RUNTIME_DELETE_FACTS_SQL = """
DELETE FROM knowledge_workbench_runtime_retrieval_entries
WHERE project_id = $1
  AND fact_id = ANY($2::text[])
"""


_RUNTIME_INSERT_SQL = """
INSERT INTO knowledge_workbench_runtime_retrieval_entries (
    runtime_entry_id,
    project_id,
    fact_id,
    claim,
    possible_questions,
    answer_text,
    embedding_text,
    source_refs,
    visibility,
    status
)
VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7,$8::jsonb,$9,$10)
ON CONFLICT (runtime_entry_id) DO UPDATE SET
    claim = EXCLUDED.claim,
    possible_questions = EXCLUDED.possible_questions,
    answer_text = EXCLUDED.answer_text,
    embedding_text = EXCLUDED.embedding_text,
    source_refs = EXCLUDED.source_refs,
    visibility = EXCLUDED.visibility,
    status = EXCLUDED.status
"""


_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё_]+")


@dataclass(frozen=True, slots=True)
class _RuntimeRowScore:
    score: float
    matched_fields: tuple[str, ...]


class WorkbenchRuntimeRetrievalRepository:
    """Runtime retrieval adapter over published FAQ Workbench surfaces.

    This is the production RAG/SearchKnowledgeTool read side for FAQ Workbench.
    It deliberately reads only Workbench runtime retrieval entries and avoids
    retired compiler/candidate/source-chunk tables.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
        hybrid_fallback: bool = True,
        thread_id: str | None = None,
    ) -> list[KnowledgeSearchResultView]:
        del hybrid_fallback, thread_id

        normalized_query = _normalize_query(query)
        if not project_id or not normalized_query or limit <= 0:
            return []

        db_limit = max(limit * 8, 40)
        like_query = f"%{normalized_query}%"

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                _RUNTIME_SEARCH_SQL,
                ensure_uuid(project_id),
                like_query,
                db_limit,
            )

        results: list[KnowledgeSearchResultView] = []
        for row in rows:
            score = _score_runtime_row(row, normalized_query)
            if score.score <= 0:
                continue

            source_refs = _text_tuple(row.get("source_refs"))
            possible_questions = _text_tuple(row.get("possible_questions"))

            results.append(
                KnowledgeSearchResultView(
                    id=str(row["runtime_entry_id"]),
                    content=str(row["answer_text"]),
                    score=score.score,
                    method="workbench_runtime_retrieval",
                    document_id=None,
                    source=str(row["fact_id"]),
                    document_status="published",
                    entry_kind="faq_workbench_fact",
                    title=str(row["claim"]),
                    source_excerpt=source_refs[0] if source_refs else None,
                    source_refs=source_refs,
                    embedding_text=str(row["embedding_text"]),
                    questions=(str(row["claim"]), *possible_questions),
                    synonyms=(),
                    tags=("faq_workbench", "runtime"),
                    trace=KnowledgeSearchTraceView(
                        matched_fields=score.matched_fields,
                        lexical_score=score.score,
                        vector_score=0.0,
                        exact_claim_match="claim"
                        in score.matched_fields,
                        title_match="claim" in score.matched_fields,
                        length_penalty=0.0,
                        final_score=score.score,
                        retrieval_surface_role="faq_workbench_runtime",
                        displayed_field="answer",
                        is_production_safe=True,
                    ),
                )
            )

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]


    async def publish_fact_registry_runtime_entries(
        self,
        *,
        project_id: str,
        document_id: str,
        fact_registry_payload: Any,
    ) -> int:
        del document_id

        if not project_id:
            return 0
        if not isinstance(fact_registry_payload, dict):
            return 0

        canonical_facts = fact_registry_payload.get("canonical_facts")
        if not isinstance(canonical_facts, list) or not canonical_facts:
            return 0

        rows = tuple(_runtime_rows_from_fact_registry(project_id, canonical_facts))
        if not rows:
            return 0

        fact_ids = tuple(row["fact_id"] for row in rows)

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    _RUNTIME_DELETE_FACTS_SQL,
                    ensure_uuid(project_id),
                    list(fact_ids),
                )
                for row in rows:
                    await conn.execute(
                        _RUNTIME_INSERT_SQL,
                        row["runtime_entry_id"],
                        ensure_uuid(project_id),
                        row["fact_id"],
                        row["claim"],
                        _json(row["possible_questions"]),
                        row["answer_text"],
                        row["embedding_text"],
                        _json(row["source_refs"]),
                        "runtime",
                        "published",
                    )

        return len(rows)


def _normalize_query(value: str) -> str:
    return " ".join(_WORD_RE.findall(value.lower()))


def _field_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value if item is not None)
    return str(value)


def _text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value),)


def _score_runtime_row(row: asyncpg.Record, normalized_query: str) -> _RuntimeRowScore:
    terms = tuple(term for term in normalized_query.split() if term)
    if not terms:
        return _RuntimeRowScore(score=0.0, matched_fields=())

    fields = {
        "claim": _field_text(row.get("claim")).lower(),
        "possible_questions": _field_text(row.get("possible_questions")).lower(),
        "embedding_text": _field_text(row.get("embedding_text")).lower(),
        "answer_text": _field_text(row.get("answer_text")).lower(),
        "source_refs": _field_text(row.get("source_refs")).lower(),
    }

    weights = {
        "claim": 4.0,
        "possible_questions": 3.0,
        "embedding_text": 2.4,
        "answer_text": 1.5,
        "source_refs": 0.6,
    }

    matched_fields: list[str] = []
    raw_score = 0.0

    for field, text in fields.items():
        if not text:
            continue
        matches = sum(1 for term in terms if term in text)
        if matches <= 0:
            continue
        matched_fields.append(field)
        raw_score += weights[field] * (matches / len(terms))

    if normalized_query in fields["claim"]:
        raw_score += 2.0
    if normalized_query in fields["embedding_text"]:
        raw_score += 1.0

    score = min(1.0, raw_score / 8.0)
    if math.isnan(score) or math.isinf(score):
        score = 0.0

    return _RuntimeRowScore(
        score=score,
        matched_fields=tuple(matched_fields),
    )


__all__ = ["WorkbenchRuntimeRetrievalRepository"]

def _runtime_rows_from_fact_registry(
    project_id: str,
    canonical_facts: list[Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for raw_fact in canonical_facts:
        if not isinstance(raw_fact, dict):
            continue

        fact_id = _clean_text(raw_fact.get("fact_id"))
        claim = _clean_text(raw_fact.get("claim"))
        status = _clean_text(raw_fact.get("status")) or "active"

        if not fact_id or not claim or status != "active":
            continue

        answer_text = (
            _clean_text(raw_fact.get("answer"))
            or _clean_text(raw_fact.get("short_answer"))
            or claim
        )
        possible_questions = _text_list(raw_fact.get("question_variants"))
        source_refs = _source_refs_from_fact(raw_fact)
        embedding_text = _embedding_text_from_fact(
            claim=claim,
            answer_text=answer_text,
            possible_questions=possible_questions,
            source_refs=source_refs,
            scope=_clean_text(raw_fact.get("scope")),
            exclusion_scope=_clean_text(raw_fact.get("exclusion_scope")),
            triples=raw_fact.get("triples"),
        )

        rows.append(
            {
                "runtime_entry_id": f"runtime:{project_id}:{fact_id}",
                "fact_id": fact_id,
                "claim": claim,
                "possible_questions": possible_questions,
                "answer_text": answer_text,
                "embedding_text": embedding_text,
                "source_refs": source_refs,
            }
        )

    return rows


def _embedding_text_from_fact(
    *,
    claim: str,
    answer_text: str,
    possible_questions: tuple[str, ...],
    source_refs: tuple[str, ...],
    scope: str,
    exclusion_scope: str,
    triples: Any,
) -> str:
    parts: list[str] = [
        f"claim: {claim}",
        f"answer: {answer_text}",
    ]

    if possible_questions:
        parts.append("questions: " + " | ".join(possible_questions))
    if scope:
        parts.append(f"scope: {scope}")
    if exclusion_scope:
        parts.append(f"exclusion_scope: {exclusion_scope}")

    triple_texts = _triple_texts(triples)
    if triple_texts:
        parts.append("triples: " + " | ".join(triple_texts))

    if source_refs:
        parts.append("source_refs: " + " | ".join(source_refs))

    return "\n".join(part for part in parts if part.strip())


def _triple_texts(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()

    result: list[str] = []
    for item in value:
        if isinstance(item, dict):
            subject = _clean_text(item.get("subject"))
            predicate = _clean_text(item.get("predicate"))
            object_ = _clean_text(item.get("object"))
            text = " ".join(part for part in (subject, predicate, object_) if part)
            if text:
                result.append(text)
        else:
            text = _clean_text(item)
            if text:
                result.append(text)

    return tuple(result)


def _source_refs_from_fact(raw_fact: dict[str, Any]) -> tuple[str, ...]:
    direct = _text_list(raw_fact.get("source_refs"))
    if direct:
        return direct

    refs: list[str] = []
    evidence = raw_fact.get("evidence")
    if isinstance(evidence, list):
        for item in evidence:
            if isinstance(item, dict):
                for key in ("source_ref", "source_section_ref", "source_local_ref"):
                    value = _clean_text(item.get(key))
                    if value:
                        refs.append(value)
            else:
                value = _clean_text(item)
                if value:
                    refs.append(value)

    mentions = raw_fact.get("mentions")
    if isinstance(mentions, list):
        for item in mentions:
            if not isinstance(item, dict):
                continue
            for key in ("source_ref", "source_section_ref", "source_local_ref"):
                value = _clean_text(item.get(key))
                if value:
                    refs.append(value)

    return tuple(dict.fromkeys(refs))


def _text_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        text
        for item in value
        if (text := _clean_text(item))
    )


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


