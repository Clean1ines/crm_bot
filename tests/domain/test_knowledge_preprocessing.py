from __future__ import annotations

import json

import pytest

from src.domain.project_plane.knowledge_preprocessing import (
    ANSWER_RESOLUTION_PROMPT_VERSION,
    MODE_FAQ,
    MODE_PRICE_LIST,
    KnowledgeAnswerResolutionCandidate,
    KnowledgeAnswerResolutionCase,
    KnowledgePreprocessingValidationError,
    normalize_preprocessing_mode,
    parse_answer_resolution_payload,
    parse_preprocessing_payload,
    prompt_version_for_mode,
)


def _valid_entry() -> dict[str, object]:
    return {
        "title": "Refund policy",
        "answer": "Refund requests are reviewed by a manager.",
        "source_excerpt": "Refund requests are reviewed by a manager.",
        "canonical_question": "Can I get a refund?",
        "question_variants": [
            "Can I get a refund?",
            "How do refunds work?",
            "Can you return my payment?",
        ],
    }


def test_preprocessing_prompt_versions_are_current() -> None:
    assert prompt_version_for_mode(MODE_FAQ) == "knowledge_answer_compiler_faq_v1"
    assert (
        prompt_version_for_mode(MODE_PRICE_LIST) == "knowledge_preprocess_price_list_v2"
    )


def test_removed_modes_are_rejected() -> None:
    with pytest.raises(KnowledgePreprocessingValidationError, match="Unsupported"):
        normalize_preprocessing_mode("plain")
    with pytest.raises(KnowledgePreprocessingValidationError, match="Unsupported"):
        normalize_preprocessing_mode("instruction")


def test_faq_legacy_fragments_parser_is_forbidden() -> None:
    with pytest.raises(
        KnowledgePreprocessingValidationError,
        match="Legacy fragments parser is forbidden for mode=faq",
    ):
        parse_preprocessing_payload(
            {"fragments": [_valid_entry()]},
            mode=MODE_FAQ,
            model="test-model",
            prompt_version="faq_surface_compilation_v1",
        )


def test_price_list_fragment_schema_derives_embedding_text() -> None:
    result = parse_preprocessing_payload(
        {"fragments": [_valid_entry()]},
        mode=MODE_PRICE_LIST,
        model="test-model",
        prompt_version="knowledge_preprocess_price_list_v2",
    )

    entry = result.entries[0]

    assert entry.title == "Refund policy"
    assert len(entry.questions) == 3
    assert entry.synonyms == ()
    assert entry.tags == ()
    assert "Can I get a refund?" in entry.embedding_text
    assert "Refund requests are reviewed" in entry.embedding_text


def test_price_list_parser_ignores_llm_authored_embedding_text() -> None:
    fragment = _valid_entry()
    fragment["embedding_text"] = "LLM-authored retrieval text"

    result = parse_preprocessing_payload(
        {"fragments": [fragment]},
        mode=MODE_PRICE_LIST,
        model="test-model",
        prompt_version="knowledge_preprocess_price_list_v2",
    )

    assert "LLM-authored" not in result.entries[0].embedding_text
    assert "Refund policy" in result.entries[0].embedding_text


def test_price_list_still_rejects_broad_noisy_synonyms() -> None:
    entry = _valid_entry()
    entry["question_variants"] = [
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
            {"fragments": [entry]},
            mode=MODE_PRICE_LIST,
            model="test-model",
            prompt_version="knowledge_preprocess_price_list_v2",
        )


def test_price_list_parser_rejects_trailing_text_after_json_object() -> None:
    raw_payload = json.dumps(
        {
            "fragments": [_valid_entry()],
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
            mode=MODE_PRICE_LIST,
            model="test-model",
            prompt_version="knowledge_preprocess_price_list_v2",
        )


def test_answer_resolution_case_payload_is_json_serializable() -> None:
    group = KnowledgeAnswerResolutionCase(
        case_id="manager_handoff",
        candidates=(
            KnowledgeAnswerResolutionCandidate(
                candidate_id="entry-a",
                answer="Ассистент передаёт вопрос менеджеру.",
                source_excerpt="Ассистент передаёт вопрос менеджеру.",
            ),
        ),
    )

    payload = group.to_payload()

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
        mode=MODE_PRICE_LIST,
        model="test-model",
        prompt_version=ANSWER_RESOLUTION_PROMPT_VERSION,
    )

    assert len(result.decisions) == 1
    assert result.decisions[0].case_id == "manager_handoff"
