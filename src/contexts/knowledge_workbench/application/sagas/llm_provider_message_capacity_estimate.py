from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.contexts.knowledge_workbench.document_segmentation.domain.segmentation_budget import (
    estimate_tokens_roughly,
)


@dataclass(frozen=True, slots=True)
class ProviderMessageCapacityEstimate:
    input_tokens: int
    planned_output_tokens: int
    safety_gap_tokens: int
    required_window_tokens: int

    def __post_init__(self) -> None:
        _require_positive_int(
            self.input_tokens,
            field_name="input_tokens",
        )
        _require_non_negative_int(
            self.planned_output_tokens,
            field_name="planned_output_tokens",
        )
        _require_non_negative_int(
            self.safety_gap_tokens,
            field_name="safety_gap_tokens",
        )
        _require_positive_int(
            self.required_window_tokens,
            field_name="required_window_tokens",
        )
        if self.required_window_tokens != (
            self.input_tokens + self.planned_output_tokens + self.safety_gap_tokens
        ):
            raise ValueError(
                "required_window_tokens must equal input plus planned output plus safety gap",
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "budget_contract_version": "v3",
            "estimator": "rough_char_div_4_actual_provider_messages",
            "input_tokens": self.input_tokens,
            "planned_output_tokens": self.planned_output_tokens,
            "safety_gap_tokens": self.safety_gap_tokens,
            "required_window_tokens": self.required_window_tokens,
        }


def estimate_provider_message_capacity(
    *,
    provider_messages: tuple[Mapping[str, str], ...],
) -> ProviderMessageCapacityEstimate:
    if not isinstance(provider_messages, tuple) or not provider_messages:
        raise ValueError("provider_messages must be non-empty tuple")

    input_tokens = 0
    for message in provider_messages:
        if not isinstance(message, Mapping):
            raise TypeError("provider_messages must contain mappings")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("provider message content must be non-empty")
        input_tokens += max(1, estimate_tokens_roughly(content))

    planned_output_tokens = max(1024, min(4096, input_tokens))
    safety_gap_tokens = 300
    return ProviderMessageCapacityEstimate(
        input_tokens=input_tokens,
        planned_output_tokens=planned_output_tokens,
        safety_gap_tokens=safety_gap_tokens,
        required_window_tokens=input_tokens + planned_output_tokens + safety_gap_tokens,
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
