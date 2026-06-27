from __future__ import annotations

from dataclasses import dataclass


PromptProfileKey = tuple[str, str, str, str]


@dataclass(frozen=True, slots=True)
class PromptProfile:
    prompt_id: str
    prompt_version: str
    provider_id: str
    model_ref: str
    prompt_tokens: int
    prompt_source_ref: str
    output_contract_ref: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.prompt_id, field_name="prompt_id")
        _require_non_empty_text(self.prompt_version, field_name="prompt_version")
        _require_non_empty_text(self.provider_id, field_name="provider_id")
        _require_non_empty_text(self.model_ref, field_name="model_ref")
        _require_positive_int(self.prompt_tokens, field_name="prompt_tokens")
        _require_non_empty_text(self.prompt_source_ref, field_name="prompt_source_ref")
        _require_non_empty_text(
            self.output_contract_ref, field_name="output_contract_ref"
        )

    @property
    def key(self) -> PromptProfileKey:
        return (
            self.prompt_id,
            self.prompt_version,
            self.provider_id,
            self.model_ref,
        )


@dataclass(frozen=True, slots=True)
class PromptProfileCatalog:
    profiles: tuple[PromptProfile, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.profiles, tuple):
            raise TypeError("profiles must be tuple")
        if not self.profiles:
            raise ValueError("profiles must be non-empty")
        keys = tuple(profile.key for profile in self.profiles)
        if len(set(keys)) != len(keys):
            raise ValueError("prompt profiles must have unique keys")

    def profile_for_prompt(
        self,
        *,
        prompt_id: str,
        prompt_version: str,
        provider_id: str,
        model_ref: str,
    ) -> PromptProfile:
        key = _profile_key(
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            provider_id=provider_id,
            model_ref=model_ref,
        )
        for profile in self.profiles:
            if profile.key == key:
                return profile
        raise ValueError("prompt profile is not configured")


def _profile_key(
    *,
    prompt_id: str,
    prompt_version: str,
    provider_id: str,
    model_ref: str,
) -> PromptProfileKey:
    _require_non_empty_text(prompt_id, field_name="prompt_id")
    _require_non_empty_text(prompt_version, field_name="prompt_version")
    _require_non_empty_text(provider_id, field_name="provider_id")
    _require_non_empty_text(model_ref, field_name="model_ref")
    return prompt_id, prompt_version, provider_id, model_ref


def _require_positive_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
