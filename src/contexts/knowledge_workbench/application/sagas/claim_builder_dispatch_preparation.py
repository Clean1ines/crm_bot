from __future__ import annotations

from dataclasses import dataclass, field

from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelRouteCatalog,
    default_groq_llm_model_route_catalog,
)

CLAIM_BUILDER_DISPATCH_PROFILE_ID = "faq_claim_observations"
CLAIM_BUILDER_DISPATCH_ESTIMATED_PROMPT_TOKENS = 3000
CLAIM_BUILDER_DISPATCH_ESTIMATED_COMPLETION_TOKENS = 500
CLAIM_BUILDER_DISPATCH_PROVIDER = "groq"
CLAIM_BUILDER_DISPATCH_ACCOUNT_REF = "groq_org_primary"
CLAIM_BUILDER_DISPATCH_WORKER_REF = "knowledge-workbench-claim-builder-dispatch"
CLAIM_BUILDER_DISPATCH_LEASE_TTL_SECONDS = 300


@dataclass(frozen=True, slots=True)
class ClaimBuilderDispatchAccountCapacity:
    provider: str
    account_ref: str
    model_ref: str
    remaining_minute_requests: int
    remaining_minute_tokens: int
    remaining_daily_requests: int
    remaining_daily_tokens: int

    def __post_init__(self) -> None:
        _require_non_empty_text(self.provider, "provider")
        _require_non_empty_text(self.account_ref, "account_ref")
        _require_non_empty_text(self.model_ref, "model_ref")
        for field_name, value in (
            ("remaining_minute_requests", self.remaining_minute_requests),
            ("remaining_minute_tokens", self.remaining_minute_tokens),
            ("remaining_daily_requests", self.remaining_daily_requests),
            ("remaining_daily_tokens", self.remaining_daily_tokens),
        ):
            _require_non_negative_int(value, field_name)

    def to_payload(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "account_ref": self.account_ref,
            "model_ref": self.model_ref,
            "remaining_minute_requests": self.remaining_minute_requests,
            "remaining_minute_tokens": self.remaining_minute_tokens,
            "remaining_daily_requests": self.remaining_daily_requests,
            "remaining_daily_tokens": self.remaining_daily_tokens,
        }


@dataclass(frozen=True, slots=True)
class ClaimBuilderDispatchPreparation:
    profile_id: str
    estimated_prompt_tokens: int
    estimated_completion_tokens: int
    estimated_requests: int
    account_capacities: tuple[ClaimBuilderDispatchAccountCapacity, ...]
    active_model_ref: str
    requested_items: int
    worker_ref: str
    lease_token_prefix: str
    lease_ttl_seconds: int

    def __post_init__(self) -> None:
        _require_non_empty_text(self.profile_id, "profile_id")
        _require_positive_int(
            self.estimated_prompt_tokens,
            "estimated_prompt_tokens",
        )
        _require_non_negative_int(
            self.estimated_completion_tokens,
            "estimated_completion_tokens",
        )
        _require_positive_int(self.estimated_requests, "estimated_requests")
        if not isinstance(self.account_capacities, tuple):
            raise TypeError("account_capacities must be tuple")
        if not self.account_capacities:
            raise ValueError("account_capacities must be non-empty")
        for account_capacity in self.account_capacities:
            if not isinstance(
                account_capacity,
                ClaimBuilderDispatchAccountCapacity,
            ):
                raise TypeError(
                    "account_capacities must contain ClaimBuilderDispatchAccountCapacity"
                )
        _require_non_empty_text(self.active_model_ref, "active_model_ref")
        _require_positive_int(self.requested_items, "requested_items")
        _require_non_empty_text(self.worker_ref, "worker_ref")
        _require_non_empty_text(self.lease_token_prefix, "lease_token_prefix")
        _require_positive_int(self.lease_ttl_seconds, "lease_ttl_seconds")

    def to_payload(self) -> dict[str, object]:
        return {
            "profile": {
                "profile_id": self.profile_id,
                "estimated_prompt_tokens": self.estimated_prompt_tokens,
                "estimated_completion_tokens": self.estimated_completion_tokens,
                "estimated_requests": self.estimated_requests,
            },
            "account_capacities": [
                account_capacity.to_payload()
                for account_capacity in self.account_capacities
            ],
            "active_model_ref": self.active_model_ref,
            "requested_items": self.requested_items,
            "worker_ref": self.worker_ref,
            "lease_token_prefix": self.lease_token_prefix,
            "lease_ttl_seconds": self.lease_ttl_seconds,
        }


@dataclass(frozen=True, slots=True)
class ClaimBuilderDispatchPreparationBuilder:
    route_catalog: LlmModelRouteCatalog = field(
        default_factory=default_groq_llm_model_route_catalog,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.route_catalog, LlmModelRouteCatalog):
            raise TypeError("route_catalog must be LlmModelRouteCatalog")

    def build_payload(
        self,
        *,
        workflow_run_id: str,
        scheduled_work_item_count: int,
    ) -> dict[str, object]:
        _require_non_empty_text(workflow_run_id, "workflow_run_id")
        _require_positive_int(
            scheduled_work_item_count,
            "scheduled_work_item_count",
        )

        active_model_ref = self.route_catalog.primary_model_ref()
        estimated_total_tokens = (
            CLAIM_BUILDER_DISPATCH_ESTIMATED_PROMPT_TOKENS
            + CLAIM_BUILDER_DISPATCH_ESTIMATED_COMPLETION_TOKENS
        )

        preparation = ClaimBuilderDispatchPreparation(
            profile_id=CLAIM_BUILDER_DISPATCH_PROFILE_ID,
            estimated_prompt_tokens=CLAIM_BUILDER_DISPATCH_ESTIMATED_PROMPT_TOKENS,
            estimated_completion_tokens=(
                CLAIM_BUILDER_DISPATCH_ESTIMATED_COMPLETION_TOKENS
            ),
            estimated_requests=1,
            account_capacities=(
                ClaimBuilderDispatchAccountCapacity(
                    provider=CLAIM_BUILDER_DISPATCH_PROVIDER,
                    account_ref=CLAIM_BUILDER_DISPATCH_ACCOUNT_REF,
                    model_ref=active_model_ref,
                    remaining_minute_requests=scheduled_work_item_count,
                    remaining_minute_tokens=(
                        estimated_total_tokens * scheduled_work_item_count
                    ),
                    remaining_daily_requests=scheduled_work_item_count,
                    remaining_daily_tokens=(
                        estimated_total_tokens * scheduled_work_item_count
                    ),
                ),
            ),
            active_model_ref=active_model_ref,
            requested_items=scheduled_work_item_count,
            worker_ref=CLAIM_BUILDER_DISPATCH_WORKER_REF,
            lease_token_prefix=f"claim-builder-dispatch:{workflow_run_id}",
            lease_ttl_seconds=CLAIM_BUILDER_DISPATCH_LEASE_TTL_SECONDS,
        )
        return preparation.to_payload()


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
