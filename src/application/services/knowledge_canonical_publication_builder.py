from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from src.application.errors import ValidationError
from src.domain.project_plane.embedding_text import CANONICAL_EMBEDDING_TEXT_VERSION
from src.domain.project_plane.knowledge_compilation import (
    AnswerCandidate,
    CanonicalKnowledgeEntry,
    KnowledgeEnrichment,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
    SourceChunk,
    SourceRef,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingMode,
    KnowledgePreprocessingResult,
    entry_kind_for_preprocessing_mode,
)


KCD_STAGE_K_COMPILER_VERSION = "kcd_v1_stage_k_answer_compiler"
KCD_STAGE_K_ANSWER_DIGEST_MAX_CHARS = 220


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


def answer_digest(
    value: str,
    *,
    max_chars: int = KCD_STAGE_K_ANSWER_DIGEST_MAX_CHARS,
) -> str:
    text = _clean_optional_text(value)
    if len(text) <= max_chars:
        return text
    trimmed = text[:max_chars].rsplit(" ", 1)[0].strip()
    return trimmed or text[:max_chars].strip()


def _question_intent_primary_question(entry: KnowledgePreprocessingEntry) -> str:
    if entry.canonical_question:
        return entry.canonical_question
    for question in _text_tuple(entry.questions):
        if question:
            return question
    return answer_digest(entry.answer)


def _metadata_text_tuple(metadata: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = metadata.get(key)
    if isinstance(value, str):
        values: Sequence[object] = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        values = value
    else:
        return ()

    result: list[str] = []
    for item in values:
        text = _clean_optional_text(str(item or ""))
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _canonical_entries_from_raw_answer_candidates(
    *,
    project_id: str,
    document_id: str,
    compiler_run_id: str,
    mode: KnowledgePreprocessingMode,
    candidates: Sequence[AnswerCandidate],
) -> tuple[CanonicalKnowledgeEntry, ...]:
    entry_kind = entry_kind_for_preprocessing_mode(mode)
    entries: list[CanonicalKnowledgeEntry] = []

    for index, candidate in enumerate(candidates):
        answer = _clean_optional_text(candidate.candidate_answer)
        if not answer:
            continue

        candidate_metadata = dict(candidate.metadata)
        canonical_question = _clean_optional_text(
            str(candidate_metadata.get("canonical_question") or "")
        )
        question_variants = _metadata_text_tuple(
            candidate_metadata, "question_variants"
        )
        questions = (
            _merge_text_tuple_values((canonical_question,), question_variants)
            if canonical_question
            else question_variants
        )
        stable_key_digest = hashlib.sha256(
            f"{document_id}:stage_k_raw:{entry_kind.value}:{candidate.id}".encode(
                "utf-8"
            )
        ).hexdigest()
        stable_key = f"{document_id}:stage_k_retry:{stable_key_digest[:24]}"
        metadata: dict[str, object] = dict(candidate_metadata)
        metadata["source_candidate_id"] = candidate.id
        metadata["compiler_index"] = index
        metadata["compiler_stage"] = "stage_k_answer_compiler_retry"

        entry = CanonicalKnowledgeEntry(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key)),
            project_id=project_id,
            document_id=document_id,
            compiler_run_id=compiler_run_id,
            stable_key=stable_key,
            entry_kind=entry_kind,
            title=_clean_optional_text(candidate.title) or f"Answer entry {index + 1}",
            answer=answer,
            source_refs=candidate.source_refs,
            enrichment=KnowledgeEnrichment(
                questions=questions,
                synonyms=(),
                tags=(),
            ),
            embedding_text=None,
            status=KnowledgeEntryStatus.PUBLISHED,
            visibility=KnowledgeEntryVisibility.RUNTIME,
            version=1,
            compiler_version=KCD_STAGE_K_COMPILER_VERSION,
            embedding_text_version=CANONICAL_EMBEDDING_TEXT_VERSION,
            metadata=metadata,
        )
        entry.assert_publishable()
        entries.append(entry)

    return tuple(entries)


@dataclass(frozen=True, slots=True)
class CompiledAnswerEntryDraft:
    title: str
    answer: str
    source_excerpts: tuple[str, ...]
    source_refs: tuple[SourceRef, ...]
    questions: tuple[str, ...]
    synonyms: tuple[str, ...]
    tags: tuple[str, ...]
    embedding_text: str
    metadata: Mapping[str, object]


