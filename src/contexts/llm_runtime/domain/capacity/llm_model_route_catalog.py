from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


DAILY_LIMIT_FALLBACK_EXCLUDED_MODEL_REFS = ("openai/gpt-oss-120b",)


class LlmModelRouteRole(StrEnum):
    PRIMARY = "primary"
    AUTOMATIC_FALLBACK = "automatic_fallback"
    DEGRADED_USER_CHOICE = "degraded_user_choice"


@dataclass(frozen=True, slots=True)
class LlmModelExecutionSettings:
    reasoning_enabled: bool
    reasoning_effort: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reasoning_enabled, bool):
            raise TypeError("reasoning_enabled must be bool")
        if self.reasoning_effort is not None:
            _require_non_empty_text(
                self.reasoning_effort,
                field_name="reasoning_effort",
            )
        if not self.reasoning_enabled and self.reasoning_effort is not None:
            raise ValueError(
                "reasoning_effort must be None when reasoning_enabled is False",
            )

    def to_provider_options(self) -> dict[str, object]:
        if not self.reasoning_enabled:
            return {"reasoning_enabled": False}

        payload: dict[str, object] = {"reasoning_enabled": True}
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        return payload


@dataclass(frozen=True, slots=True)
class LlmModelCapacityLimits:
    input_token_limit: int
    output_token_limit: int

    def __post_init__(self) -> None:
        _require_positive_int(
            self.input_token_limit,
            field_name="input_token_limit",
        )
        _require_positive_int(
            self.output_token_limit,
            field_name="output_token_limit",
        )


@dataclass(frozen=True, slots=True)
class LlmModelRoute:
    model_ref: str
    role: LlmModelRouteRole
    order: int
    execution_settings: LlmModelExecutionSettings
    capacity_limits: LlmModelCapacityLimits

    def __post_init__(self) -> None:
        _require_non_empty_text(self.model_ref, field_name="model_ref")
        if not isinstance(self.role, LlmModelRouteRole):
            raise TypeError("role must be LlmModelRouteRole")
        if not isinstance(self.order, int):
            raise TypeError("order must be int")
        if self.order < 0:
            raise ValueError("order must be >= 0")
        if not isinstance(self.execution_settings, LlmModelExecutionSettings):
            raise TypeError("execution_settings must be LlmModelExecutionSettings")
        if not isinstance(self.capacity_limits, LlmModelCapacityLimits):
            raise TypeError("capacity_limits must be LlmModelCapacityLimits")


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

    def automatic_fallback_model_refs_for_daily_limit(self) -> tuple[str, ...]:
        return tuple(
            model_ref
            for model_ref in self.automatic_fallback_model_refs()
            if model_ref not in DAILY_LIMIT_FALLBACK_EXCLUDED_MODEL_REFS
        )

    def automatic_fallback_model_refs_with_larger_output_limit(
        self,
        current_model_ref: str,
    ) -> tuple[str, ...]:
        current_limits = self.capacity_limits_for_model_ref(current_model_ref)
        return tuple(
            route.model_ref
            for route in self._ordered_routes_with_role(
                LlmModelRouteRole.AUTOMATIC_FALLBACK,
            )
            if route.capacity_limits.output_token_limit
            > current_limits.output_token_limit
        )

    def automatic_fallback_model_refs_with_larger_input_limit(
        self,
        current_model_ref: str,
    ) -> tuple[str, ...]:
        current_limits = self.capacity_limits_for_model_ref(current_model_ref)
        return tuple(
            route.model_ref
            for route in self._ordered_routes_with_role(
                LlmModelRouteRole.AUTOMATIC_FALLBACK,
            )
            if route.capacity_limits.input_token_limit
            > current_limits.input_token_limit
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

    def execution_settings_for_model_ref(
        self,
        model_ref: str,
    ) -> LlmModelExecutionSettings:
        route = self.route_for_model_ref(model_ref)
        if route is None:
            raise ValueError("model_ref is not in route catalog")
        return route.execution_settings

    def capacity_limits_for_model_ref(
        self,
        model_ref: str,
    ) -> LlmModelCapacityLimits:
        route = self.route_for_model_ref(model_ref)
        if route is None:
            raise ValueError("model_ref is not in route catalog")
        return route.capacity_limits

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
    reasoning_disabled = LlmModelExecutionSettings(reasoning_enabled=False)
    return LlmModelRouteCatalog(
        routes=(
            LlmModelRoute(
                model_ref="qwen/qwen3-32b",
                role=LlmModelRouteRole.PRIMARY,
                order=0,
                execution_settings=reasoning_disabled,
                capacity_limits=LlmModelCapacityLimits(
                    input_token_limit=6_000,
                    output_token_limit=8192,
                ),
            ),
            LlmModelRoute(
                model_ref="llama-3.3-70b-versatile",
                role=LlmModelRouteRole.AUTOMATIC_FALLBACK,
                order=1,
                execution_settings=reasoning_disabled,
                capacity_limits=LlmModelCapacityLimits(
                    input_token_limit=12_000,
                    output_token_limit=32_768,
                ),
            ),
            LlmModelRoute(
                model_ref="meta-llama/llama-4-scout-17b-16e-instruct",
                role=LlmModelRouteRole.AUTOMATIC_FALLBACK,
                order=2,
                execution_settings=reasoning_disabled,
                capacity_limits=LlmModelCapacityLimits(
                    input_token_limit=30_000,
                    output_token_limit=32_768,
                ),
            ),
            LlmModelRoute(
                model_ref="openai/gpt-oss-120b",
                role=LlmModelRouteRole.AUTOMATIC_FALLBACK,
                order=3,
                execution_settings=reasoning_disabled,
                capacity_limits=LlmModelCapacityLimits(
                    input_token_limit=131_072,
                    output_token_limit=65_536,
                ),
            ),
            LlmModelRoute(
                model_ref="llama-3.1-8b-instant",
                role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
                order=4,
                execution_settings=reasoning_disabled,
                capacity_limits=LlmModelCapacityLimits(
                    input_token_limit=6_000,
                    output_token_limit=4096,
                ),
            ),
        ),
    )


def _require_positive_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
