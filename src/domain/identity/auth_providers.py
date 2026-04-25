"""Identity/auth invariants for provider names and auth lifecycle responses."""

AUTH_PROVIDER_TELEGRAM = "telegram"
AUTH_PROVIDER_EMAIL = "email"
AUTH_PROVIDER_GOOGLE = "google"

ALLOWED_AUTH_PROVIDERS = {
    AUTH_PROVIDER_TELEGRAM,
    AUTH_PROVIDER_EMAIL,
    AUTH_PROVIDER_GOOGLE,
}

AUTH_DELIVERY_MANUAL_LINK = "manual_link"

AUTH_STATUS_VERIFICATION_REQUESTED = "verification_requested"
AUTH_STATUS_PASSWORD_RESET_REQUESTED = "password_reset_requested"
AUTH_STATUS_PASSWORD_RESET_COMPLETED = "password_reset_completed"

EMAIL_VERIFICATION_QUERY_KEY = "verify_email_token"
PASSWORD_RESET_QUERY_KEY = "reset_password_token"
