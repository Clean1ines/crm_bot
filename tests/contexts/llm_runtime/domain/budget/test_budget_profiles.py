from __future__ import annotations

import pytest

from src.contexts.llm_runtime.domain.budget.llm_phase_operation_profile import (
    LlmPhaseOperationProfile,
)
from src.contexts.llm_runtime.domain.budget.prompt_profile import (
    PromptProfile,
    PromptProfileCatalog,
)
from src.contexts.llm_runtime.domain.budget.provider_budget_profile import (
    ProviderBudgetProfile,
    ProviderBudgetProfileCatalog,
)


def test_prompt_profile_catalog_is_model_specific() -> None:
    catalog = PromptProfileCatalog(
        profiles=(
            PromptProfile(
                prompt_id="faq_claim_observations",
                prompt_version="v1",
                provider_id="groq",
                model_ref="qwen/qwen3-32b",
                prompt_tokens=1953,
                prompt_source_ref="prompts/faq_surface_claim_observations.ru.txt",
                output_contract_ref="claim_builder_section_extraction",
            ),
            PromptProfile(
                prompt_id="faq_claim_observations",
                prompt_version="v1",
                provider_id="groq",
                model_ref="openai/gpt-oss-120b",
                prompt_tokens=2100,
                prompt_source_ref="prompts/faq_surface_claim_observations.ru.txt",
                output_contract_ref="claim_builder_section_extraction",
            ),
        )
    )

    assert (
        catalog.profile_for_prompt(
            prompt_id="faq_claim_observations",
            prompt_version="v1",
            provider_id="groq",
            model_ref="qwen/qwen3-32b",
        ).prompt_tokens
        == 1953
    )
    assert (
        catalog.profile_for_prompt(
            prompt_id="faq_claim_observations",
            prompt_version="v1",
            provider_id="groq",
            model_ref="openai/gpt-oss-120b",
        ).prompt_tokens
        == 2100
    )


def test_prompt_profile_catalog_rejects_duplicate_keys() -> None:
    profile = PromptProfile(
        prompt_id="draft_claim_compaction",
        prompt_version="v1",
        provider_id="groq",
        model_ref="openai/gpt-oss-120b",
        prompt_tokens=2050,
        prompt_source_ref="prompts/draft_claim_compaction.txt",
        output_contract_ref="draft_claim_compaction",
    )

    with pytest.raises(ValueError, match="unique keys"):
        PromptProfileCatalog(profiles=(profile, profile))


def test_provider_budget_profile_catalog_resolves_provider() -> None:
    catalog = ProviderBudgetProfileCatalog(
        profiles=(
            ProviderBudgetProfile(
                provider_id="groq",
                provider_default_completion_tokens=2048,
                request_safety_gap_tokens=300,
                output_safety_gap_tokens=300,
            ),
        )
    )

    profile = catalog.profile_for_provider("groq")

    assert profile.provider_default_completion_tokens == 2048
    assert profile.request_safety_gap_tokens == 300
    assert profile.output_safety_gap_tokens == 300


def test_llm_phase_operation_profile_keeps_operation_metadata() -> None:
    profile = LlmPhaseOperationProfile(
        phase="claim_builder",
        operation="section_claim_extraction",
        provider_id="groq",
        primary_model_ref="qwen/qwen3-32b",
        fallback_model_refs=("llama-3.3-70b-versatile",),
        prompt_id="faq_claim_observations",
        prompt_version="v1",
        input_artifact_kind="source_unit",
        output_artifact_kind="draft_claim",
        batching_strategy="source_unit_one_to_one",
    )

    assert profile.operation_key == "claim_builder.section_claim_extraction"
