from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from src.domain.commercial.price_knowledge import (
    PriceCondition,
    PriceRange,
    PriceValueKind,
    PublishedPriceFact,
)
from src.domain.commercial.pricing import (
    MoneyAmount,
    normalize_slot_value,
)


class CommercialSourceKind(StrEnum):
    LIVE_CRM = "live_crm"
    LIVE_CATALOG = "live_catalog"
    LIVE_BILLING = "live_billing"
    LIVE_STOCK = "live_stock"
    STRUCTURED_PRICE_LIST = "structured_price_list"
    COMMERCIAL_OFFER = "commercial_offer"
    FAQ = "faq"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


class CommercialSourceAuthority(StrEnum):
    LIVE = "live"
    PRIMARY = "primary"
    SUPPORTING = "supporting"
    UNKNOWN = "unknown"


class CommercialTruthResolutionPolicy(StrEnum):
    MANUAL_REVIEW = "manual_review"
    HIGHER_AUTHORITY_WINS = "higher_authority_wins"
    NEWER_SOURCE_WINS = "newer_source_wins"


class CommercialConflictReason(StrEnum):
    DIFFERENT_VALUES = "different_values"


class CommercialConflictResolutionStatus(StrEnum):
    UNRESOLVED = "unresolved"
    RESOLVED_BY_POLICY = "resolved_by_policy"


_LIVE_SOURCE_KINDS = {
    CommercialSourceKind.LIVE_CRM,
    CommercialSourceKind.LIVE_CATALOG,
    CommercialSourceKind.LIVE_BILLING,
    CommercialSourceKind.LIVE_STOCK,
}

_PRIMARY_SOURCE_KINDS = {
    CommercialSourceKind.STRUCTURED_PRICE_LIST,
    CommercialSourceKind.COMMERCIAL_OFFER,
}

_SUPPORTING_SOURCE_KINDS = {
    CommercialSourceKind.FAQ,
    CommercialSourceKind.DOCUMENT,
}


@dataclass(frozen=True, slots=True)
class CommercialSourceDescriptor:
    id: str
    kind: CommercialSourceKind
    authority: CommercialSourceAuthority | None = None
    title: str = ""
    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("commercial source id must not be empty")

    @property
    def effective_authority(self) -> CommercialSourceAuthority:
        if self.authority is not None:
            return self.authority
        return default_commercial_source_authority(self.kind)

    @property
    def authority_rank(self) -> int:
        return commercial_source_authority_rank(self.effective_authority)


@dataclass(frozen=True, slots=True)
class CommercialFactIdentity:
    project_id: str
    normalized_item_name: str
    normalized_unit: str
    normalized_variant: tuple[tuple[str, str], ...] = ()
    fact_kind: str = "price"

    @classmethod
    def from_price_fact(cls, fact: PublishedPriceFact) -> "CommercialFactIdentity":
        return cls(
            project_id=fact.project_id,
            normalized_item_name=fact.normalized_item_name,
            normalized_unit=normalize_slot_value(fact.unit),
            normalized_variant=tuple(sorted(fact.normalized_variant.items())),
        )

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise ValueError("commercial fact identity project_id must not be empty")
        if not self.normalized_item_name.strip():
            raise ValueError(
                "commercial fact identity normalized_item_name must not be empty"
            )
        if not self.normalized_unit.strip():
            raise ValueError(
                "commercial fact identity normalized_unit must not be empty"
            )
        if not self.fact_kind.strip():
            raise ValueError("commercial fact identity fact_kind must not be empty")


@dataclass(frozen=True, slots=True)
class CommercialFactValueSignature:
    value_kind: PriceValueKind
    amount: tuple[str, str] | None = None
    price_range: tuple[tuple[str, str], tuple[str, str]] | None = None
    price_text: str = ""
    conditions: tuple[str, ...] = ()

    @classmethod
    def from_price_fact(
        cls, fact: PublishedPriceFact
    ) -> "CommercialFactValueSignature":
        return cls(
            value_kind=fact.value_kind,
            amount=_money_signature(fact.amount),
            price_range=_range_signature(fact.price_range),
            price_text=normalize_slot_value(fact.price_text),
            conditions=_condition_signature(fact.conditions),
        )

    def __post_init__(self) -> None:
        if self.value_kind in {PriceValueKind.EXACT, PriceValueKind.STARTING_FROM}:
            if self.amount is None:
                raise ValueError("numeric commercial value signature requires amount")
            if self.price_range is not None:
                raise ValueError(
                    "numeric commercial value signature must not include price_range"
                )
            return

        if self.value_kind == PriceValueKind.RANGE:
            if self.price_range is None:
                raise ValueError(
                    "range commercial value signature requires price_range"
                )
            if self.amount is not None:
                raise ValueError(
                    "range commercial value signature must not include amount"
                )
            return

        if self.value_kind == PriceValueKind.ON_REQUEST:
            if self.amount is not None or self.price_range is not None:
                raise ValueError(
                    "on_request commercial value signature must not include numeric value"
                )
            if not self.price_text.strip():
                raise ValueError(
                    "on_request commercial value signature requires price_text"
                )
            return

        raise ValueError("commercial value signature value_kind must be explicit")


