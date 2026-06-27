from __future__ import annotations

from decimal import Decimal

from src.contexts.knowledge_workbench.application.sagas.knowledge_workbench_llm_budget_catalog import (
    CLAIM_BUILDER_PRIMARY_MODEL_REF,
)
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

CLAIM_BUILDER_PROMPT_NAME = "claim_builder_section_extraction"
CLAIM_BUILDER_PROMPT_NODE_ID = "faq_claim_observations"
CLAIM_BUILDER_PROMPT_PATH = (
    "src/contexts/knowledge_workbench/extraction/application/prompts/"
    "faq_surface_claim_observations.ru.txt"
)
CLAIM_BUILDER_PROMPT_TOKEN_COUNT = 1_953
CLAIM_BUILDER_SEGMENTATION_PROFILE_NAME = "claim_builder_primary_model"


def claim_builder_model_profile() -> ModelProfile:
    for profile in build_groq_free_plan_model_profiles():
        if profile.model_id.value == CLAIM_BUILDER_PRIMARY_MODEL_REF:
            return profile
    raise ValueError(
        f"model profile is not configured: {CLAIM_BUILDER_PRIMARY_MODEL_REF}"
    )


def claim_builder_provider_profile() -> ProviderBudgetProfile:
    return default_groq_provider_budget_profile_catalog().profile_for_provider(
        GROQ_PROVIDER_ID.value,
    )


def claim_builder_model_tpm() -> int:
    value = claim_builder_model_profile().rate_limits.tokens_per_minute
    if value is None:
        raise ValueError("claim-builder model TPM must be configured")
    return value


def claim_builder_char_to_token_multiplier() -> Decimal:
    return claim_builder_model_profile().model_char_to_token_multiplier


def claim_builder_request_safety_gap_tokens() -> int:
    return claim_builder_provider_profile().request_safety_gap_tokens


def claim_builder_artifact_tokens(text: str) -> int:
    if not isinstance(text, str):
        raise TypeError("text must be str")
    if not text.strip():
        return 0
    return artifact_tokens(len(text), claim_builder_model_profile())


def claim_builder_max_source_segment_tokens(
    *,
    prompt_tokens: int = CLAIM_BUILDER_PROMPT_TOKEN_COUNT,
) -> int:
    return max_artifact_tokens(
        model_profile=claim_builder_model_profile(),
        prompt_tokens=prompt_tokens,
        provider_profile=claim_builder_provider_profile(),
    )