def _normalized_answer_topic_key(value: str) -> str:
    text = value.lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return " ".join(text.split())


def build_answer_topic_key(entry: KnowledgePreprocessingEntry, *, index: int) -> str:
    title_key = _normalized_answer_topic_key(entry.title)
    question_key = _normalized_answer_topic_key(
        entry.canonical_question or _question_intent_primary_question(entry)
    )
    answer_key = _normalized_answer_topic_key(entry.answer)
    source_excerpt_key = _normalized_answer_topic_key(entry.source_excerpt)

    if answer_key and source_excerpt_key:
        return f"exact-answer-source:{answer_key}:{source_excerpt_key}"
    if title_key and question_key and answer_key:
        return f"exact-title-question-answer:{title_key}:{question_key}:{answer_key}"
    if answer_key:
        return f"exact-answer:{answer_key}"

    return f"entry-{index}"


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


def _merge_int_tuple_values(*groups: tuple[int, ...]) -> tuple[int, ...]:
    result: list[int] = []
    for group in groups:
        for value in group:
            if value not in result:
                result.append(value)
    return tuple(result)


def merge_answer_text(left: str, right: str) -> str:
    left_clean = _clean_optional_text(left)
    right_clean = _clean_optional_text(right)

    if not left_clean:
        return right_clean
    if not right_clean:
        return left_clean

    left_normalized = _normalized_answer_topic_key(left_clean)
    right_normalized = _normalized_answer_topic_key(right_clean)

    if left_normalized == right_normalized:
        return left_clean
    if right_normalized and right_normalized in left_normalized:
        return left_clean
    if left_normalized and left_normalized in right_normalized:
        return right_clean

    unit_merge = merge_answer_units_deterministically(left_clean, right_clean)
    if unit_merge is not None:
        return _cleanup_answer_resolution_text(unit_merge.answer)

    return _cleanup_answer_resolution_text(f"{left_clean}\n\n{right_clean}")


def source_excerpts_from_preprocessing_entry(
    entry: KnowledgePreprocessingEntry,
) -> tuple[str, ...]:
    normalized = entry.source_excerpt.replace("\r\n", "\n").replace("\r", "\n")
    parts = tuple(part.strip() for part in normalized.split("\n\n"))
    return _text_tuple(parts)


def _preprocessing_entry_to_compiled_draft(
    entry: KnowledgePreprocessingEntry,
    *,
    mode: KnowledgePreprocessingMode,
    index: int,
) -> CompiledAnswerEntryDraft:
    return CompiledAnswerEntryDraft(
        title=_clean_optional_text(entry.title) or f"Answer entry {index + 1}",
        answer=_clean_optional_text(entry.answer),
        source_excerpts=source_excerpts_from_preprocessing_entry(entry),
        source_refs=tuple(
            SourceRef(
                source_index=index,
                quote=source_excerpt,
                source_chunk_id=None,
                confidence=1.0,
            )
            for source_excerpt in source_excerpts_from_preprocessing_entry(entry)
        ),
        questions=_text_tuple(entry.questions),
        synonyms=_text_tuple(entry.synonyms),
        tags=_text_tuple(entry.tags),
        embedding_text=_clean_optional_text(entry.embedding_text),
        metadata={
            "compiler_stage": "stage_k_answer_compiler",
            "preprocessing_mode": mode,
            "preprocessing_entry_indices": (index,),
        },
    )


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


def _source_refs_from_compiled_answer_draft(
    draft: CompiledAnswerEntryDraft,
    *,
    fallback_source_index: int,
) -> tuple[SourceRef, ...]:
    if draft.source_refs:
        return draft.source_refs

    return tuple(
        SourceRef(
            source_index=fallback_source_index,
            quote=source_excerpt,
            source_chunk_id=None,
            confidence=1.0,
        )
        for source_excerpt in draft.source_excerpts
    )


