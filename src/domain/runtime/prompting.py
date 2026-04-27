from dataclasses import dataclass, field
from typing import Mapping, Protocol

from src.domain.runtime.project_runtime_profile import ProjectRuntimeProfile
from src.domain.runtime.state_contracts import ProjectChannelState, ProjectIntegrationState, ProjectRuntimeConfigurationState


NO_DATA_TEXT = "none"
NO_KNOWLEDGE_TEXT = "No knowledge-base evidence found."

ACTIVE_STATUSES = frozenset({"active", "enabled"})
SETTING_LABELS = (
    ("brand_name", "brand", 160),
    ("industry", "industry", 160),
    ("tone_of_voice", "tone", 160),
    ("default_language", "language", 160),
    ("default_timezone", "timezone", 160),
)
POLICY_KEYS = (
    "escalation_policy_json",
    "routing_policy_json",
    "crm_policy_json",
    "response_policy_json",
    "privacy_policy_json",
)


class TruncateText(Protocol):
    def __call__(self, value: str, limit: int) -> str:
        ...


@dataclass(slots=True)
class ProjectPromptContext:
    settings: Mapping[str, object] = field(default_factory=dict)
    policies: Mapping[str, object] = field(default_factory=dict)
    integrations: list[ProjectIntegrationState] = field(default_factory=list)
    channels: list[ProjectChannelState] = field(default_factory=list)
    runtime_profile: ProjectRuntimeProfile = field(default_factory=ProjectRuntimeProfile)

    @classmethod
    def from_configuration(cls, configuration: ProjectRuntimeConfigurationState | None) -> "ProjectPromptContext":
        payload = configuration or {}
        return cls(
            settings=payload.get("settings") or {},
            policies=payload.get("policies") or {},
            integrations=list(payload.get("integrations") or []),
            channels=list(payload.get("channels") or []),
            runtime_profile=ProjectRuntimeProfile.from_configuration(payload),
        )

    def format_lines(self, *, truncate: TruncateText) -> list[str]:
        return [
            *_format_settings(self.settings, truncate),
            *_format_prompt_override(self.settings, truncate),
            *_format_policies(self.policies, truncate),
            *_format_runtime_profile(self.runtime_profile, truncate),
            *_format_active_integrations(self.integrations),
            *_format_active_channels(self.channels),
        ]


def _format_settings(settings: Mapping[str, object], truncate: TruncateText) -> list[str]:
    return [
        f"- {label}: {truncate(str(value), limit)}"
        for key, label, limit in SETTING_LABELS
        if (value := settings.get(key))
    ]


def _format_prompt_override(settings: Mapping[str, object], truncate: TruncateText) -> list[str]:
    prompt_override = settings.get("system_prompt_override")
    if not prompt_override:
        return []

    return [f"- project instruction: {truncate(str(prompt_override), 500)}"]


def _format_policies(policies: Mapping[str, object], truncate: TruncateText) -> list[str]:
    return [
        f"- {key}: {truncate(str(value), 350)}"
        for key in POLICY_KEYS
        if (value := policies.get(key))
    ]


def _format_runtime_profile(profile: ProjectRuntimeProfile, truncate: TruncateText) -> list[str]:
    lines: list[str] = []

    if profile.fallback_model:
        lines.append(f"- fallback_model: {truncate(profile.fallback_model, 120)}")
    if profile.requests_per_minute:
        lines.append(f"- requests_per_minute: {profile.requests_per_minute}")
    if profile.max_concurrent_threads:
        lines.append(f"- max_concurrent_threads: {profile.max_concurrent_threads}")

    return lines


def _format_active_integrations(integrations: list[ProjectIntegrationState]) -> list[str]:
    providers = [
        str(provider)
        for item in integrations
        if (provider := item.get("provider")) and item.get("status") in ACTIVE_STATUSES
    ]
    return _format_joined_line("active_integrations", providers)


def _format_active_channels(channels: list[ProjectChannelState]) -> list[str]:
    active_channels = [
        f"{kind}/{provider}"
        for item in channels
        if (
            (kind := item.get("kind"))
            and (provider := item.get("provider"))
            and item.get("status") in ACTIVE_STATUSES
        )
    ]
    return _format_joined_line("active_channels", active_channels)


def _format_joined_line(label: str, values: list[str]) -> list[str]:
    if not values:
        return []

    return [f"- {label}: {', '.join(values)}"]
