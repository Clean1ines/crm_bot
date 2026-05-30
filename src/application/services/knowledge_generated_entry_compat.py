from __future__ import annotations


from src.application.services.knowledge_generated_entry_repair import answer_digest
from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingEntry


def _regenerate_entry_from_source_excerpt(
    entry: KnowledgePreprocessingEntry, source_excerpt: str
) -> KnowledgePreprocessingEntry:
    sanitized_source = "\n".join(
        line
        for line in source_excerpt.splitlines()
        if not line.lstrip().startswith("#")
    ).strip()
    rebuilt_answer = answer_digest(
        sanitized_source or source_excerpt,
        max_chars=KCD_STAGE_K_MERGED_ANSWER_MAX_CHARS,
    )
    rebuilt = KnowledgePreprocessingEntry(
        title=entry.title,
        answer=rebuilt_answer,
        source_excerpt=source_excerpt or entry.source_excerpt,
        questions=entry.questions,
        synonyms=entry.synonyms,
        tags=entry.tags,
        embedding_text=entry.embedding_text,
        canonical_question=entry.canonical_question,
        source_chunk_indexes=entry.source_chunk_indexes,
    )
    return rebuilt


KCD_STAGE_K_MERGED_ANSWER_MAX_CHARS = 3600


__all__ = [
    "_regenerate_entry_from_source_excerpt",
    "answer_digest",
]
