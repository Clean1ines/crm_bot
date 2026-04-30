from src.application.dto.project_dto import (
    ProjectChannelDto,
    ProjectConfigurationDto,
    ProjectIntegrationDto,
    ProjectPromptVersionDto,
    ProjectSummaryDto,
)


def test_project_summary_dto_normalizes_repository_record():
    dto = ProjectSummaryDto.from_record(
        {
            "id": "project-1",
            "name": "Acme",
            "is_pro_mode": 1,
            "user_id": "user-1",
            "client_bot_username": "client_bot",
            "manager_bot_username": None,
            "access_role": "manager",
        }
    )

    assert dto.to_dict() == {
        "id": "project-1",
        "name": "Acme",
        "is_pro_mode": True,
        "user_id": "user-1",
        "client_bot_username": "client_bot",
        "manager_bot_username": None,
        "access_role": "manager",
    }


def test_project_configuration_dto_normalizes_nested_blocks():
    dto = ProjectConfigurationDto.from_record(
        {
            "project_id": "project-1",
            "settings": {"brand_name": "Acme"},
            "policies": {"escalation_policy_json": {"mode": "manual"}},
            "limit_profile": {"fallback_model": "llama-3.1-8b-instant"},
            "integrations": [{"provider": "amo", "status": "active"}],
            "channels": [{"kind": "widget", "provider": "web"}],
            "prompt_versions": [{"version": 1, "is_active": True}],
        }
    )

    assert dto.project_id == "project-1"
    assert dto.settings["brand_name"] == "Acme"
    assert dto.policies["escalation_policy_json"] == {"mode": "manual"}
    assert dto.limit_profile["fallback_model"] == "llama-3.1-8b-instant"
    assert isinstance(dto.integrations[0], ProjectIntegrationDto)
    assert dto.integrations[0].provider == "amo"
    assert isinstance(dto.channels[0], ProjectChannelDto)
    assert dto.channels[0].kind == "widget"
    assert isinstance(dto.prompt_versions[0], ProjectPromptVersionDto)
    assert dto.prompt_versions[0].version == 1
    assert dto.to_dict()["integrations"][0]["provider"] == "amo"
