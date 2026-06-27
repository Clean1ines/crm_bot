from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderOutputCapProfile:
    provider_default_completion_tokens: int
    completion_safety_gap_tokens: int

    def __post_init__(self) -> None:
        _require_positive_int(
            self.provider_default_completion_tokens,
            field_name="provider_default_completion_tokens",
        )
        _require_non_negative_int(
            self.completion_safety_gap_tokens,
            field_name="completion_safety_gap_tokens",
        )


@dataclass(frozen=True, slots=True)
class RequestOutputCapDecision:
    input_tokens: int
    artifact_tokens: int
    remaining_after_input_tokens: int
    max_completion_tokens: int | None
    required_window_tokens: int

    def __post_init__(self) -> None:
        _require_positive_int(self.input_tokens, field_name="input_tokens")
        _require_non_negative_int(
            self.artifact_tokens,
            field_name="artifact_tokens",
        )
        _require_int(
            self.remaining_after_input_tokens,
            field_name="remaining_after_input_tokens",
        )
        if self.max_completion_tokens is not None:
            _require_positive_int(
                self.max_completion_tokens,
                field_name="max_completion_tokens",
            )
        _require_positive_int(
            self.required_window_tokens,
            field_name="required_window_tokens",
        )


@dataclass(frozen=True, slots=True)
class RequestOutputCapPolicy:
    provider_profile: ProviderOutputCapProfile

    def __post_init__(self) -> None:
        if not isinstance(self.provider_profile, ProviderOutputCapProfile):
            raise TypeError("provider_profile must be ProviderOutputCapProfile")

    def decide(
        self,
        *,
        input_tokens: int,
        artifact_tokens: int,
        tokens_remaining: int,
        model_max_output_tokens: int,
    ) -> RequestOutputCapDecision:
        _require_positive_int(input_tokens, field_name="input_tokens")
        _require_non_negative_int(artifact_tokens, field_name="artifact_tokens")
        _require_non_negative_int(tokens_remaining, field_name="tokens_remaining")
        _require_positive_int(
            model_max_output_tokens,
            field_name="model_max_output_tokens",
        )
        if (
            self.provider_profile.provider_default_completion_tokens
            > model_max_output_tokens
        ):
            raise ValueError(
                "provider_default_completion_tokens must not exceed "
                "model_max_output_tokens"
            )

        remaining_after_input_tokens = (
            tokens_remaining
            - input_tokens
            - self.provider_profile.completion_safety_gap_tokens
        )
        max_completion_tokens: int | None = None
        if (
            remaining_after_input_tokens
            > self.provider_profile.provider_default_completion_tokens
        ):
            max_completion_tokens = min(
                remaining_after_input_tokens,
                model_max_output_tokens,
            )

        return RequestOutputCapDecision(
            input_tokens=input_tokens,
            artifact_tokens=artifact_tokens,
            remaining_after_input_tokens=remaining_after_input_tokens,
            max_completion_tokens=max_completion_tokens,
            required_window_tokens=(
                input_tokens
                + artifact_tokens
                + self.provider_profile.completion_safety_gap_tokens
            ),
        )


def _require_positive_int(value: int, *, field_name: str) -> None:
    _require_int(value, field_name=field_name)
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    _require_int(value, field_name=field_name)
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")


def _require_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
