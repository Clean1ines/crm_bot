from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from src.contexts.knowledge_workbench.extraction.application.policies.prompt_fit_policy import (
    PromptEnvelope,
    PromptFitDecisionKind,
    PromptFitPolicy,
    SourceUnitFitInput,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.value_objects.prompt_version import PromptVersion


ROOT = Path(__file__).resolve().parents[6]
EXTRACTION_PROMPT_FIT_POLICY = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "application"
    / "policies"
    / "prompt_fit_policy.py"
)


@dataclass(frozen=True, slots=True)
class _ModelProfileForTest:
    context_window_tokens: int
    max_output_tokens: int


def _model_profile(
    *,
    context_window_tokens: int = 100,
    max_output_tokens: int = 20,
) -> ModelProfile:
    return cast(
        ModelProfile,
        _ModelProfileForTest(
            context_window_tokens=context_window_tokens,
            max_output_tokens=max_output_tokens,
        ),
    )


def _prompt_version() -> PromptVersion:
    return cast(PromptVersion, "v1")


def _input(
    *,
    source_text_token_estimate: int,
    static_prompt_token_estimate: int,
    output_token_budget: int,
    context_window_tokens: int = 100,
    max_output_tokens: int = 20,
) -> SourceUnitFitInput:
    return SourceUnitFitInput(
        source_unit_ref=SourceUnitRef("source-unit-1"),
        source_text_token_estimate=source_text_token_estimate,
        prompt_envelope=PromptEnvelope(
            prompt_id="claim_extraction",
            prompt_version=_prompt_version(),
            static_prompt_token_estimate=static_prompt_token_estimate,
            output_token_budget=output_token_budget,
        ),
        model_profile=_model_profile(
            context_window_tokens=context_window_tokens,
            max_output_tokens=max_output_tokens,
        ),
    )


def test_exact_fit_returns_fits() -> None:
    decision = PromptFitPolicy().decide(
        _input(
            source_text_token_estimate=70,
            static_prompt_token_estimate=10,
            output_token_budget=20,
            context_window_tokens=100,
            max_output_tokens=20,
        )
    )

    assert decision.kind is PromptFitDecisionKind.FITS
    assert decision.input_tokens == 80
    assert decision.output_token_budget == 20
    assert decision.context_window_tokens == 100
    assert decision.max_output_tokens == 20


def test_normal_fit_returns_fits() -> None:
    decision = PromptFitPolicy().decide(
        _input(
            source_text_token_estimate=20,
            static_prompt_token_estimate=10,
            output_token_budget=15,
            context_window_tokens=100,
            max_output_tokens=20,
        )
    )

    assert decision.kind is PromptFitDecisionKind.FITS
    assert decision.input_tokens == 30


def test_input_too_large_returns_input_too_large() -> None:
    decision = PromptFitPolicy().decide(
        _input(
            source_text_token_estimate=80,
            static_prompt_token_estimate=10,
            output_token_budget=15,
            context_window_tokens=100,
            max_output_tokens=20,
        )
    )

    assert decision.kind is PromptFitDecisionKind.INPUT_TOO_LARGE
    assert decision.input_tokens == 90


def test_output_budget_too_large_returns_output_budget_too_large() -> None:
    decision = PromptFitPolicy().decide(
        _input(
            source_text_token_estimate=10,
            static_prompt_token_estimate=10,
            output_token_budget=21,
            context_window_tokens=100,
            max_output_tokens=20,
        )
    )

    assert decision.kind is PromptFitDecisionKind.OUTPUT_BUDGET_TOO_LARGE


def test_negative_estimates_are_rejected() -> None:
    with pytest.raises(ValueError):
        PromptEnvelope(
            prompt_id="claim_extraction",
            prompt_version=_prompt_version(),
            static_prompt_token_estimate=-1,
            output_token_budget=10,
        )

    with pytest.raises(ValueError):
        PromptEnvelope(
            prompt_id="claim_extraction",
            prompt_version=_prompt_version(),
            static_prompt_token_estimate=10,
            output_token_budget=-1,
        )

    with pytest.raises(ValueError):
        _input(
            source_text_token_estimate=-1,
            static_prompt_token_estimate=10,
            output_token_budget=10,
        )


def test_empty_prompt_id_is_rejected() -> None:
    with pytest.raises(ValueError):
        PromptEnvelope(
            prompt_id=" ",
            prompt_version=_prompt_version(),
            static_prompt_token_estimate=10,
            output_token_budget=10,
        )


def test_prompt_fit_policy_does_not_import_provider_or_groq_infrastructure() -> None:
    text = EXTRACTION_PROMPT_FIT_POLICY.read_text(encoding="utf-8")

    forbidden_markers = (
        "provider_adapter",
        "infrastructure.groq",
        "groq",
        "Groq",
        "Qwen",
        "qwen",
    )

    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not offenders
