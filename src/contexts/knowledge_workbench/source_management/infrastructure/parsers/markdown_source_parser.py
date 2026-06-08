from __future__ import annotations

import re
from dataclasses import dataclass

from src.contexts.knowledge_workbench.source_management.domain.entities.source_document import (
    SourceDocument,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.heading_path import (
    HeadingPath,
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


_HEADING_PATTERN = re.compile(r"^(#{1,3})\s+(.+?)\s*$")


@dataclass(frozen=True, slots=True)
class _Heading:
    line_index: int
    level: int
    title: str


class MarkdownSourceParser:
    """Parse Markdown into source units.

    Default split boundary is the highest-level heading present in the document.
    If a document contains # headings, nested ##/### headings remain inside the
    parent source unit instead of becoming separate units.
    """

    def parse(
        self,
        *,
        document: SourceDocument,
        raw_text: str,
    ) -> tuple[SourceUnit, ...]:
        if not raw_text or not raw_text.strip():
            raise ValueError("raw_text must be non-empty")

        lines = raw_text.strip().splitlines()
        headings = self._find_headings(lines)

        if not headings:
            return (
                self._build_unit(
                    document=document,
                    ordinal=0,
                    unit_kind=SourceUnitKind.DOCUMENT,
                    text="\n".join(lines).strip(),
                    heading_path=HeadingPath(()),
                ),
            )

        boundary_level = min(heading.level for heading in headings)
        boundary_headings = tuple(
            heading for heading in headings if heading.level == boundary_level
        )

        units: list[SourceUnit] = []
        for ordinal, heading in enumerate(boundary_headings):
            next_heading = (
                boundary_headings[ordinal + 1]
                if ordinal + 1 < len(boundary_headings)
                else None
            )
            start_line = heading.line_index
            end_line = (
                next_heading.line_index if next_heading is not None else len(lines)
            )
            unit_text = "\n".join(lines[start_line:end_line]).strip()

            units.append(
                self._build_unit(
                    document=document,
                    ordinal=ordinal,
                    unit_kind=self._unit_kind_for_heading_level(heading.level),
                    text=unit_text,
                    heading_path=HeadingPath((heading.title,)),
                )
            )

        return tuple(units)

    def _find_headings(self, lines: list[str]) -> tuple[_Heading, ...]:
        headings: list[_Heading] = []

        for line_index, line in enumerate(lines):
            match = _HEADING_PATTERN.match(line)
            if match is None:
                continue

            headings.append(
                _Heading(
                    line_index=line_index,
                    level=len(match.group(1)),
                    title=match.group(2).strip(),
                )
            )

        return tuple(headings)

    def _build_unit(
        self,
        *,
        document: SourceDocument,
        ordinal: int,
        unit_kind: SourceUnitKind,
        text: str,
        heading_path: HeadingPath,
    ) -> SourceUnit:
        return SourceUnit(
            unit_ref=SourceUnitRef(f"{document.document_ref.value}.unit.{ordinal}"),
            document_ref=document.document_ref,
            unit_kind=unit_kind,
            text=SourceUnitText(text),
            heading_path=heading_path,
            lineage=SourceUnitLineage(),
            ordinal=ordinal,
            created_at=document.created_at,
        )

    def _unit_kind_for_heading_level(self, heading_level: int) -> SourceUnitKind:
        if heading_level == 1:
            return SourceUnitKind.SECTION
        return SourceUnitKind.SUBSECTION
