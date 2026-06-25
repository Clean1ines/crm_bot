from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.entities.provider_account import ProviderAccount
from src.contexts.llm_runtime.domain.routing.phase_route_policy import (
    PhaseRouteActivationScope,
    PhaseRouteKind,
    PhaseRouteReason,
    PhaseRouteRule,
)
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import (
    ProviderAccountRef,
)
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId


class CapacityScopePolicy(StrEnum):
    ACCOUNT_MODEL = "account_model"
    ACCOUNT = "account"


class ProviderParallelismPolicyKind(StrEnum):
    ONE_SLOT_PER_ACCOUNT_MODEL_ROUTE = "one_slot_per_account_model_route"
    FIXED_SLOTS_PER_ACCOUNT_MODEL_ROUTE = "fixed_slots_per_account_model_route"


class RouteActivationStatus(StrEnum):
    ACTIVE = "active"
    WAITING_CAPACITY = "waiting_capacity"
    WAITING_USER_CHOICE = "waiting_user_choice"
    EXHAUSTED = "exhausted"
    PAUSED = "paused"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class RouteActivation:
    activation_ref: str
    phase: str
    work_kind: str
    route_kind: PhaseRouteKind
    route_reason: PhaseRouteReason
    model_ref: str
    activation_scope: PhaseRouteActivationScope
    status: RouteActivationStatus = RouteActivationStatus.ACTIVE
    target_work_item_id: str | None = None
    retry_group_ref: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.activation_ref, "activation_ref")
        _require_non_empty_text(self.phase, "phase")
        _require_non_empty_text(self.work_kind, "work_kind")
        _require_non_empty_text(self.model_ref, "model_ref")
        if not isinstance(self.route_kind, PhaseRouteKind):
            raise TypeError("route_kind must be PhaseRouteKind")
        if not isinstance(self.route_reason, PhaseRouteReason):
            raise TypeError("route_reason must be PhaseRouteReason")
        if not isinstance(self.activation_scope, PhaseRouteActivationScope):
            raise TypeError("activation_scope must be PhaseRouteActivationScope")
        if not isinstance(self.status, RouteActivationStatus):
            raise TypeError("status must be RouteActivationStatus")
        if self.target_work_item_id is not None:
            _require_non_empty_text(self.target_work_item_id, "target_work_item_id")
        if self.retry_group_ref is not None:
            _require_non_empty_text(self.retry_group_ref, "retry_group_ref")
        if (
            self.activation_scope is PhaseRouteActivationScope.WORK_ITEM
            and self.target_work_item_id is None
        ):
            raise ValueError("work_item route activation requires target_work_item_id")
        if (
            self.activation_scope is PhaseRouteActivationScope.RETRY_GROUP
            and self.retry_group_ref is None
        ):
            raise ValueError("retry_group route activation requires retry_group_ref")
        if self.status is not RouteActivationStatus.ACTIVE:
            raise ValueError("only active route activations can expand into windows")

    @classmethod
    def from_phase_route_rule(
        cls,
        *,
        phase: str,
        work_kind: str,
        route: PhaseRouteRule,
        activation_ref: str | None = None,
        status: RouteActivationStatus = RouteActivationStatus.ACTIVE,
        target_work_item_id: str | None = None,
        retry_group_ref: str | None = None,
    ) -> RouteActivation:
        if not isinstance(route, PhaseRouteRule):
            raise TypeError("route must be PhaseRouteRule")
        return cls(
            activation_ref=activation_ref
            if activation_ref is not None
            else route.route_ref,
            phase=phase,
            work_kind=work_kind,
            route_kind=route.route_kind,
            route_reason=route.route_reason,
            model_ref=route.model_ref,
            activation_scope=route.activation_scope,
            status=status,
            target_work_item_id=target_work_item_id,
            retry_group_ref=retry_group_ref,
        )


