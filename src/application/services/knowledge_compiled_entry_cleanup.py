from __future__ import annotations


from collections.abc import (
    Mapping,
    Sequence,
)
from dataclasses import dataclass
from src.application.services.knowledge_answer_resolution_service import (
    fingerprint_answer_resolution_text,
)
from src.application.services.knowledge_answer_resolution_service import (
    calculate_answer_resolution_token_similarity,
)
from src.application.services.knowledge_answer_resolution_service import (
    tokenize_answer_resolution_text,
)
from src.application.services.knowledge_answer_resolution_service import (
    cleanup_answer_resolution_text_with_metrics,
)
from src.application.services.knowledge_answer_resolution_service import (
    merge_answer_text,
)
from src.application.services.knowledge_answer_resolution_service import (
    merge_answer_units_deterministically,
)
from src.application.services.knowledge_answer_resolution_service import (
    merge_entry_fields_deterministically,
)
from src.application.services.knowledge_generated_entry_repair import answer_digest
from src.domain.project_plane.json_types import (
    JsonObject,
    JsonValue,
)
from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingEntry
from typing import cast


def _clean_optional_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def _text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        candidates: tuple[object, ...] = (value,)
    elif isinstance(value, tuple):
        candidates = value
    elif isinstance(value, list):
        candidates = tuple(value)
    else:
        return ()

    result: list[str] = []
    for item in candidates:
        cleaned = _clean_optional_text(item)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return tuple(result)


def _question_intent_primary_question(entry: KnowledgePreprocessingEntry) -> str:
    if entry.canonical_question:
        return entry.canonical_question
    for question in _text_tuple(entry.questions):
        if question:
            return question
    return answer_digest(entry.answer)


def _question_intent_tokens_from_entry(
    entry: KnowledgePreprocessingEntry,
) -> tuple[str, ...]:
    return tokenize_answer_resolution_text(
        " ".join(
            part
            for part in (
                _question_intent_primary_question(entry),
                " ".join(_text_tuple(entry.questions)),
                answer_digest(entry.answer),
            )
            if part
        )
    )


def _merge_text_tuple_values(
    *groups: tuple[str, ...],
) -> tuple[str, ...]:
    result: list[str] = []
    for group in groups:
        for value in group:
            cleaned = _clean_optional_text(value)
            if cleaned and cleaned not in result:
                result.append(cleaned)
    return tuple(result)


def source_excerpts_from_preprocessing_entry(
    entry: KnowledgePreprocessingEntry,
) -> tuple[str, ...]:
    normalized = entry.source_excerpt.replace("\r\n", "\n").replace("\r", "\n")
    parts = tuple(part.strip() for part in normalized.split("\n\n"))
    return _text_tuple(parts)


def json_metric_int(metrics: Mapping[str, JsonValue], key: str) -> int:
    value = metrics.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


@dataclass(frozen=True, slots=True)
class MechanicalCleanupCompiledEntriesResult:
    entries: tuple[KnowledgePreprocessingEntry, ...]
    source_excerpts_by_entry: tuple[tuple[str, ...], ...]
    metrics: JsonObject


