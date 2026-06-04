from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from src.application.services.faq_workbench_local_claim_graph_loader_service import (
    FaqWorkbenchLocalClaimGraphLoaderService,
    LoadDocumentLocalClaimGraphsCommand,
)
from src.domain.project_plane.knowledge_workbench.local_claim_retrieval import (
    LocalClaimSimilarityEdge,
    LocalClaimSimilaritySignal,
)
from src.domain.project_plane.knowledge_workbench.local_claim_search import (
    LocalClaimSearchDocument,
    local_claim_search_documents_from_graphs,
)
from src.domain.project_plane.knowledge_workbench.shared import DomainInvariantError


class LocalClaimRetrievalSurfaceEmbeddingPort(Protocol):
    async def embed_passages(
        self,
        texts: list[str],
    ) -> LocalClaimRetrievalSurfaceEmbeddingResult: ...


class LocalClaimRetrievalSurfaceRepositoryPort(Protocol):
    async def has_indexed_local_claim_retrieval_entries_for_node_run(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        node_run_id: str,
    ) -> bool: ...

    async def replace_local_claim_retrieval_entries(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        entries: tuple[LocalClaimRetrievalSurfaceEntry, ...],
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class LocalClaimRetrievalSurfaceEmbeddingResult:
    embeddings: list[list[float]]


@dataclass(frozen=True, slots=True)
class LocalClaimRetrievalSurfaceEntry:
    entry_id: str
    project_id: str
    document_id: str
    processing_run_id: str
    section_id: str
    node_run_id: str
    search_document_id: str
    local_ref: str
    claim: str
    claim_kind: str
    granularity: str
    search_text: str
    triple_texts: tuple[str, ...]
    possible_questions: tuple[str, ...]
    scope: str
    exclusion_scope: str
    evidence_block: str
    relation_texts: tuple[str, ...]
    embedding: tuple[float, ...]
    status: str = "indexed"


@dataclass(frozen=True, slots=True)
class CheckLocalClaimRetrievalSurfaceIndexedCommand:
    project_id: str
    document_id: str
    processing_run_id: str
    node_run_id: str

    def __post_init__(self) -> None:
        if not self.project_id:
            raise DomainInvariantError(
                "local claim retrieval surface index check requires project_id"
            )
        if not self.document_id:
            raise DomainInvariantError(
                "local claim retrieval surface index check requires document_id"
            )
        if not self.processing_run_id:
            raise DomainInvariantError(
                "local claim retrieval surface index check requires processing_run_id"
            )
        if not self.node_run_id:
            raise DomainInvariantError(
                "local claim retrieval surface index check requires node_run_id"
            )


@dataclass(frozen=True, slots=True)
class CheckLocalClaimRetrievalSurfaceIndexedResult:
    indexed: bool


@dataclass(frozen=True, slots=True)
class IndexDocumentLocalClaimRetrievalSurfaceCommand:
    project_id: str
    document_id: str
    processing_run_id: str
    search_documents: tuple[LocalClaimSearchDocument, ...] | None = None
    min_vector_similarity_score: float = 0.72

    def __post_init__(self) -> None:
        if not self.project_id:
            raise DomainInvariantError(
                "local claim retrieval surface indexing requires project_id"
            )
        if not self.document_id:
            raise DomainInvariantError(
                "local claim retrieval surface indexing requires document_id"
            )
        if not self.processing_run_id:
            raise DomainInvariantError(
                "local claim retrieval surface indexing requires processing_run_id"
            )
        if self.min_vector_similarity_score < 0 or self.min_vector_similarity_score > 1:
            raise DomainInvariantError(
                "local claim retrieval surface min_vector_similarity_score must be in [0, 1]"
            )


@dataclass(frozen=True, slots=True)
class IndexDocumentLocalClaimRetrievalSurfaceResult:
    indexed_entry_count: int
    indexed_node_run_count: int
    vector_similarity_edges: tuple[LocalClaimSimilarityEdge, ...]

    @property
    def vector_edge_count(self) -> int:
        return len(self.vector_similarity_edges)


@dataclass(frozen=True, slots=True)
class FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService:
    graph_loader: FaqWorkbenchLocalClaimGraphLoaderService
    repository: LocalClaimRetrievalSurfaceRepositoryPort
    embedding_service: LocalClaimRetrievalSurfaceEmbeddingPort

    async def has_indexed_node_run(
        self,
        command: CheckLocalClaimRetrievalSurfaceIndexedCommand,
    ) -> CheckLocalClaimRetrievalSurfaceIndexedResult:
        indexed = await self.repository.has_indexed_local_claim_retrieval_entries_for_node_run(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=command.processing_run_id,
            node_run_id=command.node_run_id,
        )
        return CheckLocalClaimRetrievalSurfaceIndexedResult(indexed=indexed)

    async def index_document_local_claim_retrieval_surface(
        self,
        command: IndexDocumentLocalClaimRetrievalSurfaceCommand,
    ) -> IndexDocumentLocalClaimRetrievalSurfaceResult:
        search_documents = command.search_documents
        if search_documents is None:
            graph_result = await self.graph_loader.load_document_local_claim_graphs(
                LoadDocumentLocalClaimGraphsCommand(
                    project_id=command.project_id,
                    document_id=command.document_id,
                    processing_run_id=command.processing_run_id,
                )
            )
            search_documents = local_claim_search_documents_from_graphs(
                tuple(item.graph for item in graph_result.graphs)
            )

        if not search_documents:
            indexed_count = await self.repository.replace_local_claim_retrieval_entries(
                project_id=command.project_id,
                document_id=command.document_id,
                processing_run_id=command.processing_run_id,
                entries=(),
            )
            return IndexDocumentLocalClaimRetrievalSurfaceResult(
                indexed_entry_count=indexed_count,
                indexed_node_run_count=0,
                vector_similarity_edges=(),
            )

        embedding_result = await self.embedding_service.embed_passages(
            [document.search_text for document in search_documents]
        )
        if len(embedding_result.embeddings) != len(search_documents):
            raise DomainInvariantError(
                "local claim retrieval surface embedding count does not match documents"
            )

        entries = tuple(
            _entry_from_search_document(
                processing_run_id=command.processing_run_id,
                document=document,
                embedding=tuple(float(value) for value in vector),
            )
            for document, vector in zip(
                search_documents,
                embedding_result.embeddings,
                strict=True,
            )
        )

        indexed_count = await self.repository.replace_local_claim_retrieval_entries(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=command.processing_run_id,
            entries=entries,
        )
        vector_edges = _vector_similarity_edges(
            search_documents=search_documents,
            embeddings=tuple(entry.embedding for entry in entries),
            min_score=command.min_vector_similarity_score,
        )

        return IndexDocumentLocalClaimRetrievalSurfaceResult(
            indexed_entry_count=indexed_count,
            indexed_node_run_count=len({entry.node_run_id for entry in entries}),
            vector_similarity_edges=vector_edges,
        )


def _entry_from_search_document(
    *,
    processing_run_id: str,
    document: LocalClaimSearchDocument,
    embedding: tuple[float, ...],
) -> LocalClaimRetrievalSurfaceEntry:
    if not embedding:
        raise DomainInvariantError("local claim retrieval surface embedding is empty")

    return LocalClaimRetrievalSurfaceEntry(
        entry_id=(
            "local_claim:"
            f"{document.project_id}:"
            f"{document.document_id}:"
            f"{processing_run_id}:"
            f"{document.search_document_id}"
        ),
        project_id=str(document.project_id),
        document_id=str(document.document_id),
        processing_run_id=processing_run_id,
        section_id=str(document.section_id),
        node_run_id=str(document.node_run_id),
        search_document_id=document.search_document_id,
        local_ref=document.local_ref,
        claim=document.claim,
        claim_kind=document.claim_kind,
        granularity=document.granularity,
        search_text=document.search_text,
        triple_texts=document.triple_texts,
        possible_questions=document.possible_questions,
        scope=document.scope,
        exclusion_scope=document.exclusion_scope,
        evidence_block=document.evidence_block,
        relation_texts=document.relation_texts,
        embedding=embedding,
    )


def _vector_similarity_edges(
    *,
    search_documents: tuple[LocalClaimSearchDocument, ...],
    embeddings: tuple[tuple[float, ...], ...],
    min_score: float,
) -> tuple[LocalClaimSimilarityEdge, ...]:
    edges: list[LocalClaimSimilarityEdge] = []

    for left_index, left_document in enumerate(search_documents):
        left_vector = embeddings[left_index]
        for right_index in range(left_index + 1, len(search_documents)):
            right_document = search_documents[right_index]
            right_vector = embeddings[right_index]
            score = _cosine_score_0_1(left_vector, right_vector)
            if score < min_score:
                continue
            edges.append(
                LocalClaimSimilarityEdge(
                    source_search_document_id=left_document.search_document_id,
                    target_search_document_id=right_document.search_document_id,
                    score=score,
                    signals=(
                        LocalClaimSimilaritySignal(
                            signal_type="embedding_similarity",
                            score=score,
                        ),
                    ),
                )
            )

    return tuple(
        sorted(
            edges,
            key=lambda item: (
                -item.score,
                item.source_search_document_id,
                item.target_search_document_id,
            ),
        )
    )


def _cosine_score_0_1(
    left: Sequence[float],
    right: Sequence[float],
) -> float:
    if len(left) != len(right):
        raise DomainInvariantError(
            "local claim retrieval surface vector dimensions do not match"
        )

    dot = sum(left_value * right_value for left_value, right_value in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0

    cosine = dot / (left_norm * right_norm)
    bounded_cosine = max(-1.0, min(1.0, cosine))
    return (bounded_cosine + 1.0) / 2.0


__all__ = [
    "CheckLocalClaimRetrievalSurfaceIndexedCommand",
    "CheckLocalClaimRetrievalSurfaceIndexedResult",
    "FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService",
    "IndexDocumentLocalClaimRetrievalSurfaceCommand",
    "IndexDocumentLocalClaimRetrievalSurfaceResult",
    "LocalClaimRetrievalSurfaceEmbeddingPort",
    "LocalClaimRetrievalSurfaceEmbeddingResult",
    "LocalClaimRetrievalSurfaceEntry",
    "LocalClaimRetrievalSurfaceRepositoryPort",
]
