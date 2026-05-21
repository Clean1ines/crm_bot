from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from src.domain.project_plane.knowledge_retrieval_surface import (
    RUNTIME_ENTRY_KIND_VALUES,
)
from src.domain.project_plane.knowledge_views import KnowledgeSearchTraceView


class _RowLookup(Protocol):
    def __getitem__(self, key: str) -> object: ...


@dataclass(frozen=True, slots=True)
class _TraceScore:
    score: float
    trace: KnowledgeSearchTraceView


@dataclass(frozen=True)
class SearchScoreAndTrace:
    score: float
    method: str
    trace: KnowledgeSearchTraceView


@dataclass(frozen=True, slots=True)
class _PreviewTextFields:
    search_text: str
    title: str
    questions: str
    synonyms: str
    tags: str
    embedding_text: str


@dataclass(frozen=True, slots=True)
class _PreviewOverlaps:
    search: float
    answer: float
    title: float
    questions: float
    synonyms: float
    tags: float
    embedding_text: float


@dataclass(frozen=True, slots=True)
class _PreviewMatchFlags:
    title: bool
    question: bool
    exact_question: bool


def _optional_row_text(row: _RowLookup, key: str) -> str | None:
    try:
        value = row[key]
    except KeyError:
        return None

    return str(value) if value is not None else None


def _optional_row_value(row: _RowLookup, key: str) -> object:
    try:
        return row[key]
    except KeyError:
        return None


def optional_row_text(row: _RowLookup, key: str) -> str | None:
    return _optional_row_text(row, key)


def optional_row_value(row: _RowLookup, key: str) -> object:
    return _optional_row_value(row, key)


def query_tokens(text: str) -> set[str]:
    """
    Lightweight lexical normalization for hybrid ranking.

    This is intentionally deterministic and domain-agnostic:
    - works without LLM;
    - handles punctuation better than str.split();
    - keeps Russian and English words;
    - ignores very short noise tokens.
    """
    return {
        token
        for token in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", text.lower())
        if len(token) >= 3
    }


def keyword_overlap(query: str, text: str) -> float:
    query_token_set = query_tokens(query)
    text_token_set = query_tokens(text)
    if not query_token_set:
        return 0.0
    return len(query_token_set & text_token_set) / len(query_token_set)


def _row_float(row: _RowLookup, key: str) -> float:
    value = _optional_row_value(row, key)
    if value is None or isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _trace_text_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return tuple(str(item) for item in value if str(item).strip())
    return ()


def _trace_contains_query(value: object, query: str) -> bool:
    normalized_query = " ".join(query.lower().replace("ё", "е").split())
    if not normalized_query:
        return False

    for item in _trace_text_values(value):
        normalized_item = " ".join(item.lower().replace("ё", "е").split())
        if normalized_item == normalized_query or normalized_query in normalized_item:
            return True
    return False


def _dedupe_matched_fields(fields: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(field for field in fields if field))


def _row_is_production_safe(row: _RowLookup) -> bool:
    entry_kind = str(_optional_row_value(row, "entry_kind") or "").strip().lower()
    return entry_kind in RUNTIME_ENTRY_KIND_VALUES


