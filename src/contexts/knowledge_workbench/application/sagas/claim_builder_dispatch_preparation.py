from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    DueWorkItemRecord,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile


CLAIM_BUILDER_DISPATCH_PROFILE_ID = "faq_claim_observations.real_due_batch"


@dataclass(frozen=True, slots=True)
class ClaimBuilderDispatchPreparation:
    profile: LlmTaskCapacityProfile
    account_capacities: tuple[LlmProviderAccountCapacity, ...]
    active_model_ref: str
    requested_items: int

    def __post_init__(self) -> None:
        if not isinstance(self.profile, LlmTaskCapacityProfile):
            raise TypeError("profile must be LlmTaskCapacityProfile")
        if (
            not isinstance(self.account_capacities, tuple)
            or not self.account_capacities
        ):
            raise ValueError("account_capacities must be non-empty tuple")
        for account_capacity in self.account_capacities:
            if not isinstance(account_capacity, LlmProviderAccountCapacity):
                raise TypeError(
                    "account_capacities must contain LlmProviderAccountCapacity",
                )
        _require_non_empty_text(self.active_model_ref, field_name="active_model_ref")
        _require_positive_int(self.requested_items, field_name="requested_items")

    def to_payload(self) -> dict[str, object]:
        return {
            "profile": {
                "profile_id": self.profile.profile_id,
                "estimated_prompt_tokens": self.profile.estimated_prompt_tokens,
                "estimated_completion_tokens": self.profile.estimated_completion_tokens,
                "estimated_requests": self.profile.estimated_requests,
            },
            "account_capacities": [
                {
                    "provider": account.provider,
                    "account_ref": account.account_ref,
                    "model_ref": account.model_ref,
                    "remaining_minute_requests": account.remaining_minute_requests,
                    "remaining_minute_tokens": account.remaining_minute_tokens,
                    "remaining_daily_requests": account.remaining_daily_requests,
                    "remaining_daily_tokens": account.remaining_daily_tokens,
                }
                for account in self.account_capacities
            ],
            "active_model_ref": self.active_model_ref,
            "requested_items": self.requested_items,
        }


