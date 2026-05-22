from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from src.domain.commercial.price_knowledge import (
    PriceCondition,
    PriceDocumentInputKind,
    PriceDocumentSourceFormat,
    PriceRange,
    PriceSourceRef,
    PriceValueKind,
)
from src.domain.commercial.pricing import (
    MoneyAmount,
    normalize_slot_name,
    normalize_slot_value,
)


class PriceAcquisitionFieldRole(StrEnum):
    ITEM_NAME = "item_name"
    AMOUNT = "amount"
    MIN_AMOUNT = "min_amount"
    MAX_AMOUNT = "max_amount"
    CURRENCY = "currency"
    UNIT = "unit"
    PRICE_TEXT = "price_text"
    VARIANT = "variant"
    CONDITION = "condition"
    VALIDITY = "validity"
    CATEGORY = "category"
    DESCRIPTION = "description"
    UNKNOWN = "unknown"


class PriceFactCandidateStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


class PriceCompilationIssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class PriceCompilationIssueCode(StrEnum):
    UNKNOWN_SOURCE_FORMAT = "unknown_source_format"
    EMPTY_SOURCE_UNIT = "empty_source_unit"
    AMBIGUOUS_TABLE_HEADER = "ambiguous_table_header"
    AMBIGUOUS_PRICE_VALUE = "ambiguous_price_value"
    MISSING_ITEM_NAME = "missing_item_name"
    MISSING_PRICE_VALUE = "missing_price_value"
    CONFLICTING_PRICE_VALUES = "conflicting_price_values"
    UNSUPPORTED_PRICE_SHAPE = "unsupported_price_shape"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


@dataclass(frozen=True, slots=True)
class PriceAcquisitionUnit:
    id: str
    price_document_id: str
    source_index: int
    source_format: PriceDocumentSourceFormat
    input_kind: PriceDocumentInputKind
    raw_text: str
    title: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("price acquisition unit id must not be empty")
        if not self.price_document_id.strip():
            raise ValueError(
                "price acquisition unit price_document_id must not be empty"
            )
        if self.source_index < 0:
            raise ValueError("price acquisition unit source_index must be non-negative")
        if not self.raw_text.strip():
            raise ValueError("price acquisition unit raw_text must not be empty")


@dataclass(frozen=True, slots=True)
class PriceAcquisitionCell:
    row_id: str
    column_name: str
    raw_value: str
    normalized_value: str = ""
    role: PriceAcquisitionFieldRole = PriceAcquisitionFieldRole.UNKNOWN
    confidence: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.row_id.strip():
            raise ValueError("price acquisition cell row_id must not be empty")
        if not self.column_name.strip():
            raise ValueError("price acquisition cell column_name must not be empty")
        _validate_confidence(self.confidence, label="price acquisition cell confidence")


@dataclass(frozen=True, slots=True)
class PriceAcquisitionRow:
    id: str
    source_unit_id: str
    row_index: int
    raw_cells: Mapping[str, object]
    cells: tuple[PriceAcquisitionCell, ...] = ()
    normalized_cells: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("price acquisition row id must not be empty")
        if not self.source_unit_id.strip():
            raise ValueError("price acquisition row source_unit_id must not be empty")
        if self.row_index < 0:
            raise ValueError("price acquisition row row_index must be non-negative")
        if not self.raw_cells and not self.cells:
            raise ValueError("price acquisition row must contain raw_cells or cells")
        for cell in self.cells:
            if cell.row_id != self.id:
                raise ValueError("price acquisition cell row_id must match row id")


