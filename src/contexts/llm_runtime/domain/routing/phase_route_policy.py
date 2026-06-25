from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PhaseRouteKind(StrEnum):
    PRIMARY = "primary"
    AUTOMATIC_FALLBACK = "automatic_fallback"
    MANUAL_FALLBACK = "manual_fallback"
    SPECIAL = "special"


class PhaseRouteReason(StrEnum):
    NORMAL = "normal"
    DAILY_LIMIT_EXHAUSTED = "daily_limit_exhausted"
    MINUTE_CAPACITY_EXHAUSTED = "minute_capacity_exhausted"
    INPUT_TOO_LARGE = "input_too_large"
    OUTPUT_TOO_LARGE = "output_too_large"
    TRUNCATED_JSON = "truncated_json"
    EMPTY_CLAIMS_VALIDATION = "empty_claims_validation"
    VALIDATION_RETRY = "validation_retry"
    USER_CONFIRMED_DEGRADED = "user_confirmed_degraded"


class PhaseRouteActivationScope(StrEnum):
    PHASE = "phase"
    WORK_ITEM = "work_item"
    RETRY_GROUP = "retry_group"


class PhaseRouteActivationStatus(StrEnum):
    ACTIVE = "active"
    WAITING_CAPACITY = "waiting_capacity"
    WAITING_USER_CHOICE = "waiting_user_choice"
    EXHAUSTED = "exhausted"
    PAUSED = "paused"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class PhaseRouteRule:
    route_ref: str
    route_kind: PhaseRouteKind
    route_reason: PhaseRouteReason
    model_ref: str
    activation_scope: PhaseRouteActivationScope
    requires_user_confirmation: bool = False

    def __post_init__(self) -> None:
        _require_non_empty_text(self.route_ref, "route_ref")
        _require_non_empty_text(self.model_ref, "model_ref")
        if not isinstance(self.route_kind, PhaseRouteKind):
            raise TypeError("route_kind must be PhaseRouteKind")
        if not isinstance(self.route_reason, PhaseRouteReason):
            raise TypeError("route_reason must be PhaseRouteReason")
        if not isinstance(self.activation_scope, PhaseRouteActivationScope):
            raise TypeError("activation_scope must be PhaseRouteActivationScope")
        if not isinstance(self.requires_user_confirmation, bool):
            raise TypeError("requires_user_confirmation must be bool")
        if (
            self.route_kind is PhaseRouteKind.MANUAL_FALLBACK
            and not self.requires_user_confirmation
        ):
            raise ValueError("manual fallback routes must require user confirmation")
        if (
            self.route_kind is PhaseRouteKind.PRIMARY
            and self.route_reason is not PhaseRouteReason.NORMAL
        ):
            raise ValueError("primary route reason must be normal")


@dataclass(frozen=True, slots=True)
class PhaseRoutePolicy:
    phase: str
    work_kind: str
    routes: tuple[PhaseRouteRule, ...]

    def __post_init__(self) -> None:
        _require_non_empty_text(self.phase, "phase")
        _require_non_empty_text(self.work_kind, "work_kind")
        if not isinstance(self.routes, tuple):
            raise TypeError("routes must be tuple")
        if not self.routes:
            raise ValueError("routes must be non-empty")
        for route in self.routes:
            if not isinstance(route, PhaseRouteRule):
                raise TypeError("routes must contain PhaseRouteRule")

        route_refs = tuple(route.route_ref for route in self.routes)
        if len(set(route_refs)) != len(route_refs):
            raise ValueError("route_ref values must be unique")

        primary_routes = tuple(
            route for route in self.routes if route.route_kind is PhaseRouteKind.PRIMARY
        )
        if len(primary_routes) != 1:
            raise ValueError(
                "phase route policy must contain exactly one primary route"
            )

    def primary_route(self) -> PhaseRouteRule:
        return next(
            route for route in self.routes if route.route_kind is PhaseRouteKind.PRIMARY
        )

    def automatic_fallback_routes(self) -> tuple[PhaseRouteRule, ...]:
        return tuple(
            route
            for route in self.routes
            if route.route_kind is PhaseRouteKind.AUTOMATIC_FALLBACK
        )

    def manual_fallback_routes(self) -> tuple[PhaseRouteRule, ...]:
        return tuple(
            route
            for route in self.routes
            if route.route_kind is PhaseRouteKind.MANUAL_FALLBACK
        )

    def special_routes_for_reason(
        self,
        reason: PhaseRouteReason,
    ) -> tuple[PhaseRouteRule, ...]:
        if not isinstance(reason, PhaseRouteReason):
            raise TypeError("reason must be PhaseRouteReason")
        return tuple(
            route
            for route in self.routes
            if route.route_kind is PhaseRouteKind.SPECIAL
            and route.route_reason is reason
        )


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
