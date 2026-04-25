from src.domain.runtime.prompting import NO_DATA_TEXT, ProjectPromptContext


def test_project_prompt_context_formats_active_project_lines():
    context = ProjectPromptContext.from_configuration(
        {
            "settings": {
                "brand_name": "Acme",
                "tone_of_voice": "precise",
                "system_prompt_override": "Be careful with pricing promises.",
            },
            "integrations": [
                {"provider": "amo_crm", "status": "active"},
                {"provider": "old_crm", "status": "disabled"},
            ],
            "channels": [
                {"kind": "widget", "provider": "web", "status": "active"},
            ],
        }
    )

    lines = context.format_lines(truncate=lambda value, _limit: value)

    assert "- brand: Acme" in lines
    assert "- tone: precise" in lines
    assert "- project instruction: Be careful with pricing promises." in lines
    assert "- active_integrations: amo_crm" in lines
    assert "- active_channels: widget/web" in lines


def test_project_prompt_context_is_empty_when_configuration_missing():
    context = ProjectPromptContext.from_configuration(None)

    assert context.format_lines(truncate=lambda value, _limit: value) == []
    assert NO_DATA_TEXT == "none"