@dataclass(frozen=True, slots=True)
class CapacityScopeKey:
    provider_id: ProviderId
    account_ref: ProviderAccountRef
    model_id: ModelId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, ProviderId):
            raise TypeError("provider_id must be ProviderId")
        if not isinstance(self.account_ref, ProviderAccountRef):
            raise TypeError("account_ref must be ProviderAccountRef")
        if self.model_id is not None and not isinstance(self.model_id, ModelId):
            raise TypeError("model_id must be ModelId or None")

    @property
    def value(self) -> str:
        if self.model_id is None:
            return f"{self.provider_id}:{self.account_ref}"
        return f"{self.provider_id}:{self.account_ref}:{self.model_id}"


@dataclass(frozen=True, slots=True)
class CapacityExecutionSlotKey:
    provider_id: ProviderId
    account_ref: ProviderAccountRef
    model_id: ModelId
    slot_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, ProviderId):
            raise TypeError("provider_id must be ProviderId")
        if not isinstance(self.account_ref, ProviderAccountRef):
            raise TypeError("account_ref must be ProviderAccountRef")
        if not isinstance(self.model_id, ModelId):
            raise TypeError("model_id must be ModelId")
        _require_non_empty_text(self.slot_ref, "slot_ref")

    @property
    def value(self) -> str:
        return f"{self.provider_id}:{self.account_ref}:{self.model_id}:{self.slot_ref}"


@dataclass(frozen=True, slots=True)
class CapacityExecutionWindow:
    route_activation_ref: str
    route_kind: PhaseRouteKind
    route_reason: PhaseRouteReason
    activation_scope: PhaseRouteActivationScope
    provider_id: ProviderId
    account_ref: ProviderAccountRef
    model_id: ModelId
    capacity_scope_key: CapacityScopeKey
    execution_slot_key: CapacityExecutionSlotKey

    def __post_init__(self) -> None:
        _require_non_empty_text(self.route_activation_ref, "route_activation_ref")
        if not isinstance(self.route_kind, PhaseRouteKind):
            raise TypeError("route_kind must be PhaseRouteKind")
        if not isinstance(self.route_reason, PhaseRouteReason):
            raise TypeError("route_reason must be PhaseRouteReason")
        if not isinstance(self.activation_scope, PhaseRouteActivationScope):
            raise TypeError("activation_scope must be PhaseRouteActivationScope")
        if not isinstance(self.provider_id, ProviderId):
            raise TypeError("provider_id must be ProviderId")
        if not isinstance(self.account_ref, ProviderAccountRef):
            raise TypeError("account_ref must be ProviderAccountRef")
        if not isinstance(self.model_id, ModelId):
            raise TypeError("model_id must be ModelId")
        if not isinstance(self.capacity_scope_key, CapacityScopeKey):
            raise TypeError("capacity_scope_key must be CapacityScopeKey")
        if not isinstance(self.execution_slot_key, CapacityExecutionSlotKey):
            raise TypeError("execution_slot_key must be CapacityExecutionSlotKey")
        if self.capacity_scope_key.provider_id != self.provider_id:
            raise ValueError("capacity_scope_key provider_id must match window")
        if self.capacity_scope_key.account_ref != self.account_ref:
            raise ValueError("capacity_scope_key account_ref must match window")
        if self.capacity_scope_key.model_id is not None and (
            self.capacity_scope_key.model_id != self.model_id
        ):
            raise ValueError("capacity_scope_key model_id must match window")
        if self.execution_slot_key.provider_id != self.provider_id:
            raise ValueError("execution_slot_key provider_id must match window")
        if self.execution_slot_key.account_ref != self.account_ref:
            raise ValueError("execution_slot_key account_ref must match window")
        if self.execution_slot_key.model_id != self.model_id:
            raise ValueError("execution_slot_key model_id must match window")

    @property
    def window_key(self) -> str:
        return self.execution_slot_key.value


