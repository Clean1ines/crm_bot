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

    def model_profile_for_route(self, route: PhaseRouteRule) -> ModelProfile:
        if not isinstance(route, PhaseRouteRule):
            raise TypeError("route must be PhaseRouteRule")
        for model_profile in self.model_profiles:
            if model_profile.model_id.value == route.model_ref:
                return model_profile
        raise ValueError(
            f"route model_ref is not in provider profile: {route.model_ref}"
        )

    def enabled_accounts(self) -> tuple[ProviderAccount, ...]:
        return tuple(account for account in self.accounts if account.enabled)


class ProviderCapacityExecutionWindowExpander:
    def expand_route(
        self,
        *,
        provider_profile: ProviderCapacityProfile,
        route: PhaseRouteRule,
    ) -> tuple[CapacityExecutionWindow, ...]:
        if not isinstance(provider_profile, ProviderCapacityProfile):
            raise TypeError("provider_profile must be ProviderCapacityProfile")
        if not isinstance(route, PhaseRouteRule):
            raise TypeError("route must be PhaseRouteRule")

        model_profile = provider_profile.model_profile_for_route(route)
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
                        route_activation_ref=route.route_ref,
                        route_kind=route.route_kind,
                        route_reason=route.route_reason,
                        activation_scope=route.activation_scope,
                        provider_id=provider_profile.provider_id,
                        account_ref=account.account_ref,
                        model_id=model_profile.model_id,
                        capacity_scope_key=capacity_scope_key,
                        execution_slot_key=execution_slot_key,
                    )
                )
        return tuple(windows)


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
