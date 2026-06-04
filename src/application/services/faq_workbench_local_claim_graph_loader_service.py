from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    JsonValue,
    LocalClaimGraph,
    ProcessingNodeArtifact,
    local_claim_graph_from_claim_observations_payload,
)


class LocalClaimGraphArtifactRepositoryPort(Protocol):
    async def list_claim_observation_parsed_artifacts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> tuple[ProcessingNodeArtifact, ...]: ...


@dataclass(frozen=True, slots=True)
class LoadDocumentLocalClaimGraphsCommand:
    project_id: str
    document_id: str
    processing_run_id: str

    def __post_init__(self) -> None:
        if not self.project_id:
            raise DomainInvariantError("local claim graph loading requires project_id")
        if not self.document_id:
            raise DomainInvariantError("local claim graph loading requires document_id")
        if not self.processing_run_id:
            raise DomainInvariantError(
                "local claim graph loading requires processing_run_id"
            )


@dataclass(frozen=True, slots=True)
class DocumentLocalClaimGraph:
    artifact_id: str
    node_run_id: str
    section_id: str
    graph: LocalClaimGraph
    artifact_metadata: dict[str, JsonValue]

    def __post_init__(self) -> None:
        if not self.artifact_id:
            raise DomainInvariantError(
                "document local claim graph requires artifact_id"
            )
        if not self.node_run_id:
            raise DomainInvariantError(
                "document local claim graph requires node_run_id"
            )
        if not self.section_id:
            raise DomainInvariantError("document local claim graph requires section_id")


@dataclass(frozen=True, slots=True)
class LoadDocumentLocalClaimGraphsResult:
    graphs: tuple[DocumentLocalClaimGraph, ...]

    @property
    def graph_count(self) -> int:
        return len(self.graphs)

    @property
    def claim_count(self) -> int:
        return sum(len(item.graph.claims) for item in self.graphs)


@dataclass(frozen=True, slots=True)
class FaqWorkbenchLocalClaimGraphLoaderService:
    repository: LocalClaimGraphArtifactRepositoryPort

    async def load_document_local_claim_graphs(
        self,
        command: LoadDocumentLocalClaimGraphsCommand,
    ) -> LoadDocumentLocalClaimGraphsResult:
        artifacts = await self.repository.list_claim_observation_parsed_artifacts(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=command.processing_run_id,
        )

        graphs: list[DocumentLocalClaimGraph] = []
        for artifact in artifacts:
            if artifact.section_id is None:
                raise DomainInvariantError(
                    "claim observation parsed artifact requires section_id"
                )

            graph = local_claim_graph_from_claim_observations_payload(
                artifact.payload_json,
                project_id=artifact.project_id,
                document_id=artifact.document_id,
                section_id=artifact.section_id,
                node_run_id=artifact.node_run_id,
            )
            graphs.append(
                DocumentLocalClaimGraph(
                    artifact_id=artifact.artifact_id,
                    node_run_id=artifact.node_run_id,
                    section_id=artifact.section_id,
                    graph=graph,
                    artifact_metadata=dict(artifact.metadata),
                )
            )

        return LoadDocumentLocalClaimGraphsResult(graphs=tuple(graphs))


__all__ = [
    "DocumentLocalClaimGraph",
    "FaqWorkbenchLocalClaimGraphLoaderService",
    "LoadDocumentLocalClaimGraphsCommand",
    "LoadDocumentLocalClaimGraphsResult",
    "LocalClaimGraphArtifactRepositoryPort",
]
