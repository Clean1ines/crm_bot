from __future__ import annotations


from collections.abc import Sequence
from dataclasses import dataclass
from src.application.ports.knowledge import KnowledgeRuntimeRetrievalPort
from src.application.services.knowledge_answer_resolution_service import (
    _answer_resolution_candidate_index,
    _answer_resolution_survivor_index,
    _answer_resolution_text_fingerprint,
    _answer_resolution_token_similarity,
    _answer_resolution_tokens_from_text,
    _cleanup_answer_resolution_text_with_metrics,
    _entry_with_answer_resolution_decision,
    _limit_compiled_text,
    _merge_answer_text,
    _merge_answer_units_deterministically,
    _merge_entry_fields_deterministically,
)
from src.application.services.knowledge_generated_entry_repair import _answer_digest
from src.domain.project_plane.embedding_text import CANONICAL_EMBEDDING_TEXT_VERSION
from src.domain.project_plane.json_types import (
    JsonObject,
    JsonValue,
)
from src.domain.project_plane.knowledge_compilation import (
    CanonicalKnowledgeEntry,
    EmbeddingText,
    KnowledgeEnrichment,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
    SourceRef,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgeAnswerResolutionDecision,
    KnowledgePreprocessingEntry,
)
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
    return _answer_digest(entry.answer)


def _source_excerpts_from_preprocessing_entry(
    entry: KnowledgePreprocessingEntry,
) -> tuple[str, ...]:
    normalized = entry.source_excerpt.replace("\r\n", "\n").replace("\r", "\n")
    parts = tuple(part.strip() for part in normalized.split("\n\n"))
    return _text_tuple(parts)


def _merge_compiled_source_refs(
    first: tuple[SourceRef, ...],
    second: tuple[SourceRef, ...],
) -> tuple[SourceRef, ...]:
    refs: list[SourceRef] = []
    seen: set[tuple[int | None, str, str | None]] = set()

    for source_ref in (*first, *second):
        key = (
            source_ref.source_index,
            source_ref.quote,
            source_ref.source_chunk_id,
        )
        if key in seen:
            continue
        seen.add(key)
        refs.append(source_ref)

    return tuple(refs)


def _entry_question_intent_fingerprints(
    entry: KnowledgePreprocessingEntry,
) -> tuple[str, ...]:
    values: list[str] = []
    for value in (
        entry.canonical_question,
        _question_intent_primary_question(entry),
        *_text_tuple(entry.questions),
    ):
        fingerprint = _answer_resolution_text_fingerprint(value)
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


async def _existing_project_titles_for_answer_resolution(
    *,
    repo: KnowledgeRuntimeRetrievalPort,
    project_id: str,
    document_id: str,
) -> tuple[str, ...]:
    try:
        titles = await repo.list_runtime_entry_titles(
            project_id=project_id,
            exclude_document_id=document_id,
            limit=300,
        )
    except (AttributeError, TypeError):
        return ()

    result: list[str] = []
    for title in titles:
        cleaned = _clean_optional_text(title)
        if cleaned and cleaned not in result:
            result.append(cleaned)

    return tuple(result)


KCD_STAGE_K_MERGED_QUESTION_LIMIT = 40


KCD_STAGE_K_MERGED_SYNONYM_LIMIT = 64


KCD_STAGE_K_MERGED_TAG_LIMIT = 32


KCD_STAGE_K_MERGED_ANSWER_MAX_CHARS = 3600


KCD_STAGE_K_MERGED_SOURCE_EXCERPT_MAX_CHARS = 7000


KCD_STAGE_K_MERGED_EMBEDDING_TEXT_MAX_CHARS = 2400