def cleanup_compiled_entries_mechanically(
    *,
    entries: Sequence[KnowledgePreprocessingEntry],
    source_excerpts_by_entry: Sequence[tuple[str, ...]],
) -> MechanicalCleanupCompiledEntriesResult:
    source_excerpts = tuple(source_excerpts_by_entry)
    if len(source_excerpts) != len(entries):
        source_excerpts = tuple(
            source_excerpts_from_preprocessing_entry(entry) for entry in entries
        )

    deduped_question_variant_count = 0
    deduped_synonym_count = 0
    deduped_tag_count = 0
    cleaned_entries: list[KnowledgePreprocessingEntry] = []
    cleaned_source_excerpts: list[tuple[str, ...]] = []

    for entry, entry_source_excerpts in zip(entries, source_excerpts, strict=True):
        deduped_entry, field_metrics = _retighten_entry_with_deduped_fields(entry)
        deduped_question_variant_count += json_metric_int(
            field_metrics, "deduped_question_variant_count"
        )
        deduped_synonym_count += json_metric_int(field_metrics, "deduped_synonym_count")
        deduped_tag_count += json_metric_int(field_metrics, "deduped_tag_count")
        cleaned_entries.append(deduped_entry)
        cleaned_source_excerpts.append(entry_source_excerpts)

    retained_entries: list[KnowledgePreprocessingEntry] = []
    retained_source_excerpts: list[tuple[str, ...]] = []
    retained_merged_entry_counts: list[int] = []
    index_by_exact_key: dict[tuple[str, str, str, str], int] = {}
    exact_duplicate_candidate_collapse_count = 0

    for entry, entry_source_excerpts in zip(
        cleaned_entries, cleaned_source_excerpts, strict=True
    ):
        source_fingerprint = " | ".join(
            fingerprint_answer_resolution_text(excerpt)
            for excerpt in entry_source_excerpts
            if fingerprint_answer_resolution_text(excerpt)
        )
        exact_key = (
            fingerprint_answer_resolution_text(entry.title),
            fingerprint_answer_resolution_text(entry.canonical_question),
            fingerprint_answer_resolution_text(entry.answer),
            source_fingerprint,
        )
        existing_index = index_by_exact_key.get(exact_key)
        deterministic_reason = (
            "exact_candidate_key" if existing_index is not None else ""
        )

        if existing_index is None:
            for candidate_index, existing_entry in enumerate(retained_entries):
                reason = _retighten_deterministic_duplicate_reason(
                    existing_entry,
                    entry,
                )
                if reason is None:
                    continue
                existing_index = candidate_index
                deterministic_reason = reason
                break

        if existing_index is None:
            index_by_exact_key[exact_key] = len(retained_entries)
            retained_entries.append(entry)
            retained_source_excerpts.append(entry_source_excerpts)
            retained_merged_entry_counts.append(1)
            continue

        existing_entry = retained_entries[existing_index]
        if deterministic_reason == "exact_candidate_key":
            merged_entry = merge_entry_fields_deterministically(
                existing_entry=existing_entry,
                incoming_entry=entry,
                merged_answer=existing_entry.answer,
            )
            exact_duplicate_candidate_collapse_count += 1
        else:
            merged_entry = _retighten_merge_entries_deterministically(
                existing_entry=existing_entry,
                incoming_entry=entry,
                reason=deterministic_reason,
            )

        retained_entries[existing_index] = merged_entry
        retained_source_excerpts[existing_index] = _merge_text_tuple_values(
            retained_source_excerpts[existing_index],
            entry_source_excerpts,
        )
        retained_merged_entry_counts[existing_index] += 1

    metrics: JsonObject = {
        "deduped_question_variant_count": deduped_question_variant_count,
        "deduped_synonym_count": deduped_synonym_count,
        "deduped_tag_count": deduped_tag_count,
        "exact_duplicate_candidate_collapse_count": (
            exact_duplicate_candidate_collapse_count
        ),
        "deterministic_candidate_collapse_count": (
            len(entries) - len(retained_entries)
        ),
        "deterministic_cleanup_entry_count_before": len(entries),
        "deterministic_cleanup_entry_count_after": len(retained_entries),
        "merged_preprocessing_entry_counts": cast(
            JsonValue, retained_merged_entry_counts
        ),
    }
    return MechanicalCleanupCompiledEntriesResult(
        entries=tuple(retained_entries),
        source_excerpts_by_entry=tuple(retained_source_excerpts),
        metrics=metrics,
    )


def _entry_question_intent_fingerprints(
    entry: KnowledgePreprocessingEntry,
) -> tuple[str, ...]:
    values: list[str] = []
    for value in (
        entry.canonical_question,
        _question_intent_primary_question(entry),
        *_text_tuple(entry.questions),
    ):
        fingerprint = fingerprint_answer_resolution_text(value)
        if fingerprint and fingerprint not in values:
            values.append(fingerprint)
    return tuple(values)


def _entries_have_exact_question_intent(
    left: KnowledgePreprocessingEntry,
    right: KnowledgePreprocessingEntry,
) -> bool:
    left_fingerprints = set(_entry_question_intent_fingerprints(left))
    right_fingerprints = set(_entry_question_intent_fingerprints(right))
    return bool(
        left_fingerprints
        and right_fingerprints
        and left_fingerprints & right_fingerprints
    )


def _retighten_deduped_text_tuple(
    values: object,
) -> tuple[tuple[str, ...], int]:
    result: list[str] = []
    seen: set[str] = set()
    duplicate_count = 0

    for value in _text_tuple(values):
        cleaned = _clean_optional_text(value)
        if not cleaned:
            continue

        fingerprint = fingerprint_answer_resolution_text(cleaned)
        if not fingerprint:
            continue

        if fingerprint in seen:
            duplicate_count += 1
            continue

        seen.add(fingerprint)
        result.append(cleaned)

    return tuple(result), duplicate_count


def _retighten_entry_with_deduped_fields(
    entry: KnowledgePreprocessingEntry,
) -> tuple[KnowledgePreprocessingEntry, JsonObject]:
    questions, duplicate_question_count = _retighten_deduped_text_tuple(entry.questions)
    synonyms, duplicate_synonym_count = _retighten_deduped_text_tuple(entry.synonyms)
    tags, duplicate_tag_count = _retighten_deduped_text_tuple(entry.tags)

    answer_cleanup = cleanup_answer_resolution_text_with_metrics(entry.answer)
    embedding_cleanup = cleanup_answer_resolution_text_with_metrics(
        entry.embedding_text
    )

    deduped = KnowledgePreprocessingEntry(
        title=entry.title,
        answer=answer_cleanup.text or entry.answer,
        source_excerpt=entry.source_excerpt,
        questions=questions,
        synonyms=synonyms,
        tags=tags,
        embedding_text=embedding_cleanup.text or entry.embedding_text,
        canonical_question=entry.canonical_question,
    )
    metrics: JsonObject = {
        "deduped_question_variant_count": duplicate_question_count,
        "deduped_synonym_count": duplicate_synonym_count,
        "deduped_tag_count": duplicate_tag_count,
        "deduped_answer_unit_count": answer_cleanup.removed_unit_count,
        "deduped_embedding_text_unit_count": embedding_cleanup.removed_unit_count,
    }
    return deduped, metrics


