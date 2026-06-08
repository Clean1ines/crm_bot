from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute


class LlmRoutePlanDecisionKind(StrEnum):
    USE_ROUTE = "use_route"
    RETRY_SAME_ROUTE = "retry_same_route"
    WAIT_UNTIL = "wait_until"
    SPLIT_REQUIRED = "split_required"
    DAILY_EXHAUSTED = "daily_exhausted"
    TERMINAL_FAILURE = "terminal_failure"


@dataclass(frozen=True, slots=True)
class LlmRouteCandidate:
    route: LlmRoute
    context_window_tokens: int
    max_output_tokens: int
    model_rank: int
    account_rank: int
    minute_capacity_available: bool = True
    daily_capacity_available: bool = True
    unavailable_until: datetime | None = None

    def __post_init__(self) -> None:
        if self.context_window_tokens <= 0:
            raise ValueError("context_window_tokens must be > 0")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be > 0")
        if self.model_rank < 0:
            raise ValueError("model_rank must be >= 0")
        if self.account_rank < 0:
            raise ValueError("account_rank must be >= 0")
        if self.unavailable_until is not None:
            if (
                self.unavailable_until.tzinfo is None
                or self.unavailable_until.utcoffset() is None
            ):
                raise ValueError("unavailable_until must be timezone-aware")

    @property
    def available_now(self) -> bool:
        return self.minute_capacity_available and self.daily_capacity_available


@dataclass(frozen=True, slots=True)
class LlmRoutePlanDecision:
    kind: LlmRoutePlanDecisionKind
    error_kind: LlmErrorKind
    route: LlmRoute | None = None
    wait_until: datetime | None = None

    def __post_init__(self) -> None:
        if self.kind is LlmRoutePlanDecisionKind.USE_ROUTE and self.route is None:
            raise ValueError("USE_ROUTE decision must carry route")
        if (
            self.kind is not LlmRoutePlanDecisionKind.USE_ROUTE
            and self.route is not None
        ):
            raise ValueError("Only USE_ROUTE decision may carry route")

        if self.kind is LlmRoutePlanDecisionKind.WAIT_UNTIL:
            if self.wait_until is None:
                raise ValueError("WAIT_UNTIL decision must carry wait_until")
            if self.wait_until.tzinfo is None or self.wait_until.utcoffset() is None:
                raise ValueError("wait_until must be timezone-aware")
        if (
            self.kind is not LlmRoutePlanDecisionKind.WAIT_UNTIL
            and self.wait_until is not None
        ):
            raise ValueError("Only WAIT_UNTIL decision may carry wait_until")


