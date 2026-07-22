from enum import StrEnum


class KnowledgeQuerySource(StrEnum):
    NONE = "none"
    MODEL_CONTEXTUAL = "model_contextual"
    CANONICAL_CONTINUE_EXPLANATION = "canonical_continue_explanation"


def normalize_knowledge_query_source(value: object) -> KnowledgeQuerySource:
    if isinstance(value, KnowledgeQuerySource):
        return value
    text = str(value or "").strip().lower()
    for source in KnowledgeQuerySource:
        if text == source.value:
            return source
    return KnowledgeQuerySource.NONE
