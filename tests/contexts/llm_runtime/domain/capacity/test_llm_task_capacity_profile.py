import pytest

from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)


def test_required_window_tokens_is_input_plus_artifact() -> None:
    profile = LlmTaskCapacityProfile(
        profile_id="prompt-a",
        input_tokens=3000,
        artifact_tokens=500,
    )

    assert profile.input_tokens == 3000
    assert profile.artifact_tokens == 500
    assert profile.required_window_tokens == 3500
    assert profile.request_count == 1


def test_rejects_empty_profile_id() -> None:
    with pytest.raises(ValueError, match="profile_id must be non-empty"):
        LlmTaskCapacityProfile(
            profile_id=" ",
            input_tokens=1,
            artifact_tokens=0,
        )


def test_rejects_non_positive_input_tokens() -> None:
    with pytest.raises(ValueError, match="input_tokens must be > 0"):
        LlmTaskCapacityProfile(
            profile_id="prompt-a",
            input_tokens=0,
            artifact_tokens=0,
        )


def test_rejects_negative_artifact_tokens() -> None:
    with pytest.raises(ValueError, match="artifact_tokens must be >= 0"):
        LlmTaskCapacityProfile(
            profile_id="prompt-a",
            input_tokens=1,
            artifact_tokens=-1,
        )


def test_rejects_non_positive_request_count() -> None:
    with pytest.raises(ValueError, match="request_count must be > 0"):
        LlmTaskCapacityProfile(
            profile_id="prompt-a",
            input_tokens=1,
            artifact_tokens=0,
            request_count=0,
        )
