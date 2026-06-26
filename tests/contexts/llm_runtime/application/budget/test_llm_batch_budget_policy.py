from __future__ import annotations

from decimal import Decimal

from src.contexts.llm_runtime.application.budget.llm_batch_budget_policy import (
    LlmBatchBudgetPolicy,
)
from src.contexts.llm_runtime.domain.budget.prompt_profile import PromptProfile
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    build_groq_free_plan_model_profiles,
    groq_free_provider_budget_profile,
)


def _model(model_ref: str):
    for profile in build_groq_free_plan_model_profiles():
        if profile.model_id.value == model_ref:
            return profile
    raise AssertionError(f"missing model profile: {model_ref}")


def _prompt(model_ref: str, prompt_tokens: int = 1953) -> PromptProfile:
    return PromptProfile(
        prompt_id="faq_claim_observations",
        prompt_version="v1",
        provider_id="groq",
        model_ref=model_ref,
        prompt_tokens=prompt_tokens,
        prompt_source_ref="prompts/faq_surface_claim_observations.ru.txt",
        output_contract_ref="claim_builder_section_extraction",
    )


def test_qwen_batch_budget_uses_model_multiplier_and_adr_split_formula() -> None:
    model = _model("qwen/qwen3-32b")

    decision = LlmBatchBudgetPolicy(
        provider_profile=groq_free_provider_budget_profile(),
        model_profile=model,
        prompt_profile=_prompt(model.model_id.value),
    ).decide(batch_input_char_count=3300)

    assert model.model_char_to_token_multiplier == Decimal("3.3")
    assert decision.prompt_tokens == 1953
    assert decision.batch_input_estimated_tokens == 1000
    assert decision.batch_input_max_tokens == 1873
    assert decision.planned_output_reserve_tokens == 1874
    assert decision.request_input_estimated_tokens == 2953
    assert decision.request_total_estimated_tokens == 4827
    assert decision.request_output_cap_tokens == 2747
    assert decision.batch_input_fits is True


def test_observed_batch_tokens_override_rough_char_estimate() -> None:
    decision = LlmBatchBudgetPolicy(
        provider_profile=groq_free_provider_budget_profile(),
        model_profile=_model("qwen/qwen3-32b"),
        prompt_profile=_prompt("qwen/qwen3-32b"),
    ).decide(
        batch_input_char_count=999_999,
        observed_batch_input_tokens=1200,
    )

    assert decision.batch_input_estimated_tokens == 1200
    assert decision.request_input_estimated_tokens == 3153


def test_large_batch_marks_fit_false_and_omits_explicit_output_cap() -> None:
    decision = LlmBatchBudgetPolicy(
        provider_profile=groq_free_provider_budget_profile(),
        model_profile=_model("qwen/qwen3-32b"),
        prompt_profile=_prompt("qwen/qwen3-32b"),
    ).decide(
        batch_input_char_count=0,
        observed_batch_input_tokens=3600,
    )

    assert decision.batch_input_fits is False
    assert decision.request_output_cap_tokens is None


def test_gpt_oss_batch_budget_uses_its_model_tpm_and_multiplier() -> None:
    model = _model("openai/gpt-oss-120b")

    decision = LlmBatchBudgetPolicy(
        provider_profile=groq_free_provider_budget_profile(),
        model_profile=model,
        prompt_profile=_prompt(model.model_id.value, prompt_tokens=2050),
    ).decide(batch_input_char_count=3700)

    assert model.model_char_to_token_multiplier == Decimal("3.7")
    assert decision.batch_input_estimated_tokens == 1000
    assert decision.batch_input_max_tokens == 2825
    assert decision.planned_output_reserve_tokens == 2825
    assert decision.request_input_estimated_tokens == 3050
    assert decision.request_output_cap_tokens == 4650
