from __future__ import annotations

from decimal import Decimal

from src.contexts.llm_runtime.domain.budget.provider_budget_profile import (
    ProviderBudgetProfile,
)
from src.contexts.llm_runtime.domain.budget.token_budget import (
    artifact_tokens,
    max_artifact_tokens,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    GROQ_PROVIDER_ID,
    build_groq_free_plan_model_profiles,
    default_groq_provider_budget_profile_catalog,
)

DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF = "openai/gpt-oss-120b"
DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_DRAFT_VS_DRAFT = "draft_vs_draft"
DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_SINGLE_DRAFT = "single_draft_claim_enrichment"
DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_COMPACTED_VS_COMPACTED = "compacted_vs_compacted"
DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_MIXED = "mixed"
DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_REDUCED_REWRITE = "reduced_rewrite"

DRAFT_CLAIM_COMPACTION_PROMPT_TOKENS_BY_VARIANT: dict[str, int] = {
    DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_DRAFT_VS_DRAFT: 2050,
    DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_SINGLE_DRAFT: 1100,
    DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_COMPACTED_VS_COMPACTED: 2150,
    DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_MIXED: 2150,
    DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_REDUCED_REWRITE: 400,
}


def draft_claim_compaction_model_profile() -> ModelProfile:
    for profile in build_groq_free_plan_model_profiles():
        if profile.model_id.value == DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF:
            return profile
    raise ValueError(
        "draft claim compaction model profile is not configured: "
        f"{DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF}"
    )


def draft_claim_compaction_provider_profile() -> ProviderBudgetProfile:
    return default_groq_provider_budget_profile_catalog().profile_for_provider(
        GROQ_PROVIDER_ID.value,
    )


def draft_claim_compaction_model_tpm() -> int:
    value = draft_claim_compaction_model_profile().rate_limits.tokens_per_minute
    if value is None:
        raise ValueError("draft claim compaction model TPM must be configured")
    return value


def draft_claim_compaction_char_to_token_multiplier() -> Decimal:
    return draft_claim_compaction_model_profile().model_char_to_token_multiplier


def draft_claim_compaction_request_safety_gap_tokens() -> int:
    return draft_claim_compaction_provider_profile().request_safety_gap_tokens


def draft_claim_compaction_prompt_tokens(prompt_variant: str) -> int:
    try:
        return DRAFT_CLAIM_COMPACTION_PROMPT_TOKENS_BY_VARIANT[prompt_variant]
    except KeyError as exc:
        raise ValueError(
            f"unknown draft claim compaction prompt variant: {prompt_variant}"
        ) from exc


def draft_claim_compaction_artifact_tokens(text: str) -> int:
    if not isinstance(text, str):
        raise TypeError("text must be str")
    if not text.strip():
        return 0
    return artifact_tokens(len(text), draft_claim_compaction_model_profile())


def draft_claim_compaction_max_batch_tokens(prompt_variant: str) -> int:
    return max_artifact_tokens(
        model_profile=draft_claim_compaction_model_profile(),
        prompt_tokens=draft_claim_compaction_prompt_tokens(prompt_variant),
        provider_profile=draft_claim_compaction_provider_profile(),
    )
