from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.knowledge_workbench.source_management.application.ports.source_parser_port import (
    SourceParserPort,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_document import (
    SourceDocument,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.heading_path import (
    HeadingPath,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
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


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _document() -> SourceDocument:
    return SourceDocument(
        document_ref=SourceDocumentRef("document-1"),
        source_format=SourceFormat.MARKDOWN,
        content_hash="sha256:abc",
        created_at=_now(),
        original_filename="knowledge.md",
    )


def _unit(document: SourceDocument) -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef(f"{document.document_ref.value}.unit.0"),
        document_ref=document.document_ref,
        unit_kind=SourceUnitKind.DOCUMENT,
        text=SourceUnitText("Plain text."),
        heading_path=HeadingPath(()),
        lineage=SourceUnitLineage(),
        ordinal=0,
        created_at=document.created_at,
    )


class FakeSourceParser:
    def parse(
        self,
        *,
        document: SourceDocument,
        raw_text: str,
    ) -> tuple[SourceUnit, ...]:
        if not raw_text:
            return ()
        return (_unit(document),)


def _accept_parser(parser: SourceParserPort) -> SourceParserPort:
    return parser


def test_fake_source_parser_implements_port_contract() -> None:
    parser = FakeSourceParser()
    document = _document()

    accepted = _accept_parser(parser)

    assert accepted.parse(document=document, raw_text="text") == (_unit(document),)
