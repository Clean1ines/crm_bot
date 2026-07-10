from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_question_generation_errors import (
    WorkbenchRagEvalQuestionGenerationError,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.llm.workbench_rag_eval_question_generator import (
    WORKBENCH_RAG_EVAL_QUESTION_CONTRACT_VERSION,
    WORKBENCH_RAG_EVAL_QUESTION_PROMPT_VERSION,
    WorkbenchRagEvalQuestionGenerator,
)


def _valid_payload() -> dict[str, object]:
    kinds = (
        "direct_paraphrase",
        "direct_paraphrase",
        "lexical_variant",
        "lexical_variant",
        "naive_user",
        "naive_user",
        "entity_first",
        "action_first",
        "constraint_first",
        "domain_specific",
    )
    return {
        "contract_version": WORKBENCH_RAG_EVAL_QUESTION_CONTRACT_VERSION,
        "questions": [
            {
                "question": f"Уникальный пользовательский вопрос номер {index}?",
                "question_kind": kind,
                "promotion_eligible": index % 2 == 0,
                "ambiguity_risk": "low" if index % 2 == 0 else "medium",
                "rationale": f"Новый retrieval signal {index}",
            }
            for index, kind in enumerate(kinds)
        ],
    }


def _raw(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _parse(payload: dict[str, object], *, existing: tuple[str, ...] = ()):
    return WorkbenchRagEvalQuestionGenerator.from_prompt_file().parse_questions_from_raw_text(
        raw_text=_raw(payload),
        generation_model="qwen/qwen3-32b",
        generation_account_ref="groq_org_secondary",
        generation_slot_index=1,
        existing_possible_questions=existing,
    )


def test_question_generator_builds_v2_provider_messages() -> None:
    generator = WorkbenchRagEvalQuestionGenerator.from_prompt_file()

    messages = generator.build_provider_messages(
        claim="Claim text",
        possible_questions=("Existing?",),
        exclusion_scope="Not X",
        evidence_block="Evidence",
        triples=(),
    )

    assert generator.prompt_version == WORKBENCH_RAG_EVAL_QUESTION_PROMPT_VERSION
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"

    user_payload = json.loads(messages[1]["content"])
    assert user_payload["claim"] == "Claim text"
    assert user_payload["required_question_count"] == 10
    assert (
        user_payload["contract_version"] == WORKBENCH_RAG_EVAL_QUESTION_CONTRACT_VERSION
    )
    assert user_payload["required_distribution"] == {
        "direct_paraphrase": 2,
        "lexical_variant": 2,
        "naive_user": 2,
        "entity_first": 1,
        "action_first": 1,
        "constraint_first": 1,
        "domain_specific": 1,
    }


def test_question_generator_parses_strict_v2_distribution() -> None:
    result = _parse(_valid_payload())

    assert len(result) == 10
    assert result[0].generation_model == "qwen/qwen3-32b"
    assert result[0].generation_account_ref == "groq_org_secondary"
    assert result[0].generation_slot_index == 1
    assert result[0].contract_version == WORKBENCH_RAG_EVAL_QUESTION_CONTRACT_VERSION
    assert result[0].promotion_eligible is True
    assert result[0].ambiguity_risk.value == "low"
    assert result[0].generation_rationale


def test_question_generator_rejects_wrong_contract_version() -> None:
    payload = _valid_payload()
    payload["contract_version"] = "workbench_rag_eval_questions.v1"

    with pytest.raises(
        WorkbenchRagEvalQuestionGenerationError,
        match="INVALID_CONTRACT_VERSION",
    ):
        _parse(payload)


def test_question_generator_rejects_nine_questions() -> None:
    payload = _valid_payload()
    payload["questions"] = payload["questions"][:-1]

    with pytest.raises(
        WorkbenchRagEvalQuestionGenerationError,
        match="INVALID_QUESTION_COUNT",
    ):
        _parse(payload)


def test_question_generator_rejects_old_all_paraphrase_contract() -> None:
    payload = _valid_payload()
    for question in payload["questions"]:
        question["question_kind"] = "paraphrase"

    with pytest.raises(
        WorkbenchRagEvalQuestionGenerationError,
        match="not allowed in V2",
    ):
        _parse(payload)


def test_question_generator_rejects_wrong_distribution() -> None:
    payload = _valid_payload()
    payload["questions"][6]["question_kind"] = "domain_specific"

    with pytest.raises(
        WorkbenchRagEvalQuestionGenerationError,
        match="INVALID_KIND_DISTRIBUTION",
    ):
        _parse(payload)


def test_question_generator_rejects_unknown_kind() -> None:
    payload = _valid_payload()
    payload["questions"][0]["question_kind"] = "invented_kind"

    with pytest.raises(
        WorkbenchRagEvalQuestionGenerationError,
        match="unknown question_kind",
    ):
        _parse(payload)


@pytest.mark.parametrize(
    "field,value",
    (
        ("question", " "),
        ("rationale", ""),
        ("ambiguity_risk", ""),
    ),
)
def test_question_generator_rejects_empty_fields(
    field: str,
    value: object,
) -> None:
    payload = _valid_payload()
    payload["questions"][0][field] = value

    with pytest.raises(
        WorkbenchRagEvalQuestionGenerationError,
        match="INVALID_ITEM",
    ):
        _parse(payload)


def test_question_generator_rejects_exact_duplicate() -> None:
    payload = _valid_payload()
    payload["questions"][1]["question"] = payload["questions"][0]["question"]

    with pytest.raises(
        WorkbenchRagEvalQuestionGenerationError,
        match="DUPLICATE_GENERATED_QUESTION",
    ):
        _parse(payload)


def test_question_generator_rejects_normalized_duplicate() -> None:
    payload = _valid_payload()
    payload["questions"][0]["question"] = "Как оформить заказ?"
    payload["questions"][1]["question"] = "  КАК   ОФОРМИТЬ ЗАКАЗ!!!  "

    with pytest.raises(
        WorkbenchRagEvalQuestionGenerationError,
        match="DUPLICATE_GENERATED_QUESTION",
    ):
        _parse(payload)


def test_question_generator_rejects_existing_possible_question_duplicate() -> None:
    payload = _valid_payload()
    payload["questions"][0]["question"] = "Как оформить заказ?"

    with pytest.raises(
        WorkbenchRagEvalQuestionGenerationError,
        match="DUPLICATE_EXISTING_QUESTION",
    ):
        _parse(
            payload,
            existing=("  КАК оформить заказ!!! ",),
        )


@pytest.mark.parametrize("risk", ("medium", "high"))
def test_question_generator_rejects_promotion_for_non_low_risk(risk: str) -> None:
    payload = _valid_payload()
    payload["questions"][0]["promotion_eligible"] = True
    payload["questions"][0]["ambiguity_risk"] = risk

    with pytest.raises(
        WorkbenchRagEvalQuestionGenerationError,
        match="INVALID_PROMOTION_ELIGIBILITY",
    ):
        _parse(payload)


def test_question_generator_source_has_no_direct_dispatch() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/rag_eval/infrastructure/llm/"
        "workbench_rag_eval_question_generator.py"
    ).read_text(encoding="utf-8")

    assert "execute_dispatch" not in source
    assert "GroqDispatchExecutor" not in source
    assert "llama-3.1-8b-instant" not in source
    assert "llama-3.3-70b-versatile" not in source
    assert "llama-4-scout" not in source
