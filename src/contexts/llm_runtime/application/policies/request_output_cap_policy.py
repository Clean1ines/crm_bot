from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderOutputCapProfile:
    provider_default_output_cap_tokens: int
    request_safety_gap_tokens: int

    def __post_init__(self) -> None:
        _require_positive_int(
            self.provider_default_output_cap_tokens,
            field_name="provider_default_output_cap_tokens",
        )
        _require_non_negative_int(
            self.request_safety_gap_tokens,
            field_name="request_safety_gap_tokens",
        )


@dataclass(frozen=True, slots=True)
class RequestOutputCapDecision:
    effective_output_cap_tokens: int
    request_output_cap_tokens: int | None
    reserved_total_tokens: int

    def __post_init__(self) -> None:
        _require_positive_int(
            self.effective_output_cap_tokens,
            field_name="effective_output_cap_tokens",
        )
        if self.request_output_cap_tokens is not None:
            _require_positive_int(
                self.request_output_cap_tokens,
                field_name="request_output_cap_tokens",
            )
            if self.effective_output_cap_tokens != self.request_output_cap_tokens:
                raise ValueError(
                    "effective_output_cap_tokens must equal request_output_cap_tokens "
                    "when an explicit request output cap is present"
                )
        if self.reserved_total_tokens <= self.effective_output_cap_tokens:
            raise ValueError(
                "reserved_total_tokens must include input plus effective output cap"
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
        estimated_input_tokens: int,
        estimated_output_tokens: int,
        tokens_remaining: int,
        hard_output_limit_tokens: int,
    ) -> RequestOutputCapDecision:
        _require_positive_int(
            estimated_input_tokens,
            field_name="estimated_input_tokens",
        )
        _require_non_negative_int(
            estimated_output_tokens,
            field_name="estimated_output_tokens",
        )
        _require_non_negative_int(tokens_remaining, field_name="tokens_remaining")
        _require_positive_int(
            hard_output_limit_tokens,
            field_name="hard_output_limit_tokens",
        )
        if (
            self.provider_profile.provider_default_output_cap_tokens
            > hard_output_limit_tokens
        ):
            raise ValueError(
                "provider_default_output_cap_tokens must not exceed "
                "hard_output_limit_tokens"
            )

        available_output_cap_tokens = (
            tokens_remaining
            - estimated_input_tokens
            - self.provider_profile.request_safety_gap_tokens
        )
        minimum_explicit_cap_tokens = max(
            self.provider_profile.provider_default_output_cap_tokens,
            estimated_output_tokens,
        )

        request_output_cap_tokens: int | None = None
        if available_output_cap_tokens >= minimum_explicit_cap_tokens:
            candidate_cap = min(
                available_output_cap_tokens,
                hard_output_limit_tokens,
            )
            if candidate_cap >= minimum_explicit_cap_tokens:
                request_output_cap_tokens = candidate_cap

        effective_output_cap_tokens = (
            request_output_cap_tokens
            if request_output_cap_tokens is not None
            else self.provider_profile.provider_default_output_cap_tokens
        )
        return RequestOutputCapDecision(
            effective_output_cap_tokens=effective_output_cap_tokens,
            request_output_cap_tokens=request_output_cap_tokens,
            reserved_total_tokens=estimated_input_tokens + effective_output_cap_tokens,
        )


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
