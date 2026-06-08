from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from src.contexts.llm_runtime.application.policies.llm_route_planning_policy import (
    LlmRouteCandidate,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.entities.provider_account import ProviderAccount
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute


@dataclass(frozen=True, slots=True)
class LlmRouteAvailability:
    minute_capacity_available: bool = True
    daily_capacity_available: bool = True
    unavailable_until: datetime | None = None

    def __post_init__(self) -> None:
        if self.unavailable_until is not None:
            if (
                self.unavailable_until.tzinfo is None
                or self.unavailable_until.utcoffset() is None
            ):
                raise ValueError("unavailable_until must be timezone-aware")


class LlmRouteCandidateBuilder:
    """Build route candidates from provider-neutral model/account catalog data."""

    def build_candidates(
        self,
        *,
        models: tuple[ModelProfile, ...],
        accounts: tuple[ProviderAccount, ...],
        availability_by_route: Mapping[LlmRoute, LlmRouteAvailability] | None = None,
    ) -> tuple[LlmRouteCandidate, ...]:
        availability_by_route = availability_by_route or {}
        candidates: list[LlmRouteCandidate] = []

        for model in models:
            if not model.enabled:
                continue

            for account in accounts:
                if not account.enabled:
                    continue

                if account.provider_id != model.provider_id:
                    continue

                route = LlmRoute(
                    provider_id=model.provider_id,
                    model_id=model.model_id,
                    account_ref=account.account_ref,
                )
                availability = availability_by_route.get(route, LlmRouteAvailability())

                candidates.append(
                    LlmRouteCandidate(
                        route=route,
                        context_window_tokens=model.context_window_tokens,
                        max_output_tokens=model.max_output_tokens,
                        model_rank=model.model_rank,
                        account_rank=account.account_rank,
                        minute_capacity_available=availability.minute_capacity_available,
                        daily_capacity_available=availability.daily_capacity_available,
                        unavailable_until=availability.unavailable_until,
                    ),
                )

        return tuple(
            sorted(
                candidates,
                key=lambda candidate: (
                    candidate.model_rank,
                    candidate.account_rank,
                    candidate.route.provider_id.value,
                    candidate.route.model_id.value,
                    candidate.route.account_ref.value,
                ),
            ),
        )
