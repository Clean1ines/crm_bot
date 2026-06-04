from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.application.services.faq_workbench_local_claim_graph_loader_service import (
    FaqWorkbenchLocalClaimGraphLoaderService,
    LoadDocumentLocalClaimGraphsCommand,
)
from src.application.services.faq_workbench_local_claim_retrieval_surface_indexing_service import (
    IndexDocumentLocalClaimRetrievalSurfaceCommand,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    LocalClaimCandidateGroup,
    LocalClaimCanonicalizationUnit,
    LocalClaimSearchDocument,
    LocalClaimSimilarityEdge,
    build_local_claim_candidate_groups,
    build_local_claim_hybrid_similarity_edges,
    local_claim_canonicalization_units_from_retrieval,
    local_claim_search_documents_from_graphs,
)


class LocalClaimRetrievalSurfaceIndexingPort(Protocol):
    async def index_document_local_claim_retrieval_surface(
        self,
        command: IndexDocumentLocalClaimRetrievalSurfaceCommand,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class BuildDocumentLocalClaimRetrievalCommand:
    project_id: str
    document_id: str
    processing_run_id: str
    min_similarity_score: float = 0.18

    def __post_init__(self) -> None:
        if not self.project_id:
            raise DomainInvariantError("local claim retrieval requires project_id")
        if not self.document_id:
            raise DomainInvariantError("local claim retrieval requires document_id")
        if not self.processing_run_id:
            raise DomainInvariantError(
                "local claim retrieval requires processing_run_id"
            )
        if self.min_similarity_score < 0 or self.min_similarity_score > 1:
            raise DomainInvariantError(
                "local claim retrieval min_similarity_score must be in [0, 1]"
            )


@dataclass(frozen=True, slots=True)
class DocumentLocalClaimRetrievalResult:
    search_documents: tuple[LocalClaimSearchDocument, ...]
    similarity_edges: tuple[LocalClaimSimilarityEdge, ...]
    candidate_groups: tuple[LocalClaimCandidateGroup, ...]
    canonicalization_units: tuple[LocalClaimCanonicalizationUnit, ...]

    @property
    def claim_count(self) -> int:
        return len(self.search_documents)

    @property
    def edge_count(self) -> int:
        return len(self.similarity_edges)

    @property
    def group_count(self) -> int:
        return len(self.candidate_groups)

    @property
    def unit_count(self) -> int:
        return len(self.canonicalization_units)

    @property
    def singleton_group_count(self) -> int:
        return sum(
            1 for group in self.candidate_groups if len(group.search_document_ids) == 1
        )


@dataclass(frozen=True, slots=True)
class FaqWorkbenchLocalClaimRetrievalService:
    graph_loader: FaqWorkbenchLocalClaimGraphLoaderService
    retrieval_surface_indexing_service: (
        LocalClaimRetrievalSurfaceIndexingPort | None
    ) = None

    async def build_document_local_claim_retrieval(
        self,
        command: BuildDocumentLocalClaimRetrievalCommand,
    ) -> DocumentLocalClaimRetrievalResult:
        graph_result = await self.graph_loader.load_document_local_claim_graphs(
            LoadDocumentLocalClaimGraphsCommand(
                project_id=command.project_id,
                document_id=command.document_id,
                processing_run_id=command.processing_run_id,
            )
        )

        graphs = tuple(item.graph for item in graph_result.graphs)
        search_documents = local_claim_search_documents_from_graphs(graphs)
        vector_edges = await self._index_and_get_vector_edges(
            command=command,
            search_documents=search_documents,
        )
        deterministic_edges = build_local_claim_hybrid_similarity_edges(
            search_documents,
            min_score=command.min_similarity_score,
        )
        similarity_edges = _merge_similarity_edges(
            deterministic_edges=deterministic_edges,
            vector_edges=vector_edges,
        )
        candidate_groups = build_local_claim_candidate_groups(
            search_documents,
            similarity_edges,
        )
        canonicalization_units = local_claim_canonicalization_units_from_retrieval(
            search_documents=search_documents,
            candidate_groups=candidate_groups,
            similarity_edges=similarity_edges,
        )

        return DocumentLocalClaimRetrievalResult(
            search_documents=search_documents,
            similarity_edges=similarity_edges,
            candidate_groups=candidate_groups,
            canonicalization_units=canonicalization_units,
        )

    async def _index_and_get_vector_edges(
        self,
        *,
        command: BuildDocumentLocalClaimRetrievalCommand,
        search_documents: tuple[LocalClaimSearchDocument, ...],
    ) -> tuple[LocalClaimSimilarityEdge, ...]:
        if self.retrieval_surface_indexing_service is None:
            return ()

        indexing_result = await self.retrieval_surface_indexing_service.index_document_local_claim_retrieval_surface(
            IndexDocumentLocalClaimRetrievalSurfaceCommand(
                project_id=command.project_id,
                document_id=command.document_id,
                processing_run_id=command.processing_run_id,
                search_documents=search_documents,
            )
        )
        vector_edges = getattr(indexing_result, "vector_similarity_edges", ())
        if isinstance(vector_edges, tuple) and all(
            isinstance(edge, LocalClaimSimilarityEdge) for edge in vector_edges
        ):
            return vector_edges
        return ()


def _merge_similarity_edges(
    *,
    deterministic_edges: tuple[LocalClaimSimilarityEdge, ...],
    vector_edges: tuple[LocalClaimSimilarityEdge, ...],
) -> tuple[LocalClaimSimilarityEdge, ...]:
    merged: dict[tuple[str, str], LocalClaimSimilarityEdge] = {}

    for edge in deterministic_edges + vector_edges:
        left_id, right_id = sorted(
            (
                edge.source_search_document_id,
                edge.target_search_document_id,
            )
        )
        key: tuple[str, str] = (left_id, right_id)
        existing = merged.get(key)
        if existing is None:
            merged[key] = edge
            continue

        merged[key] = LocalClaimSimilarityEdge(
            source_search_document_id=existing.source_search_document_id,
            target_search_document_id=existing.target_search_document_id,
            score=max(existing.score, edge.score),
            signals=tuple(
                sorted(
                    existing.signals + edge.signals,
                    key=lambda signal: signal.signal_type,
                )
            ),
        )

    return tuple(
        sorted(
            merged.values(),
            key=lambda item: (
                -item.score,
                item.source_search_document_id,
                item.target_search_document_id,
            ),
        )
    )


__all__ = [
    "BuildDocumentLocalClaimRetrievalCommand",
    "DocumentLocalClaimRetrievalResult",
    "FaqWorkbenchLocalClaimRetrievalService",
    "LocalClaimRetrievalSurfaceIndexingPort",
]
