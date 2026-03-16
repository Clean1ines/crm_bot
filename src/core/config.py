"""
Configuration management for the application.
Uses Pydantic Settings to load and validate environment variables.
"""

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

    # Admin bot
    ADMIN_CHAT_ID: str = Field(..., description="Telegram chat ID of the platform administrator")
    ADMIN_BOT_TOKEN: str = Field("", description="Token of the admin bot (used for first project creation)")

    # Manager bot (notifications)
    MANAGER_BOT_TOKEN: str = Field("", description="Token of the bot that sends notifications to managers")
    MANAGER_CHAT_ID: str = Field("", description="Telegram chat ID of the manager (who receives notifications)")

    # External URLs
    RENDER_EXTERNAL_URL: str = Field("", description="Public URL of the service (set by Render)")
    PUBLIC_URL: str = Field("", description="Alternative public URL if not using Render")

    # Groq
    GROQ_API_KEY: str = Field(..., description="API key for Groq LLM")

    # Optional Redis (for future use)
    REDIS_URL: str = Field("", description="Redis connection string (optional)")

    # Other settings
    PROJECT_NAME: str = "MRAK-OS CRM Bot"
    DEBUG: bool = Field(False, description="Enable debug mode")

    @field_validator("ADMIN_CHAT_ID")
    def validate_chat_id(cls, v: str) -> str:
        """Ensure chat ID is a valid integer string."""
        try:
            int(v)
        except ValueError:
            raise ValueError("ADMIN_CHAT_ID must be a numeric string (Telegram chat ID)")
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True

# Global instance for easy import
settings = Settings()
