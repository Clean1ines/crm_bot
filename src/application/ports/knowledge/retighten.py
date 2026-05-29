from __future__ import annotations

from typing import Protocol

from src.application.ports.knowledge.canonical_entries import (
    KnowledgeCanonicalEntryPort,
)
from src.application.ports.knowledge.documents import KnowledgeDbPoolPort
from src.application.ports.knowledge.runtime_retrieval import (
    KnowledgeRuntimeRetrievalPort,
)


class KnowledgeRetightenRepositoryPort(
    KnowledgeCanonicalEntryPort,
    KnowledgeRuntimeRetrievalPort,
    Protocol,
):
    """Repository surface for retightening already published runtime entries."""


class KnowledgeRetightenRepositoryFactoryPort(Protocol):
    def __call__(
        self,
        pool: KnowledgeDbPoolPort,
    ) -> KnowledgeRetightenRepositoryPort: ...


__all__ = [
    "KnowledgeRetightenRepositoryFactoryPort",
    "KnowledgeRetightenRepositoryPort",
]
