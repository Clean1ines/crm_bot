import pytest

from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)


def test_total_tokens_is_prompt_plus_completion() -> None:
    profile = LlmTaskCapacityProfile(
        profile_id="prompt-a",
        estimated_prompt_tokens=3000,
        estimated_completion_tokens=500,
    )

    assert profile.estimated_total_tokens == 3500
    assert profile.estimated_requests == 1


def test_rejects_empty_profile_id() -> None:
    with pytest.raises(ValueError, match="profile_id must be non-empty"):
        LlmTaskCapacityProfile(
            profile_id=" ",
            estimated_prompt_tokens=1,
            estimated_completion_tokens=0,
        )


def test_rejects_non_positive_prompt_tokens() -> None:
    with pytest.raises(ValueError, match="estimated_prompt_tokens must be > 0"):
        LlmTaskCapacityProfile(
            profile_id="prompt-a",
            estimated_prompt_tokens=0,
            estimated_completion_tokens=0,
        )


def test_rejects_negative_completion_tokens() -> None:
    with pytest.raises(ValueError, match="estimated_completion_tokens must be >= 0"):
        LlmTaskCapacityProfile(
            profile_id="prompt-a",
            estimated_prompt_tokens=1,
            estimated_completion_tokens=-1,
        )


def test_rejects_non_positive_estimated_requests() -> None:
    with pytest.raises(ValueError, match="estimated_requests must be > 0"):
        LlmTaskCapacityProfile(
            profile_id="prompt-a",
            estimated_prompt_tokens=1,
            estimated_completion_tokens=0,
            estimated_requests=0,
        )