def _retighten_entry_intent_fingerprint(
    entry: KnowledgePreprocessingEntry,
) -> str:
    return fingerprint_answer_resolution_text(
        " ".join(
            part
            for part in (
                entry.title,
                entry.canonical_question,
                " ".join(_text_tuple(entry.questions)),
                " ".join(_text_tuple(entry.synonyms)),
            )
            if _clean_optional_text(part)
        )
    )


def _retighten_answer_fingerprint(entry: KnowledgePreprocessingEntry) -> str:
    return fingerprint_answer_resolution_text(entry.answer)


def _retighten_answer_contains(
    left: KnowledgePreprocessingEntry,
    right: KnowledgePreprocessingEntry,
) -> bool:
    left_answer = _retighten_answer_fingerprint(left)
    right_answer = _retighten_answer_fingerprint(right)
    if not left_answer or not right_answer:
        return False
    if len(left_answer) < 32 or len(right_answer) < 32:
        return False
    return left_answer in right_answer or right_answer in left_answer


def _retighten_deterministic_duplicate_reason(
    left: KnowledgePreprocessingEntry,
    right: KnowledgePreprocessingEntry,
) -> str | None:
    left_answer = _retighten_answer_fingerprint(left)
    right_answer = _retighten_answer_fingerprint(right)
    if left_answer and right_answer and left_answer == right_answer:
        return "exact_answer"

    if _retighten_answer_contains(left, right):
        return "answer_containment"

    left_intent = _retighten_entry_intent_fingerprint(left)
    right_intent = _retighten_entry_intent_fingerprint(right)
    if _entries_have_exact_question_intent(left, right):
        answer_unit_merge = merge_answer_units_deterministically(
            left.answer,
            right.answer,
            allow_disjoint_union=True,
        )
        if answer_unit_merge is not None:
            return answer_unit_merge.strategy

    if left_intent and right_intent and left_intent == right_intent:
        answer_score = calculate_answer_resolution_token_similarity(
            tokenize_answer_resolution_text(left.answer),
            tokenize_answer_resolution_text(right.answer),
        )
        if answer_score >= 0.72:
            return "exact_intent_high_answer_overlap"

    return None


def _retighten_entry_richness_score(
    entry: KnowledgePreprocessingEntry,
) -> tuple[int, int, int, int]:
    return (
        len(_clean_optional_text(entry.answer)),
        len(source_excerpts_from_preprocessing_entry(entry)),
        len(_text_tuple(entry.questions)),
        len(_clean_optional_text(entry.embedding_text)),
    )


def _retighten_merge_entries_deterministically(
    *,
    existing_entry: KnowledgePreprocessingEntry,
    incoming_entry: KnowledgePreprocessingEntry,
    reason: str,
) -> KnowledgePreprocessingEntry:
    existing_score = _retighten_entry_richness_score(existing_entry)
    incoming_score = _retighten_entry_richness_score(incoming_entry)
    survivor = incoming_entry if incoming_score > existing_score else existing_entry
    absorbed = existing_entry if survivor is incoming_entry else incoming_entry

    answer_unit_merge = merge_answer_units_deterministically(
        existing_entry.answer,
        incoming_entry.answer,
        allow_disjoint_union=reason == "same_intent_complementary_answer_unit_union",
    )
    if answer_unit_merge is not None:
        survivor_answer = answer_unit_merge.answer
    elif reason == "answer_containment":
        survivor_answer = survivor.answer
    elif _retighten_answer_fingerprint(existing_entry) == _retighten_answer_fingerprint(
        incoming_entry
    ):
        survivor_answer = survivor.answer
    else:
        survivor_answer = merge_answer_text(
            existing_entry.answer, incoming_entry.answer
        )

    merged = merge_entry_fields_deterministically(
        existing_entry=survivor,
        incoming_entry=absorbed,
        merged_answer=survivor_answer,
    )
    deduped, _ = _retighten_entry_with_deduped_fields(merged)
    return deduped


__all__ = [
    "_question_intent_primary_question",
    "_question_intent_tokens_from_entry",
    "MechanicalCleanupCompiledEntriesResult",
    "cleanup_compiled_entries_mechanically",
    "source_excerpts_from_preprocessing_entry",
    "_entry_question_intent_fingerprints",
    "_entries_have_exact_question_intent",
]
