from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from src.application.ports.commercial_price_acquisition import (
    CommercialPriceAcquisitionAdapterPort,
)
from src.domain.commercial.price_acquisition import (
    PriceAcquisitionCell,
    PriceAcquisitionFieldRole,
    PriceAcquisitionResult,
    PriceAcquisitionRow,
    PriceAcquisitionUnit,
    PriceColumnRoleCandidate,
    PriceCompilationIssue,
    PriceCompilationIssueCode,
    PriceCompilationIssueSeverity,
    PriceFactCandidate,
    PriceFieldCandidate,
)
from src.domain.commercial.price_knowledge import (
    PriceDocumentInputKind,
    PriceDocumentSourceFormat,
    PriceSourceRef,
    PriceValueKind,
)
from src.domain.commercial.pricing import MoneyAmount, normalize_slot_name


_MARKDOWN_PRICE_ADAPTER_NAMESPACE = uuid.UUID("c9cf40c9-06f6-472e-810e-0052de769275")
_AMOUNT_RE = re.compile(
    r"(?P<prefix>от\s+)?(?P<amount>\d[\d\s.,]*)\s*(?P<currency>₽|руб\.?|rub|usd|eur|\$|€)?",
    re.IGNORECASE,
)
_ON_REQUEST_MARKERS = (
    "по запросу",
    "индивидуально",
    "индивидуальная",
    "рассчитывается",
    "on request",
    "custom",
)
_ITEM_HEADER_MARKERS = (
    "service",
    "услуга",
    "товар",
    "позиция",
    "тариф",
    "plan",
    "name",
    "название",
)
_PRICE_HEADER_MARKERS = (
    "price",
    "цена",
    "стоимость",
    "тариф",
    "amount",
    "руб",
    "₽",
)
_UNIT_HEADER_MARKERS = (
    "unit",
    "период",
    "единица",
    "за",
    "billing",
)


@dataclass(frozen=True, slots=True)
class MarkdownTable:
    unit: PriceAcquisitionUnit
    start_line: int
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


class MarkdownPriceAcquisitionAdapter(CommercialPriceAcquisitionAdapterPort):
    @property
    def adapter_name(self) -> str:
        return "markdown_price_acquisition"

    def supports(
        self,
        *,
        source_format: PriceDocumentSourceFormat,
        input_kind: PriceDocumentInputKind,
    ) -> bool:
        if source_format == PriceDocumentSourceFormat.MARKDOWN:
            return input_kind in {
                PriceDocumentInputKind.TABLE,
                PriceDocumentInputKind.MIXED,
                PriceDocumentInputKind.STRUCTURED_TEXT,
            }

        return (
            source_format == PriceDocumentSourceFormat.PLAIN_TEXT
            and input_kind == PriceDocumentInputKind.STRUCTURED_TEXT
        )

    async def acquire(
        self,
        *,
        project_id: str,
        price_document_id: str,
        source_format: PriceDocumentSourceFormat,
        input_kind: PriceDocumentInputKind,
        units: Sequence[PriceAcquisitionUnit],
    ) -> PriceAcquisitionResult:
        tables = tuple(_markdown_tables_from_units(units))
        rows: list[PriceAcquisitionRow] = []
        column_roles: list[PriceColumnRoleCandidate] = []
        field_candidates: list[PriceFieldCandidate] = []
        fact_candidates: list[PriceFactCandidate] = []
        issues: list[PriceCompilationIssue] = []

        if not tables:
            return PriceAcquisitionResult(
                price_document_id=price_document_id,
                source_format=source_format,
                input_kind=input_kind,
                units=tuple(units),
                issues=(
                    PriceCompilationIssue(
                        severity=PriceCompilationIssueSeverity.WARNING,
                        code=PriceCompilationIssueCode.NEEDS_HUMAN_REVIEW,
                        message="No Markdown price table was detected.",
                    ),
                ),
            )

        for table in tables:
            roles = _column_roles(table)
            if not _has_role(roles, PriceAcquisitionFieldRole.ITEM_NAME):
                issues.append(
                    _table_issue(
                        table=table,
                        code=PriceCompilationIssueCode.MISSING_ITEM_NAME,
                        message="Markdown price table has no recognizable item/name column.",
                    )
                )
            if not _has_any_role(
                roles,
                (
                    PriceAcquisitionFieldRole.AMOUNT,
                    PriceAcquisitionFieldRole.PRICE_TEXT,
                ),
            ):
                issues.append(
                    _table_issue(
                        table=table,
                        code=PriceCompilationIssueCode.MISSING_PRICE_VALUE,
                        message="Markdown price table has no recognizable price column.",
                    )
                )

            column_roles.extend(roles)

            item_column = _first_column_for_role(
                roles, PriceAcquisitionFieldRole.ITEM_NAME
            )
            price_column = _first_column_for_any_role(
                roles,
                (
                    PriceAcquisitionFieldRole.AMOUNT,
                    PriceAcquisitionFieldRole.PRICE_TEXT,
                ),
            )
            unit_column = _first_column_for_role(roles, PriceAcquisitionFieldRole.UNIT)

            for row_index, values in enumerate(table.rows):
                acquisition_row = _row_from_values(
                    table=table,
                    row_index=row_index,
                    values=values,
                    roles=roles,
                )
                rows.append(acquisition_row)

                row_fields = _field_candidates_from_row(
                    table=table,
                    row=acquisition_row,
                    roles=roles,
                )
                field_candidates.extend(row_fields)

                candidate = _fact_candidate_from_row(
                    project_id=project_id,
                    price_document_id=price_document_id,
                    table=table,
                    row=acquisition_row,
                    item_column=item_column,
                    price_column=price_column,
                    unit_column=unit_column,
                    field_candidates=row_fields,
                )
                if candidate is None:
                    issues.append(
                        PriceCompilationIssue(
                            severity=PriceCompilationIssueSeverity.WARNING,
                            code=PriceCompilationIssueCode.NEEDS_HUMAN_REVIEW,
                            message="Markdown table row could not be converted to a price fact candidate.",
                            source_refs=(
                                _source_ref_for_row(
                                    price_document_id=price_document_id,
                                    source_unit_id=table.unit.id,
                                    source_row_id=acquisition_row.id,
                                    quote=_row_quote(table.headers, values),
                                ),
                            ),
                            metadata={
                                "source_unit_id": table.unit.id,
                                "row_index": row_index,
                            },
                        )
                    )
                else:
                    fact_candidates.append(candidate)

        return PriceAcquisitionResult(
            price_document_id=price_document_id,
            source_format=source_format,
            input_kind=input_kind,
            units=tuple(units),
            rows=tuple(rows),
            column_roles=tuple(column_roles),
            field_candidates=tuple(field_candidates),
            fact_candidates=tuple(fact_candidates),
            issues=tuple(issues),
        )