def _merge_compiled_answer_drafts(
    left: CompiledAnswerEntryDraft,
    right: CompiledAnswerEntryDraft,
) -> CompiledAnswerEntryDraft:
    left_indices = left.metadata.get("preprocessing_entry_indices")
    right_indices = right.metadata.get("preprocessing_entry_indices")
    merged_indices: list[int] = []

    for value in (left_indices, right_indices):
        if not isinstance(value, tuple):
            continue
        for item in value:
            if isinstance(item, int) and item not in merged_indices:
                merged_indices.append(item)

    metadata: dict[str, object] = dict(left.metadata)
    metadata["compiler_merge"] = "exact_duplicate_grouping"
    metadata["preprocessing_entry_indices"] = tuple(merged_indices)
    metadata["merged_preprocessing_entry_count"] = len(merged_indices)

    return CompiledAnswerEntryDraft(
        title=left.title,
        answer=merge_answer_text(left.answer, right.answer),
        source_excerpts=_merge_text_tuple_values(
            left.source_excerpts,
            right.source_excerpts,
        ),
        source_refs=_merge_compiled_source_refs(
            left.source_refs,
            right.source_refs,
        ),
        questions=_merge_text_tuple_values(left.questions, right.questions),
        synonyms=_merge_text_tuple_values(left.synonyms, right.synonyms),
        tags=_merge_text_tuple_values(left.tags, right.tags),
        embedding_text=merge_answer_text(left.embedding_text, right.embedding_text),
        metadata=metadata,
    )


def _compiled_answer_drafts_from_preprocessing_result(
    result: KnowledgePreprocessingResult,
) -> tuple[CompiledAnswerEntryDraft, ...]:
    grouped: dict[str, CompiledAnswerEntryDraft] = {}
    ordered_keys: list[str] = []

    for index, entry in enumerate(result.entries):
        draft = _preprocessing_entry_to_compiled_draft(
            entry,
            mode=result.mode,
            index=index,
        )
        if not draft.answer:
            continue

        key = build_answer_topic_key(entry, index=index)
        if key in grouped:
            grouped[key] = _merge_compiled_answer_drafts(grouped[key], draft)
            continue

        grouped[key] = draft
        ordered_keys.append(key)

    return tuple(grouped[key] for key in ordered_keys)


def _source_chunk_for_quote(
    *,
    quote: str,
    source_chunks: Sequence[SourceChunk],
) -> SourceChunk:
    if not source_chunks:
        raise ValidationError("Cannot ground answer entry without source chunks")

    quote_clean = _clean_optional_text(quote)
    if quote_clean:
        for source_chunk in source_chunks:
            if (
                quote_clean in source_chunk.content
                or source_chunk.content in quote_clean
            ):
                return source_chunk

    quote_terms = {
        token
        for token in re.findall(
            r"[0-9a-zа-яё]+",
            quote_clean.lower().replace("ё", "е"),
        )
        if len(token) >= 4
    }

    if quote_terms:
        best_chunk = source_chunks[0]
        best_score = -1
        for source_chunk in source_chunks:
            chunk_terms = {
                token
                for token in re.findall(
                    r"[0-9a-zа-яё]+",
                    source_chunk.content.lower().replace("ё", "е"),
                )
                if len(token) >= 4
            }
            score = len(quote_terms & chunk_terms)
            if score > best_score:
                best_chunk = source_chunk
                best_score = score
        return best_chunk

    return source_chunks[0]


def build_source_refs_for_compiled_answer_draft(
    *,
    draft: CompiledAnswerEntryDraft,
    source_chunks: Sequence[SourceChunk],
) -> tuple[SourceRef, ...]:
    refs: list[SourceRef] = []
    seen_quotes: set[str] = set()

    quotes = draft.source_excerpts or (draft.answer,)
    for quote in quotes:
        cleaned_quote = _clean_optional_text(quote)
        if not cleaned_quote or cleaned_quote in seen_quotes:
            continue

        source_chunk = _source_chunk_for_quote(
            quote=cleaned_quote,
            source_chunks=source_chunks,
        )
        refs.append(
            SourceRef(
                source_index=source_chunk.source_index,
                quote=cleaned_quote,
                source_chunk_id=source_chunk.id,
                start_offset=source_chunk.start_offset,
                end_offset=source_chunk.end_offset,
                confidence=1.0,
            )
        )
        seen_quotes.add(cleaned_quote)

    return tuple(refs)


