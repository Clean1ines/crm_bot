from __future__ import annotations

from src.contexts.knowledge_workbench.application.sagas.llm_phase_token_budget import (
    LlmPhaseTokenBudgetPolicy,
    model_profile_by_ref,
)
from src.contexts.llm_runtime.domain.budget.llm_phase_operation_profile import (
    LlmPhaseOperationProfile,
)
from src.contexts.llm_runtime.domain.budget.prompt_profile import (
    PromptProfile,
    PromptProfileCatalog,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    GROQ_PROVIDER_ID,
    build_groq_free_plan_model_profiles,
    default_groq_provider_budget_profile_catalog,
)

CLAIM_BUILDER_PHASE = "claim_builder"
CLAIM_BUILDER_SECTION_EXTRACTION_OPERATION = "section_claim_extraction"
CLAIM_BUILDER_PRIMARY_MODEL_REF = "qwen/qwen3-32b"
CLAIM_BUILDER_INPUT_ARTIFACT_KIND = "source_unit"
CLAIM_BUILDER_OUTPUT_ARTIFACT_KIND = "draft_claims"
CLAIM_BUILDER_BATCHING_STRATEGY = "single_source_unit"


def claim_builder_prompt_profile_catalog(
    *,
    prompt_id: str,
    prompt_version: str,
    prompt_tokens: int,
) -> PromptProfileCatalog:
    return PromptProfileCatalog(
        profiles=(
            PromptProfile(
                prompt_id=prompt_id,
                prompt_version=prompt_version,
                provider_id=GROQ_PROVIDER_ID.value,
                model_ref=CLAIM_BUILDER_PRIMARY_MODEL_REF,
                prompt_tokens=prompt_tokens,
                prompt_source_ref=f"prompt:{prompt_id}:{prompt_version}",
                output_contract_ref=f"contract:{prompt_id}:{prompt_version}",
            ),
        ),
    )


def claim_builder_section_extraction_operation_profile(
    *,
    prompt_id: str,
    prompt_version: str,
) -> LlmPhaseOperationProfile:
    return LlmPhaseOperationProfile(
        phase=CLAIM_BUILDER_PHASE,
        operation=CLAIM_BUILDER_SECTION_EXTRACTION_OPERATION,
        provider_id=GROQ_PROVIDER_ID.value,
        primary_model_ref=CLAIM_BUILDER_PRIMARY_MODEL_REF,
        fallback_model_refs=(),
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        input_artifact_kind=CLAIM_BUILDER_INPUT_ARTIFACT_KIND,
        output_artifact_kind=CLAIM_BUILDER_OUTPUT_ARTIFACT_KIND,
        batching_strategy=CLAIM_BUILDER_BATCHING_STRATEGY,
    )


def claim_builder_phase_token_budget_policy(
    *,
    prompt_id: str,
    prompt_version: str,
    prompt_tokens: int,
) -> LlmPhaseTokenBudgetPolicy:
    model_profile = model_profile_by_ref(
        build_groq_free_plan_model_profiles(),
        CLAIM_BUILDER_PRIMARY_MODEL_REF,
    )
    provider_profile = (
        default_groq_provider_budget_profile_catalog().profile_for_provider(
            GROQ_PROVIDER_ID.value,
        )
    )
    prompt_profile = claim_builder_prompt_profile_catalog(
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        prompt_tokens=prompt_tokens,
    ).profile_for_prompt(
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        provider_id=GROQ_PROVIDER_ID.value,
        model_ref=CLAIM_BUILDER_PRIMARY_MODEL_REF,
    )
    operation_profile = claim_builder_section_extraction_operation_profile(
        prompt_id=prompt_id,
        prompt_version=prompt_version,
    )

    return LlmPhaseTokenBudgetPolicy(
        provider_profile=provider_profile,
        model_profile=model_profile,
        prompt_profile=prompt_profile,
        operation_profile=operation_profile,
    )
