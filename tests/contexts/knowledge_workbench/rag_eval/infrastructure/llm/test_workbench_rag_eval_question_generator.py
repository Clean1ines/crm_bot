from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_question_generation_errors import (
    WorkbenchRagEvalQuestionGenerationError,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.llm.workbench_rag_eval_question_generator import (
    WorkbenchRagEvalQuestionGenerator,
)


def _raw_questions(count: int = 10) -> str:
    return json.dumps(
        {
            "questions": [
                {
                    "question": f"Как спросить про факт {index}?",
                    "question_kind": "paraphrase",
                }
                for index in range(count)
            ]
        },
        ensure_ascii=False,
    )


def test_question_generator_builds_provider_messages_without_direct_dispatch() -> None:
    generator = WorkbenchRagEvalQuestionGenerator.from_prompt_file()

    messages = generator.build_provider_messages(
        claim="Claim text",
        possible_questions=("Existing?",),
        exclusion_scope="Not X",
        evidence_block="Evidence",
        triples=(),
    )

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    user_payload = json.loads(messages[1]["content"])
    assert user_payload["claim"] == "Claim text"
    assert user_payload["expected_question_count"] == 10


def test_question_generator_parses_exactly_ten_questions_with_route_metadata() -> None:
    generator = WorkbenchRagEvalQuestionGenerator.from_prompt_file()

    result = generator.parse_questions_from_raw_text(
        raw_text=_raw_questions(),
        generation_model="qwen/qwen3-32b",
        generation_account_ref="groq_org_secondary",
        generation_slot_index=1,
    )

    assert len(result) == 10
    assert result[0].generation_model == "qwen/qwen3-32b"
    assert result[0].generation_account_ref == "groq_org_secondary"
    assert result[0].generation_slot_index == 1


def test_question_generator_rejects_non_ten_question_output() -> None:
    generator = WorkbenchRagEvalQuestionGenerator.from_prompt_file()

    with pytest.raises(
        WorkbenchRagEvalQuestionGenerationError,
        match="exactly 10",
    ):
        generator.parse_questions_from_raw_text(
            raw_text=_raw_questions(9),
            generation_model="qwen/qwen3-32b",
            generation_account_ref="groq_org_primary",
            generation_slot_index=0,
        )


def test_question_generator_source_has_no_fallback_or_direct_provider_client() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/rag_eval/infrastructure/llm/"
        "workbench_rag_eval_question_generator.py"
    ).read_text(encoding="utf-8")

    assert "execute_dispatch" not in source
    assert "GroqDispatchExecutor" not in source
    assert "openai/gpt-oss-120b" not in source
    assert "llama-3.1-8b-instant" not in source
    assert "answer_text" not in source