class LlmRoutePlanningPolicy:
    """Provider-neutral route planning policy.

    The policy decides only how to move across already known route candidates.
    It does not know concrete provider adapters or business workflow state.
    """

    def decide(
        self,
        error_kind: LlmErrorKind,
        *,
        current_route: LlmRoute,
        candidates: tuple[LlmRouteCandidate, ...],
    ) -> LlmRoutePlanDecision:
        current_candidate = self._find_current_candidate(
            current_route=current_route,
            candidates=candidates,
        )

        if error_kind is LlmErrorKind.AUTH_ERROR:
            return LlmRoutePlanDecision(
                kind=LlmRoutePlanDecisionKind.TERMINAL_FAILURE,
                error_kind=error_kind,
            )

        if error_kind is LlmErrorKind.REQUEST_TOO_LARGE:
            return self._larger_context_route_or_split(
                error_kind=error_kind,
                current_candidate=current_candidate,
                candidates=candidates,
            )

        if error_kind is LlmErrorKind.OUTPUT_TOO_LARGE:
            return self._larger_output_route_or_split(
                error_kind=error_kind,
                current_candidate=current_candidate,
                candidates=candidates,
            )

        if error_kind is LlmErrorKind.MINUTE_LIMIT:
            return self._same_model_other_account_or_wait(
                error_kind=error_kind,
                current_candidate=current_candidate,
                candidates=candidates,
            )

        if error_kind is LlmErrorKind.DAILY_LIMIT:
            return self._same_model_other_account_then_other_model_or_exhausted(
                error_kind=error_kind,
                current_candidate=current_candidate,
                candidates=candidates,
            )

        return LlmRoutePlanDecision(
            kind=LlmRoutePlanDecisionKind.RETRY_SAME_ROUTE,
            error_kind=error_kind,
        )

    def _larger_context_route_or_split(
        self,
        *,
        error_kind: LlmErrorKind,
        current_candidate: LlmRouteCandidate,
        candidates: tuple[LlmRouteCandidate, ...],
    ) -> LlmRoutePlanDecision:
        larger_candidates = tuple(
            candidate
            for candidate in candidates
            if candidate.available_now
            and candidate.context_window_tokens
            > current_candidate.context_window_tokens
        )

        selected = self._prefer_same_account_then_rank(
            current_candidate=current_candidate,
            candidates=larger_candidates,
        )

        if selected is None:
            return LlmRoutePlanDecision(
                kind=LlmRoutePlanDecisionKind.SPLIT_REQUIRED,
                error_kind=error_kind,
            )

        return LlmRoutePlanDecision(
            kind=LlmRoutePlanDecisionKind.USE_ROUTE,
            error_kind=error_kind,
            route=selected.route,
        )

    def _larger_output_route_or_split(
        self,
        *,
        error_kind: LlmErrorKind,
        current_candidate: LlmRouteCandidate,
        candidates: tuple[LlmRouteCandidate, ...],
    ) -> LlmRoutePlanDecision:
        larger_candidates = tuple(
            candidate
            for candidate in candidates
            if candidate.available_now
            and candidate.max_output_tokens > current_candidate.max_output_tokens
        )

        selected = self._prefer_same_account_then_rank(
            current_candidate=current_candidate,
            candidates=larger_candidates,
        )

        if selected is None:
            return LlmRoutePlanDecision(
                kind=LlmRoutePlanDecisionKind.SPLIT_REQUIRED,
                error_kind=error_kind,
            )

        return LlmRoutePlanDecision(
            kind=LlmRoutePlanDecisionKind.USE_ROUTE,
            error_kind=error_kind,
            route=selected.route,
        )

    def _same_model_other_account_or_wait(
        self,
        *,
        error_kind: LlmErrorKind,
        current_candidate: LlmRouteCandidate,
        candidates: tuple[LlmRouteCandidate, ...],
    ) -> LlmRoutePlanDecision:
        same_model_other_accounts = tuple(
            candidate
            for candidate in candidates
            if candidate.available_now
            and candidate.route.provider_id == current_candidate.route.provider_id
            and candidate.route.model_id == current_candidate.route.model_id
            and candidate.route.account_ref != current_candidate.route.account_ref
        )

        selected = self._lowest_account_rank(same_model_other_accounts)

        if selected is not None:
            return LlmRoutePlanDecision(
                kind=LlmRoutePlanDecisionKind.USE_ROUTE,
                error_kind=error_kind,
                route=selected.route,
            )

        nearest_wait_until = self._nearest_unavailable_until(candidates)

        if nearest_wait_until is None:
            return LlmRoutePlanDecision(
                kind=LlmRoutePlanDecisionKind.RETRY_SAME_ROUTE,
                error_kind=error_kind,
            )

        return LlmRoutePlanDecision(
            kind=LlmRoutePlanDecisionKind.WAIT_UNTIL,
            error_kind=error_kind,
            wait_until=nearest_wait_until,
        )

    def _same_model_other_account_then_other_model_or_exhausted(
        self,
        *,
        error_kind: LlmErrorKind,
        current_candidate: LlmRouteCandidate,
        candidates: tuple[LlmRouteCandidate, ...],
    ) -> LlmRoutePlanDecision:
        same_model_other_accounts = tuple(
            candidate
            for candidate in candidates
            if candidate.available_now
            and candidate.route.provider_id == current_candidate.route.provider_id
            and candidate.route.model_id == current_candidate.route.model_id
            and candidate.route.account_ref != current_candidate.route.account_ref
        )

        selected = self._lowest_account_rank(same_model_other_accounts)

        if selected is not None:
            return LlmRoutePlanDecision(
                kind=LlmRoutePlanDecisionKind.USE_ROUTE,
                error_kind=error_kind,
                route=selected.route,
            )

        other_models = tuple(
            candidate
            for candidate in candidates
            if candidate.available_now
            and candidate.route.provider_id == current_candidate.route.provider_id
            and candidate.route.model_id != current_candidate.route.model_id
        )

        selected = self._lowest_model_then_account_rank(other_models)

        if selected is not None:
            return LlmRoutePlanDecision(
                kind=LlmRoutePlanDecisionKind.USE_ROUTE,
                error_kind=error_kind,
                route=selected.route,
            )

        return LlmRoutePlanDecision(
            kind=LlmRoutePlanDecisionKind.DAILY_EXHAUSTED,
            error_kind=error_kind,
        )

    def _find_current_candidate(
        self,
        *,
        current_route: LlmRoute,
        candidates: tuple[LlmRouteCandidate, ...],
    ) -> LlmRouteCandidate:
        for candidate in candidates:
            if candidate.route == current_route:
                return candidate

        raise ValueError("current_route must be present in candidates")

    def _prefer_same_account_then_rank(
        self,
        *,
        current_candidate: LlmRouteCandidate,
        candidates: tuple[LlmRouteCandidate, ...],
    ) -> LlmRouteCandidate | None:
        same_account = tuple(
            candidate
            for candidate in candidates
            if candidate.route.provider_id == current_candidate.route.provider_id
            and candidate.route.account_ref == current_candidate.route.account_ref
        )

        selected = self._lowest_model_then_account_rank(same_account)

        if selected is not None:
            return selected

        return self._lowest_model_then_account_rank(candidates)

    def _lowest_account_rank(
        self,
        candidates: tuple[LlmRouteCandidate, ...],
    ) -> LlmRouteCandidate | None:
        if not candidates:
            return None
        return min(candidates, key=lambda candidate: candidate.account_rank)

    def _lowest_model_then_account_rank(
        self,
        candidates: tuple[LlmRouteCandidate, ...],
    ) -> LlmRouteCandidate | None:
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda candidate: (candidate.model_rank, candidate.account_rank),
        )

    def _nearest_unavailable_until(
        self,
        candidates: tuple[LlmRouteCandidate, ...],
    ) -> datetime | None:
        waits = tuple(
            candidate.unavailable_until
            for candidate in candidates
            if candidate.unavailable_until is not None
        )

        if not waits:
            return None

        return min(waits)
