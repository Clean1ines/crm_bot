from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderBudgetProfile:
    provider_id: str
    provider_default_completion_tokens: int
    request_safety_gap_tokens: int
    output_safety_gap_tokens: int

    def __post_init__(self) -> None:
        _require_non_empty_text(self.provider_id, field_name="provider_id")
        _require_positive_int(
            self.provider_default_completion_tokens,
            field_name="provider_default_completion_tokens",
        )
        _require_non_negative_int(
            self.request_safety_gap_tokens,
            field_name="request_safety_gap_tokens",
        )
        _require_non_negative_int(
            self.output_safety_gap_tokens,
            field_name="output_safety_gap_tokens",
        )


@dataclass(frozen=True, slots=True)
class ProviderBudgetProfileCatalog:
    profiles: tuple[ProviderBudgetProfile, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.profiles, tuple):
            raise TypeError("profiles must be tuple")
        if not self.profiles:
            raise ValueError("profiles must be non-empty")
        provider_ids = tuple(profile.provider_id for profile in self.profiles)
        if len(set(provider_ids)) != len(provider_ids):
            raise ValueError("provider budget profiles must have unique provider_id")

    def profile_for_provider(self, provider_id: str) -> ProviderBudgetProfile:
        _require_non_empty_text(provider_id, field_name="provider_id")
        for profile in self.profiles:
            if profile.provider_id == provider_id:
                return profile
        raise ValueError("provider budget profile is not configured")


def _require_positive_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
