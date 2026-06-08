from __future__ import annotations

from typing import Protocol

from src.contexts.knowledge_workbench.source_management.domain.entities.source_document import (
    SourceDocument,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)


class SourceParserPort(Protocol):
    def parse(
        self,
        *,
        document: SourceDocument,
        raw_text: str,
    ) -> tuple[SourceUnit, ...]: ...
