from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Sequence

from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
    build_embedding_text,
)


@dataclass(frozen=True, slots=True)
class KnowledgePreprocessingCleanupResult:
    entries: tuple[KnowledgePreprocessingEntry, ...]
    metrics: dict[str, object]


_SHORT_ANSWER_SERVICE_LABELS: frozenset[str] = frozenset(
    {
        "короткий ответ",
        "короткий ответ клиенту",
        "short answer",
        "customer short answer",
        "short customer answer",
    }
)

_BROAD_CARD_TITLE_PATTERNS: tuple[str, ...] = (
    "что это за продукт",
    "что это за сервис",
    "описание продукта",
    "обзор продукта",
    "как работает система",
    "главная ценность",
)

_MIN_BROAD_QUESTION_COUNT = 5
_MIN_DIRECT_QUESTION_SCORE = 0.34


def cleanup_faq_preprocessing_entries(
    entries: Sequence[KnowledgePreprocessingEntry],
) -> KnowledgePreprocessingCleanupResult:
    """Apply deterministic post-merge cleanup for FAQ preprocessing entries.

    This is intentionally a small local layer: it does not introduce hierarchy,
    graph relations, new persistence tables, or LLM calls. It only prevents
    service summary cards from being published as standalone knowledge and moves
    clearly narrower questions away from broad overview cards.
    """

    absorbed = absorb_short_answer_cards(entries)
    pruned = prune_broad_card_questions(absorbed.entries)
    metrics: dict[str, object] = {
        **absorbed.metrics,
        **pruned.metrics,
    }
    return KnowledgePreprocessingCleanupResult(entries=pruned.entries, metrics=metrics)


def absorb_short_answer_cards(
    entries: Sequence[KnowledgePreprocessingEntry],
) -> KnowledgePreprocessingCleanupResult:
    retained: list[KnowledgePreprocessingEntry] = []
    absorbed_indexes: set[int] = set()
    absorbed_count = 0
    unpublishable_count = 0

    for index, entry in enumerate(entries):
        if not _is_short_answer_service_card(entry):
            continue
        parent_index = _find_short_answer_parent(index=index, entries=entries)
        if parent_index is None:
            absorbed_indexes.add(index)
            unpublishable_count += 1
            continue
        absorbed_indexes.add(index)
        absorbed_count += 1

    for index, entry in enumerate(entries):
        if index in absorbed_indexes:
            continue
        children = [
            child
            for child_index, child in enumerate(entries)
            if child_index in absorbed_indexes
            and _find_short_answer_parent(index=child_index, entries=entries) == index
        ]
        merged = entry
        for child in children:
            merged = _merge_child_summary_into_parent(parent=merged, child=child)
        retained.append(merged)

    return KnowledgePreprocessingCleanupResult(
        entries=tuple(retained),
        metrics={
            "short_answer_absorbed_count": absorbed_count,
            "short_answer_unpublishable_count": unpublishable_count,
        },
    )


def prune_broad_card_questions(
    entries: Sequence[KnowledgePreprocessingEntry],
) -> KnowledgePreprocessingCleanupResult:
    result = list(entries)
    moved_question_count = 0
    audit: list[dict[str, str]] = []

    for broad_index, broad_entry in enumerate(tuple(result)):
        if not _is_broad_card(broad_entry, entries=result):
            continue

        broad_questions = list(broad_entry.questions)
        retained_questions: list[str] = []
        changed_broad = False

        for question in broad_questions:
            narrow_index = _best_narrow_question_owner(
                question=question,
                broad_index=broad_index,
                entries=result,
            )
            if narrow_index is None:
                retained_questions.append(question)
                continue

            narrow_entry = result[narrow_index]
            updated_questions = _merge_text_tuple_values(
                narrow_entry.questions,
                (question,),
            )
            result[narrow_index] = _entry_with_rebuilt_embedding(
                replace(narrow_entry, questions=updated_questions)
            )
            moved_question_count += 1
            changed_broad = True
            audit.append(
                {
                    "question": question,
                    "from_title": broad_entry.title,
                    "to_title": narrow_entry.title,
                }
            )

        if changed_broad:
            result[broad_index] = _entry_with_rebuilt_embedding(
                replace(broad_entry, questions=tuple(retained_questions))
            )

    return KnowledgePreprocessingCleanupResult(
        entries=tuple(result),
        metrics={
            "moved_question_count": moved_question_count,
            "moved_question_audit": audit,
        },
    )


def dedupe_source_excerpts(
    excerpts: Sequence[str],
) -> tuple[str, ...]:
    """Dedupe evidence excerpts and keep the richer containing quote."""

    retained: list[str] = []
    for excerpt in excerpts:
        cleaned = _compact_text(excerpt)
        if not cleaned:
            continue
        normalized = _text_fingerprint(cleaned)
        if not normalized:
            continue

        replaced_existing = False
        duplicate = False
        for existing_index, existing in enumerate(tuple(retained)):
            existing_normalized = _text_fingerprint(existing)
            if normalized == existing_normalized:
                duplicate = True
                break
            if normalized in existing_normalized:
                duplicate = True
                break
            if existing_normalized in normalized:
                retained[existing_index] = cleaned
                replaced_existing = True
                break
        if duplicate or replaced_existing:
            continue
        retained.append(cleaned)
    return tuple(retained)


def _is_short_answer_service_card(entry: KnowledgePreprocessingEntry) -> bool:
    title = _service_label_fingerprint(entry.title)
    canonical = _service_label_fingerprint(entry.canonical_question)
    if title in _SHORT_ANSWER_SERVICE_LABELS or canonical in _SHORT_ANSWER_SERVICE_LABELS:
        return True
    excerpt = _compact_text(entry.source_excerpt).lower()
    if excerpt.startswith("короткий ответ клиенту:"):
        return True
    return excerpt.startswith("короткий ответ:")


