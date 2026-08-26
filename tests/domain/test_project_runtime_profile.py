from src.domain.runtime.project_runtime_profile import ProjectRuntimeProfile


def test_project_runtime_profile_extracts_limits_and_settings():
    profile = ProjectRuntimeProfile.from_configuration(
        {
            "settings": {
                "default_language": "ru",
                "target_language": "de",
                "default_timezone": "Europe/Moscow",
                "tone_of_voice": "warm",
                "system_prompt_override": "Уточняй город клиента.",
            },
            "limit_profile": {
                "requests_per_minute": 25,
                "max_concurrent_threads": 3,
                "fallback_model": "llama-3.1-8b-instant",
            },
        }
    )

    assert profile.requests_per_minute == 25
    assert profile.max_concurrent_threads == 3
    assert profile.fallback_model == "llama-3.1-8b-instant"
    assert profile.default_language == "ru"
    assert profile.default_timezone == "Europe/Moscow"
    assert profile.target_language == "de"
    assert profile.tone_of_voice == "warm"
    assert profile.system_prompt_override == "Уточняй город клиента."


def test_project_runtime_profile_uses_russian_when_language_is_unset():
    empty_profile = ProjectRuntimeProfile.from_configuration(None)
    configured_without_language = ProjectRuntimeProfile.from_configuration(
        {"settings": {}, "limit_profile": {}}
    )

    assert empty_profile.default_language == "ru"
    assert configured_without_language.default_language == "ru"


def test_project_runtime_profile_ignores_invalid_values():
    profile = ProjectRuntimeProfile.from_configuration(
        {
            "settings": {
                "default_language": "",
            },
            "limit_profile": {
                "requests_per_minute": "bad",
                "max_concurrent_threads": 0,
                "fallback_model": " ",
            },
        }
    )

    assert profile.requests_per_minute is None
    assert profile.max_concurrent_threads is None
    assert profile.fallback_model is None
    assert profile.default_language == "ru"