def _markdown_tables_from_units(
    units: Sequence[PriceAcquisitionUnit],
) -> tuple[MarkdownTable, ...]:
    tables: list[MarkdownTable] = []
    for unit in units:
        tables.extend(_markdown_tables_from_unit(unit))
    return tuple(tables)


def _markdown_tables_from_unit(unit: PriceAcquisitionUnit) -> tuple[MarkdownTable, ...]:
    lines = unit.raw_text.splitlines()
    tables: list[MarkdownTable] = []
    index = 0

    while index < len(lines) - 1:
        header = _parse_pipe_row(lines[index])
        separator = _parse_pipe_row(lines[index + 1])
        if header and separator and _is_separator_row(separator):
            row_values: list[tuple[str, ...]] = []
            row_index = index + 2
            while row_index < len(lines):
                parsed = _parse_pipe_row(lines[row_index])
                if not parsed:
                    break
                if len(parsed) < len(header):
                    parsed = (*parsed, *("" for _ in range(len(header) - len(parsed))))
                row_values.append(tuple(parsed[: len(header)]))
                row_index += 1

            if row_values:
                tables.append(
                    MarkdownTable(
                        unit=unit,
                        start_line=index,
                        headers=tuple(header),
                        rows=tuple(row_values),
                    )
                )
            index = max(row_index, index + 1)
            continue

        index += 1

    return tuple(tables)


def _parse_pipe_row(line: str) -> tuple[str, ...]:
    stripped = line.strip()
    if "|" not in stripped:
        return ()

    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]

    cells = tuple(cell.strip() for cell in stripped.split("|"))
    return cells if any(cells) else ()


def _is_separator_row(cells: Sequence[str]) -> bool:
    return bool(cells) and all(
        re.fullmatch(r":?-{3,}:?", cell.strip()) is not None for cell in cells
    )


def _column_roles(table: MarkdownTable) -> tuple[PriceColumnRoleCandidate, ...]:
    roles: list[PriceColumnRoleCandidate] = []
    for header in table.headers:
        role = _role_for_header(header)
        if role == PriceAcquisitionFieldRole.UNKNOWN:
            continue
        roles.append(
            PriceColumnRoleCandidate(
                source_unit_id=table.unit.id,
                column_name=header,
                role=role,
                confidence=Decimal("0.85"),
                source_refs=(
                    _source_ref_for_table_header(
                        price_document_id=table.unit.price_document_id,
                        source_unit_id=table.unit.id,
                        header=header,
                    ),
                ),
            )
        )

    return tuple(roles)