def _rank_text_from_value(value: object) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return " ".join(_rank_text_from_value(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return " ".join(_rank_text_from_value(item) for item in value)
    return str(value)


def _preview_text_fields(row: _RowLookup, *, content: str) -> _PreviewTextFields:
    search_text = _rank_text_from_value(_optional_row_value(row, "search_text"))
    return _PreviewTextFields(
        search_text=search_text or content,
        title=_rank_text_from_value(_optional_row_value(row, "title")),
        questions=_rank_text_from_value(_optional_row_value(row, "questions")),
        synonyms=_rank_text_from_value(_optional_row_value(row, "synonyms")),
        tags=_rank_text_from_value(_optional_row_value(row, "tags")),
        embedding_text=_rank_text_from_value(
            _optional_row_value(row, "embedding_text")
        ),
    )


def _preview_overlaps(
    *,
    query: str,
    content: str,
    fields: _PreviewTextFields,
) -> _PreviewOverlaps:
    return _PreviewOverlaps(
        search=keyword_overlap(query, fields.search_text),
        answer=keyword_overlap(query, content),
        title=keyword_overlap(query, fields.title),
        questions=keyword_overlap(query, fields.questions),
        synonyms=keyword_overlap(query, fields.synonyms),
        tags=keyword_overlap(query, fields.tags),
        embedding_text=keyword_overlap(query, fields.embedding_text),
    )


def _preview_match_flags(
    row: _RowLookup,
    *,
    query: str,
    fields: _PreviewTextFields,
    overlaps: _PreviewOverlaps,
) -> _PreviewMatchFlags:
    query_lower = query.lower().strip()
    title_match = bool(
        query_lower and (query_lower in fields.title.lower() or overlaps.title >= 0.72)
    )
    question_match = bool(
        query_lower
        and (query_lower in fields.questions.lower() or overlaps.questions >= 0.72)
    )
    return _PreviewMatchFlags(
        title=title_match,
        question=question_match,
        exact_question=_trace_contains_query(
            _optional_row_value(row, "questions"),
            query,
        ),
    )


def _preview_exact_phrase_bonus(query: str, search_text: str) -> float:
    query_lower = query.lower().strip()
    return 0.24 if query_lower and query_lower in search_text.lower() else 0.0


def _preview_length_penalty(payload_len: int) -> float:
    if payload_len > 2500:
        return 0.20
    if payload_len > 1400:
        return 0.09
    return 0.0


def _preview_generic_long_penalty(
    *,
    payload_len: int,
    overlaps: _PreviewOverlaps,
    matches: _PreviewMatchFlags,
) -> float:
    strongest_specific_overlap = max(
        overlaps.search,
        overlaps.answer,
        overlaps.questions,
    )
    if payload_len <= 1800:
        return 0.0
    if strongest_specific_overlap >= 0.35:
        return 0.0
    if matches.title or matches.question:
        return 0.0
    return 0.18


def _preview_matched_fields(
    *,
    overlaps: _PreviewOverlaps,
    matches: _PreviewMatchFlags,
    lexical_score: float,
    vector_score: float,
    exact_score: float,
    exact_phrase_bonus: float,
) -> tuple[str, ...]:
    field_checks = (
        (matches.title or overlaps.title > 0.0, "title"),
        (
            matches.exact_question or matches.question or overlaps.questions > 0.0,
            "questions",
        ),
        (overlaps.synonyms > 0.0, "synonyms"),
        (overlaps.tags > 0.0, "tags"),
        (overlaps.answer > 0.0, "answer"),
        (overlaps.search > 0.0 or lexical_score > 0.0, "search_text"),
        (overlaps.embedding_text > 0.0, "embedding_text"),
        (exact_score > 0.0 or exact_phrase_bonus > 0.0, "exact"),
        (vector_score > 0.0, "embedding"),
    )
    return _dedupe_matched_fields(
        tuple(field for matched, field in field_checks if matched)
    )


def _preview_final_score(
    *,
    vector_score: float,
    lexical_bonus: float,
    exact_score: float,
    overlaps: _PreviewOverlaps,
    rare_token_bonus: float,
    exact_phrase_bonus: float,
    matches: _PreviewMatchFlags,
    length_penalty: float,
    generic_long_penalty: float,
) -> float:
    score = (
        vector_score * 0.10
        + lexical_bonus
        + exact_score * 0.18
        + overlaps.search * 0.10
        + overlaps.answer * 0.12
        + rare_token_bonus
        + exact_phrase_bonus
        + (0.78 if matches.exact_question else 0.0)
        + (0.50 if matches.question else overlaps.questions * 0.38)
        + (0.56 if matches.title else overlaps.title * 0.30)
        + overlaps.synonyms * 0.22
        + overlaps.tags * 0.12
        - length_penalty
        - generic_long_penalty
    )
    return max(0.0, score)


def _trace_default_matched_fields(
    *,
    title_match: bool,
    exact_question_match: bool,
    lexical_score: float,
    exact_score: float,
    vector_score: float,
) -> tuple[str, ...]:
    field_checks = (
        (title_match, "title"),
        (exact_question_match, "questions"),
        (lexical_score > 0.0, "search_text"),
        (exact_score > 0.0 and lexical_score <= 0.0, "exact"),
        (vector_score > 0.0, "embedding"),
    )
    return _dedupe_matched_fields(
        tuple(field for matched, field in field_checks if matched)
    )


def _trace_length_penalty_from_row(row: _RowLookup) -> float:
    content_len = len(str(_optional_row_value(row, "content") or ""))
    embedding_len = len(str(_optional_row_value(row, "embedding_text") or ""))
    payload_len = max(content_len, embedding_len)
    if payload_len > 2500:
        return 0.08
    if payload_len > 1400:
        return 0.04
    return 0.0


def _search_trace_from_row(
    row: _RowLookup,
    *,
    query: str,
    matched_fields: Sequence[str] | None = None,
    final_score: float | None = None,
    length_penalty: float | None = None,
) -> KnowledgeSearchTraceView:
    lexical_score = _row_float(row, "lexical_score")
    vector_score = _row_float(row, "vector_score")
    exact_score = _row_float(row, "exact_score")
    title_match = _trace_contains_query(_optional_row_value(row, "title"), query)
    exact_question_match = _trace_contains_query(
        _optional_row_value(row, "questions"),
        query,
    )
    fields = matched_fields or _trace_default_matched_fields(
        title_match=title_match,
        exact_question_match=exact_question_match,
        lexical_score=lexical_score,
        exact_score=exact_score,
        vector_score=vector_score,
    )
    is_production_safe = _row_is_production_safe(row)

    return KnowledgeSearchTraceView(
        matched_fields=_dedupe_matched_fields(fields),
        lexical_score=lexical_score,
        vector_score=vector_score,
        exact_question_match=exact_question_match,
        title_match=title_match,
        length_penalty=(
            _trace_length_penalty_from_row(row)
            if length_penalty is None
            else length_penalty
        ),
        final_score=_row_float(row, "score") if final_score is None else final_score,
        retrieval_surface_role=(
            "production_runtime" if is_production_safe else "non_production"
        ),
        displayed_field="answer",
        is_production_safe=is_production_safe,
    )


def _preview_rare_token_bonus(query: str, search_text: str) -> float:
    query_token_set = query_tokens(query)
    search_token_set = query_tokens(search_text)
    rare_token_hits = sum(
        1 for token in query_token_set if len(token) >= 5 and token in search_token_set
    )
    return min(0.24, rare_token_hits * 0.08)


def search_score_and_trace(
    row: _RowLookup,
    *,
    query: str,
    content: str,
) -> SearchScoreAndTrace:
    raw_search_text = _optional_row_value(row, "search_text")
    search_text = str(raw_search_text or content)
    search_lower = search_text.lower()
    search_tokens = query_tokens(search_text)

    query_token_set = query_tokens(query)
    query_lower = query.lower().strip()

    vector_score = _row_float(row, "vector_score")
    lexical_score = _row_float(row, "lexical_score")
    exact_score = _row_float(row, "exact_score")

    token_overlap = 0.0
    if query_token_set:
        token_overlap = len(query_token_set & search_tokens) / len(query_token_set)

    rare_token_hits = sum(
        1 for token in query_token_set if len(token) >= 5 and token in search_tokens
    )
    rare_token_bonus = min(0.24, rare_token_hits * 0.08)
    exact_phrase_bonus = 0.22 if query_lower and query_lower in search_lower else 0.0
    lexical_bonus = min(0.35, lexical_score * 4.0)

    title_text = _rank_text_from_value(_optional_row_value(row, "title"))
    questions_text = _rank_text_from_value(_optional_row_value(row, "questions"))
    synonyms_text = _rank_text_from_value(_optional_row_value(row, "synonyms"))
    tags_text = _rank_text_from_value(_optional_row_value(row, "tags"))

    title_lower = title_text.lower()
    questions_lower = questions_text.lower()

    title_overlap = keyword_overlap(query, title_text)
    questions_overlap = keyword_overlap(query, questions_text)
    synonyms_overlap = keyword_overlap(query, synonyms_text)
    tags_overlap = keyword_overlap(query, tags_text)

    title_match = bool(
        query_lower and (query_lower in title_lower or title_overlap >= 0.72)
    )
    question_match = bool(
        query_lower and (query_lower in questions_lower or questions_overlap >= 0.72)
    )

    question_bonus = 0.58 if question_match else questions_overlap * 0.34
    title_bonus = 0.48 if title_match else title_overlap * 0.24
    synonym_bonus = synonyms_overlap * 0.18
    tag_bonus = tags_overlap * 0.10

    payload_len = max(
        len(content),
        len(str(_optional_row_value(row, "embedding_text") or "")),
    )
    length_penalty = _preview_length_penalty(payload_len)

    generic_long_penalty = (
        0.16
        if payload_len > 1800
        and token_overlap < 0.35
        and not title_match
        and not question_match
        else 0.0
    )

    score = (
        vector_score * 0.26
        + lexical_bonus
        + exact_score * 0.18
        + token_overlap * 0.24
        + rare_token_bonus
        + exact_phrase_bonus
        + question_bonus
        + title_bonus
        + synonym_bonus
        + tag_bonus
        - length_penalty
        - generic_long_penalty
    )

    method = "hybrid"
    if lexical_score <= 0.0 and token_overlap <= 0.0:
        method = "vector"
    elif vector_score <= 0.0:
        method = "fts"

    return SearchScoreAndTrace(
        score=score,
        method=method,
        trace=_search_trace_from_row(
            row,
            query=query,
            final_score=score,
            length_penalty=length_penalty + generic_long_penalty,
        ),
    )


def preview_score_and_trace(
    row: _RowLookup,
    *,
    query: str,
    content: str,
) -> _TraceScore:
    fields = _preview_text_fields(row, content=content)
    overlaps = _preview_overlaps(
        query=query,
        content=content,
        fields=fields,
    )
    matches = _preview_match_flags(
        row,
        query=query,
        fields=fields,
        overlaps=overlaps,
    )
    lexical_score = _row_float(row, "lexical_score")
    vector_score = _row_float(row, "vector_score")
    exact_score = _row_float(row, "exact_score")
    exact_phrase_bonus = _preview_exact_phrase_bonus(query, fields.search_text)
    payload_len = max(len(content), len(fields.embedding_text))
    length_penalty = _preview_length_penalty(payload_len)
    generic_long_penalty = _preview_generic_long_penalty(
        payload_len=payload_len,
        overlaps=overlaps,
        matches=matches,
    )
    score = _preview_final_score(
        vector_score=vector_score,
        lexical_bonus=min(0.30, lexical_score * 4.0),
        exact_score=exact_score,
        overlaps=overlaps,
        rare_token_bonus=_preview_rare_token_bonus(
            query,
            fields.search_text,
        ),
        exact_phrase_bonus=exact_phrase_bonus,
        matches=matches,
        length_penalty=length_penalty,
        generic_long_penalty=generic_long_penalty,
    )
    matched_fields = _preview_matched_fields(
        overlaps=overlaps,
        matches=matches,
        lexical_score=lexical_score,
        vector_score=vector_score,
        exact_score=exact_score,
        exact_phrase_bonus=exact_phrase_bonus,
    )

    return _TraceScore(
        score=score,
        trace=_search_trace_from_row(
            row,
            query=query,
            matched_fields=matched_fields,
            final_score=score,
            length_penalty=length_penalty + generic_long_penalty,
        ),
    )