@dataclass(frozen=True, slots=True)
class ProviderParallelismPolicy:
    kind: ProviderParallelismPolicyKind
    slots_per_account_model_route: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ProviderParallelismPolicyKind):
            raise TypeError("kind must be ProviderParallelismPolicyKind")
        if isinstance(self.slots_per_account_model_route, bool) or not isinstance(
            self.slots_per_account_model_route,
            int,
        ):
            raise TypeError("slots_per_account_model_route must be int")
        if self.slots_per_account_model_route <= 0:
            raise ValueError("slots_per_account_model_route must be positive")
        if (
            self.kind is ProviderParallelismPolicyKind.ONE_SLOT_PER_ACCOUNT_MODEL_ROUTE
            and self.slots_per_account_model_route != 1
        ):
            raise ValueError("one-slot policy must use exactly one slot")

    @classmethod
    def one_slot_per_account_model_route(cls) -> ProviderParallelismPolicy:
        return cls(
            kind=ProviderParallelismPolicyKind.ONE_SLOT_PER_ACCOUNT_MODEL_ROUTE,
            slots_per_account_model_route=1,
        )

    @classmethod
    def fixed_slots_per_account_model_route(
        cls,
        slots_per_account_model_route: int,
    ) -> ProviderParallelismPolicy:
        return cls(
            kind=ProviderParallelismPolicyKind.FIXED_SLOTS_PER_ACCOUNT_MODEL_ROUTE,
            slots_per_account_model_route=slots_per_account_model_route,
        )


@dataclass(frozen=True, slots=True)
class ProviderCapacityProfile:
    provider_id: ProviderId
    accounts: tuple[ProviderAccount, ...]
    model_profiles: tuple[ModelProfile, ...]
    capacity_scope_policy: CapacityScopePolicy
    parallelism_policy: ProviderParallelismPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, ProviderId):
            raise TypeError("provider_id must be ProviderId")
        if not isinstance(self.accounts, tuple):
            raise TypeError("accounts must be tuple")
        if not self.accounts:
            raise ValueError("accounts must be non-empty")
        if not isinstance(self.model_profiles, tuple):
            raise TypeError("model_profiles must be tuple")
        if not self.model_profiles:
            raise ValueError("model_profiles must be non-empty")
        if not isinstance(self.capacity_scope_policy, CapacityScopePolicy):
            raise TypeError("capacity_scope_policy must be CapacityScopePolicy")
        if not isinstance(self.parallelism_policy, ProviderParallelismPolicy):
            raise TypeError("parallelism_policy must be ProviderParallelismPolicy")

        account_refs: list[ProviderAccountRef] = []
        for account in self.accounts:
            if not isinstance(account, ProviderAccount):
                raise TypeError("accounts must contain ProviderAccount")
            if account.provider_id != self.provider_id:
                raise ValueError("account provider_id must match profile provider_id")
            account_refs.append(account.account_ref)
        if len(set(account_refs)) != len(account_refs):
            raise ValueError("account refs must be unique")

        model_ids: list[ModelId] = []
        for model_profile in self.model_profiles:
            if not isinstance(model_profile, ModelProfile):
                raise TypeError("model_profiles must contain ModelProfile")
            if model_profile.provider_id != self.provider_id:
                raise ValueError("model provider_id must match profile provider_id")
            model_ids.append(model_profile.model_id)
        if len(set(model_ids)) != len(model_ids):
            raise ValueError("model ids must be unique")

    def model_profile_for_model_ref(self, model_ref: str) -> ModelProfile:
        _require_non_empty_text(model_ref, "model_ref")
        for model_profile in self.model_profiles:
            if model_profile.model_id.value == model_ref:
                return model_profile
        raise ValueError(f"model_ref is not in provider profile: {model_ref}")

    def model_profile_for_route(self, route: PhaseRouteRule) -> ModelProfile:
        if not isinstance(route, PhaseRouteRule):
            raise TypeError("route must be PhaseRouteRule")
        try:
            return self.model_profile_for_model_ref(route.model_ref)
        except ValueError as exc:
            raise ValueError(
                f"route model_ref is not in provider profile: {route.model_ref}"
            ) from exc

    def model_profile_for_activation(
        self,
        activation: RouteActivation,
    ) -> ModelProfile:
        if not isinstance(activation, RouteActivation):
            raise TypeError("activation must be RouteActivation")
        try:
            return self.model_profile_for_model_ref(activation.model_ref)
        except ValueError as exc:
            raise ValueError(
                "route activation model_ref is not in provider profile: "
                f"{activation.model_ref}"
            ) from exc

    def enabled_accounts(self) -> tuple[ProviderAccount, ...]:
        return tuple(account for account in self.accounts if account.enabled)


