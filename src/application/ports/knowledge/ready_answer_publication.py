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


class KnowledgeStageEPublicationPort(
    KnowledgeAnswerCandidatePort,
    KnowledgeCanonicalEntryPort,
    KnowledgeCompilationTracePort,
    Protocol,
):
    """Minimal persistence surface for publishing Stage E compiler outputs."""


class KnowledgeReadyAnswerPublicationRepositoryPort(
    KnowledgeDocumentPort,
    KnowledgeSourceMaterialPort,
    KnowledgeCompilationTracePort,
    KnowledgeAnswerCandidatePort,
    KnowledgeCanonicalEntryPort,
    Protocol,
):
    """Repository surface for publishing already compiled ready answers."""


class KnowledgeReadyAnswerPublicationRepositoryFactoryPort(Protocol):
    def __call__(
        self,
        pool: KnowledgeDbPoolPort,
    ) -> KnowledgeReadyAnswerPublicationRepositoryPort: ...


__all__ = [
    "KnowledgeReadyAnswerPublicationRepositoryFactoryPort",
    "KnowledgeReadyAnswerPublicationRepositoryPort",
    "KnowledgeStageEPublicationPort",
]
