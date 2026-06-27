from decimal import Decimal

import pytest

from src.contexts.knowledge_workbench.application.sagas.llm_phase_token_budget import (
    LlmPhaseTokenBudgetPolicy,
    model_profile_by_ref,
)
from src.contexts.llm_runtime.domain.budget.llm_phase_operation_profile import (
    LlmPhaseOperationProfile,
)
from src.contexts.llm_runtime.domain.budget.prompt_profile import PromptProfile
from src.contexts.llm_runtime.domain.budget.provider_budget_profile import (
    ProviderBudgetProfile,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    build_groq_free_plan_model_profiles,
)


def _provider_profile() -> ProviderBudgetProfile:
    return ProviderBudgetProfile(
        provider_id="groq",
        provider_default_completion_tokens=2048,
        request_safety_gap_tokens=300,
        output_safety_gap_tokens=300,
    )


def _prompt_profile(
    *,
    prompt_id: str,
    prompt_version: str = "v1",
    model_ref: str,
    prompt_tokens: int,
) -> PromptProfile:
    return PromptProfile(
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        provider_id="groq",
        model_ref=model_ref,
        prompt_tokens=prompt_tokens,
        prompt_source_ref=f"prompt:{prompt_id}:{prompt_version}",
        output_contract_ref=f"contract:{prompt_id}:{prompt_version}",
    )


def _operation_profile(
    *,
    phase: str,
    operation: str,
    model_ref: str,
    prompt_id: str,
    prompt_version: str = "v1",
    input_artifact_kind: str,
    output_artifact_kind: str,
) -> LlmPhaseOperationProfile:
    return LlmPhaseOperationProfile(
        phase=phase,
        operation=operation,
        provider_id="groq",
        primary_model_ref=model_ref,
        fallback_model_refs=(),
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        input_artifact_kind=input_artifact_kind,
        output_artifact_kind=output_artifact_kind,
        batching_strategy="single_artifact",
    )


def _policy(
    *,
    model_ref: str,
    prompt_id: str,
    prompt_tokens: int,
    phase: str = "claim_builder",
    operation: str = "section_claim_extraction",
    input_artifact_kind: str = "source_unit",
    output_artifact_kind: str = "draft_claims",
) -> LlmPhaseTokenBudgetPolicy:
    model_profile = model_profile_by_ref(
        build_groq_free_plan_model_profiles(),
        model_ref,
    )
    return LlmPhaseTokenBudgetPolicy(
        provider_profile=_provider_profile(),
        model_profile=model_profile,
        prompt_profile=_prompt_profile(
            prompt_id=prompt_id,
            model_ref=model_ref,
            prompt_tokens=prompt_tokens,
        ),
        operation_profile=_operation_profile(
            phase=phase,
            operation=operation,
            model_ref=model_ref,
            prompt_id=prompt_id,
            input_artifact_kind=input_artifact_kind,
            output_artifact_kind=output_artifact_kind,
        ),
    )


def test_claim_builder_budget_uses_qwen_model_tpm_prompt_and_provider_gaps() -> None:
    policy = _policy(
        model_ref="qwen/qwen3-32b",
        prompt_id="faq_claim_observations",
        prompt_tokens=1953,
    )

    budget = policy.calculate_for_artifact_chars(3300)
    payload = budget.to_capacity_estimate_payload(
        estimator="claim_builder_phase_budget",
        extra_metadata={"source_unit_ref": "source-unit-1"},
    )

    assert budget.model_tpm_limit == 6000
    assert budget.model_char_to_token_multiplier == Decimal("3.3")
    assert budget.artifact_tokens == 1000
    assert budget.max_artifact_tokens == 1873
    assert budget.artifact_tokens == 1000
    assert budget.input_tokens == 2953
    assert budget.remaining_after_input_tokens == 2747
    assert budget.max_completion_tokens == 2747
    assert budget.max_completion_tokens == 2747
    assert budget.required_window_tokens == 4253

    assert payload["budget_contract_version"] == "v2"
    assert payload["provider"] == "groq"
    assert payload["model_ref"] == "qwen/qwen3-32b"
    assert payload["model_tpm_limit"] == 6000
    assert payload["model_char_to_token_multiplier"] == "3.3"
    assert payload["prompt_id"] == "faq_claim_observations"
    assert payload["prompt_version"] == "v1"
    assert payload["prompt_tokens"] == 1953
    assert payload["request_safety_gap_tokens"] == 300
    assert payload["completion_safety_gap_tokens"] == 300
    assert payload["provider_default_completion_tokens"] == 2048
    assert payload["input_artifact_kind"] == "source_unit"
    assert payload["output_artifact_kind"] == "draft_claims"
    assert payload["artifact_tokens"] == 1000
    assert payload["artifact_tokens"] == 1000
    assert payload["max_artifact_tokens"] == 1873
    assert payload["max_artifact_tokens"] == 1873
    assert payload["artifact_tokens"] == 1000
    assert payload["input_tokens"] == 2953
    assert payload["max_completion_tokens"] == 2747
    assert payload["max_completion_tokens"] == 2747
    assert payload["required_window_tokens"] == 4253
    assert payload["source_unit_ref"] == "source-unit-1"


