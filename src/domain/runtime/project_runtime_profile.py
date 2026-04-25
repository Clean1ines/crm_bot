from dataclasses import dataclass
from typing import Mapping

from src.domain.runtime.state_contracts import ProjectRuntimeConfigurationState
from src.domain.runtime.value_parsing import coerce_int


def _positive_int(value: object) -> int | None:
    parsed = coerce_int(value, 0)
    return parsed if parsed > 0 else None


@dataclass(frozen=True)
class ProjectRuntimeProfile:
    requests_per_minute: int | None = None
    max_concurrent_threads: int | None = None
    fallback_model: str | None = None
    default_language: str | None = None
    default_timezone: str | None = None
    tone_of_voice: str | None = None
    system_prompt_override: str | None = None

    @classmethod
    def from_configuration(cls, project_configuration: ProjectRuntimeConfigurationState | Mapping[str, object] | None) -> "ProjectRuntimeProfile":
        if not project_configuration:
            return cls()

        raw_settings = project_configuration.get("settings") or {}
        raw_limits = project_configuration.get("limit_profile") or project_configuration.get("limits") or {}

        settings_block = raw_settings if isinstance(raw_settings, Mapping) else {}
        limit_block = raw_limits if isinstance(raw_limits, Mapping) else {}

        fallback_model = str(limit_block.get("fallback_model") or "").strip() or None
        return cls(
            requests_per_minute=_positive_int(limit_block.get("requests_per_minute")),
            max_concurrent_threads=_positive_int(limit_block.get("max_concurrent_threads")),
            fallback_model=fallback_model,
            default_language=str(settings_block.get("default_language")).strip() if settings_block.get("default_language") else None,
            default_timezone=str(settings_block.get("default_timezone")).strip() if settings_block.get("default_timezone") else None,
            tone_of_voice=str(settings_block.get("tone_of_voice")).strip() if settings_block.get("tone_of_voice") else None,
            system_prompt_override=str(settings_block.get("system_prompt_override")).strip() if settings_block.get("system_prompt_override") else None,
        )
