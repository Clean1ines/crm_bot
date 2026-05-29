from __future__ import annotations

from typing import Protocol

from src.application.ports.knowledge.answer_candidates import (
    KnowledgeAnswerCandidatePort,
)
from src.application.ports.knowledge.canonical_entries import (
    KnowledgeCanonicalEntryPort,
)
from src.application.ports.knowledge.compilation_trace import (
    KnowledgeCompilationTracePort,
)
from src.application.ports.knowledge.documents import (
    KnowledgeDbPoolPort,
    KnowledgeDocumentPort,
)
from src.application.ports.knowledge.source_material import KnowledgeSourceMaterialPort


class KnowledgeFailedBatchRetryRepositoryPort(
    KnowledgeDocumentPort,
    KnowledgeSourceMaterialPort,
    KnowledgeCompilationTracePort,
    KnowledgeAnswerCandidatePort,
    KnowledgeCanonicalEntryPort,
    Protocol,
):
    """Repository surface for retrying failed structured ingestion compiler batches."""


class KnowledgeFailedBatchRetryRepositoryFactoryPort(Protocol):
    def __call__(
        self,
        pool: KnowledgeDbPoolPort,
    ) -> KnowledgeFailedBatchRetryRepositoryPort: ...


__all__ = [
    "KnowledgeFailedBatchRetryRepositoryFactoryPort",
    "KnowledgeFailedBatchRetryRepositoryPort",
]
