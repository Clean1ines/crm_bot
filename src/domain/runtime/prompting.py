from dataclasses import dataclass, field
from typing import Mapping

from src.domain.runtime.project_runtime_profile import ProjectRuntimeProfile
from src.domain.runtime.state_contracts import ProjectChannelState, ProjectIntegrationState, ProjectRuntimeConfigurationState


NO_DATA_TEXT = "none"
NO_KNOWLEDGE_TEXT = "No knowledge-base evidence found."


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

    def format_lines(self, *, truncate) -> list[str]:
        lines: list[str] = []
        setting_labels = [
            ("brand_name", "brand"),
            ("industry", "industry"),
            ("tone_of_voice", "tone"),
            ("default_language", "language"),
            ("default_timezone", "timezone"),
        ]
        for key, label in setting_labels:
            value = self.settings.get(key)
            if value:
                lines.append(f"- {label}: {truncate(str(value), 160)}")

        prompt_override = self.settings.get("system_prompt_override")
        if prompt_override:
            lines.append(f"- project instruction: {truncate(str(prompt_override), 500)}")

        for key in [
            "escalation_policy_json",
            "routing_policy_json",
            "crm_policy_json",
            "response_policy_json",
            "privacy_policy_json",
        ]:
            value = self.policies.get(key)
            if value:
                lines.append(f"- {key}: {truncate(str(value), 350)}")

        if self.runtime_profile.fallback_model:
            lines.append(f"- fallback_model: {truncate(self.runtime_profile.fallback_model, 120)}")
        if self.runtime_profile.requests_per_minute:
            lines.append(f"- requests_per_minute: {self.runtime_profile.requests_per_minute}")
        if self.runtime_profile.max_concurrent_threads:
            lines.append(f"- max_concurrent_threads: {self.runtime_profile.max_concurrent_threads}")

        active_integrations = [
            str(item.get("provider"))
            for item in self.integrations
            if item.get("provider") and item.get("status") in {"active", "enabled"}
        ]
        if active_integrations:
            lines.append(f"- active_integrations: {', '.join(active_integrations)}")

        active_channels = [
            f"{item.get('kind')}/{item.get('provider')}"
            for item in self.channels
            if item.get("kind") and item.get("provider") and item.get("status") in {"active", "enabled"}
        ]
        if active_channels:
            lines.append(f"- active_channels: {', '.join(active_channels)}")

        return lines