def _publication_text_fingerprint(value: str) -> str:
    return " ".join(
        re.sub(r"[^0-9a-zа-яё]+", " ", value.lower().replace("ё", "е")).split()
    )


def _source_ref_fingerprint(source_ref: SourceRef) -> tuple[object, ...]:
    return (
        source_ref.source_chunk_id or "",
        source_ref.source_index,
        _publication_text_fingerprint(source_ref.quote),
    )


def _merge_source_ref_tuple_values(
    *groups: tuple[SourceRef, ...],
) -> tuple[SourceRef, ...]:
    result: list[SourceRef] = []
    for group in groups:
        for source_ref in group:
            quote_fp = _publication_text_fingerprint(source_ref.quote)
            if not quote_fp:
                continue
            duplicate_index = None
            for idx, existing in enumerate(result):
                same_origin = (existing.source_chunk_id or "") == (
                    source_ref.source_chunk_id or ""
                ) and existing.source_index == source_ref.source_index
                if not same_origin:
                    continue
                existing_fp = _publication_text_fingerprint(existing.quote)
                if existing_fp == quote_fp:
                    duplicate_index = idx
                    break
                if quote_fp in existing_fp:
                    duplicate_index = idx
                    break
                if existing_fp in quote_fp:
                    if len(source_ref.quote) > len(existing.quote):
                        result[idx] = source_ref
                    duplicate_index = idx
                    break
            if duplicate_index is not None:
                continue
            result.append(source_ref)
    return tuple(result)


def _merge_canonical_entries_structurally(
    existing_entry: CanonicalKnowledgeEntry,
    incoming_entry: CanonicalKnowledgeEntry,
) -> CanonicalKnowledgeEntry:
    source_refs = _merge_source_ref_tuple_values(
        existing_entry.source_refs,
        incoming_entry.source_refs,
    )
    enrichment = KnowledgeEnrichment(
        questions=_merge_text_tuple_values(
            existing_entry.enrichment.questions,
            incoming_entry.enrichment.questions,
        ),
        paraphrases=_merge_text_tuple_values(
            existing_entry.enrichment.paraphrases,
            incoming_entry.enrichment.paraphrases,
        ),
        synonyms=_merge_text_tuple_values(
            existing_entry.enrichment.synonyms,
            incoming_entry.enrichment.synonyms,
        ),
        typo_queries=_merge_text_tuple_values(
            existing_entry.enrichment.typo_queries,
            incoming_entry.enrichment.typo_queries,
        ),
        colloquial_queries=_merge_text_tuple_values(
            existing_entry.enrichment.colloquial_queries,
            incoming_entry.enrichment.colloquial_queries,
        ),
        tags=_merge_text_tuple_values(
            existing_entry.enrichment.tags,
            incoming_entry.enrichment.tags,
        ),
        retrieval_guards=_merge_text_tuple_values(
            existing_entry.enrichment.retrieval_guards,
            incoming_entry.enrichment.retrieval_guards,
        ),
    )
    metadata = dict(existing_entry.metadata)
    merged_ids = _merge_text_tuple_values(
        _text_tuple(metadata.get("merged_entry_ids")),
        (existing_entry.id, incoming_entry.id),
        _text_tuple(incoming_entry.metadata.get("merged_entry_ids")),
    )
    metadata["publication_guard"] = "exact_fingerprint_collapse"
    metadata["merged_candidate_count"] = len(merged_ids)
    metadata["merged_candidate_ids"] = list(merged_ids)
    metadata["source_ref_count"] = len(source_refs)
    return replace(
        existing_entry,
        source_refs=source_refs,
        enrichment=enrichment,
        metadata=metadata,
    )


def _final_publication_guard_collapse_exact_duplicates(
    entries: Sequence[CanonicalKnowledgeEntry],
) -> tuple[CanonicalKnowledgeEntry, ...]:
    result: list[CanonicalKnowledgeEntry] = []
    key_to_index: dict[tuple[str, str], int] = {}

    for entry in entries:
        fingerprints = (
            (
                "question",
                _publication_text_fingerprint(entry.enrichment.questions[0])
                if entry.enrichment.questions
                else "",
            ),
            ("answer", _publication_text_fingerprint(entry.answer)),
            (
                "title_answer",
                _publication_text_fingerprint(f"{entry.title} {entry.answer}"),
            ),
        )
        target_index: int | None = None
        for fingerprint in fingerprints:
            if fingerprint[1] and fingerprint in key_to_index:
                target_index = key_to_index[fingerprint]
                break

        if target_index is None:
            target_index = len(result)
            result.append(entry)
        else:
            result[target_index] = _merge_canonical_entries_structurally(
                result[target_index],
                entry,
            )

        for fingerprint in fingerprints:
            if fingerprint[1]:
                key_to_index[fingerprint] = target_index

    return tuple(result)