@dataclass(frozen=True, slots=True)
class ClaimBuilderDispatchPreparationBuilder:
    def build_from_due_work_items(
        self,
        *,
        due_work_items: tuple[DueWorkItemRecord, ...],
        active_model_ref: str,
        provider_account_refs: tuple[str, ...],
        model_profiles: tuple[ModelProfile, ...],
    ) -> ClaimBuilderDispatchPreparation:
        _require_non_empty_text(active_model_ref, field_name="active_model_ref")
        _require_non_empty_text_tuple(
            provider_account_refs,
            field_name="provider_account_refs",
        )
        if not due_work_items:
            raise ValueError("due_work_items must be non-empty")

        profile = self.build_profile_from_due_work_items(due_work_items)
        return ClaimBuilderDispatchPreparation(
            profile=profile,
            account_capacities=self.build_account_capacities(
                active_model_ref=active_model_ref,
                provider_account_refs=provider_account_refs,
                model_profiles=model_profiles,
            ),
            active_model_ref=active_model_ref,
            requested_items=len(due_work_items),
        )

    def build_profile_from_due_work_items(
        self,
        due_work_items: tuple[DueWorkItemRecord, ...],
    ) -> LlmTaskCapacityProfile:
        if not due_work_items:
            raise ValueError("due_work_items must be non-empty")

        estimates = tuple(
            _capacity_estimate_from_schedule_payload(record.schedule_payload)
            for record in due_work_items
        )
        return LlmTaskCapacityProfile(
            profile_id=CLAIM_BUILDER_DISPATCH_PROFILE_ID,
            estimated_prompt_tokens=max(
                estimate.estimated_input_tokens for estimate in estimates
            ),
            estimated_completion_tokens=max(
                estimate.estimated_output_tokens for estimate in estimates
            ),
            estimated_requests=1,
        )

    def build_account_capacities(
        self,
        *,
        active_model_ref: str,
        provider_account_refs: tuple[str, ...],
        model_profiles: tuple[ModelProfile, ...],
    ) -> tuple[LlmProviderAccountCapacity, ...]:
        _require_non_empty_text(active_model_ref, field_name="active_model_ref")
        _require_non_empty_text_tuple(
            provider_account_refs,
            field_name="provider_account_refs",
        )

        model_profile = _model_profile_for_ref(
            model_profiles=model_profiles,
            model_ref=active_model_ref,
        )
        limits = model_profile.rate_limits
        remaining_minute_requests = _rate_limit_positive_int(
            limits.requests_per_minute,
            field_name="requests_per_minute",
        )
        remaining_minute_tokens = _rate_limit_positive_int(
            limits.tokens_per_minute,
            field_name="tokens_per_minute",
        )
        remaining_daily_requests = _rate_limit_positive_int(
            limits.requests_per_day,
            field_name="requests_per_day",
        )
        remaining_daily_tokens = _rate_limit_positive_int(
            limits.tokens_per_day,
            field_name="tokens_per_day",
        )

        return tuple(
            LlmProviderAccountCapacity(
                provider="groq",
                account_ref=account_ref,
                model_ref=active_model_ref,
                remaining_minute_requests=remaining_minute_requests,
                remaining_minute_tokens=remaining_minute_tokens,
                remaining_daily_requests=remaining_daily_requests,
                remaining_daily_tokens=remaining_daily_tokens,
            )
            for account_ref in provider_account_refs
        )

    def build_payload(
        self,
        *,
        workflow_run_id: str,
        scheduled_work_item_count: int,
    ) -> dict[str, object]:
        _require_non_empty_text(workflow_run_id, field_name="workflow_run_id")
        _require_positive_int(
            scheduled_work_item_count,
            field_name="scheduled_work_item_count",
        )
        raise ValueError(
            "claim-builder dispatch preparation requires due work item "
            "schedule payload estimates; synthetic scheduled-count payloads "
            "are not allowed",
        )


@dataclass(frozen=True, slots=True)
class _CapacityEstimate:
    estimated_input_tokens: int
    estimated_output_tokens: int


def _capacity_estimate_from_schedule_payload(
    payload: Mapping[str, object],
) -> _CapacityEstimate:
    estimate_payload = payload.get("llm_capacity_estimate")
    if not isinstance(estimate_payload, Mapping):
        raise ValueError("schedule_payload.llm_capacity_estimate is required")

    return _CapacityEstimate(
        estimated_input_tokens=_mapping_positive_int(
            estimate_payload,
            "estimated_input_tokens",
        ),
        estimated_output_tokens=_mapping_non_negative_int(
            estimate_payload,
            "estimated_output_tokens",
        ),
    )


def _model_profile_for_ref(
    *,
    model_profiles: tuple[ModelProfile, ...],
    model_ref: str,
) -> ModelProfile:
    if not isinstance(model_profiles, tuple) or not model_profiles:
        raise ValueError("model_profiles must be non-empty tuple")
    for model_profile in model_profiles:
        if not isinstance(model_profile, ModelProfile):
            raise TypeError("model_profiles must contain ModelProfile")
        if model_profile.model_id.value == model_ref:
            return model_profile
    raise ValueError(f"No ModelProfile found for model_ref: {model_ref}")


def _rate_limit_positive_int(value: int | None, *, field_name: str) -> int:
    if value is None:
        raise ValueError(f"model rate limit {field_name} must be configured")
    _require_positive_int(value, field_name=field_name)
    return value


def _mapping_positive_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{key} must be positive int")
    return value


def _mapping_non_negative_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be non-negative int")
    return value


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_empty_text_tuple(
    value: tuple[str, ...],
    *,
    field_name: str,
) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    if not value:
        raise ValueError(f"{field_name} must be non-empty")
    for item in value:
        _require_non_empty_text(item, field_name=field_name)


def _require_positive_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")