@dataclass(frozen=True, slots=True)
class PriceColumnRoleCandidate:
    source_unit_id: str
    column_name: str
    role: PriceAcquisitionFieldRole
    confidence: Decimal
    source_refs: tuple[PriceSourceRef, ...]
    alternatives: tuple[PriceAcquisitionFieldRole, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_unit_id.strip():
            raise ValueError("price column role source_unit_id must not be empty")
        if not self.column_name.strip():
            raise ValueError("price column role column_name must not be empty")
        if self.role == PriceAcquisitionFieldRole.UNKNOWN:
            raise ValueError("price column role candidate role must be explicit")
        if not self.source_refs:
            raise ValueError("price column role candidate must be source-grounded")
        _validate_confidence(self.confidence, label="price column role confidence")


@dataclass(frozen=True, slots=True)
class PriceFieldCandidate:
    role: PriceAcquisitionFieldRole
    value: str
    source_refs: tuple[PriceSourceRef, ...]
    normalized_value: str = ""
    confidence: Decimal = Decimal("0")
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.role == PriceAcquisitionFieldRole.UNKNOWN:
            raise ValueError("price field candidate role must be explicit")
        if not self.value.strip():
            raise ValueError("price field candidate value must not be empty")
        if not self.source_refs:
            raise ValueError("price field candidate must be source-grounded")
        _validate_confidence(self.confidence, label="price field confidence")


@dataclass(frozen=True, slots=True)
class PriceFactCandidate:
    id: str
    project_id: str
    price_document_id: str
    item_name: str
    value_kind: PriceValueKind
    unit: str
    source_refs: tuple[PriceSourceRef, ...]
    status: PriceFactCandidateStatus = PriceFactCandidateStatus.NEEDS_REVIEW
    amount: MoneyAmount | None = None
    price_range: PriceRange | None = None
    price_text: str = ""
    variant: Mapping[str, str] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    conditions: tuple[PriceCondition, ...] = ()
    field_candidates: tuple[PriceFieldCandidate, ...] = ()
    confidence: Decimal = Decimal("0")
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("price fact candidate id must not be empty")
        if not self.project_id.strip():
            raise ValueError("price fact candidate project_id must not be empty")
        if not self.price_document_id.strip():
            raise ValueError("price fact candidate price_document_id must not be empty")
        if not self.item_name.strip():
            raise ValueError("price fact candidate item_name must not be empty")
        if not self.unit.strip():
            raise ValueError("price fact candidate unit must not be empty")
        if not self.source_refs:
            raise ValueError("price fact candidate must be source-grounded")
        _validate_confidence(self.confidence, label="price fact candidate confidence")
        _validate_price_value_shape(
            value_kind=self.value_kind,
            amount=self.amount,
            price_range=self.price_range,
            price_text=self.price_text,
        )

    @property
    def normalized_item_name(self) -> str:
        return normalize_slot_value(self.item_name)

    @property
    def normalized_variant(self) -> Mapping[str, str]:
        return {
            normalize_slot_name(key): normalize_slot_value(value)
            for key, value in self.variant.items()
            if normalize_slot_name(key) and normalize_slot_value(value)
        }

    @property
    def is_publishable_without_review(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class PriceCompilationIssue:
    severity: PriceCompilationIssueSeverity
    code: PriceCompilationIssueCode
    message: str
    source_refs: tuple[PriceSourceRef, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("price compilation issue message must not be empty")


@dataclass(frozen=True, slots=True)
class PriceAcquisitionResult:
    price_document_id: str
    source_format: PriceDocumentSourceFormat
    input_kind: PriceDocumentInputKind
    units: tuple[PriceAcquisitionUnit, ...] = ()
    rows: tuple[PriceAcquisitionRow, ...] = ()
    column_roles: tuple[PriceColumnRoleCandidate, ...] = ()
    field_candidates: tuple[PriceFieldCandidate, ...] = ()
    fact_candidates: tuple[PriceFactCandidate, ...] = ()
    issues: tuple[PriceCompilationIssue, ...] = ()

    def __post_init__(self) -> None:
        if not self.price_document_id.strip():
            raise ValueError(
                "price acquisition result price_document_id must not be empty"
            )

        unit_ids = {unit.id for unit in self.units}
        for unit in self.units:
            if unit.price_document_id != self.price_document_id:
                raise ValueError(
                    "price acquisition unit price_document_id must match result"
                )

        for row in self.rows:
            if row.source_unit_id not in unit_ids:
                raise ValueError("price acquisition row must reference a known unit")

        for role in self.column_roles:
            if role.source_unit_id not in unit_ids:
                raise ValueError("price column role must reference a known unit")

        for candidate in self.fact_candidates:
            if candidate.price_document_id != self.price_document_id:
                raise ValueError(
                    "price fact candidate price_document_id must match result"
                )

    @property
    def has_errors(self) -> bool:
        return any(
            issue.severity == PriceCompilationIssueSeverity.ERROR
            for issue in self.issues
        )

    @property
    def needs_review(self) -> bool:
        return self.has_errors or bool(self.fact_candidates or self.issues)


def _validate_confidence(value: Decimal, *, label: str) -> None:
    if value < 0 or value > 1:
        raise ValueError(f"{label} must be between 0 and 1")


def _validate_price_value_shape(
    *,
    value_kind: PriceValueKind,
    amount: MoneyAmount | None,
    price_range: PriceRange | None,
    price_text: str,
) -> None:
    if value_kind in {PriceValueKind.EXACT, PriceValueKind.STARTING_FROM}:
        if amount is None:
            raise ValueError("numeric price fact candidate requires amount")
        if price_range is not None:
            raise ValueError(
                "exact/starting_from price fact candidate must not include price_range"
            )
        return

    if value_kind == PriceValueKind.RANGE:
        if price_range is None:
            raise ValueError("range price fact candidate requires price_range")
        if amount is not None:
            raise ValueError("range price fact candidate must not include amount")
        return

    if value_kind == PriceValueKind.ON_REQUEST:
        if amount is not None or price_range is not None:
            raise ValueError(
                "on_request price fact candidate must not include numeric price"
            )
        if not price_text.strip():
            raise ValueError("on_request price fact candidate requires price_text")
        return

    raise ValueError("price fact candidate value_kind must be explicit")
