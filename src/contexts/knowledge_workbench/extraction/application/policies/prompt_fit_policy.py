from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.value_objects.prompt_version import PromptVersion


@dataclass(frozen=True, slots=True)
class PromptEnvelope:
    prompt_id: str
    prompt_version: PromptVersion
    static_prompt_token_estimate: int
    output_token_budget: int

    def __post_init__(self) -> None:
        if not self.prompt_id or not self.prompt_id.strip():
            raise ValueError("prompt_id must be non-empty")
        if self.static_prompt_token_estimate < 0:
            raise ValueError("static_prompt_token_estimate must be >= 0")
        if self.output_token_budget < 0:
            raise ValueError("output_token_budget must be >= 0")


@dataclass(frozen=True, slots=True)
class SourceUnitFitInput:
    source_unit_ref: SourceUnitRef
    source_text_token_estimate: int
    prompt_envelope: PromptEnvelope
    model_profile: ModelProfile

    def __post_init__(self) -> None:
        if self.source_text_token_estimate < 0:
            raise ValueError("source_text_token_estimate must be >= 0")


class PromptFitDecisionKind(StrEnum):
    FITS = "fits"
    INPUT_TOO_LARGE = "input_too_large"
    OUTPUT_BUDGET_TOO_LARGE = "output_budget_too_large"


@dataclass(frozen=True, slots=True)
class PromptFitDecision:
    kind: PromptFitDecisionKind
    input_tokens: int
    output_token_budget: int
    context_window_tokens: int
    max_output_tokens: int


class PromptFitPolicy:
    def decide(self, input: SourceUnitFitInput) -> PromptFitDecision:
        input_tokens = (
            input.prompt_envelope.static_prompt_token_estimate
            + input.source_text_token_estimate
        )
        output_token_budget = input.prompt_envelope.output_token_budget
        context_window_tokens = input.model_profile.context_window_tokens
        max_output_tokens = input.model_profile.max_output_tokens

        if output_token_budget > max_output_tokens:
            decision_kind = PromptFitDecisionKind.OUTPUT_BUDGET_TOO_LARGE
        elif input_tokens + output_token_budget > context_window_tokens:
            decision_kind = PromptFitDecisionKind.INPUT_TOO_LARGE
        else:
            decision_kind = PromptFitDecisionKind.FITS

        return PromptFitDecision(
            kind=decision_kind,
            input_tokens=input_tokens,
            output_token_budget=output_token_budget,
            context_window_tokens=context_window_tokens,
            max_output_tokens=max_output_tokens,
        )
