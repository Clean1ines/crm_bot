from __future__ import annotations

import re
from dataclasses import dataclass

from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_kind import (
    SourceUnitKind,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_lineage import (
    SourceUnitLineage,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_text import (
    SourceUnitText,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.split_reason import (
    SplitReason,
)


class SourceUnitCannotBeSplitFurther(ValueError):
    """Raised when mechanical paragraph splitting cannot produce valid children."""


class SourceUnitSplitWouldNotReduceInput(ValueError):
    """Raised when splitting would produce fewer than two child units."""


@dataclass(frozen=True, slots=True)
class SourceUnitSplitCommand:
    source_unit: SourceUnit
    reason: SplitReason
    max_child_characters: int

    def __post_init__(self) -> None:
        if self.max_child_characters <= 0:
            raise ValueError("max_child_characters must be > 0")


@dataclass(frozen=True, slots=True)
class SourceUnitSplitResult:
    parent_unit: SourceUnit
    child_units: tuple[SourceUnit, ...]


class SourceUnitSplitPolicy:
    def split(self, command: SourceUnitSplitCommand) -> SourceUnitSplitResult:
        paragraphs = self._paragraphs(command.source_unit.text.value)
        child_texts = self._group_paragraphs(
            paragraphs=paragraphs,
            max_child_characters=command.max_child_characters,
        )

        if len(child_texts) < 2:
            raise SourceUnitSplitWouldNotReduceInput(
                "Source unit split must produce at least two child units"
            )

        child_units = tuple(
            self._build_child_unit(
                parent=command.source_unit,
                child_text=child_text,
                child_index=child_index,
            )
            for child_index, child_text in enumerate(child_texts)
        )

        child_refs = tuple(child.unit_ref for child in child_units)
        if len(set(child_refs)) != len(child_refs):
            raise ValueError("split produced duplicate child refs")

        return SourceUnitSplitResult(
            parent_unit=command.source_unit,
            child_units=child_units,
        )

    def _paragraphs(self, text: str) -> tuple[str, ...]:
        return tuple(
            paragraph.strip()
            for paragraph in re.split(r"\n\s*\n", text)
            if paragraph.strip()
        )

    def _group_paragraphs(
        self,
        *,
        paragraphs: tuple[str, ...],
        max_child_characters: int,
    ) -> tuple[str, ...]:
        if not paragraphs:
            raise SourceUnitCannotBeSplitFurther(
                "Source unit has no paragraphs to split"
            )

        chunks: list[str] = []
        current_chunk = ""

        for paragraph in paragraphs:
            if len(paragraph) > max_child_characters:
                raise SourceUnitCannotBeSplitFurther(
                    "Single paragraph exceeds max_child_characters"
                )

            if not current_chunk:
                current_chunk = paragraph
                continue

            candidate = f"{current_chunk}\n\n{paragraph}"
            if len(candidate) <= max_child_characters:
                current_chunk = candidate
                continue

            chunks.append(current_chunk)
            current_chunk = paragraph

        if current_chunk:
            chunks.append(current_chunk)

        return tuple(chunks)

    def _build_child_unit(
        self,
        *,
        parent: SourceUnit,
        child_text: str,
        child_index: int,
    ) -> SourceUnit:
        return SourceUnit(
            unit_ref=SourceUnitRef(f"{parent.unit_ref.value}.split.{child_index}"),
            document_ref=parent.document_ref,
            unit_kind=SourceUnitKind.SPLIT_FRAGMENT,
            text=SourceUnitText(child_text),
            heading_path=parent.heading_path,
            lineage=SourceUnitLineage(parent_refs=(parent.unit_ref,)),
            ordinal=parent.ordinal * 1000 + child_index,
            created_at=parent.created_at,
        )
