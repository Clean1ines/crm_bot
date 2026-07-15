from __future__ import annotations

from collections.abc import Mapping

from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile


CANONICAL_LLM_BUDGET_CONTRACT_VERSION = "v3"
RESERVED_LLM_CAPACITY_ESTIMATE_KEYS = frozenset(
    {
        "budget_contract_version",
        "provider",
        "model_ref",
        "model_tpm_limit",
        "phase",
        "operation",
        "estimator",
        "prompt_tokens",
        "artifact_tokens",
        "input_tokens",
        "planned_output_tokens",
        "safety_gap_tokens",
        "required_window_tokens",
    }
)


def build_llm_capacity_estimate_payload(
    *,
    model_profile: ModelProfile,
    phase: str,
    operation: str,
    estimator: str,
    prompt_tokens: int,
    artifact_tokens: int,
    input_tokens: int,
    planned_output_tokens: int,
    safety_gap_tokens: int,
    metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if not isinstance(model_profile, ModelProfile):
        raise TypeError("model_profile must be ModelProfile")
    _require_non_empty_text(phase, field_name="phase")
    _require_non_empty_text(operation, field_name="operation")
    _require_non_empty_text(estimator, field_name="estimator")
    _require_non_negative_int(prompt_tokens, field_name="prompt_tokens")
    _require_non_negative_int(artifact_tokens, field_name="artifact_tokens")
    _require_positive_int(input_tokens, field_name="input_tokens")
    _require_non_negative_int(
        planned_output_tokens,
        field_name="planned_output_tokens",
    )
    _require_non_negative_int(safety_gap_tokens, field_name="safety_gap_tokens")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError("metadata must be Mapping when provided")
    if metadata is not None:
        reserved_metadata_keys = RESERVED_LLM_CAPACITY_ESTIMATE_KEYS.intersection(
            metadata
        )
        if reserved_metadata_keys:
            raise ValueError(
                "metadata must not override reserved LLM capacity estimate keys: "
                + ", ".join(sorted(reserved_metadata_keys))
            )

    model_tpm_limit = model_profile.rate_limits.tokens_per_minute
    _require_positive_int(model_tpm_limit, field_name="model_tpm_limit")

    payload: dict[str, object] = {
        "budget_contract_version": CANONICAL_LLM_BUDGET_CONTRACT_VERSION,
        "provider": model_profile.provider_id.value,
        "model_ref": model_profile.model_id.value,
        "model_tpm_limit": model_tpm_limit,
        "phase": phase,
        "operation": operation,
        "estimator": estimator,
        "prompt_tokens": prompt_tokens,
        "artifact_tokens": artifact_tokens,
        "input_tokens": input_tokens,
        "planned_output_tokens": planned_output_tokens,
        "safety_gap_tokens": safety_gap_tokens,
        "required_window_tokens": (
            input_tokens + planned_output_tokens + safety_gap_tokens
        ),
    }
    if metadata is not None:
        payload.update(dict(metadata))
    return payload


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_positive_int(value: object, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
