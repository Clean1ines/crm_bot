from __future__ import annotations

import pytest

from src.contexts.llm_runtime.application.capacity.llm_capacity_estimate_payload import (
    build_llm_capacity_estimate_payload,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    model_budget_profile_for_ref,
)


def test_build_llm_capacity_estimate_payload_uses_model_profile_tpm_limit() -> None:
    payload = build_llm_capacity_estimate_payload(
        model_profile=model_budget_profile_for_ref("qwen/qwen3-32b"),
        phase="question_generation",
        operation="prepare_workbench_rag_eval_question_generation",
        estimator="provider_message_char_div_4",
        prompt_tokens=100,
        artifact_tokens=0,
        input_tokens=100,
        planned_output_tokens=1200,
        safety_gap_tokens=25,
    )

    assert payload == {
        "budget_contract_version": "v3",
        "provider": "groq",
        "model_ref": "qwen/qwen3-32b",
        "model_tpm_limit": 6_000,
        "phase": "question_generation",
        "operation": "prepare_workbench_rag_eval_question_generation",
        "estimator": "provider_message_char_div_4",
        "prompt_tokens": 100,
        "artifact_tokens": 0,
        "input_tokens": 100,
        "planned_output_tokens": 1200,
        "safety_gap_tokens": 25,
        "required_window_tokens": 1325,
    }


def test_build_llm_capacity_estimate_payload_keeps_estimator_metadata_optional() -> (
    None
):
    payload = build_llm_capacity_estimate_payload(
        model_profile=model_budget_profile_for_ref("qwen/qwen3-32b"),
        phase="claim_builder_section_extraction",
        operation="section_extraction",
        estimator="measured_prompt_source_char_div_3_3",
        prompt_tokens=10,
        artifact_tokens=20,
        input_tokens=30,
        planned_output_tokens=20,
        safety_gap_tokens=100,
        metadata={"model_char_to_token_multiplier": "3.7"},
    )

    assert payload["model_char_to_token_multiplier"] == "3.7"


def test_build_llm_capacity_estimate_payload_rejects_reserved_metadata_keys() -> None:
    with pytest.raises(
        ValueError,
        match="metadata must not override reserved LLM capacity estimate keys",
    ):
        build_llm_capacity_estimate_payload(
            model_profile=model_budget_profile_for_ref("qwen/qwen3-32b"),
            phase="question_generation",
            operation="prepare_workbench_rag_eval_question_generation",
            estimator="provider_message_char_div_4",
            prompt_tokens=100,
            artifact_tokens=0,
            input_tokens=100,
            planned_output_tokens=1200,
            safety_gap_tokens=0,
            metadata={"model_tpm_limit": 1},
        )
