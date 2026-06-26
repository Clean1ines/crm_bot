from src.contexts.llm_runtime.domain.budget.token_budget import (
    artifact_tokens,
    input_tokens,
    max_artifact_tokens,
    request_output_cap_tokens,
    required_window_tokens,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    default_groq_provider_budget_profile_catalog,
    build_groq_free_plan_model_profiles,
)


def _model(model_ref: str):
    for profile in build_groq_free_plan_model_profiles():
        if profile.model_id.value == model_ref:
            return profile
    raise AssertionError(f"missing model profile: {model_ref}")


def _provider():
    return default_groq_provider_budget_profile_catalog().profile_for_provider("groq")


def test_artifact_tokens_rounds_up_from_chars_and_model_multiplier() -> None:
    assert artifact_tokens(1000, _model("qwen/qwen3-32b")) == 304
    assert artifact_tokens(0, _model("qwen/qwen3-32b")) == 0


def test_max_artifact_tokens_uses_model_tpm_prompt_tokens_and_provider_safety_gap() -> (
    None
):
    assert (
        max_artifact_tokens(
            model_profile=_model("qwen/qwen3-32b"),
            prompt_tokens=1953,
            provider_profile=_provider(),
        )
        == 1873
    )


def test_input_tokens_adds_prompt_and_artifact_tokens() -> None:
    assert input_tokens(prompt_tokens=1953, artifact_tokens=304) == 2257


def test_required_window_tokens_adds_input_artifact_and_safety_gap() -> None:
    assert (
        required_window_tokens(
            input_tokens=2257,
            artifact_tokens=304,
            safety_gap_tokens=300,
        )
        == 2861
    )


def test_request_output_cap_tokens_is_only_sent_when_above_provider_default() -> None:
    provider = _provider()

    assert (
        request_output_cap_tokens(
            remaining_window_tokens=6000,
            input_tokens=2257,
            provider_profile=provider,
        )
        == 3443
    )
    assert (
        request_output_cap_tokens(
            remaining_window_tokens=4605,
            input_tokens=2257,
            provider_profile=provider,
        )
        is None
    )
