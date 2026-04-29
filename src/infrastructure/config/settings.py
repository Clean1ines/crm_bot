"""
Configuration management for the application.
Uses Pydantic Settings to load and validate environment variables.
"""

from typing import TYPE_CHECKING

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    All variables are validated and typed.
    """

    # Database
    DATABASE_URL: str = Field(..., description="PostgreSQL connection string")

    # Database pool settings
    DB_POOL_MIN_SIZE: int = Field(
        1, ge=1, le=10, description="Minimum database pool connections"
    )
    DB_POOL_MAX_SIZE: int = Field(
        10, ge=1, le=50, description="Maximum database pool connections"
    )
    DB_COMMAND_TIMEOUT: float = Field(
        60.0, gt=0, description="Database command timeout in seconds"
    )

    # Admin bot
    ADMIN_CHAT_ID: str = Field(
        ..., description="Telegram chat ID of the platform administrator"
    )
    ADMIN_BOT_TOKEN: str = Field(
        "", description="Token of the admin bot (used for first project creation)"
    )
    BOOTSTRAP_PLATFORM_OWNER: bool = Field(
        True,
        description="Ensure the configured platform owner exists as a global platform admin on startup",
    )
    PLATFORM_OWNER_TELEGRAM_ID: str | None = Field(
        None,
        description="Telegram ID of the global platform owner; falls back to ADMIN_CHAT_ID",
    )
    PLATFORM_WEBHOOK_SECRET: str | None = Field(
        None,
        description="Telegram webhook secret for the global platform bot surface",
    )
    ADMIN_PROJECT_ID: str | None = Field(
        None, description="ID of the admin project (excluded from user lists)"
    )

    # External URLs
    RENDER_EXTERNAL_URL: str = Field(
        "", description="Public URL of the service (set by Render)"
    )
    PUBLIC_URL: str = Field(
        "", description="Alternative public URL if not using Render"
    )

    # Groq
    GROQ_API_KEY: str = Field(..., description="API key for Groq LLM")
    GROQ_MODEL: str = Field(
        "llama-3.3-70b-versatile", description="Default Groq model for agent"
    )

    # Optional Redis (for future use)
    REDIS_URL: str = Field("", description="Redis connection string (optional)")

    # Encryption key for bot tokens (must be a valid Fernet key)
    TOKEN_ENCRYPTION_KEY: str = Field(
        ..., description="Fernet key for encrypting bot tokens"
    )

    # Legacy env compatibility only. Active platform admin checks use users.is_platform_admin.
    ADMIN_API_TOKEN: str | None = Field(
        None,
        description="Deprecated legacy admin token; do not use for domain authorization",
    )

    # Other settings
    PROJECT_NAME: str = "MRAK-OS CRM Bot"
    DEBUG: bool = Field(False, description="Enable debug mode")
    # Новые поля из .env
    CANVAS_ENABLED: bool = False
    EVENT_STORE_ENABLED: bool = False
    EVENT_TTL_DAYS: int = 90
    PRO_MODE_ENABLED: bool = False
    RATE_LIMIT_BURST: int = 10
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    TOOL_HTTP_ALLOWED_DOMAINS: str | None = None
    TOOL_N8N_ALLOWED_WEBHOOKS: str | None = None

    # Model and rate limit configuration
    MODEL_CONFIG_PATH: str = Field(
        "models.yaml", description="Path to YAML file with model definitions"
    )
    DEFAULT_MODEL: str = Field(
        "llama-3.1-8b-instant",
        description="Fallback model when preferred ones are rate-limited",
    )
    MODEL_SELECTION_STRATEGY: str = Field(
        "priority",
        description="Strategy for model selection: priority, round-robin, etc.",
    )
    RATE_LIMIT_REDIS_PREFIX: str = Field(
        "ratelimit:", description="Redis key prefix for rate limit tracking"
    )

    # JWT for web authentication
    JWT_SECRET_KEY: str = Field(
        ..., description="Secret key for signing JWT tokens (used for web auth)"
    )
    GOOGLE_CLIENT_ID: str | None = Field(
        None, description="Google OAuth client ID for ID token audience validation"
    )

    VITE_API_URL: str | None = Field(None, description="Frontend API URL (for CORS)")
    FRONTEND_URL: str | None = Field(None, description="Frontend URL (for autologin)")

    HF_MODEL_URL: str = "https://huggingface.co/intfloat/multilingual-e5-large"
    HF_TOKEN: str = ""

    @field_validator("ADMIN_CHAT_ID")
    def validate_chat_id(cls, v: str) -> str:
        """Ensure chat ID is a valid integer string."""
        try:
            int(v)
        except ValueError:
            raise ValueError(
                "ADMIN_CHAT_ID must be a numeric string (Telegram chat ID)"
            )
        return v

    @field_validator("PLATFORM_OWNER_TELEGRAM_ID")
    def validate_platform_owner_telegram_id(cls, v: str | None) -> str | None:
        """Ensure optional platform owner Telegram ID is numeric when configured."""
        if not v:
            return v
        try:
            int(v)
        except ValueError:
            raise ValueError(
                "PLATFORM_OWNER_TELEGRAM_ID must be a numeric string (Telegram ID)"
            )
        return v

    @field_validator("TOKEN_ENCRYPTION_KEY")
    def validate_encryption_key(cls, v: str) -> str:
        """Basic length check for Fernet key (should be 32 base64 bytes)."""
        if len(v) < 20:
            raise ValueError(
                "TOKEN_ENCRYPTION_KEY must be a valid Fernet key (minimum length 20)"
            )
        return v

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


# Global instance for easy import
if TYPE_CHECKING:
    settings: Settings
else:
    settings = Settings()
