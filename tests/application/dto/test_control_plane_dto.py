from src.application.dto.control_plane_dto import (
    ProjectMemberDto,
    ProjectMutationResultDto,
)


def test_project_member_dto_normalizes_identity_fields():
    dto = ProjectMemberDto.from_record(
        {
            "id": "member-1",
            "project_id": "project-1",
            "user_id": "user-1",
            "role": "manager",
            "telegram_id": "12345",
            "username": "manager_user",
            "full_name": "Manager User",
            "email": "manager@example.com",
            "created_at": "2026-04-23T12:00:00+00:00",
        }
    )

    assert dto.to_dict() == {
        "id": "member-1",
        "project_id": "project-1",
        "user_id": "user-1",
        "role": "manager",
        "telegram_id": 12345,
        "username": "manager_user",
        "full_name": "Manager User",
        "display_name": "Manager User",
        "email": "manager@example.com",
        "created_at": "2026-04-23T12:00:00+00:00",
    }


def test_project_mutation_result_dto_omits_empty_fields():
    dto = ProjectMutationResultDto.create(status="ok", type="client")

    assert dto.to_dict() == {
        "status": "ok",
        "type": "client",
    }