def _canonical_entries_from_preprocessing_result(
    *,
    project_id: str,
    document_id: str,
    compiler_run_id: str,
    result: KnowledgePreprocessingResult,
    source_chunks: Sequence[SourceChunk],
) -> tuple[CanonicalKnowledgeEntry, ...]:
    drafts = _compiled_answer_drafts_from_preprocessing_result(result)
    entry_kind = entry_kind_for_preprocessing_mode(result.mode)
    entries: list[CanonicalKnowledgeEntry] = []

    for index, draft in enumerate(drafts):
        source_refs = build_source_refs_for_compiled_answer_draft(
            draft=draft,
            source_chunks=source_chunks,
        )
        stable_key_digest = hashlib.sha256(
            (
                f"{document_id}:stage_k:{entry_kind.value}:{draft.title}:{draft.answer}"
            ).encode("utf-8")
        ).hexdigest()
        stable_key = f"{document_id}:stage_k:{stable_key_digest[:24]}"
        entry_id = str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key))
        metadata: dict[str, object] = dict(draft.metadata)
        merged_counts = result.metrics.get("merged_preprocessing_entry_counts")
        if isinstance(merged_counts, list) and index < len(merged_counts):
            merged_count = merged_counts[index]
            if isinstance(merged_count, int) and merged_count > 1:
                metadata["compiler_merge"] = "exact_duplicate_grouping"
                metadata["merged_preprocessing_entry_count"] = merged_count
        metadata["source_ref_count"] = len(source_refs)
        metadata["compiler_index"] = index

        entry = CanonicalKnowledgeEntry(
            id=entry_id,
            project_id=project_id,
            document_id=document_id,
            compiler_run_id=compiler_run_id,
            stable_key=stable_key,
            entry_kind=entry_kind,
            title=draft.title,
            answer=draft.answer,
            source_refs=source_refs,
            enrichment=KnowledgeEnrichment(
                questions=draft.questions,
                synonyms=draft.synonyms,
                tags=draft.tags,
            ),
            embedding_text=None,
            status=KnowledgeEntryStatus.PUBLISHED,
            visibility=KnowledgeEntryVisibility.RUNTIME,
            version=1,
            compiler_version=KCD_STAGE_K_COMPILER_VERSION,
            embedding_text_version=CANONICAL_EMBEDDING_TEXT_VERSION,
            metadata=metadata,
        )
        entry.assert_publishable()
        entries.append(entry)

    return _final_publication_guard_collapse_exact_duplicates(entries)


def fingerprint_answer_resolution_text(value: str) -> str:
    return " ".join(
        re.sub(r"[^0-9a-zа-яё]+", " ", value.lower().replace("ё", "е")).split()
    )


def _answer_resolution_text_units(value: str) -> tuple[str, ...]:
    compact = _clean_optional_text(value)
    if not compact:
        return ()

    units = re.split(r"(?<=[.!?])\s+|[\n;]+", compact)
    return tuple(
        _clean_optional_text(unit) for unit in units if _clean_optional_text(unit)
    )


@dataclass(frozen=True, slots=True)
class _DeterministicAnswerUnitMergeResult:
    answer: str
    strategy: str
    left_unit_count: int
    right_unit_count: int
    merged_unit_count: int
    overlap_unit_count: int


def _answer_unit_fingerprint(value: str) -> str:
    return fingerprint_answer_resolution_text(value)