def _find_short_answer_parent(
    *,
    index: int,
    entries: Sequence[KnowledgePreprocessingEntry],
) -> int | None:
    child = entries[index]
    best_index: int | None = None
    best_score = 0.0
    for candidate_index, candidate in enumerate(entries):
        if candidate_index == index or _is_short_answer_service_card(candidate):
            continue
        score = _short_answer_parent_score(child=child, candidate=candidate)
        if score > best_score:
            best_score = score
            best_index = candidate_index
    if best_score >= 0.38:
        return best_index
    return None


def _short_answer_parent_score(
    *,
    child: KnowledgePreprocessingEntry,
    candidate: KnowledgePreprocessingEntry,
) -> float:
    score = 0.0
    if child.source_chunk_indexes and set(child.source_chunk_indexes) & set(
        candidate.source_chunk_indexes
    ):
        score += 0.35
    if _contained_evidence(child.source_excerpt, candidate.source_excerpt):
        score += 0.35
    score += _token_similarity(child.answer, candidate.answer) * 0.3
    if len(candidate.answer) > len(child.answer):
        score += 0.08
    return min(1.0, score)


def _contained_evidence(left: str, right: str) -> bool:
    left_key = _text_fingerprint(left)
    right_key = _text_fingerprint(right)
    if not left_key or not right_key:
        return False
    return left_key in right_key or right_key in left_key


def _merge_child_summary_into_parent(
    *,
    parent: KnowledgePreprocessingEntry,
    child: KnowledgePreprocessingEntry,
) -> KnowledgePreprocessingEntry:
    source_excerpt = "\n\n".join(
        dedupe_source_excerpts((parent.source_excerpt, child.source_excerpt))
    )
    questions = _merge_text_tuple_values(parent.questions, child.questions)
    synonyms = _merge_text_tuple_values(parent.synonyms, child.synonyms)
    tags = _merge_text_tuple_values(parent.tags, child.tags)
    source_chunk_indexes = tuple(
        dict.fromkeys((*parent.source_chunk_indexes, *child.source_chunk_indexes))
    )
    merged = replace(
        parent,
        source_excerpt=source_excerpt,
        questions=questions,
        synonyms=synonyms,
        tags=tags,
        source_chunk_indexes=source_chunk_indexes,
    )
    return _entry_with_rebuilt_embedding(merged)


def _is_broad_card(
    entry: KnowledgePreprocessingEntry,
    *,
    entries: Sequence[KnowledgePreprocessingEntry],
) -> bool:
    title = _service_label_fingerprint(entry.title)
    canonical = _service_label_fingerprint(entry.canonical_question)
    if title in _BROAD_CARD_TITLE_PATTERNS or canonical in _BROAD_CARD_TITLE_PATTERNS:
        return True
    if len(entry.questions) >= _MIN_BROAD_QUESTION_COUNT:
        median = sorted(len(item.questions) for item in entries)[len(entries) // 2]
        return len(entry.questions) >= max(_MIN_BROAD_QUESTION_COUNT, median + 3)
    return False


def _best_narrow_question_owner(
    *,
    question: str,
    broad_index: int,
    entries: Sequence[KnowledgePreprocessingEntry],
) -> int | None:
    question_tokens = _tokens(question)
    if len(question_tokens) < 2:
        return None

    best_index: int | None = None
    best_score = 0.0
    for index, candidate in enumerate(entries):
        if index == broad_index or _is_short_answer_service_card(candidate):
            continue
        score = _direct_question_score(question=question, candidate=candidate)
        if score > best_score:
            best_score = score
            best_index = index

    if best_index is not None and best_score >= _MIN_DIRECT_QUESTION_SCORE:
        return best_index
    return None


def _direct_question_score(
    *,
    question: str,
    candidate: KnowledgePreprocessingEntry,
) -> float:
    question_key = _text_fingerprint(question)
    title_key = _text_fingerprint(candidate.title)
    canonical_key = _text_fingerprint(candidate.canonical_question)
    candidate_text = " ".join(
        (
            candidate.title,
            candidate.canonical_question,
            " ".join(candidate.questions),
            candidate.answer,
        )
    )
    score = _token_similarity(question, candidate_text)
    if title_key and (title_key in question_key or question_key in title_key):
        score = max(score, 0.82)
    if canonical_key and (canonical_key in question_key or question_key in canonical_key):
        score = max(score, 0.74)
    if _token_overlap_coverage(question, candidate.title) >= 0.5:
        score = max(score, 0.48)
    return score


def _token_similarity(left: str, right: str) -> float:
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _token_overlap_coverage(left: str, right: str) -> float:
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            token
            for token in re.findall(r"[0-9a-zа-яё]+", value.casefold().replace("ё", "е"))
            if len(token) >= 3
            and token
            not in {
                "что",
                "это",
                "как",
                "для",
                "или",
                "при",
                "про",
                "можно",
                "нужно",
            }
        )
    )


def _entry_with_rebuilt_embedding(
    entry: KnowledgePreprocessingEntry,
) -> KnowledgePreprocessingEntry:
    return replace(entry, embedding_text=build_embedding_text(entry))


def _merge_text_tuple_values(
    left: Sequence[str],
    right: Sequence[str],
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in (*left, *right):
        cleaned = _compact_text(value)
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return tuple(result)


def _service_label_fingerprint(value: str) -> str:
    return _text_fingerprint(value).strip()


def _text_fingerprint(value: str) -> str:
    return " ".join(
        re.sub(r"[^0-9a-zа-яё]+", " ", value.casefold().replace("ё", "е")).split()
    )


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
