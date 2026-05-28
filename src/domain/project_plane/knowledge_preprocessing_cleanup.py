from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

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
_STOP_TOKENS: frozenset[str] = frozenset(
    {
        "что",
        "это",
        "как",
        "для",
        "или",
        "при",
        "про",
        "можно",
        "нужно",
        "такое",
        "чем",
        "за",
    }
)
_QUESTION_TOKEN_ALIASES: dict[str, tuple[str, ...]] = {
    "удалить": ("удаление", "скрыть", "отклонить", "архивировать"),
    "удаление": ("удалить", "скрыть", "отклонить", "архивировать"),
    "скрыть": ("удалить", "отклонить", "архивировать"),
    "скрытие": ("скрыть", "удалить", "отклонить", "архивировать"),
    "отклонить": ("удалить", "скрыть", "архивировать"),
    "отклонение": ("отклонить", "удалить", "скрыть", "архивировать"),
    "архивировать": ("удалить", "скрыть", "отклонить"),
    "архивирование": ("архивировать", "удалить", "скрыть", "отклонить"),
    "плохой": ("слабый", "мусорный", "некачественный"),
    "слабый": ("плохой", "мусорный", "некачественный"),
    "мусорный": ("плохой", "слабый", "некачественный"),
}
_MODERATION_ACTION_TOKENS: frozenset[str] = frozenset(
    {
        "скрыть",
        "скрытие",
        "отклонить",
        "отклонение",
        "архивировать",
        "архивирование",
    }
)
_MIN_DIRECT_QUESTION_SCORE = 0.34


def cleanup_faq_preprocessing_entries(
    entries: Sequence[KnowledgePreprocessingEntry],
) -> KnowledgePreprocessingCleanupResult:
    absorbed = absorb_short_answer_cards(entries)
    pruned = prune_broad_card_questions(absorbed.entries)
    return KnowledgePreprocessingCleanupResult(
        entries=pruned.entries,
        metrics={**absorbed.metrics, **pruned.metrics},
    )


def absorb_short_answer_cards(
    entries: Sequence[KnowledgePreprocessingEntry],
) -> KnowledgePreprocessingCleanupResult:
    absorbed_indexes: set[int] = set()
    parent_by_child: dict[int, int] = {}
    absorbed_count = 0
    unpublishable_count = 0

    for index, entry in enumerate(entries):
        if not _is_short_answer_service_card(entry):
            continue
        parent_index = _find_short_answer_parent(index=index, entries=entries)
        absorbed_indexes.add(index)
        if parent_index is None:
            unpublishable_count += 1
            continue
        parent_by_child[index] = parent_index
        absorbed_count += 1

    retained: list[KnowledgePreprocessingEntry] = []
    for index, entry in enumerate(entries):
        if index in absorbed_indexes:
            continue
        merged = entry
        for child_index, parent_index in parent_by_child.items():
            if parent_index == index:
                merged = _merge_child_summary_into_parent(
                    parent=merged,
                    child=entries[child_index],
                )
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

    for owner_index, owner_entry in enumerate(tuple(result)):
        if not _is_question_cleanup_candidate(owner_entry, entries=result):
            continue

        retained_questions: list[str] = []
        changed_owner = False
        for question in owner_entry.questions:
            if _is_generic_overview_question(question):
                retained_questions.append(question)
                continue
            narrow_index = _best_narrow_question_owner(
                question=question,
                current_index=owner_index,
                entries=result,
            )
            if narrow_index is None:
                retained_questions.append(question)
                continue

            narrow_entry = result[narrow_index]
            result[narrow_index] = _entry_with_rebuilt_embedding(
                replace(
                    narrow_entry,
                    questions=_merge_text_tuple_values(
                        narrow_entry.questions, (question,)
                    ),
                )
            )
            moved_question_count += 1
            changed_owner = True
            audit.append(
                {
                    "question": question,
                    "from_title": owner_entry.title,
                    "to_title": narrow_entry.title,
                }
            )

        if changed_owner:
            result[owner_index] = _entry_with_rebuilt_embedding(
                replace(owner_entry, questions=tuple(retained_questions))
            )

    return KnowledgePreprocessingCleanupResult(
        entries=tuple(result),
        metrics={
            "moved_question_count": moved_question_count,
            "moved_question_audit": audit,
        },
    )


def dedupe_source_excerpts(excerpts: Sequence[str]) -> tuple[str, ...]:
    retained: list[str] = []
    for excerpt in excerpts:
        cleaned = _compact_text(excerpt)
        normalized = _text_fingerprint(cleaned)
        if not normalized:
            continue
        should_append = True
        for existing_index, existing in enumerate(tuple(retained)):
            existing_normalized = _text_fingerprint(existing)
            if normalized == existing_normalized or normalized in existing_normalized:
                should_append = False
                break
            if existing_normalized and existing_normalized in normalized:
                retained[existing_index] = cleaned
                should_append = False
                break
        if should_append:
            retained.append(cleaned)
    return tuple(retained)


