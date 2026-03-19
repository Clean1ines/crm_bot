"""
Configuration management for the application.
Uses Pydantic Settings to load and validate environment variables.
"""
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
import uuid

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    All variables are validated and typed.
    """
    # Database
    DATABASE_URL: str = Field(..., description="PostgreSQL connection string")
    
    # Database pool settings
    DB_POOL_MIN_SIZE: int = Field(1, ge=1, le=10, description="Minimum database pool connections")
    DB_POOL_MAX_SIZE: int = Field(10, ge=1, le=50, description="Maximum database pool connections")
    DB_COMMAND_TIMEOUT: float = Field(60.0, gt=0, description="Database command timeout in seconds")

    # Admin bot
    ADMIN_CHAT_ID: str = Field(..., description="Telegram chat ID of the platform administrator")
    ADMIN_BOT_TOKEN: str = Field("", description="Token of the admin bot (used for first project creation)")
    ADMIN_PROJECT_ID: Optional[str] = Field(None, description="ID of the admin project (excluded from user lists)")

    # External URLs
    RENDER_EXTERNAL_URL: str = Field("", description="Public URL of the service (set by Render)")
    PUBLIC_URL: str = Field("", description="Alternative public URL if not using Render")

    # Groq
    GROQ_API_KEY: str = Field(..., description="API key for Groq LLM")
    GROQ_MODEL: str = Field("llama-3.3-70b-versatile", description="Default Groq model for agent")

    # Optional Redis (for future use)
    REDIS_URL: str = Field("", description="Redis connection string (optional)")

    # Encryption key for bot tokens (must be a valid Fernet key)
    TOKEN_ENCRYPTION_KEY: str = Field(..., description="Fernet key for encrypting bot tokens")

    # API token for admin panel endpoints
    ADMIN_API_TOKEN: str = Field(..., description="Bearer token for accessing admin API endpoints")

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
    TOOL_HTTP_ALLOWED_DOMAINS: Optional[str] = None
    TOOL_N8N_ALLOWED_WEBHOOKS: Optional[str] = None

    # Model and rate limit configuration
    GROQ_MODEL: str = Field("llama-3.3-70b-versatile", description="Default Groq model")
    MODEL_CONFIG_PATH: str = Field("models.yaml", description="Path to YAML file with model definitions")
    DEFAULT_MODEL: str = Field("llama-3.1-8b-instant", description="Fallback model when preferred ones are rate-limited")
    MODEL_SELECTION_STRATEGY: str = Field("priority", description="Strategy for model selection: priority, round-robin, etc.")
    RATE_LIMIT_REDIS_PREFIX: str = Field("ratelimit:", description="Redis key prefix for rate limit tracking")

    @field_validator("ADMIN_CHAT_ID")
    def validate_chat_id(cls, v: str) -> str:
        """Ensure chat ID is a valid integer string."""
        try:
            int(v)
        except ValueError:
            raise ValueError("ADMIN_CHAT_ID must be a numeric string (Telegram chat ID)")
        return v

    @field_validator("TOKEN_ENCRYPTION_KEY")
    def validate_encryption_key(cls, v: str) -> str:
        """Basic length check for Fernet key (should be 32 base64 bytes)."""
        if len(v) < 20:
            raise ValueError("TOKEN_ENCRYPTION_KEY must be a valid Fernet key (minimum length 20)")
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True

# Global instance for easy import
settings = Settings()