def _answer_units_by_fingerprint(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for unit in _answer_resolution_text_units(value):
        fingerprint = _answer_unit_fingerprint(unit)
        if fingerprint and fingerprint not in result:
            result[fingerprint] = unit
    return result


def merge_answer_units_deterministically(
    left: str,
    right: str,
    *,
    allow_disjoint_union: bool = False,
) -> _DeterministicAnswerUnitMergeResult | None:
    """Merge authoritative answer text by atomic-ish answer units.

    This is deterministic-first canonicalization. It does not decide semantic
    paraphrase equivalence; it only handles exact unit equality, subset/superset,
    exact overlap union, and same-intent complementary union when the caller has
    already proven same question-intent.
    """

    left_units = _answer_units_by_fingerprint(left)
    right_units = _answer_units_by_fingerprint(right)
    left_keys = set(left_units)
    right_keys = set(right_units)

    if not left_keys or not right_keys:
        return None

    if left_keys == right_keys:
        return _DeterministicAnswerUnitMergeResult(
            answer=_clean_optional_text(left),
            strategy="exact_answer_units",
            left_unit_count=len(left_keys),
            right_unit_count=len(right_keys),
            merged_unit_count=len(left_keys),
            overlap_unit_count=len(left_keys),
        )

    if left_keys < right_keys:
        return _DeterministicAnswerUnitMergeResult(
            answer=_clean_optional_text(right),
            strategy="answer_unit_subset_superset",
            left_unit_count=len(left_keys),
            right_unit_count=len(right_keys),
            merged_unit_count=len(right_keys),
            overlap_unit_count=len(left_keys & right_keys),
        )

    if right_keys < left_keys:
        return _DeterministicAnswerUnitMergeResult(
            answer=_clean_optional_text(left),
            strategy="answer_unit_subset_superset",
            left_unit_count=len(left_keys),
            right_unit_count=len(right_keys),
            merged_unit_count=len(left_keys),
            overlap_unit_count=len(left_keys & right_keys),
        )

    overlap = left_keys & right_keys
    if not overlap and not allow_disjoint_union:
        return None

    merged_units: list[str] = list(left_units.values())
    for fingerprint, unit in right_units.items():
        if fingerprint not in left_keys:
            merged_units.append(unit)

    strategy = (
        "same_intent_complementary_answer_unit_union"
        if not overlap
        else "answer_unit_overlap_union"
    )
    return _DeterministicAnswerUnitMergeResult(
        answer=_clean_optional_text("\n".join(merged_units)),
        strategy=strategy,
        left_unit_count=len(left_keys),
        right_unit_count=len(right_keys),
        merged_unit_count=len({*left_keys, *right_keys}),
        overlap_unit_count=len(overlap),
    )


def _cleanup_answer_resolution_text(value: str) -> str:
    """Remove deterministic exact/near sentence duplicates from answer text."""

    units = _answer_resolution_text_units(value)
    if not units:
        return _clean_optional_text(value)

    kept: list[str] = []
    fingerprints: list[str] = []

    for unit in units:
        fingerprint = fingerprint_answer_resolution_text(unit)
        if not fingerprint:
            continue

        is_duplicate = False
        for existing in fingerprints:
            if fingerprint == existing:
                is_duplicate = True
                break
            if len(fingerprint) >= 48 and fingerprint in existing:
                is_duplicate = True
                break
            if len(existing) >= 48 and existing in fingerprint:
                is_duplicate = True
                break

        if is_duplicate:
            continue

        fingerprints.append(fingerprint)
        kept.append(unit)

    return _clean_optional_text(" ".join(kept))


def canonical_entries_from_preprocessing_result(
    *,
    project_id: str,
    document_id: str,
    compiler_run_id: str,
    result: KnowledgePreprocessingResult,
    source_chunks: Sequence[SourceChunk],
) -> tuple[CanonicalKnowledgeEntry, ...]:
    return _canonical_entries_from_preprocessing_result(
        project_id=project_id,
        document_id=document_id,
        compiler_run_id=compiler_run_id,
        result=result,
        source_chunks=source_chunks,
    )


def canonical_entries_from_raw_answer_candidates(
    *,
    project_id: str,
    document_id: str,
    compiler_run_id: str,
    mode: KnowledgePreprocessingMode,
    candidates: Sequence[AnswerCandidate],
) -> tuple[CanonicalKnowledgeEntry, ...]:
    return _canonical_entries_from_raw_answer_candidates(
        project_id=project_id,
        document_id=document_id,
        compiler_run_id=compiler_run_id,
        mode=mode,
        candidates=candidates,
    )
