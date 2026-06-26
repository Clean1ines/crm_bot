from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LlmPhaseOperationProfile:
    phase: str
    operation: str
    provider_id: str
    primary_model_ref: str
    prompt_id: str
    prompt_version: str
    input_artifact_kind: str
    output_artifact_kind: str
    batching_strategy: str
    fallback_model_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty_text(self.phase, field_name="phase")
        _require_non_empty_text(self.operation, field_name="operation")
        _require_non_empty_text(self.provider_id, field_name="provider_id")
        _require_non_empty_text(self.primary_model_ref, field_name="primary_model_ref")
        _require_non_empty_text(self.prompt_id, field_name="prompt_id")
        _require_non_empty_text(self.prompt_version, field_name="prompt_version")
        _require_non_empty_text(
            self.input_artifact_kind,
            field_name="input_artifact_kind",
        )
        _require_non_empty_text(
            self.output_artifact_kind,
            field_name="output_artifact_kind",
        )
        _require_non_empty_text(self.batching_strategy, field_name="batching_strategy")
        if not isinstance(self.fallback_model_refs, tuple):
            raise TypeError("fallback_model_refs must be tuple")
        for model_ref in self.fallback_model_refs:
            _require_non_empty_text(model_ref, field_name="fallback_model_refs")

    @property
    def operation_key(self) -> str:
        return f"{self.phase}.{self.operation}"


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
