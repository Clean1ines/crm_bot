from src.agent.router.prompt_builder import (
    build_intent_prompt,
    build_response_prompt,
    format_project_configuration,
)


def test_format_project_configuration_compacts_personalization_context():
    result = format_project_configuration(
        {
            "settings": {
                "brand_name": "Acme",
                "industry": "home services",
                "tone_of_voice": "warm and precise",
                "default_language": "ru",
                "default_timezone": "Europe/Moscow",
                "system_prompt_override": "Always ask the client for their city.",
            },
            "policies": {
                "escalation_policy_json": {"after_minutes": 3},
                "privacy_policy_json": {"mask_phone": True},
            },
            "limit_profile": {
                "fallback_model": "llama-3.1-8b-instant",
                "requests_per_minute": 20,
                "max_concurrent_threads": 3,
            },
            "integrations": [
                {"provider": "amo_crm", "status": "active"},
                {"provider": "disabled_crm", "status": "disabled"},
            ],
            "channels": [
                {"kind": "widget", "provider": "web", "status": "active"},
                {"kind": "client", "provider": "telegram", "status": "disabled"},
            ],
        }
    )

    assert "- brand: Acme" in result
    assert "- tone: warm and precise" in result
    assert "- project instruction: Always ask the client for their city." in result
    assert "escalation_policy_json" in result
    assert "privacy_policy_json" in result
    assert "- fallback_model: llama-3.1-8b-instant" in result
    assert "- requests_per_minute: 20" in result
    assert "- max_concurrent_threads: 3" in result
    assert "- active_integrations: amo_crm" in result
    assert "disabled_crm" not in result
    assert "- active_channels: widget/web" in result


def test_build_response_prompt_includes_project_context():
    prompt = build_response_prompt(
        decision="LLM_GENERATE",
        user_input="How much does it cost?",
        project_configuration={
            "settings": {
                "brand_name": "Acme",
                "tone_of_voice": "concise",
                "default_language": "ru",
            },
            "channels": [{"kind": "widget", "provider": "web", "status": "active"}],
        },
    )

    assert "Project context:" in prompt
    assert "- brand: Acme" in prompt
    assert "- tone: concise" in prompt
    assert "- active_channels: widget/web" in prompt


def test_build_intent_prompt_uses_clean_fallback_text():
    prompt = build_intent_prompt(
        user_input="Need help",
        conversation_summary=None,
        history=None,
        user_memory=None,
    )

    assert "User message: Need help" in prompt
    assert "- Summary: none" in prompt
    assert "- User memory: none" in prompt