class ProviderCapacityExecutionWindowExpander:
    def expand_activation(
        self,
        *,
        provider_profile: ProviderCapacityProfile,
        activation: RouteActivation,
    ) -> tuple[CapacityExecutionWindow, ...]:
        if not isinstance(provider_profile, ProviderCapacityProfile):
            raise TypeError("provider_profile must be ProviderCapacityProfile")
        if not isinstance(activation, RouteActivation):
            raise TypeError("activation must be RouteActivation")

        model_profile = provider_profile.model_profile_for_activation(activation)
        windows: list[CapacityExecutionWindow] = []
        for account in provider_profile.enabled_accounts():
            capacity_scope_key = _capacity_scope_key(
                provider_profile=provider_profile,
                account=account,
                model_id=model_profile.model_id,
            )
            for slot_number in range(
                provider_profile.parallelism_policy.slots_per_account_model_route
            ):
                slot_ref = _slot_ref(slot_number)
                execution_slot_key = CapacityExecutionSlotKey(
                    provider_id=provider_profile.provider_id,
                    account_ref=account.account_ref,
                    model_id=model_profile.model_id,
                    slot_ref=slot_ref,
                )
                windows.append(
                    CapacityExecutionWindow(
                        route_activation_ref=activation.activation_ref,
                        route_kind=activation.route_kind,
                        route_reason=activation.route_reason,
                        activation_scope=activation.activation_scope,
                        provider_id=provider_profile.provider_id,
                        account_ref=account.account_ref,
                        model_id=model_profile.model_id,
                        capacity_scope_key=capacity_scope_key,
                        execution_slot_key=execution_slot_key,
                    )
                )
        return tuple(windows)

    def expand_route(
        self,
        *,
        provider_profile: ProviderCapacityProfile,
        route: PhaseRouteRule,
        phase: str = "compatibility_phase",
        work_kind: str = "compatibility_work_kind",
    ) -> tuple[CapacityExecutionWindow, ...]:
        if not isinstance(route, PhaseRouteRule):
            raise TypeError("route must be PhaseRouteRule")
        activation = RouteActivation.from_phase_route_rule(
            phase=phase,
            work_kind=work_kind,
            route=route,
        )
        return self.expand_activation(
            provider_profile=provider_profile,
            activation=activation,
        )


def _capacity_scope_key(
    *,
    provider_profile: ProviderCapacityProfile,
    account: ProviderAccount,
    model_id: ModelId,
) -> CapacityScopeKey:
    if provider_profile.capacity_scope_policy is CapacityScopePolicy.ACCOUNT_MODEL:
        return CapacityScopeKey(
            provider_id=provider_profile.provider_id,
            account_ref=account.account_ref,
            model_id=model_id,
        )
    if provider_profile.capacity_scope_policy is CapacityScopePolicy.ACCOUNT:
        return CapacityScopeKey(
            provider_id=provider_profile.provider_id,
            account_ref=account.account_ref,
            model_id=None,
        )
    raise ValueError("unsupported capacity scope policy")


def _slot_ref(slot_number: int) -> str:
    return f"slot-{slot_number + 1}"


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
