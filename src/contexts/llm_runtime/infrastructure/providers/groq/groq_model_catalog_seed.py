from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.contexts.llm_runtime.application.policies.request_output_cap_policy import (
    ProviderOutputCapProfile,
)
from src.contexts.llm_runtime.domain.budget.provider_budget_profile import (
    ProviderBudgetProfile,
    ProviderBudgetProfileCatalog,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.entities.provider_account import ProviderAccount
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.model_lifecycle import ModelLifecycle
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import (
    ProviderAccountRef,
)
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId
from src.contexts.llm_runtime.domain.value_objects.rate_limit_profile import (
    RateLimitProfile,
)
from src.contexts.llm_runtime.domain.value_objects.reasoning_effort import (
    ReasoningEffort,
)
from src.contexts.llm_runtime.domain.value_objects.reasoning_profile import (
    ReasoningProfile,
)
from src.contexts.llm_runtime.domain.value_objects.token_price import TokenPrice


GROQ_PROVIDER_ID = ProviderId("groq")
GROQ_FREE_PROVIDER_DEFAULT_COMPLETION_TOKENS = 2048
GROQ_FREE_REQUEST_SAFETY_GAP_TOKENS = 300
GROQ_FREE_OUTPUT_SAFETY_GAP_TOKENS = 300


def groq_free_combined_tpm_output_cap_profile() -> ProviderOutputCapProfile:
    return ProviderOutputCapProfile(
        provider_default_completion_tokens=(
            GROQ_FREE_PROVIDER_DEFAULT_COMPLETION_TOKENS
        ),
        completion_safety_gap_tokens=GROQ_FREE_OUTPUT_SAFETY_GAP_TOKENS,
    )


def groq_free_provider_budget_profile() -> ProviderBudgetProfile:
    return ProviderBudgetProfile(
        provider_id=GROQ_PROVIDER_ID.value,
        provider_default_completion_tokens=(
            GROQ_FREE_PROVIDER_DEFAULT_COMPLETION_TOKENS
        ),
        request_safety_gap_tokens=GROQ_FREE_REQUEST_SAFETY_GAP_TOKENS,
        output_safety_gap_tokens=GROQ_FREE_OUTPUT_SAFETY_GAP_TOKENS,
    )


def default_groq_provider_budget_profile_catalog() -> ProviderBudgetProfileCatalog:
    return ProviderBudgetProfileCatalog(
        profiles=(groq_free_provider_budget_profile(),),
    )


@dataclass(frozen=True, slots=True)
class GroqAccountSeed:
    account_ref: str
    account_rank: int

    def __post_init__(self) -> None:
        if not self.account_ref or not self.account_ref.strip():
            raise ValueError("GroqAccountSeed.account_ref must be non-empty")
        if self.account_rank < 0:
            raise ValueError("GroqAccountSeed.account_rank must be >= 0")


def build_groq_free_plan_model_profiles() -> tuple[ModelProfile, ...]:
    return (
        ModelProfile(
            provider_id=GROQ_PROVIDER_ID,
            model_id=ModelId("qwen/qwen3-32b"),
            lifecycle=ModelLifecycle.PREVIEW,
            context_window_tokens=131_072,
            max_output_tokens=40_960,
            model_rank=0,
            rate_limits=RateLimitProfile(
                requests_per_minute=60,
                requests_per_day=1_000,
                tokens_per_minute=6_000,
                tokens_per_day=500_000,
            ),
            token_price=TokenPrice(
                input_per_million=Decimal("0.29"),
                output_per_million=Decimal("0.59"),
            ),
            reasoning_profile=ReasoningProfile(
                supported_efforts=(
                    ReasoningEffort.NONE,
                    ReasoningEffort.DEFAULT,
                ),
                default_effort=ReasoningEffort.NONE,
            ),
            supports_json_object=True,
            supports_json_schema=False,
            model_char_to_token_multiplier=Decimal("3.3"),
        ),
        ModelProfile(
            provider_id=GROQ_PROVIDER_ID,
            model_id=ModelId("llama-3.1-8b-instant"),
            lifecycle=ModelLifecycle.PRODUCTION,
            context_window_tokens=131_072,
            max_output_tokens=131_072,
            model_rank=2,
            rate_limits=RateLimitProfile(
                requests_per_minute=30,
                requests_per_day=14_400,
                tokens_per_minute=6_000,
                tokens_per_day=500_000,
            ),
            token_price=TokenPrice(
                input_per_million=Decimal("0.05"),
                output_per_million=Decimal("0.08"),
            ),
            reasoning_profile=ReasoningProfile.unsupported(),
            supports_json_object=True,
            supports_json_schema=False,
            model_char_to_token_multiplier=Decimal("3.7"),
        ),
        ModelProfile(
            provider_id=GROQ_PROVIDER_ID,
            model_id=ModelId("llama-3.3-70b-versatile"),
            lifecycle=ModelLifecycle.PRODUCTION,
            context_window_tokens=131_072,
            max_output_tokens=32_768,
            model_rank=3,
            rate_limits=RateLimitProfile(
                requests_per_minute=30,
                requests_per_day=1_000,
                tokens_per_minute=12_000,
                tokens_per_day=100_000,
            ),
            token_price=TokenPrice(
                input_per_million=Decimal("0.59"),
                output_per_million=Decimal("0.79"),
            ),
            reasoning_profile=ReasoningProfile.unsupported(),
            supports_json_object=True,
            supports_json_schema=False,
            model_char_to_token_multiplier=Decimal("3.7"),
        ),
        ModelProfile(
            provider_id=GROQ_PROVIDER_ID,
            model_id=ModelId("meta-llama/llama-4-scout-17b-16e-instruct"),
            lifecycle=ModelLifecycle.PRODUCTION,
            context_window_tokens=131_072,
            max_output_tokens=32_768,
            model_rank=4,
            rate_limits=RateLimitProfile(
                requests_per_minute=30,
                requests_per_day=1_000,
                tokens_per_minute=30_000,
                tokens_per_day=500_000,
            ),
            token_price=TokenPrice(
                input_per_million=Decimal("0.11"),
                output_per_million=Decimal("0.34"),
            ),
            reasoning_profile=ReasoningProfile.unsupported(),
            supports_json_object=True,
            supports_json_schema=False,
            model_char_to_token_multiplier=Decimal("3.7"),
        ),
        ModelProfile(
            provider_id=GROQ_PROVIDER_ID,
            model_id=ModelId("openai/gpt-oss-120b"),
            lifecycle=ModelLifecycle.PRODUCTION,
            context_window_tokens=131_072,
            max_output_tokens=65_536,
            model_rank=5,
            rate_limits=RateLimitProfile(
                requests_per_minute=30,
                requests_per_day=1_000,
                tokens_per_minute=8_000,
                tokens_per_day=200_000,
            ),
            token_price=TokenPrice(
                input_per_million=Decimal("0.15"),
                output_per_million=Decimal("0.60"),
            ),
            reasoning_profile=ReasoningProfile(
                supported_efforts=(
                    ReasoningEffort.LOW,
                    ReasoningEffort.MEDIUM,
                    ReasoningEffort.HIGH,
                ),
                default_effort=ReasoningEffort.MEDIUM,
            ),
            supports_json_object=True,
            supports_json_schema=False,
            model_char_to_token_multiplier=Decimal("3.7"),
        ),
    )


def build_groq_provider_accounts(
    account_seeds: tuple[GroqAccountSeed, ...],
) -> tuple[ProviderAccount, ...]:
    return tuple(
        ProviderAccount(
            provider_id=GROQ_PROVIDER_ID,
            account_ref=ProviderAccountRef(seed.account_ref),
            account_rank=seed.account_rank,
        )
        for seed in account_seeds
    )