@dataclass(frozen=True, slots=True)
class CommercialFactSnapshot:
    fact: PublishedPriceFact
    source: CommercialSourceDescriptor
    identity: CommercialFactIdentity = field(init=False)
    value_signature: CommercialFactValueSignature = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "identity",
            CommercialFactIdentity.from_price_fact(self.fact),
        )
        object.__setattr__(
            self,
            "value_signature",
            CommercialFactValueSignature.from_price_fact(self.fact),
        )


@dataclass(frozen=True, slots=True)
class CommercialConflictGroup:
    identity: CommercialFactIdentity
    snapshots: tuple[CommercialFactSnapshot, ...]
    reason: CommercialConflictReason = CommercialConflictReason.DIFFERENT_VALUES

    def __post_init__(self) -> None:
        if len(self.snapshots) < 2:
            raise ValueError(
                "commercial conflict group requires at least two snapshots"
            )

        identities = {snapshot.identity for snapshot in self.snapshots}
        if identities != {self.identity}:
            raise ValueError("commercial conflict group snapshots must share identity")

        if len(self.value_signatures) < 2:
            raise ValueError(
                "commercial conflict group requires at least two different values"
            )

    @property
    def value_signatures(self) -> tuple[CommercialFactValueSignature, ...]:
        signatures: list[CommercialFactValueSignature] = []
        for snapshot in self.snapshots:
            if snapshot.value_signature not in signatures:
                signatures.append(snapshot.value_signature)
        return tuple(signatures)

    @property
    def fact_ids(self) -> tuple[str, ...]:
        return tuple(snapshot.fact.id for snapshot in self.snapshots)


@dataclass(frozen=True, slots=True)
class CommercialConflictResolution:
    group: CommercialConflictGroup
    policy: CommercialTruthResolutionPolicy
    status: CommercialConflictResolutionStatus
    selected_snapshot: CommercialFactSnapshot | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status == CommercialConflictResolutionStatus.RESOLVED_BY_POLICY:
            if self.selected_snapshot is None:
                raise ValueError(
                    "resolved commercial conflict requires selected_snapshot"
                )
        if not self.reason.strip():
            raise ValueError("commercial conflict resolution reason must not be empty")

    @property
    def is_resolved(self) -> bool:
        return self.status == CommercialConflictResolutionStatus.RESOLVED_BY_POLICY


def default_commercial_source_authority(
    kind: CommercialSourceKind,
) -> CommercialSourceAuthority:
    if kind in _LIVE_SOURCE_KINDS:
        return CommercialSourceAuthority.LIVE
    if kind in _PRIMARY_SOURCE_KINDS:
        return CommercialSourceAuthority.PRIMARY
    if kind in _SUPPORTING_SOURCE_KINDS:
        return CommercialSourceAuthority.SUPPORTING
    return CommercialSourceAuthority.UNKNOWN


def commercial_source_authority_rank(
    authority: CommercialSourceAuthority,
) -> int:
    if authority == CommercialSourceAuthority.LIVE:
        return 300
    if authority == CommercialSourceAuthority.PRIMARY:
        return 200
    if authority == CommercialSourceAuthority.SUPPORTING:
        return 100
    return 0


def detect_commercial_fact_conflicts(
    snapshots: Sequence[CommercialFactSnapshot],
) -> tuple[CommercialConflictGroup, ...]:
    grouped: dict[CommercialFactIdentity, list[CommercialFactSnapshot]] = {}
    for snapshot in snapshots:
        grouped.setdefault(snapshot.identity, []).append(snapshot)

    conflicts: list[CommercialConflictGroup] = []
    for identity, group_snapshots in grouped.items():
        signatures = {snapshot.value_signature for snapshot in group_snapshots}
        if len(signatures) > 1:
            conflicts.append(
                CommercialConflictGroup(
                    identity=identity,
                    snapshots=tuple(group_snapshots),
                )
            )

    return tuple(conflicts)


def resolve_commercial_conflict_by_policy(
    group: CommercialConflictGroup,
    policy: CommercialTruthResolutionPolicy,
) -> CommercialConflictResolution:
    if policy == CommercialTruthResolutionPolicy.MANUAL_REVIEW:
        return CommercialConflictResolution(
            group=group,
            policy=policy,
            status=CommercialConflictResolutionStatus.UNRESOLVED,
            reason="manual_review_required",
        )

    if policy == CommercialTruthResolutionPolicy.HIGHER_AUTHORITY_WINS:
        return _resolve_by_higher_authority(group, policy=policy)

    if policy == CommercialTruthResolutionPolicy.NEWER_SOURCE_WINS:
        return _resolve_by_newer_source(group, policy=policy)


