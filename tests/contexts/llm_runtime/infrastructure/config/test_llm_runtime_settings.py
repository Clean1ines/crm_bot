from __future__ import annotations

import pytest

from src.contexts.llm_runtime.infrastructure.config.llm_runtime_settings import (
    LlmRuntimeSettings,
)


def test_settings_from_env_mapping_reads_legacy_groq_key_names_without_legacy_settings() -> (
    None
):
    settings = LlmRuntimeSettings.from_env_mapping(
        {
            "GROQ_API_KEY": " primary ",
            "GROQ_API_KEY2": "secondary",
            "GROQ_API_KEY3": "",
            "GROQ_API_KEY4": "quaternary",
            "LLM_RUNTIME_GROQ_BASE_URL": "https://example.test/openai/v1",
            "LLM_RUNTIME_GROQ_TIMEOUT_SECONDS": "12.5",
            "GROQ_MAX_COMPLETION_TOKEN_GAP": "250",
        },
    )

    assert settings.groq_api_key == "primary"
    assert settings.groq_api_key2 == "secondary"
    assert settings.groq_api_key3 is None
    assert settings.groq_api_key4 == "quaternary"
    assert settings.groq_base_url == "https://example.test/openai/v1"
    assert settings.groq_timeout_seconds == 12.5
    assert settings.groq_max_completion_token_gap == 250


def test_settings_defaults_base_url_and_timeout() -> None:
    settings = LlmRuntimeSettings.from_env_mapping(
        {
            "GROQ_API_KEY": "primary",
        },
    )

    assert settings.groq_base_url == "https://api.groq.com/openai/v1"
    assert settings.groq_timeout_seconds == 60.0
    assert settings.groq_max_completion_token_gap == 300


def test_settings_to_groq_env_config_maps_keys_to_capacity_slots() -> None:
    config = LlmRuntimeSettings(
        groq_api_key="primary",
        groq_api_key2="secondary",
        groq_api_key3=None,
        groq_api_key4="quaternary",
    ).to_groq_env_config()

    assert [account.account_seed.account_ref for account in config.accounts] == [
        "groq_org_primary",
        "groq_org_secondary",
        "groq_org_quaternary",
    ]
    assert [account.account_seed.account_rank for account in config.accounts] == [
        0,
        1,
        3,
    ]
    assert [account.api_key.value for account in config.accounts] == [
        "primary",
        "secondary",
        "quaternary",
    ]


def test_settings_to_groq_env_config_rejects_missing_all_keys() -> None:
    with pytest.raises(ValueError):
        LlmRuntimeSettings().to_groq_env_config()


def test_settings_validates_base_url_and_timeout() -> None:
    with pytest.raises(ValueError):
        LlmRuntimeSettings(groq_base_url="")

    with pytest.raises(ValueError):
        LlmRuntimeSettings(groq_timeout_seconds=0)

    with pytest.raises(ValueError):
        LlmRuntimeSettings.from_env_mapping(
            {
                "LLM_RUNTIME_GROQ_TIMEOUT_SECONDS": "not-a-float",
            },
        )

    with pytest.raises(ValueError):
        LlmRuntimeSettings.from_env_mapping(
            {
                "LLM_RUNTIME_GROQ_TIMEOUT_SECONDS": "-1",
            },
        )

    with pytest.raises(ValueError):
        LlmRuntimeSettings.from_env_mapping(
            {
                "GROQ_MAX_COMPLETION_TOKEN_GAP": "-1",
            },
        )