@dataclass(frozen=True, slots=True)
class _RetightenExistingDocumentPlan:
    entries: tuple[KnowledgePreprocessingEntry, ...]
    survivor_source_indexes: tuple[int, ...]
    merged_source_indexes_by_entry: tuple[tuple[int, ...], ...]
    removed_source_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _DeterministicRetightenResult:
    plan: _RetightenExistingDocumentPlan
    metrics: JsonObject


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

        fingerprint = _answer_resolution_text_fingerprint(cleaned)
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

    answer_cleanup = _cleanup_answer_resolution_text_with_metrics(entry.answer)
    embedding_cleanup = _cleanup_answer_resolution_text_with_metrics(
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
    return _answer_resolution_text_fingerprint(
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
    return _answer_resolution_text_fingerprint(entry.answer)


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
        answer_unit_merge = _merge_answer_units_deterministically(
            left.answer,
            right.answer,
            allow_disjoint_union=True,
        )
        if answer_unit_merge is not None:
            return answer_unit_merge.strategy

    if left_intent and right_intent and left_intent == right_intent:
        answer_score = _answer_resolution_token_similarity(
            _answer_resolution_tokens_from_text(left.answer),
            _answer_resolution_tokens_from_text(right.answer),
        )
        if answer_score >= 0.72:
            return "exact_intent_high_answer_overlap"

    return None


def _retighten_entry_richness_score(
    entry: KnowledgePreprocessingEntry,
) -> tuple[int, int, int, int]:
    return (
        len(_clean_optional_text(entry.answer)),
        len(_source_excerpts_from_preprocessing_entry(entry)),
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

    answer_unit_merge = _merge_answer_units_deterministically(
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
        survivor_answer = _merge_answer_text(
            existing_entry.answer, incoming_entry.answer
        )

    merged = _merge_entry_fields_deterministically(
        existing_entry=survivor,
        incoming_entry=absorbed,
        merged_answer=survivor_answer,
    )
    deduped, _ = _retighten_entry_with_deduped_fields(merged)
    return deduped


def _retighten_entry_is_suspicious_meta(
    entry: KnowledgePreprocessingEntry,
) -> bool:
    """KAD v1 forbids keyword dictionaries for semantic/meta filtering.

    Deterministic code may dedupe and validate structure, but it must not
    classify meta/test/RAG/business roles by hardcoded terms.
    """
    return False


def _deterministic_retighten_existing_document_plan(
    entries: Sequence[KnowledgePreprocessingEntry],
) -> _DeterministicRetightenResult:
    working_entries: list[KnowledgePreprocessingEntry] = []
    survivor_source_indexes: list[int] = []
    merged_source_indexes: list[list[int]] = []

    metrics: JsonObject = {
        "deterministic_duplicate_group_count": 0,
        "deterministic_collapsed_entry_count": 0,
        "deterministic_exact_answer_collapse_count": 0,
        "deterministic_exact_intent_merge_count": 0,
        "deterministic_answer_containment_merge_count": 0,
        "deterministic_answer_unit_subset_merge_count": 0,
        "deterministic_answer_unit_overlap_merge_count": 0,
        "deterministic_same_intent_complementary_merge_count": 0,
        "deduped_question_variant_count": 0,
        "deduped_synonym_count": 0,
        "deduped_tag_count": 0,
        "deduped_answer_unit_count": 0,
        "deduped_embedding_text_unit_count": 0,
        "suspicious_meta_entry_count": 0,
    }
    suspicious_examples: list[JsonObject] = []

    for source_index, raw_entry in enumerate(entries):
        entry, dedupe_metrics = _retighten_entry_with_deduped_fields(raw_entry)
        for key, value in dedupe_metrics.items():
            metrics[key] = int(cast(int, metrics.get(key, 0))) + int(cast(int, value))

        if _retighten_entry_is_suspicious_meta(entry):
            metrics["suspicious_meta_entry_count"] = (
                int(cast(int, metrics["suspicious_meta_entry_count"])) + 1
            )
            if len(suspicious_examples) < 5:
                suspicious_examples.append(
                    {
                        "title": _limit_compiled_text(entry.title, max_chars=120),
                        "answer_preview": _limit_compiled_text(
                            entry.answer,
                            max_chars=180,
                        ),
                    }
                )

        target_index: int | None = None
        target_reason: str | None = None
        for existing_index, existing_entry in enumerate(working_entries):
            reason = _retighten_deterministic_duplicate_reason(existing_entry, entry)
            if reason is None:
                continue
            target_index = existing_index
            target_reason = reason
            break

        if target_index is None or target_reason is None:
            working_entries.append(entry)
            survivor_source_indexes.append(source_index)
            merged_source_indexes.append([source_index])
            continue

        existing_entry = working_entries[target_index]
        existing_survivor = survivor_source_indexes[target_index]
        merged_entry = _retighten_merge_entries_deterministically(
            existing_entry=existing_entry,
            incoming_entry=entry,
            reason=target_reason,
        )

        if _retighten_entry_richness_score(entry) > _retighten_entry_richness_score(
            existing_entry
        ):
            survivor_source_indexes[target_index] = source_index
            if existing_survivor not in merged_source_indexes[target_index]:
                merged_source_indexes[target_index].append(existing_survivor)

        if source_index not in merged_source_indexes[target_index]:
            merged_source_indexes[target_index].append(source_index)

        working_entries[target_index] = merged_entry
        metrics["deterministic_duplicate_group_count"] = (
            int(cast(int, metrics["deterministic_duplicate_group_count"])) + 1
        )
        metrics["deterministic_collapsed_entry_count"] = (
            int(cast(int, metrics["deterministic_collapsed_entry_count"])) + 1
        )

        if target_reason == "exact_answer":
            metrics["deterministic_exact_answer_collapse_count"] = (
                int(cast(int, metrics["deterministic_exact_answer_collapse_count"])) + 1
            )
        elif target_reason == "answer_containment":
            metrics["deterministic_answer_containment_merge_count"] = (
                int(cast(int, metrics["deterministic_answer_containment_merge_count"]))
                + 1
            )
        elif target_reason == "exact_intent_high_answer_overlap":
            metrics["deterministic_exact_intent_merge_count"] = (
                int(cast(int, metrics["deterministic_exact_intent_merge_count"])) + 1
            )
        elif target_reason == "answer_unit_subset_superset":
            metrics["deterministic_answer_unit_subset_merge_count"] = (
                int(cast(int, metrics["deterministic_answer_unit_subset_merge_count"]))
                + 1
            )
        elif target_reason == "answer_unit_overlap_union":
            metrics["deterministic_answer_unit_overlap_merge_count"] = (
                int(cast(int, metrics["deterministic_answer_unit_overlap_merge_count"]))
                + 1
            )
        elif target_reason == "same_intent_complementary_answer_unit_union":
            metrics["deterministic_same_intent_complementary_merge_count"] = (
                int(
                    cast(
                        int,
                        metrics["deterministic_same_intent_complementary_merge_count"],
                    )
                )
                + 1
            )

    survivor_set = set(survivor_source_indexes)
    removed_source_indexes = tuple(
        sorted(
            source_index
            for source_indexes in merged_source_indexes
            for source_index in source_indexes
            if source_index not in survivor_set
        )
    )
    if suspicious_examples:
        metrics["suspicious_meta_examples"] = cast(JsonValue, suspicious_examples)

    return _DeterministicRetightenResult(
        plan=_RetightenExistingDocumentPlan(
            entries=tuple(working_entries),
            survivor_source_indexes=tuple(survivor_source_indexes),
            merged_source_indexes_by_entry=tuple(
                tuple(source_indexes) for source_indexes in merged_source_indexes
            ),
            removed_source_indexes=removed_source_indexes,
        ),
        metrics=metrics,
    )


def _compose_retighten_existing_document_plans(
    *,
    base: _RetightenExistingDocumentPlan,
    overlay: _RetightenExistingDocumentPlan,
) -> _RetightenExistingDocumentPlan:
    survivor_source_indexes = tuple(
        base.survivor_source_indexes[index] for index in overlay.survivor_source_indexes
    )

    merged_source_indexes_by_entry: list[tuple[int, ...]] = []
    for overlay_source_indexes in overlay.merged_source_indexes_by_entry:
        original_indexes: list[int] = []
        for base_index in overlay_source_indexes:
            if base_index < 0 or base_index >= len(base.merged_source_indexes_by_entry):
                continue
            for original_index in base.merged_source_indexes_by_entry[base_index]:
                if original_index not in original_indexes:
                    original_indexes.append(original_index)
        merged_source_indexes_by_entry.append(tuple(original_indexes))

    removed_source_indexes: set[int] = set(base.removed_source_indexes)
    for base_index in overlay.removed_source_indexes:
        if base_index < 0 or base_index >= len(base.merged_source_indexes_by_entry):
            continue
        removed_source_indexes.update(base.merged_source_indexes_by_entry[base_index])

    survivor_set = set(survivor_source_indexes)
    removed_source_indexes = {
        source_index
        for source_index in removed_source_indexes
        if source_index not in survivor_set
    }

    return _RetightenExistingDocumentPlan(
        entries=overlay.entries,
        survivor_source_indexes=survivor_source_indexes,
        merged_source_indexes_by_entry=tuple(merged_source_indexes_by_entry),
        removed_source_indexes=tuple(sorted(removed_source_indexes)),
    )


def _preprocessing_entry_from_canonical_entry(
    entry: CanonicalKnowledgeEntry,
) -> KnowledgePreprocessingEntry:
    source_excerpt = "\n\n".join(
        source_ref.quote for source_ref in entry.source_refs if source_ref.quote
    )
    embedding_text = entry.embedding_text.value if entry.embedding_text else ""
    return KnowledgePreprocessingEntry(
        title=entry.title,
        answer=entry.answer,
        source_excerpt=source_excerpt,
        questions=entry.enrichment.questions,
        synonyms=entry.enrichment.synonyms,
        tags=entry.enrichment.tags,
        embedding_text=_clean_optional_text(embedding_text) or entry.answer,
    )


def _retighten_existing_document_plan(
    *,
    entries: Sequence[KnowledgePreprocessingEntry],
    decisions: Sequence[KnowledgeAnswerResolutionDecision],
) -> _RetightenExistingDocumentPlan:
    updated_entries: list[KnowledgePreprocessingEntry] = list(entries)
    merged_source_indexes: list[list[int]] = [[index] for index in range(len(entries))]
    removed_indexes: set[int] = set()

    for decision in decisions:
        if not decision.is_merge:
            continue

        candidate_indexes: list[int] = []
        for candidate_id in decision.candidate_ids:
            index = _answer_resolution_candidate_index(candidate_id)
            if index is None or index < 0 or index >= len(entries):
                continue
            if index in candidate_indexes or index in removed_indexes:
                continue
            candidate_indexes.append(index)

        if len(candidate_indexes) < 2:
            continue

        ordered_indexes = tuple(sorted(candidate_indexes))
        survivor_index = _answer_resolution_survivor_index(
            decision=decision,
            candidate_indexes=ordered_indexes,
            entries=entries,
        )

        merged_entry = updated_entries[survivor_index]
        for index in ordered_indexes:
            if index == survivor_index:
                continue
            merged_entry = _merge_entry_fields_deterministically(
                existing_entry=merged_entry,
                incoming_entry=updated_entries[index],
                merged_answer=decision.canonical_answer,
            )

        merged_indexes_for_survivor: list[int] = []
        for index in ordered_indexes:
            for source_index in merged_source_indexes[index]:
                if source_index not in merged_indexes_for_survivor:
                    merged_indexes_for_survivor.append(source_index)

        updated_entries[survivor_index] = _entry_with_answer_resolution_decision(
            entry=merged_entry,
            decision=decision,
        )
        merged_source_indexes[survivor_index] = merged_indexes_for_survivor
        removed_indexes.update(
            index for index in ordered_indexes if index != survivor_index
        )

    survivor_indexes = tuple(
        index for index in range(len(updated_entries)) if index not in removed_indexes
    )
    return _RetightenExistingDocumentPlan(
        entries=tuple(updated_entries[index] for index in survivor_indexes),
        survivor_source_indexes=survivor_indexes,
        merged_source_indexes_by_entry=tuple(
            tuple(merged_source_indexes[index]) for index in survivor_indexes
        ),
        removed_source_indexes=tuple(sorted(removed_indexes)),
    )


def _merge_source_refs_for_existing_entry_indexes(
    *,
    source_indexes: Sequence[int],
    entries: Sequence[CanonicalKnowledgeEntry],
) -> tuple[SourceRef, ...]:
    refs: tuple[SourceRef, ...] = ()
    for index in source_indexes:
        if index < 0 or index >= len(entries):
            continue
        refs = _merge_compiled_source_refs(refs, entries[index].source_refs)
    return refs


def _retightened_canonical_entry(
    *,
    original: CanonicalKnowledgeEntry,
    entry: KnowledgePreprocessingEntry,
    source_refs: tuple[SourceRef, ...],
    merged_from_entry_ids: Sequence[str],
) -> CanonicalKnowledgeEntry:
    metadata: dict[str, object] = dict(original.metadata)
    metadata["answer_resolution"] = {
        "strategy": "kcd_stage_k8_existing_document_retighten",
        "merged_from_entry_ids": tuple(merged_from_entry_ids),
        "merged_source_entry_count": len(merged_from_entry_ids),
    }

    embedding_text = (
        _clean_optional_text(entry.embedding_text)
        or (original.embedding_text.value if original.embedding_text else "")
        or entry.answer
    )

    return CanonicalKnowledgeEntry(
        id=original.id,
        project_id=original.project_id,
        document_id=original.document_id,
        compiler_run_id=original.compiler_run_id,
        stable_key=original.stable_key,
        entry_kind=original.entry_kind,
        title=entry.title,
        answer=entry.answer,
        source_refs=source_refs,
        enrichment=KnowledgeEnrichment(
            questions=_text_tuple(entry.questions),
            synonyms=_text_tuple(entry.synonyms),
            tags=_text_tuple(entry.tags),
        ),
        embedding_text=EmbeddingText(
            value=embedding_text,
            version=CANONICAL_EMBEDDING_TEXT_VERSION,
        ),
        status=KnowledgeEntryStatus.PUBLISHED,
        visibility=KnowledgeEntryVisibility.RUNTIME,
        version=original.version + 1,
        compiler_version=original.compiler_version,
        embedding_text_version=CANONICAL_EMBEDDING_TEXT_VERSION,
        metadata=metadata,
    )


def _retighten_updated_canonical_entries(
    *,
    plan: _RetightenExistingDocumentPlan,
    current_entries: Sequence[CanonicalKnowledgeEntry],
) -> tuple[CanonicalKnowledgeEntry, ...]:
    updated_entries: list[CanonicalKnowledgeEntry] = []
    for output_index, tightened_entry in enumerate(plan.entries):
        survivor_source_index = plan.survivor_source_indexes[output_index]
        merged_source_indexes = plan.merged_source_indexes_by_entry[output_index]
        original = current_entries[survivor_source_index]
        source_refs = _merge_source_refs_for_existing_entry_indexes(
            source_indexes=merged_source_indexes,
            entries=current_entries,
        )
        updated_entries.append(
            _retightened_canonical_entry(
                original=original,
                entry=tightened_entry,
                source_refs=source_refs,
                merged_from_entry_ids=tuple(
                    current_entries[index].id for index in merged_source_indexes
                ),
            )
        )
    return tuple(updated_entries)


def _retighten_archived_entry_ids(
    *,
    plan: _RetightenExistingDocumentPlan,
    current_entries: Sequence[CanonicalKnowledgeEntry],
) -> tuple[str, ...]:
    return tuple(
        current_entries[index].id
        for index in plan.removed_source_indexes
        if 0 <= index < len(current_entries)
    )


__all__ = [
    "KCD_STAGE_K_MERGED_QUESTION_LIMIT",
    "KCD_STAGE_K_MERGED_SYNONYM_LIMIT",
    "KCD_STAGE_K_MERGED_TAG_LIMIT",
    "KCD_STAGE_K_MERGED_ANSWER_MAX_CHARS",
    "KCD_STAGE_K_MERGED_SOURCE_EXCERPT_MAX_CHARS",
    "KCD_STAGE_K_MERGED_EMBEDDING_TEXT_MAX_CHARS",
    "_RetightenExistingDocumentPlan",
    "_DeterministicRetightenResult",
    "_retighten_deduped_text_tuple",
    "_retighten_entry_with_deduped_fields",
    "_retighten_entry_intent_fingerprint",
    "_retighten_answer_fingerprint",
    "_retighten_answer_contains",
    "_retighten_deterministic_duplicate_reason",
    "_retighten_entry_richness_score",
    "_retighten_merge_entries_deterministically",
    "_retighten_entry_is_suspicious_meta",
    "_deterministic_retighten_existing_document_plan",
    "_compose_retighten_existing_document_plans",
    "_preprocessing_entry_from_canonical_entry",
    "_retighten_existing_document_plan",
    "_merge_source_refs_for_existing_entry_indexes",
    "_retightened_canonical_entry",
    "_retighten_updated_canonical_entries",
    "_retighten_archived_entry_ids",
    "_existing_project_titles_for_answer_resolution",
]
