from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.contexts.knowledge_workbench.application.sagas.claim_builder_source_ingestion_budget import (
    claim_builder_artifact_tokens,
)


@dataclass(frozen=True, slots=True)
class ProviderMessageCapacityEstimate:
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_total_tokens: int

    def __post_init__(self) -> None:
        _require_positive_int(
            self.estimated_input_tokens,
            field_name="estimated_input_tokens",
        )
        _require_non_negative_int(
            self.estimated_output_tokens,
            field_name="estimated_output_tokens",
        )
        _require_positive_int(
            self.estimated_total_tokens,
            field_name="estimated_total_tokens",
        )
        if self.estimated_total_tokens != (
            self.estimated_input_tokens + self.estimated_output_tokens
        ):
            raise ValueError(
                "estimated_total_tokens must equal input plus estimated output",
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "estimator": "claim_builder_primary_model_char_multiplier_actual_provider_messages",
            "estimated_input_tokens": self.estimated_input_tokens,
            "estimated_output_tokens": self.estimated_output_tokens,
            "estimated_total_tokens": self.estimated_total_tokens,
        }


def estimate_provider_message_capacity(
    *,
    provider_messages: tuple[Mapping[str, str], ...],
) -> ProviderMessageCapacityEstimate:
    if not isinstance(provider_messages, tuple) or not provider_messages:
        raise ValueError("provider_messages must be non-empty tuple")

    estimated_input_tokens = 0
    for message in provider_messages:
        if not isinstance(message, Mapping):
            raise TypeError("provider_messages must contain mappings")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("provider message content must be non-empty")
        estimated_input_tokens += claim_builder_artifact_tokens(content)

    estimated_output_tokens = max(1024, min(4096, estimated_input_tokens))
    return ProviderMessageCapacityEstimate(
        estimated_input_tokens=estimated_input_tokens,
        estimated_output_tokens=estimated_output_tokens,
        estimated_total_tokens=estimated_input_tokens + estimated_output_tokens,
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
