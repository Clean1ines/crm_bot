from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.application.sagas.source_ingestion_segmentation_profiles import (
    SourceIngestionSegmentationProfile,
    WorkbenchModelRequestBudgetProfile,
    WorkbenchPromptProfile,
    default_source_ingestion_segmentation_profile,
)


def test_default_profile_describes_current_draft_observation_prompt() -> None:
    profile = default_source_ingestion_segmentation_profile()

    assert profile.prompt.prompt_name == "draft_observation_extraction"
    assert profile.prompt.node_id == "faq_claim_observations"
    assert (
        profile.prompt.prompt_path
        == "src/agent/prompts/faq_surface_claim_observations.ru.txt"
    )
    assert profile.prompt.prompt_token_count > 0
    assert profile.primary_model.profile_name == "primary_model"
    assert profile.primary_model.max_request_input_tokens == 6_000
    assert profile.primary_model.reserved_output_tokens == 1_000
    assert profile.max_source_segment_tokens == 3_000


def test_profile_validation_rejects_impossible_budget() -> None:
    prompt = WorkbenchPromptProfile(
        prompt_name="draft_observation_extraction",
        node_id="faq_claim_observations",
        prompt_path="src/agent/prompts/faq_surface_claim_observations.ru.txt",
        prompt_token_count=5_000,
    )
    model = WorkbenchModelRequestBudgetProfile(
        profile_name="primary_model",
        max_request_input_tokens=6_000,
        reserved_output_tokens=2_000,
    )

    with pytest.raises(ValueError, match="must be < max_request_input_tokens"):
        SourceIngestionSegmentationProfile(prompt=prompt, primary_model=model)


def test_profile_value_objects_reject_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="prompt_name must be non-empty"):
        WorkbenchPromptProfile(
            prompt_name=" ",
            node_id="faq_claim_observations",
            prompt_path="src/agent/prompts/faq_surface_claim_observations.ru.txt",
            prompt_token_count=1,
        )

    with pytest.raises(ValueError, match="node_id must be non-empty"):
        WorkbenchPromptProfile(
            prompt_name="draft_observation_extraction",
            node_id=" ",
            prompt_path="src/agent/prompts/faq_surface_claim_observations.ru.txt",
            prompt_token_count=1,
        )

    with pytest.raises(ValueError, match="profile_name must be non-empty"):
        WorkbenchModelRequestBudgetProfile(
            profile_name=" ",
            max_request_input_tokens=10,
            reserved_output_tokens=1,
        )


def test_no_provider_or_runtime_hardcode_in_profile_catalog() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "source_ingestion_segmentation_profiles.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        "qwen",
        "Qwen",
        "Groq",
        "context_window_tokens",
        "ModelProfile",
        "RateLimitProfile",
        "src.contexts.llm_runtime",
    ]

    for marker in forbidden:
        assert marker not in source
