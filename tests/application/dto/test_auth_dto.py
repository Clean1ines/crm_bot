from src.application.dto.auth_dto import AuthActionDto, AuthMethodsDto, AuthSessionDto, UserProfileDto


def test_auth_methods_dto_omits_optional_fields_when_missing():
    dto = AuthMethodsDto.from_record(
        {
            "user_id": "user-1",
            "methods": [
                {"provider": "telegram", "provider_id": "12345", "created_at": None},
                {
                    "provider": "email",
                    "provider_id": "jane@example.com",
                    "created_at": "2026-04-23T10:00:00+00:00",
                    "verified": True,
                    "verified_at": "2026-04-23T10:05:00+00:00",
                },
            ],
            "has_password": True,
        }
    )

    assert dto.to_dict() == {
        "user_id": "user-1",
        "methods": [
            {"provider": "telegram", "provider_id": "12345"},
            {
                "provider": "email",
                "provider_id": "jane@example.com",
                "created_at": "2026-04-23T10:00:00+00:00",
                "verified": True,
                "verified_at": "2026-04-23T10:05:00+00:00",
            },
        ],
        "has_password": True,
    }


def test_auth_methods_dto_preserves_verified_email():
    dto = AuthMethodsDto.from_record(
        {
            "user_id": "user-1",
            "methods": [],
            "has_password": False,
            "verified_email": "jane@example.com",
        }
    )

    assert dto.to_dict()["verified_email"] == "jane@example.com"


def test_auth_session_dto_omits_empty_fields():
    dto = AuthSessionDto.create(access_token="token", user_id="user-1")

    assert dto.to_dict() == {
        "access_token": "token",
        "user_id": "user-1",
    }


def test_auth_action_dto_omits_missing_optional_fields():
    dto = AuthActionDto.create(status="password_reset_requested", delivery="manual_link")

    assert dto.to_dict() == {
        "status": "password_reset_requested",
        "delivery": "manual_link",
        "expires_at": None,
        "token": None,
        "url": None,
        "user_id": None,
    }


def test_user_profile_dto_normalizes_id_and_telegram_id():
    dto = UserProfileDto.from_record(
        {
            "id": "user-1",
            "telegram_id": "12345",
            "username": "jane",
            "full_name": "Jane Doe",
            "email": "jane@example.com",
        }
    )

    assert dto.to_dict() == {
        "id": "user-1",
        "telegram_id": 12345,
        "username": "jane",
        "full_name": "Jane Doe",
        "email": "jane@example.com",
    }