def test_omits_request_output_cap_when_remaining_does_not_exceed_provider_default() -> (
    None
):
    policy = _policy(
        model_ref="qwen/qwen3-32b",
        prompt_id="faq_claim_observations",
        prompt_tokens=1953,
    )

    budget = policy.calculate_for_artifact_tokens(1873)
    payload = budget.to_capacity_estimate_payload(
        estimator="claim_builder_phase_budget",
    )

    assert budget.input_tokens == 3826
    assert budget.remaining_after_input_tokens == 1874
    assert budget.max_completion_tokens is None
    assert budget.max_completion_tokens is None
    assert "max_completion_tokens" not in payload


def test_compaction_budget_uses_gpt_oss_model_tpm_and_prompt_profile() -> None:
    policy = _policy(
        model_ref="openai/gpt-oss-120b",
        prompt_id="draft_claim_compaction",
        prompt_tokens=2050,
        phase="draft_claim_compaction",
        operation="draft_vs_draft",
        input_artifact_kind="draft_claim_batch",
        output_artifact_kind="compacted_claims",
    )

    budget = policy.calculate_for_artifact_chars(3700)

    assert budget.model_tpm_limit == 8000
    assert budget.model_char_to_token_multiplier == Decimal("3.7")
    assert budget.artifact_tokens == 1000
    assert budget.max_artifact_tokens == 2825
    assert budget.artifact_tokens == 1000
    assert budget.input_tokens == 3050
    assert budget.remaining_after_input_tokens == 4650
    assert budget.max_completion_tokens == 4650
    assert budget.max_completion_tokens == 4650


def test_rejects_prompt_profile_for_different_model() -> None:
    model_profile = model_profile_by_ref(
        build_groq_free_plan_model_profiles(),
        "qwen/qwen3-32b",
    )

    with pytest.raises(ValueError, match="prompt profile must match model profile"):
        LlmPhaseTokenBudgetPolicy(
            provider_profile=_provider_profile(),
            model_profile=model_profile,
            prompt_profile=_prompt_profile(
                prompt_id="faq_claim_observations",
                model_ref="openai/gpt-oss-120b",
                prompt_tokens=1953,
            ),
            operation_profile=_operation_profile(
                phase="claim_builder",
                operation="section_claim_extraction",
                model_ref="qwen/qwen3-32b",
                prompt_id="faq_claim_observations",
                input_artifact_kind="source_unit",
                output_artifact_kind="draft_claims",
            ),
        )


def test_rejects_operation_prompt_mismatch() -> None:
    model_profile = model_profile_by_ref(
        build_groq_free_plan_model_profiles(),
        "qwen/qwen3-32b",
    )

    with pytest.raises(ValueError, match="operation prompt_id"):
        LlmPhaseTokenBudgetPolicy(
            provider_profile=_provider_profile(),
            model_profile=model_profile,
            prompt_profile=_prompt_profile(
                prompt_id="faq_claim_observations",
                model_ref="qwen/qwen3-32b",
                prompt_tokens=1953,
            ),
            operation_profile=_operation_profile(
                phase="claim_builder",
                operation="section_claim_extraction",
                model_ref="qwen/qwen3-32b",
                prompt_id="wrong_prompt",
                input_artifact_kind="source_unit",
                output_artifact_kind="draft_claims",
            ),
        )
