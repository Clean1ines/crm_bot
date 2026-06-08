from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from src.contexts.llm_runtime.infrastructure.providers.groq.groq_env_config import (
    GroqEnvAccountSpec,
    GroqEnvConfig,
    GroqEnvConfigLoader,
)


@dataclass(frozen=True, slots=True)
class LlmRuntimeSettings:
    """Infrastructure settings owned by LLM Runtime bounded context.

    Env variable names can remain deployment-compatible with legacy settings,
    but this object is the new ownership boundary for LLM Runtime provider
    configuration.
    """

    groq_api_key: str | None = None
    groq_api_key2: str | None = None
    groq_api_key3: str | None = None
    groq_api_key4: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not self.groq_base_url or not self.groq_base_url.strip():
            raise ValueError("groq_base_url must be non-empty")
        if self.groq_timeout_seconds <= 0:
            raise ValueError("groq_timeout_seconds must be > 0")

    @classmethod
    def from_env_mapping(cls, env: Mapping[str, str]) -> "LlmRuntimeSettings":
        return cls(
            groq_api_key=_optional_env_value(env.get("GROQ_API_KEY")),
            groq_api_key2=_optional_env_value(env.get("GROQ_API_KEY2")),
            groq_api_key3=_optional_env_value(env.get("GROQ_API_KEY3")),
            groq_api_key4=_optional_env_value(env.get("GROQ_API_KEY4")),
            groq_base_url=_optional_env_value(env.get("LLM_RUNTIME_GROQ_BASE_URL"))
            or "https://api.groq.com/openai/v1",
            groq_timeout_seconds=_float_env_value(
                env.get("LLM_RUNTIME_GROQ_TIMEOUT_SECONDS"),
                default=60.0,
            ),
        )

    def to_groq_env_config(self) -> GroqEnvConfig:
        env = {
            "GROQ_API_KEY": self.groq_api_key or "",
            "GROQ_API_KEY2": self.groq_api_key2 or "",
            "GROQ_API_KEY3": self.groq_api_key3 or "",
            "GROQ_API_KEY4": self.groq_api_key4 or "",
        }

        return GroqEnvConfigLoader().load(
            env=env,
            account_specs=(
                GroqEnvAccountSpec(
                    account_ref="groq_org_primary",
                    env_var_name="GROQ_API_KEY",
                    account_rank=0,
                ),
                GroqEnvAccountSpec(
                    account_ref="groq_org_secondary",
                    env_var_name="GROQ_API_KEY2",
                    account_rank=1,
                ),
                GroqEnvAccountSpec(
                    account_ref="groq_org_tertiary",
                    env_var_name="GROQ_API_KEY3",
                    account_rank=2,
                ),
                GroqEnvAccountSpec(
                    account_ref="groq_org_quaternary",
                    env_var_name="GROQ_API_KEY4",
                    account_rank=3,
                ),
            ),
        )


def _optional_env_value(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = value.strip()
    return stripped or None


def _float_env_value(value: str | None, *, default: float) -> float:
    if value is None or not value.strip():
        return default

    try:
        parsed = float(value.strip())
    except ValueError as exc:
        raise ValueError("Expected float env value") from exc

    if parsed <= 0:
        raise ValueError("Expected positive float env value")

    return parsed