def commercial_retrieval_surface_facts(
    snapshots: Sequence[CommercialFactSnapshot],
    *,
    policy: CommercialTruthResolutionPolicy,
) -> tuple[PublishedPriceFact, ...]:
    snapshots_tuple = tuple(snapshots)
    conflicts = detect_commercial_fact_conflicts(snapshots_tuple)
    conflicted_fact_ids = {
        fact_id for conflict in conflicts for fact_id in conflict.fact_ids
    }

    selected: list[PublishedPriceFact] = []
    for snapshot in snapshots_tuple:
        if snapshot.fact.id in conflicted_fact_ids:
            continue
        if snapshot.fact.is_runtime_eligible:
            selected.append(snapshot.fact)

    for conflict in conflicts:
        resolution = resolve_commercial_conflict_by_policy(conflict, policy)
        if (
            resolution.is_resolved
            and resolution.selected_snapshot is not None
            and resolution.selected_snapshot.fact.is_runtime_eligible
        ):
            selected.append(resolution.selected_snapshot.fact)

    return _dedupe_facts_by_id(selected)


def _resolve_by_higher_authority(
    group: CommercialConflictGroup,
    *,
    policy: CommercialTruthResolutionPolicy,
) -> CommercialConflictResolution:
    max_rank = max(snapshot.source.authority_rank for snapshot in group.snapshots)
    winners = tuple(
        snapshot
        for snapshot in group.snapshots
        if snapshot.source.authority_rank == max_rank
    )
    selected = _select_if_winners_share_single_value(winners)
    if selected is None:
        return CommercialConflictResolution(
            group=group,
            policy=policy,
            status=CommercialConflictResolutionStatus.UNRESOLVED,
            reason="higher_authority_tie_requires_manual_review",
        )

    return CommercialConflictResolution(
        group=group,
        policy=policy,
        status=CommercialConflictResolutionStatus.RESOLVED_BY_POLICY,
        selected_snapshot=selected,
        reason="higher_authority_source_selected",
    )


def _resolve_by_newer_source(
    group: CommercialConflictGroup,
    *,
    policy: CommercialTruthResolutionPolicy,
) -> CommercialConflictResolution:
    dated_snapshots: list[tuple[CommercialFactSnapshot, datetime]] = []
    for snapshot in group.snapshots:
        observed_at = snapshot.source.observed_at
        if observed_at is not None:
            dated_snapshots.append((snapshot, observed_at))

    if not dated_snapshots:
        return CommercialConflictResolution(
            group=group,
            policy=policy,
            status=CommercialConflictResolutionStatus.UNRESOLVED,
            reason="newer_source_policy_requires_observed_at",
        )

    latest = max(observed_at for _, observed_at in dated_snapshots)
    winners = tuple(
        snapshot for snapshot, observed_at in dated_snapshots if observed_at == latest
    )
    selected = _select_if_winners_share_single_value(winners)
    if selected is None:
        return CommercialConflictResolution(
            group=group,
            policy=policy,
            status=CommercialConflictResolutionStatus.UNRESOLVED,
            reason="newer_source_tie_requires_manual_review",
        )

    return CommercialConflictResolution(
        group=group,
        policy=policy,
        status=CommercialConflictResolutionStatus.RESOLVED_BY_POLICY,
        selected_snapshot=selected,
        reason="newer_source_selected",
    )


def _select_if_winners_share_single_value(
    winners: Sequence[CommercialFactSnapshot],
) -> CommercialFactSnapshot | None:
    if not winners:
        return None

    signatures = {winner.value_signature for winner in winners}
    if len(signatures) != 1:
        return None

    return tuple(winners)[0]


def _dedupe_facts_by_id(
    facts: Sequence[PublishedPriceFact],
) -> tuple[PublishedPriceFact, ...]:
    result: dict[str, PublishedPriceFact] = {}
    for fact in facts:
        result.setdefault(fact.id, fact)
    return tuple(result.values())


def _money_signature(amount: MoneyAmount | None) -> tuple[str, str] | None:
    if amount is None:
        return None
    return (_decimal_text(amount.amount), amount.currency.strip().upper())


def _range_signature(
    price_range: PriceRange | None,
) -> tuple[tuple[str, str], tuple[str, str]] | None:
    if price_range is None:
        return None
    return (
        _money_signature_required(price_range.min_amount),
        _money_signature_required(price_range.max_amount),
    )


def _money_signature_required(amount: MoneyAmount) -> tuple[str, str]:
    return (_decimal_text(amount.amount), amount.currency.strip().upper())


def _condition_signature(
    conditions: Sequence[PriceCondition],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            normalize_slot_value(condition.text)
            for condition in conditions
            if normalize_slot_value(condition.text)
        )
    )


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")
