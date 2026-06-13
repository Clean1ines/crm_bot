from pathlib import Path
from typing import cast

import pytest

from src.contexts.knowledge_workbench.application.sagas.source_ingestion_segmentation_profiles import (
    default_source_ingestion_segmentation_profile,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_token_estimation import (
    RoughWorkbenchTokenEstimator,
    SourceIngestionPromptTokenEstimationService,
    VerifiedPromptTokenEstimate,
    WorkbenchPromptText,
    WorkbenchTokenEstimatorPort,
)


class FakeTokenEstimator:
    def __init__(self, count: int) -> None:
        self.count = count
        self.received_texts: list[str] = []

    def estimate_tokens(self, text: str) -> int:
        self.received_texts.append(text)
        return self.count


def _prompt_text(
    *,
    prompt_name: str = "claim_builder_section_extraction",
    node_id: str = "faq_claim_observations",
    prompt_path: str = "src/contexts/knowledge_workbench/extraction/application/prompts/faq_surface_claim_observations.ru.txt",
    text: str = "NODE: faq_claim_observations\nReturn JSON.",
) -> WorkbenchPromptText:
    return WorkbenchPromptText(
        prompt_name=prompt_name,
        node_id=node_id,
        prompt_path=prompt_path,
        text=text,
    )


def test_rough_estimator_returns_positive_estimate_for_non_empty_text() -> None:
    estimator = RoughWorkbenchTokenEstimator()

    assert estimator.estimate_tokens("hello world") > 0


def test_service_estimates_prompt_tokens() -> None:
    estimator = FakeTokenEstimator(count=123)
    service = SourceIngestionPromptTokenEstimationService(
        token_estimator=estimator,
    )

    result = service.estimate_prompt_tokens(_prompt_text())

    assert result == VerifiedPromptTokenEstimate(
        prompt_name="claim_builder_section_extraction",
        node_id="faq_claim_observations",
        prompt_path="src/contexts/knowledge_workbench/extraction/application/prompts/faq_surface_claim_observations.ru.txt",
        prompt_token_count=123,
    )
    assert estimator.received_texts == ["NODE: faq_claim_observations\nReturn JSON."]


def test_profile_updated_immutably_with_estimated_prompt_tokens() -> None:
    profile = default_source_ingestion_segmentation_profile()
    service = SourceIngestionPromptTokenEstimationService(
        token_estimator=FakeTokenEstimator(count=321),
    )

    updated = service.with_estimated_prompt_tokens(
        profile=profile,
        prompt_text=_prompt_text(),
    )

    assert profile.prompt.prompt_token_count == 2_000
    assert updated.prompt.prompt_token_count == 321
    assert updated.primary_model is profile.primary_model
    assert updated is not profile
    assert updated.prompt is not profile.prompt


@pytest.mark.parametrize(
    ("field_name", "prompt_text"),
    [
        (
            "prompt_name",
            _prompt_text(prompt_name="other_prompt"),
        ),
        (
            "node_id",
            _prompt_text(node_id="other_node"),
        ),
        (
            "prompt_path",
            _prompt_text(prompt_path="src/agent/prompts/other.txt"),
        ),
    ],
)
def test_prompt_metadata_mismatch_is_rejected(
    field_name: str,
    prompt_text: WorkbenchPromptText,
) -> None:
    profile = default_source_ingestion_segmentation_profile()
    service = SourceIngestionPromptTokenEstimationService(
        token_estimator=FakeTokenEstimator(count=100),
    )

    with pytest.raises(ValueError, match=f"{field_name} mismatch"):
        service.with_estimated_prompt_tokens(
            profile=profile,
            prompt_text=prompt_text,
        )


@pytest.mark.parametrize("count", [0, -1])
def test_zero_or_negative_estimator_result_is_rejected(count: int) -> None:
    service = SourceIngestionPromptTokenEstimationService(
        token_estimator=FakeTokenEstimator(count=count),
    )

    with pytest.raises(ValueError, match="estimated prompt token count must be > 0"):
        service.estimate_prompt_tokens(_prompt_text())


def test_prompt_text_and_verified_estimate_validate_input() -> None:
    with pytest.raises(ValueError, match="text must be non-empty"):
        _prompt_text(text=" ")

    with pytest.raises(ValueError, match="prompt_token_count must be > 0"):
        VerifiedPromptTokenEstimate(
            prompt_name="claim_builder_section_extraction",
            node_id="faq_claim_observations",
            prompt_path="src/contexts/knowledge_workbench/extraction/application/prompts/faq_surface_claim_observations.ru.txt",
            prompt_token_count=0,
        )


def test_estimation_service_rejects_estimator_without_estimate_method() -> None:
    with pytest.raises(TypeError, match="token_estimator must expose estimate_tokens"):
        SourceIngestionPromptTokenEstimationService(
            token_estimator=cast(WorkbenchTokenEstimatorPort, object()),
        )


def test_source_ingestion_token_estimation_source_guard() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "source_ingestion_token_estimation.py"
    ).read_text(encoding="utf-8")

    required_markers = [
        "WorkbenchTokenEstimatorPort",
        "RoughWorkbenchTokenEstimator",
        "WorkbenchPromptText",
        "VerifiedPromptTokenEstimate",
        "SourceIngestionPromptTokenEstimationService",
        "with_estimated_prompt_tokens",
        "estimate_prompt_tokens",
        "replace",
    ]
    forbidden_markers = [
        "qwen",
        "Qwen",
        "Groq",
        "context_window_tokens",
        "ModelProfile",
        "RateLimitProfile",
        "src.contexts.llm_runtime",
        "src.contexts.capacity_runtime",
        "src.contexts.execution_runtime",
        "src.contexts.artifact_runtime",
        "tiktoken",
        "transformers",
        "openai",
        "anthropic",
        "fastapi",
        "src.interfaces",
        "src.infrastructure",
        "asyncpg",
        "postgres",
        "Path(",
        "open(",
        "read_text",
    ]

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source
