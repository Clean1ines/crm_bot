from dataclasses import dataclass
from typing import Mapping

from src.domain.runtime.state_contracts import ProjectRuntimeConfigurationState
from src.domain.runtime.value_parsing import coerce_int


ConfigurationInput = ProjectRuntimeConfigurationState | Mapping[str, object]


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
    def from_configuration(cls, project_configuration: ConfigurationInput | None) -> "ProjectRuntimeProfile":
        if not project_configuration:
            return cls()

        settings_block = _mapping_block(project_configuration.get("settings"))
        limit_block = _limit_block(project_configuration)

        return cls(
            requests_per_minute=_positive_int(limit_block.get("requests_per_minute")),
            max_concurrent_threads=_positive_int(limit_block.get("max_concurrent_threads")),
            fallback_model=_optional_stripped_text(limit_block.get("fallback_model")),
            default_language=_optional_stripped_text(settings_block.get("default_language")),
            default_timezone=_optional_stripped_text(settings_block.get("default_timezone")),
            tone_of_voice=_optional_stripped_text(settings_block.get("tone_of_voice")),
            system_prompt_override=_optional_stripped_text(settings_block.get("system_prompt_override")),
        )


def _limit_block(project_configuration: ConfigurationInput) -> Mapping[str, object]:
    raw_limits = project_configuration.get("limit_profile") or project_configuration.get("limits")
    return _mapping_block(raw_limits)


def _mapping_block(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value

    return {}


def _optional_stripped_text(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None