def _role_for_header(header: str) -> PriceAcquisitionFieldRole:
    normalized = normalize_slot_name(header)

    if any(marker in normalized for marker in _ITEM_HEADER_MARKERS):
        return PriceAcquisitionFieldRole.ITEM_NAME
    if any(marker in normalized for marker in _PRICE_HEADER_MARKERS):
        return PriceAcquisitionFieldRole.AMOUNT
    if any(marker in normalized for marker in _UNIT_HEADER_MARKERS):
        return PriceAcquisitionFieldRole.UNIT
    if normalized in {"description", "описание"}:
        return PriceAcquisitionFieldRole.DESCRIPTION

    return PriceAcquisitionFieldRole.VARIANT


def _row_from_values(
    *,
    table: MarkdownTable,
    row_index: int,
    values: Sequence[str],
    roles: Sequence[PriceColumnRoleCandidate],
) -> PriceAcquisitionRow:
    row_id = _stable_id(f"row:{table.unit.id}:{table.start_line}:{row_index}")
    normalized_roles = {
        normalize_slot_name(role.column_name): role.role for role in roles
    }
    raw_cells = {
        header: values[index] if index < len(values) else ""
        for index, header in enumerate(table.headers)
    }
    normalized_cells = {
        normalize_slot_name(header): (
            values[index].strip() if index < len(values) else ""
        )
        for index, header in enumerate(table.headers)
        if header.strip()
    }
    cells = tuple(
        PriceAcquisitionCell(
            row_id=row_id,
            column_name=header,
            raw_value=values[index] if index < len(values) else "",
            normalized_value=(values[index].strip() if index < len(values) else ""),
            role=normalized_roles.get(
                normalize_slot_name(header),
                PriceAcquisitionFieldRole.UNKNOWN,
            ),
            confidence=Decimal("0.8"),
        )
        for index, header in enumerate(table.headers)
    )

    return PriceAcquisitionRow(
        id=row_id,
        source_unit_id=table.unit.id,
        row_index=row_index,
        raw_cells=raw_cells,
        cells=cells,
        normalized_cells=normalized_cells,
    )


def _field_candidates_from_row(
    *,
    table: MarkdownTable,
    row: PriceAcquisitionRow,
    roles: Sequence[PriceColumnRoleCandidate],
) -> tuple[PriceFieldCandidate, ...]:
    fields: list[PriceFieldCandidate] = []
    for role in roles:
        value = str(row.raw_cells.get(role.column_name, "")).strip()
        if not value:
            continue
        fields.append(
            PriceFieldCandidate(
                role=role.role,
                value=value,
                normalized_value=value.strip(),
                confidence=Decimal("0.8"),
                source_refs=(
                    _source_ref_for_row(
                        price_document_id=table.unit.price_document_id,
                        source_unit_id=table.unit.id,
                        source_row_id=row.id,
                        quote=f"{role.column_name}: {value}",
                    ),
                ),
            )
        )
    return tuple(fields)


def _fact_candidate_from_row(
    *,
    project_id: str,
    price_document_id: str,
    table: MarkdownTable,
    row: PriceAcquisitionRow,
    item_column: str | None,
    price_column: str | None,
    unit_column: str | None,
    field_candidates: Sequence[PriceFieldCandidate],
) -> PriceFactCandidate | None:
    if item_column is None or price_column is None:
        return None

    item_name = str(row.raw_cells.get(item_column, "")).strip()
    price_text = str(row.raw_cells.get(price_column, "")).strip()
    if not item_name or not price_text:
        return None

    parsed_price = _parse_price_value(price_text)
    if parsed_price is None:
        return None

    value_kind, amount, raw_price_text = parsed_price
    unit = (
        str(row.raw_cells.get(unit_column, "")).strip()
        if unit_column is not None
        else _unit_from_price_text(price_text)
    )
    source_ref = _source_ref_for_row(
        price_document_id=price_document_id,
        source_unit_id=table.unit.id,
        source_row_id=row.id,
        quote=_row_quote(
            table.headers,
            [str(row.raw_cells.get(header, "")) for header in table.headers],
        ),
    )

    candidate_id = _stable_id(f"candidate:{row.id}")
    common_field_candidates = tuple(field_candidates)
    confidence = Decimal("0.72")

    if value_kind in {PriceValueKind.EXACT, PriceValueKind.STARTING_FROM}:
        if amount is None:
            return None
        return PriceFactCandidate(
            id=candidate_id,
            project_id=project_id,
            price_document_id=price_document_id,
            item_name=item_name,
            value_kind=value_kind,
            unit=unit or "item",
            source_refs=(source_ref,),
            amount=amount,
            field_candidates=common_field_candidates,
            confidence=confidence,
        )

    if value_kind == PriceValueKind.ON_REQUEST:
        return PriceFactCandidate(
            id=candidate_id,
            project_id=project_id,
            price_document_id=price_document_id,
            item_name=item_name,
            value_kind=value_kind,
            unit=unit or "item",
            source_refs=(source_ref,),
            price_text=raw_price_text,
            field_candidates=common_field_candidates,
            confidence=confidence,
        )

    return None


