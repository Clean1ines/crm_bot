from __future__ import annotations


import uuid
from collections.abc import Sequence
from src.application.services.knowledge_canonical_publication_builder import (
    _CompiledAnswerEntryDraft,
    _answer_topic_key,
    _source_refs_for_compiled_answer_draft,
)
from src.domain.project_plane.knowledge_compilation import (
    AnswerCandidate,
    AnswerCandidateStatus,
    SourceChunk,
    SourceRef,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingMode,
)


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


def _raw_answer_candidate_id(
    *,
    compiler_run_id: str,
    batch_index: int,
    fragment_index: int,
) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{compiler_run_id}:batch:{batch_index}:fragment:{fragment_index}",
        )
    )


def _raw_answer_candidates_from_preprocessing_entries(
    *,
    project_id: str,
    document_id: str,
    compiler_run_id: str,
    batch_id: str,
    batch_index: int,
    entries: Sequence[KnowledgePreprocessingEntry],
    source_chunks: Sequence[SourceChunk],
    mode: KnowledgePreprocessingMode,
) -> tuple[AnswerCandidate, ...]:
    candidates: list[AnswerCandidate] = []

    for fragment_index, entry in enumerate(entries, start=1):
        draft = _preprocessing_entry_to_compiled_draft(
            entry,
            mode=mode,
            index=fragment_index - 1,
        )
        if not draft.answer:
            continue

        candidates.append(
            AnswerCandidate(
                id=_raw_answer_candidate_id(
                    compiler_run_id=compiler_run_id,
                    batch_index=batch_index,
                    fragment_index=fragment_index,
                ),
                document_id=document_id,
                project_id=project_id,
                compiler_run_id=compiler_run_id,
                topic_key=_answer_topic_key(entry, index=fragment_index - 1),
                title=draft.title,
                candidate_answer=draft.answer,
                source_refs=_source_refs_for_compiled_answer_draft(
                    draft=draft,
                    source_chunks=source_chunks,
                ),
                confidence=1.0 if draft.source_excerpts else None,
                status=AnswerCandidateStatus.EXTRACTED,
                metadata={
                    "stage": "stage_k_raw_extraction",
                    "batch_id": batch_id,
                    "batch_index": batch_index,
                    "fragment_index": fragment_index,
                    "canonical_question": entry.canonical_question,
                    "question_variants": list(entry.questions),
                    "synonyms": list(entry.synonyms),
                    "tags": list(entry.tags),
                    "source_chunk_indexes": list(entry.source_chunk_indexes),
                },
            )
        )

    return tuple(candidates)


def _source_excerpts_from_preprocessing_entry(
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
) -> _CompiledAnswerEntryDraft:
    return _CompiledAnswerEntryDraft(
        title=_clean_optional_text(entry.title) or f"Answer entry {index + 1}",
        answer=_clean_optional_text(entry.answer),
        source_excerpts=_source_excerpts_from_preprocessing_entry(entry),
        source_refs=tuple(
            SourceRef(
                source_index=index,
                quote=source_excerpt,
                source_chunk_id=None,
                confidence=1.0,
            )
            for source_excerpt in _source_excerpts_from_preprocessing_entry(entry)
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


__all__ = [
    "_raw_answer_candidate_id",
    "_raw_answer_candidates_from_preprocessing_entries",
]
