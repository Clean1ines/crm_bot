from __future__ import annotations

from src.application.ports.knowledge.answer_candidates import (
    KnowledgeAnswerCandidatePort,
)
from src.application.ports.knowledge.canonical_entries import (
    KnowledgeCanonicalEntryPort,
)
from src.application.ports.knowledge.compilation_trace import (
    KnowledgeCompilationTracePort,
)
from src.application.ports.knowledge.curation import KnowledgeCurationPort
from src.application.ports.knowledge.documents import (
    KnowledgeDbPoolPort,
    KnowledgeDocumentPort,
    KnowledgeDocumentRuntimeEntries,
)
from src.application.ports.knowledge.runtime_retrieval import (
    KnowledgeRuntimeRetrievalPort,
)
from src.application.ports.knowledge.source_material import KnowledgeSourceMaterialPort

__all__ = [
    "KnowledgeAnswerCandidatePort",
    "KnowledgeCanonicalEntryPort",
    "KnowledgeCompilationTracePort",
    "KnowledgeCurationPort",
    "KnowledgeDbPoolPort",
    "KnowledgeDocumentPort",
    "KnowledgeDocumentRuntimeEntries",
    "KnowledgeRuntimeRetrievalPort",
    "KnowledgeSourceMaterialPort",
]
