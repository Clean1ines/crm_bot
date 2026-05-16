from __future__ import annotations

import json

import pytest

from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    MODE_INSTRUCTION,
    MODE_PRICE_LIST,
    KnowledgePreprocessingValidationError,
    KnowledgeAnswerResolutionOption,
    KnowledgeAnswerResolutionCase,
    ANSWER_RESOLUTION_PROMPT_VERSION,
    parse_preprocessing_payload,
    parse_answer_resolution_payload,
    prompt_version_for_mode,
)


def _valid_entry() -> dict[str, object]:
    return {
        "title": "Refund policy",
        "answer": "Refund requests are reviewed by a manager.",
        "source_excerpt": "Refund requests are reviewed by a manager.",
        "questions": [
            "Can I get a refund?",
            "How do refunds work?",
            "Can you return my payment?",
        ],
        "synonyms": [
            "refund policy",
            "return payment",
            "money back",
            "refund request",
            "payment return",
        ],
        "tags": ["refund", "billing"],
    }


def test_preprocessing_prompt_versions_are_current() -> None:
    assert prompt_version_for_mode(MODE_FAQ) == "knowledge_answer_compiler_faq_v1"
    assert (
        prompt_version_for_mode(MODE_PRICE_LIST) == "knowledge_preprocess_price_list_v2"
    )
    assert (
        prompt_version_for_mode(MODE_INSTRUCTION)
        == "knowledge_preprocess_instruction_v2"
    )


def test_parse_preprocessing_payload_requires_dense_query_surface() -> None:
    entry = _valid_entry()
    entry["questions"] = []

    with pytest.raises(
        KnowledgePreprocessingValidationError,
        match="at least 3 grounded questions",
    ):
        parse_preprocessing_payload(
            {"entries": [entry]},
            mode=MODE_FAQ,
            model="test-model",
            prompt_version="knowledge_preprocess_faq_v2",
        )


def test_parse_preprocessing_payload_requires_grounded_synonyms() -> None:
    entry = _valid_entry()
    entry["synonyms"] = ["refund"]

    with pytest.raises(
        KnowledgePreprocessingValidationError,
        match="at least 5 grounded synonyms",
    ):
        parse_preprocessing_payload(
            {"entries": [entry]},
            mode=MODE_INSTRUCTION,
            model="test-model",
            prompt_version="knowledge_preprocess_instruction_v2",
        )


def test_parse_preprocessing_payload_requires_topical_tags() -> None:
    entry = _valid_entry()
    entry["tags"] = ["refund"]

    with pytest.raises(
        KnowledgePreprocessingValidationError,
        match="at least 2 topical tags",
    ):
        parse_preprocessing_payload(
            {"entries": [entry]},
            mode=MODE_FAQ,
            model="test-model",
            prompt_version="knowledge_preprocess_faq_v2",
        )


def test_parse_preprocessing_payload_accepts_dense_query_surface() -> None:
    result = parse_preprocessing_payload(
        {"entries": [_valid_entry()]},
        mode=MODE_FAQ,
        model="test-model",
        prompt_version="knowledge_preprocess_faq_v2",
    )

    entry = result.entries[0]

    assert entry.title == "Refund policy"
    assert len(entry.questions) == 3
    assert len(entry.synonyms) == 5
    assert len(entry.tags) == 2
    assert "Can I get a refund?" in entry.embedding_text
    assert "Refund requests are reviewed" in entry.embedding_text
    assert "billing" in entry.embedding_text


def test_price_list_still_rejects_broad_noisy_synonyms() -> None:
    entry = _valid_entry()
    entry["synonyms"] = [
        "refund policy",
        "return payment",
        "money back",
        "refund request",
        "скока",
    ]

    with pytest.raises(
        KnowledgePreprocessingValidationError,
        match="broad noisy synonyms",
    ):
        parse_preprocessing_payload(
            {"entries": [entry]},
            mode=MODE_PRICE_LIST,
            model="test-model",
            prompt_version="knowledge_preprocess_price_list_v2",
        )


def test_parse_preprocessing_payload_rejects_trailing_text_after_json_object() -> None:
    raw_payload = json.dumps(
        {
            "entries": [_valid_entry()],
            "metrics": {"source": "unit-test"},
        },
        ensure_ascii=False,
    )
    llm_response = f'{raw_payload}\n\n{{"ignored": true}}'

    with pytest.raises(
        KnowledgePreprocessingValidationError,
        match="Extra data",
    ):
        parse_preprocessing_payload(
            llm_response,
            mode=MODE_FAQ,
            model="test-model",
            prompt_version="knowledge_preprocess_faq_v2",
        )


def test_answer_resolution_case_payload_is_json_serializable() -> None:
    case = KnowledgeAnswerResolutionCase(
        case_id="manager_handoff",
        question_intent="handoff",
        answers=(
            KnowledgeAnswerResolutionOption(
                id="entry-a",
                answer="Ассистент передаёт вопрос менеджеру.",
                source_excerpt="Ассистент передаёт вопрос менеджеру.",
            ),
        ),
    )

    payload = case.to_payload()

    assert json.loads(json.dumps(payload, ensure_ascii=False))["case_id"] == (
        "manager_handoff"
    )


def test_parse_answer_resolution_payload_accepts_merge_decision() -> None:
    result = parse_answer_resolution_payload(
        {
            "decisions": [
                {
                    "case_id": "manager_handoff",
                    "action": "merge",
                    "canonical_answer": (
                        "Передача диалога менеджеру, handoff, запрос на человека, "
                        "ассистент не принимает критические решения."
                    ),
                    "reason": "same answer intent",
                    "confidence": 0.91,
                }
            ],
            "metrics": {"source": "unit-test"},
        },
        mode=MODE_FAQ,
        model="test-model",
    )

    decision = result.decisions[0]

    assert result.prompt_version == ANSWER_RESOLUTION_PROMPT_VERSION
    assert result.metrics["source"] == "unit-test"
    assert decision.is_merge
    assert decision.candidate_ids == ()
    assert "handoff" in decision.canonical_answer
    assert decision.reason == "same answer intent"
    assert decision.confidence == 0.91


def test_parse_answer_resolution_payload_accepts_keep_separate() -> None:
    result = parse_answer_resolution_payload(
        {
            "decisions": [
                {
                    "case_id": "pricing",
                    "action": "keep_separate",
                }
            ]
        },
        mode=MODE_FAQ,
        model="test-model",
    )

    decision = result.decisions[0]

    assert not decision.is_merge
    assert decision.canonical_answer == ""


def test_parse_answer_resolution_payload_requires_canonical_answer_for_merge() -> None:
    with pytest.raises(
        KnowledgePreprocessingValidationError,
        match="canonical_answer",
    ):
        parse_answer_resolution_payload(
            {
                "decisions": [
                    {
                        "case_id": "startup",
                        "action": "merge",
                        "reason": "missing answer",
                    }
                ]
            },
            mode=MODE_FAQ,
            model="test-model",
        )
