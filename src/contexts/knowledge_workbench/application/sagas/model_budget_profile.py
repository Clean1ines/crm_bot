from __future__ import annotations

from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    model_budget_profile_for_ref as groq_model_budget_profile_for_ref,
)


def model_budget_profile_for_ref(model_ref: str) -> ModelProfile:
    return groq_model_budget_profile_for_ref(model_ref)
