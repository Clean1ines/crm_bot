from __future__ import annotations

from collections.abc import Iterable

from src.domain.project_plane.knowledge_compilation import (
    CanonicalKnowledgeEntry,
    EmbeddingText,
)

CANONICAL_EMBEDDING_TEXT_VERSION = "entry_embedding_text_v2"


def build_canonical_entry_embedding_text(
    entry: CanonicalKnowledgeEntry,
) -> EmbeddingText:
    """Build the only production embedding text for a canonical entry.

    The builder is intentionally derived from authoritative entry.answer plus
    positive query enrichment. It does not consume entry.embedding_text, because
    raw LLM/preprocessing embedding text is not authoritative production content.
    """

    sections: list[str] = []

    _append_plain(sections, entry.title)
    _append_labeled(sections, "Ответ:", entry.answer)

    enrichment = entry.enrichment
    _append_values(sections, "Возможные вопросы пользователей:", enrichment.questions)
    _append_values(sections, "Перефразы:", enrichment.paraphrases)
    _append_values(sections, "Синонимы и близкие выражения:", enrichment.synonyms)
    _append_values(
        sections,
        "Разговорные/ошибочные формулировки:",
        enrichment.typo_queries + enrichment.colloquial_queries,
    )
    _append_values(sections, "Теги:", enrichment.tags)

    text = "\n\n".join(sections)
    return EmbeddingText(
        value=text or entry.answer,
        version=CANONICAL_EMBEDDING_TEXT_VERSION,
    )


def build_retrieval_surface_search_text(entry: CanonicalKnowledgeEntry) -> str:
    """Build lexical search text for the published retrieval surface.

    retrieval_guards are intentionally excluded: negative hints must not become
    positive searchable text.
    """

    embedding_text = build_canonical_entry_embedding_text(entry).value
    return _join_unique_non_blank((entry.title, entry.answer, embedding_text))


def _append_plain(sections: list[str], value: str) -> None:
    text = _clean_text(value)
    if text:
        sections.append(text)


def _append_labeled(sections: list[str], label: str, value: str) -> None:
    text = _clean_text(value)
    if text:
        sections.append(f"{label}\n{text}")


def _append_values(
    sections: list[str],
    label: str,
    values: Iterable[str],
) -> None:
    cleaned = tuple(_clean_text(value) for value in values)
    filtered = tuple(value for value in cleaned if value)
    if filtered:
        sections.append(f"{label}\n" + "\n".join(filtered))


def _join_unique_non_blank(values: Iterable[str]) -> str:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        text = _clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)

    return "\n".join(result)


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").strip().split())