def _is_short_answer_service_card(entry: KnowledgePreprocessingEntry) -> bool:
    title = _service_label_fingerprint(entry.title)
    canonical = _service_label_fingerprint(entry.canonical_question)
    if (
        title in _SHORT_ANSWER_SERVICE_LABELS
        or canonical in _SHORT_ANSWER_SERVICE_LABELS
    ):
        return True
    excerpt = _compact_text(entry.source_excerpt).lower()
    return excerpt.startswith("короткий ответ клиенту:") or excerpt.startswith(
        "короткий ответ:"
    )


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
    merged = replace(
        parent,
        source_excerpt="\n\n".join(
            dedupe_source_excerpts((parent.source_excerpt, child.source_excerpt))
        ),
        questions=_merge_text_tuple_values(parent.questions, child.questions),
        synonyms=_merge_text_tuple_values(parent.synonyms, child.synonyms),
        tags=_merge_text_tuple_values(parent.tags, child.tags),
        source_chunk_indexes=tuple(
            dict.fromkeys((*parent.source_chunk_indexes, *child.source_chunk_indexes))
        ),
    )
    return _entry_with_rebuilt_embedding(merged)


def _is_question_cleanup_candidate(
    entry: KnowledgePreprocessingEntry,
    *,
    entries: Sequence[KnowledgePreprocessingEntry],
) -> bool:
    if _is_short_answer_service_card(entry):
        return False
    if _is_broad_card(entry, entries=entries):
        return True
    return len(entry.questions) >= 2


def _is_broad_card(
    entry: KnowledgePreprocessingEntry,
    *,
    entries: Sequence[KnowledgePreprocessingEntry],
) -> bool:
    title = _service_label_fingerprint(entry.title)
    canonical = _service_label_fingerprint(entry.canonical_question)
    if title in _BROAD_CARD_TITLE_PATTERNS or canonical in _BROAD_CARD_TITLE_PATTERNS:
        return True
    if len(entry.questions) < 5:
        return False
    median = sorted(len(item.questions) for item in entries)[len(entries) // 2]
    return len(entry.questions) >= max(5, median + 3)


def _is_generic_overview_question(question: str) -> bool:
    key = _text_fingerprint(question)
    if key in {
        "что это за сервис",
        "чем вы занимаетесь",
        "для чего нужна ai база знаний",
        "для чего нужна аи база знаний",
        "для чего нужна база знаний",
    }:
        return True
    return key.startswith("для чего нужна ") and "база знаний" in key


def _best_narrow_question_owner(
    *,
    question: str,
    current_index: int,
    entries: Sequence[KnowledgePreprocessingEntry],
) -> int | None:
    if len(_tokens(question)) < 2:
        return None
    best_index: int | None = None
    best_score = 0.0
    for index, candidate in enumerate(entries):
        if index == current_index or _is_short_answer_service_card(candidate):
            continue
        if _is_broad_card(candidate, entries=entries):
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
    if canonical_key and (
        canonical_key in question_key or question_key in canonical_key
    ):
        score = max(score, 0.74)
    if _token_overlap_coverage(question, candidate.title) >= 0.5:
        score = max(score, 0.48)

    question_tokens = set(_expanded_tokens(question))
    candidate_tokens = set(_expanded_tokens(candidate_text))
    if (
        "фрагмент" in question_tokens
        and question_tokens & {"удалить", "удаление"}
        and candidate_tokens & _MODERATION_ACTION_TOKENS
    ):
        score = max(score, 0.76)
    return score


def _token_similarity(left: str, right: str) -> float:
    left_tokens = set(_expanded_tokens(left))
    right_tokens = set(_expanded_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _token_overlap_coverage(left: str, right: str) -> float:
    left_tokens = set(_expanded_tokens(left))
    right_tokens = set(_expanded_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def _expanded_tokens(value: str) -> tuple[str, ...]:
    expanded: list[str] = []
    for token in _tokens(value):
        if token not in expanded:
            expanded.append(token)
        for alias in _QUESTION_TOKEN_ALIASES.get(token, ()):
            if alias not in expanded:
                expanded.append(alias)
    return tuple(expanded)


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            token
            for token in re.findall(
                r"[0-9a-zа-яё]+",
                value.casefold().replace("ё", "е"),
            )
            if len(token) >= 3 and token not in _STOP_TOKENS
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
