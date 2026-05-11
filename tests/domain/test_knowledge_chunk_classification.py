from __future__ import annotations

from src.domain.project_plane.knowledge_chunk_classification import (
    KnowledgeChunkClassificationInput,
    classify_knowledge_chunk_role,
)
from src.domain.project_plane.knowledge_chunks import KnowledgeChunkRole


def test_classifies_generic_answer_knowledge_without_business_vocabulary() -> None:
    role = classify_knowledge_chunk_role(
        KnowledgeChunkClassificationInput(
            title="Product overview",
            body="The platform helps teams process customer requests and preserve context.",
        )
    )

    assert role == KnowledgeChunkRole.ANSWER_KNOWLEDGE


def test_classifies_faq_by_faq_title() -> None:
    role = classify_knowledge_chunk_role(
        KnowledgeChunkClassificationInput(
            title="FAQ",
            body="Can users upload documents? Yes, supported documents can be uploaded.",
        )
    )

    assert role == KnowledgeChunkRole.FAQ


def test_classifies_faq_by_answer_marker() -> None:
    role = classify_knowledge_chunk_role(
        KnowledgeChunkClassificationInput(
            title="Supported files",
            body="Question: Can I upload PDF? Answer: Yes.",
        )
    )

    assert role == KnowledgeChunkRole.FAQ


def test_classifies_price_list_only_when_title_and_body_indicate_price() -> None:
    role = classify_knowledge_chunk_role(
        KnowledgeChunkClassificationInput(
            title="Pricing",
            body="Starter plan: €19 per month. Pro plan: €49 per month.",
        )
    )

    assert role == KnowledgeChunkRole.PRICE_LIST


def test_does_not_classify_generic_cost_sentence_as_price_list() -> None:
    role = classify_knowledge_chunk_role(
        KnowledgeChunkClassificationInput(
            title="Implementation notes",
            body="The final cost depends on project scope and should be discussed.",
        )
    )

    assert role == KnowledgeChunkRole.ANSWER_KNOWLEDGE


def test_classifies_instruction_only_when_title_and_body_indicate_steps() -> None:
    role = classify_knowledge_chunk_role(
        KnowledgeChunkClassificationInput(
            title="Setup guide",
            body="Step 1: create a project. Step 2: upload documents.",
        )
    )

    assert role == KnowledgeChunkRole.INSTRUCTION


def test_does_not_classify_plain_business_rules_as_instruction() -> None:
    role = classify_knowledge_chunk_role(
        KnowledgeChunkClassificationInput(
            title="Business rules",
            body="The system should preserve context and transfer risky requests to support.",
        )
    )

    assert role == KnowledgeChunkRole.ANSWER_KNOWLEDGE


def test_classifies_internal_eval_test() -> None:
    role = classify_knowledge_chunk_role(
        KnowledgeChunkClassificationInput(
            title="Quality checks",
            body="Test questions. Expected answer: the user can upload documents.",
        )
    )

    assert role == KnowledgeChunkRole.INTERNAL_EVAL_TEST


def test_classifies_negative_test() -> None:
    role = classify_knowledge_chunk_role(
        KnowledgeChunkClassificationInput(
            title="Negative tests",
            body="The assistant must not answer unsupported questions outside knowledge base.",
        )
    )

    assert role == KnowledgeChunkRole.NEGATIVE_TEST


def test_classifies_retrieval_guideline() -> None:
    role = classify_knowledge_chunk_role(
        KnowledgeChunkClassificationInput(
            title="RAG rule",
            body="Retrieval guideline: separate topics and do not mix unrelated facts.",
        )
    )

    assert role == KnowledgeChunkRole.RETRIEVAL_GUIDELINE


def test_classifier_source_does_not_contain_document_specific_section_numbers() -> None:
    from pathlib import Path

    source = Path(
        "src/domain/project_plane/knowledge_chunk_classification.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        "section_",
        "section 30",
        "раздел 30",
        "передача менеджеру",
        "назначение продукта",
        "мультитенант",
    )

    for marker in forbidden:
        assert marker not in source.lower()
