from __future__ import annotations

from dataclasses import dataclass

from src.domain.project_plane.knowledge_chunks import KnowledgeChunkRole
from src.domain.project_plane.knowledge_semantic_markers import (
    FAQ_ANSWER_MARKERS,
    FAQ_TITLE_MARKERS,
    INSTRUCTION_STEP_MARKERS,
    INSTRUCTION_TITLE_MARKERS,
    INTERNAL_EVAL_TEST_MARKERS,
    NEGATIVE_TEST_MARKERS,
    PRICE_BODY_MARKERS,
    PRICE_TITLE_MARKERS,
    RETRIEVAL_GUIDELINE_MARKERS,
)


@dataclass(frozen=True, slots=True)
class KnowledgeChunkClassificationInput:
    title: str = ""
    header: str = ""
    body: str = ""
    parent_title: str = ""
    questions: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


def classify_knowledge_chunk_role(
    value: KnowledgeChunkClassificationInput,
) -> KnowledgeChunkRole:
    title_text = _normalize(" ".join((value.title, value.header, value.parent_title)))
    body_text = _normalize(value.body)
    combined = _normalize(
        " ".join(
            (
                value.title,
                value.header,
                value.parent_title,
                value.body[:1600],
                " ".join(value.questions),
                " ".join(value.tags),
            )
        )
    )

    if _looks_like_retrieval_guideline(combined):
        return KnowledgeChunkRole.RETRIEVAL_GUIDELINE

    if _looks_like_negative_test(combined):
        return KnowledgeChunkRole.NEGATIVE_TEST

    if _looks_like_internal_eval_test(combined):
        return KnowledgeChunkRole.INTERNAL_EVAL_TEST

    if _looks_like_price_list(title_text, body_text):
        return KnowledgeChunkRole.PRICE_LIST

    if _looks_like_instruction(title_text, body_text):
        return KnowledgeChunkRole.INSTRUCTION

    if _looks_like_faq(title_text, body_text):
        return KnowledgeChunkRole.FAQ

    return KnowledgeChunkRole.ANSWER_KNOWLEDGE


def _normalize(value: str) -> str:
    return " ".join(value.lower().replace("ё", "е").split())


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


def _looks_like_internal_eval_test(value: str) -> bool:
    return _contains_any(value, INTERNAL_EVAL_TEST_MARKERS)


def _looks_like_negative_test(value: str) -> bool:
    return _contains_any(value, NEGATIVE_TEST_MARKERS)


def _looks_like_retrieval_guideline(value: str) -> bool:
    return _contains_any(value, RETRIEVAL_GUIDELINE_MARKERS)


def _looks_like_price_list(title_text: str, body_text: str) -> bool:
    price_title = _contains_any(title_text, PRICE_TITLE_MARKERS)
    price_body = _contains_any(body_text, PRICE_BODY_MARKERS)
    return price_title and price_body


def _looks_like_instruction(title_text: str, body_text: str) -> bool:
    instruction_title = _contains_any(title_text, INSTRUCTION_TITLE_MARKERS)
    step_body = _contains_any(body_text, INSTRUCTION_STEP_MARKERS)
    return instruction_title and step_body


def _looks_like_faq(title_text: str, body_text: str) -> bool:
    faq_title = _contains_any(title_text, FAQ_TITLE_MARKERS)
    answer_marker = _contains_any(body_text, FAQ_ANSWER_MARKERS)
    return faq_title or answer_marker