def _parse_price_value(
    value: str,
) -> tuple[PriceValueKind, MoneyAmount | None, str] | None:
    normalized = value.strip().lower()
    if not normalized:
        return None

    if any(marker in normalized for marker in _ON_REQUEST_MARKERS):
        return (PriceValueKind.ON_REQUEST, None, value.strip())

    match = _AMOUNT_RE.search(normalized)
    if match is None:
        return None

    amount_text = match.group("amount").replace(" ", "").replace(",", ".")
    currency = _currency_from_text(match.group("currency") or value)
    if currency is None:
        return None

    value_kind = (
        PriceValueKind.STARTING_FROM
        if match.group("prefix") or normalized.startswith("от ")
        else PriceValueKind.EXACT
    )
    return (value_kind, MoneyAmount.from_text(amount_text, currency), value.strip())


def _currency_from_text(value: str) -> str | None:
    normalized = value.strip().lower()

    if "₽" in normalized or "руб" in normalized or "rub" in normalized:
        return "RUB"
    if "$" in normalized or "usd" in normalized:
        return "USD"
    if "€" in normalized or "eur" in normalized:
        return "EUR"

    return None


def _unit_from_price_text(value: str) -> str:
    normalized = value.strip().lower()

    if "мес" in normalized or "month" in normalized:
        return "month"
    if "год" in normalized or "year" in normalized:
        return "year"
    if "час" in normalized or "hour" in normalized:
        return "hour"
    if "день" in normalized or "day" in normalized:
        return "day"

    return "item"


def _has_role(
    roles: Sequence[PriceColumnRoleCandidate],
    role: PriceAcquisitionFieldRole,
) -> bool:
    return any(candidate.role == role for candidate in roles)


def _has_any_role(
    roles: Sequence[PriceColumnRoleCandidate],
    role_values: Sequence[PriceAcquisitionFieldRole],
) -> bool:
    return any(candidate.role in role_values for candidate in roles)


def _first_column_for_role(
    roles: Sequence[PriceColumnRoleCandidate],
    role: PriceAcquisitionFieldRole,
) -> str | None:
    for candidate in roles:
        if candidate.role == role:
            return candidate.column_name
    return None


def _first_column_for_any_role(
    roles: Sequence[PriceColumnRoleCandidate],
    role_values: Sequence[PriceAcquisitionFieldRole],
) -> str | None:
    for candidate in roles:
        if candidate.role in role_values:
            return candidate.column_name
    return None


def _table_issue(
    *,
    table: MarkdownTable,
    code: PriceCompilationIssueCode,
    message: str,
) -> PriceCompilationIssue:
    return PriceCompilationIssue(
        severity=PriceCompilationIssueSeverity.WARNING,
        code=code,
        message=message,
        source_refs=(
            PriceSourceRef(
                price_document_id=table.unit.price_document_id,
                source_unit_id=table.unit.id,
                quote=" | ".join(table.headers),
            ),
        ),
        metadata={"source_unit_id": table.unit.id, "start_line": table.start_line},
    )


def _source_ref_for_table_header(
    *,
    price_document_id: str,
    source_unit_id: str,
    header: str,
) -> PriceSourceRef:
    return PriceSourceRef(
        price_document_id=price_document_id,
        source_unit_id=source_unit_id,
        quote=header,
    )


def _source_ref_for_row(
    *,
    price_document_id: str,
    source_unit_id: str,
    source_row_id: str,
    quote: str,
) -> PriceSourceRef:
    return PriceSourceRef(
        price_document_id=price_document_id,
        source_unit_id=source_unit_id,
        source_row_id=source_row_id,
        quote=quote,
    )


def _row_quote(headers: Sequence[str], values: Sequence[str]) -> str:
    return " | ".join(
        f"{header}: {values[index] if index < len(values) else ''}"
        for index, header in enumerate(headers)
    )


def _stable_id(value: str) -> str:
    return str(uuid.uuid5(_MARKDOWN_PRICE_ADAPTER_NAMESPACE, value))
