from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LlmModelRouteRole(StrEnum):
    PRIMARY = "primary"
    AUTOMATIC_FALLBACK = "automatic_fallback"
    DEGRADED_USER_CHOICE = "degraded_user_choice"


@dataclass(frozen=True, slots=True)
class LlmModelRoute:
    model_ref: str
    role: LlmModelRouteRole
    order: int

    def __post_init__(self) -> None:
        _require_non_empty_text(self.model_ref, field_name="model_ref")
        if not isinstance(self.role, LlmModelRouteRole):
            raise TypeError("role must be LlmModelRouteRole")
        if not isinstance(self.order, int):
            raise TypeError("order must be int")
        if self.order < 0:
            raise ValueError("order must be >= 0")


@dataclass(frozen=True, slots=True)
class LlmModelRouteCatalog:
    routes: tuple[LlmModelRoute, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.routes, tuple):
            raise TypeError("routes must be tuple")
        if not self.routes:
            raise ValueError("routes must be non-empty")
        for route in self.routes:
            if not isinstance(route, LlmModelRoute):
                raise TypeError("routes must contain LlmModelRoute")

        model_refs = tuple(route.model_ref for route in self.routes)
        if len(set(model_refs)) != len(model_refs):
            raise ValueError("routes must have unique model_ref")

        orders = tuple(route.order for route in self.routes)
        if len(set(orders)) != len(orders):
            raise ValueError("routes must have unique order")

        primary_routes = self._routes_with_role(LlmModelRouteRole.PRIMARY)
        if len(primary_routes) != 1:
            raise ValueError("routes must contain exactly one PRIMARY")

        degraded_routes = self._routes_with_role(
            LlmModelRouteRole.DEGRADED_USER_CHOICE,
        )
        if len(degraded_routes) != 1:
            raise ValueError("routes must contain exactly one DEGRADED_USER_CHOICE")

    def primary_model_ref(self) -> str:
        return self._ordered_routes_with_role(LlmModelRouteRole.PRIMARY)[0].model_ref

    def automatic_fallback_model_refs(self) -> tuple[str, ...]:
        return tuple(
            route.model_ref
            for route in self._ordered_routes_with_role(
                LlmModelRouteRole.AUTOMATIC_FALLBACK,
            )
        )

    def degraded_user_choice_model_ref(self) -> str:
        return self._ordered_routes_with_role(
            LlmModelRouteRole.DEGRADED_USER_CHOICE,
        )[0].model_ref

    def route_for_model_ref(self, model_ref: str) -> LlmModelRoute | None:
        _require_non_empty_text(model_ref, field_name="model_ref")
        for route in self.routes:
            if route.model_ref == model_ref:
                return route
        return None

    def _routes_with_role(
        self,
        role: LlmModelRouteRole,
    ) -> tuple[LlmModelRoute, ...]:
        return tuple(route for route in self.routes if route.role is role)

    def _ordered_routes_with_role(
        self,
        role: LlmModelRouteRole,
    ) -> tuple[LlmModelRoute, ...]:
        return tuple(
            sorted(self._routes_with_role(role), key=lambda route: route.order)
        )


def default_groq_llm_model_route_catalog() -> LlmModelRouteCatalog:
    return LlmModelRouteCatalog(
        routes=(
            LlmModelRoute(
                model_ref="qwen/qwen3-32b",
                role=LlmModelRouteRole.PRIMARY,
                order=0,
            ),
            LlmModelRoute(
                model_ref="openai/gpt-oss-120b",
                role=LlmModelRouteRole.AUTOMATIC_FALLBACK,
                order=1,
            ),
            LlmModelRoute(
                model_ref="llama-3.3-70b-versatile",
                role=LlmModelRouteRole.AUTOMATIC_FALLBACK,
                order=2,
            ),
            LlmModelRoute(
                model_ref="meta-llama/llama-4-scout-17b-16e-instruct",
                role=LlmModelRouteRole.AUTOMATIC_FALLBACK,
                order=3,
            ),
            LlmModelRoute(
                model_ref="llama-3.1-8b-instant",
                role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
                order=4,
            ),
        ),
    )


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
