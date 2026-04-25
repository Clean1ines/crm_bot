from src.domain.identity.auth_providers import (
    ALLOWED_AUTH_PROVIDERS,
    AUTH_DELIVERY_MANUAL_LINK,
    AUTH_PROVIDER_EMAIL,
    AUTH_PROVIDER_GOOGLE,
    AUTH_PROVIDER_TELEGRAM,
    AUTH_STATUS_PASSWORD_RESET_COMPLETED,
    AUTH_STATUS_PASSWORD_RESET_REQUESTED,
    AUTH_STATUS_VERIFICATION_REQUESTED,
    EMAIL_VERIFICATION_QUERY_KEY,
    PASSWORD_RESET_QUERY_KEY,
)


def test_allowed_auth_providers_match_platform_identity_contract():
    assert ALLOWED_AUTH_PROVIDERS == {
        AUTH_PROVIDER_TELEGRAM,
        AUTH_PROVIDER_EMAIL,
        AUTH_PROVIDER_GOOGLE,
    }


def test_auth_lifecycle_constants_are_stable():
    assert AUTH_DELIVERY_MANUAL_LINK == "manual_link"
    assert AUTH_STATUS_VERIFICATION_REQUESTED == "verification_requested"
    assert AUTH_STATUS_PASSWORD_RESET_REQUESTED == "password_reset_requested"
    assert AUTH_STATUS_PASSWORD_RESET_COMPLETED == "password_reset_completed"
    assert EMAIL_VERIFICATION_QUERY_KEY == "verify_email_token"
    assert PASSWORD_RESET_QUERY_KEY == "reset_password_token"
