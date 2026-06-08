from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from src.contexts.llm_runtime.application.policies.llm_quota_availability_policy import (
    LlmEstimatedTokenNeed,
    LlmQuotaAvailabilityPolicy,
    LlmQuotaSnapshot,
)
from src.contexts.llm_runtime.application.policies.llm_route_candidate_builder import (
    LlmRouteCandidateBuilder,
)
from src.contexts.llm_runtime.application.policies.llm_route_planning_policy import (
    LlmRouteCandidate,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.entities.provider_account import ProviderAccount
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute


@dataclass(frozen=True, slots=True)
class PrepareLlmRouteCandidatesCommand:
    models: tuple[ModelProfile, ...]
    accounts: tuple[ProviderAccount, ...]
    estimated_need: LlmEstimatedTokenNeed
    quota_snapshots_by_route: Mapping[LlmRoute, LlmQuotaSnapshot]


class LlmRouteCandidatePreparationPolicy:
    """Prepare route candidates from catalog data and quota snapshots.

    This policy is intentionally provider-neutral. Provider adapters or seed
    modules may supply model/account data, but this policy only composes generic
    LLM Runtime policies.
    """

    def __init__(
        self,
        *,
        candidate_builder: LlmRouteCandidateBuilder | None = None,
    ) -> None:
        self._candidate_builder = candidate_builder or LlmRouteCandidateBuilder()

    def prepare(
        self,
        command: PrepareLlmRouteCandidatesCommand,
    ) -> tuple[LlmRouteCandidate, ...]:
        candidate_routes = self._candidate_builder.build_candidates(
            models=command.models,
            accounts=command.accounts,
        )

        availability_by_route = LlmQuotaAvailabilityPolicy(
            snapshots_by_route=command.quota_snapshots_by_route,
        ).build_availability_by_route(
            routes=tuple(candidate.route for candidate in candidate_routes),
            estimated_need=command.estimated_need,
        )

        return self._candidate_builder.build_candidates(
            models=command.models,
            accounts=command.accounts,
            availability_by_route=availability_by_route,
        )
