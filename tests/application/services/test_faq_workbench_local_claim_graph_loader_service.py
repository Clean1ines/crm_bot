from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from src.application.services.faq_workbench_local_claim_graph_loader_service import (
    FaqWorkbenchLocalClaimGraphLoaderService,
    LoadDocumentLocalClaimGraphsCommand,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
)


def _valid_payload(local_ref: str = "c1") -> dict[str, object]:
    return {
        "claim_observations": [
            {
                "local_ref": local_ref,
                "claim": "Бот автоматически отвечает клиентам в Telegram.",
                "claim_kind": "capability",
                "granularity": "atomic",
                "triples": [
                    {
                        "subject": "бот",
                        "predicate": "has_capability",
                        "object": "автоматически отвечать клиентам в Telegram",
                        "qualifiers": [],
                    }
                ],
                "evidence_block": "Бот автоматически отвечает клиентам в Telegram.",
                "possible_questions": ["Может ли бот отвечать клиентам в Telegram?"],
                "scope": "автоматические ответы в Telegram",
                "exclusion_scope": "",
                "local_relations": [],
                "confidence": 0.92,
            }
        ],
        "metadata": {
            "claim_observation_count": 1,
        },
    }


def _artifact(
    *,
    artifact_id: str = "artifact-1",
    node_run_id: str = "node-run-1",
    section_id: str | None = "section-1",
    payload_json: dict[str, object] | None = None,
) -> ProcessingNodeArtifact:
    return ProcessingNodeArtifact(
        artifact_id=artifact_id,
        node_run_id=node_run_id,
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        section_id=section_id,
        artifact_type=ProcessingNodeArtifactType.PARSED_LLM_OUTPUT,
        payload_json=payload_json if payload_json is not None else _valid_payload(),
        schema_version=1,
        metadata={"section_index": 1, "source": "test"},
        created_at=datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc),
    )


@dataclass
class FakeRepository:
    artifacts: tuple[ProcessingNodeArtifact, ...]
    calls: list[tuple[str, str, str]]

    async def list_claim_observation_parsed_artifacts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> tuple[ProcessingNodeArtifact, ...]:
        self.calls.append((project_id, document_id, processing_run_id))
        return self.artifacts


@pytest.mark.asyncio
async def test_load_document_local_claim_graphs_returns_empty_result_for_no_artifacts() -> (
    None
):
    repository = FakeRepository(artifacts=(), calls=[])
    service = FaqWorkbenchLocalClaimGraphLoaderService(repository=repository)

    result = await service.load_document_local_claim_graphs(
        LoadDocumentLocalClaimGraphsCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
        )
    )

    assert result.graphs == ()
    assert result.graph_count == 0
    assert result.claim_count == 0
    assert repository.calls == [("project-1", "document-1", "processing-run-1")]


@pytest.mark.asyncio
async def test_load_document_local_claim_graphs_converts_artifacts_to_graphs() -> None:
    repository = FakeRepository(
        artifacts=(
            _artifact(
                artifact_id="artifact-1",
                node_run_id="node-run-1",
                section_id="section-1",
                payload_json=_valid_payload("c1"),
            ),
            _artifact(
                artifact_id="artifact-2",
                node_run_id="node-run-2",
                section_id="section-2",
                payload_json=_valid_payload("c2"),
            ),
        ),
        calls=[],
    )
    service = FaqWorkbenchLocalClaimGraphLoaderService(repository=repository)

    result = await service.load_document_local_claim_graphs(
        LoadDocumentLocalClaimGraphsCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
        )
    )

    assert result.graph_count == 2
    assert result.claim_count == 2

    first = result.graphs[0]
    assert first.artifact_id == "artifact-1"
    assert first.node_run_id == "node-run-1"
    assert first.section_id == "section-1"
    assert first.artifact_metadata == {"section_index": 1, "source": "test"}
    assert first.graph.project_id == "project-1"
    assert first.graph.document_id == "document-1"
    assert first.graph.section_id == "section-1"
    assert first.graph.node_run_id == "node-run-1"
    assert first.graph.claims[0].local_ref == "c1"
    assert first.graph.claims[0].triples[0].predicate == "has_capability"


@pytest.mark.asyncio
async def test_load_document_local_claim_graphs_rejects_artifact_without_section_id() -> (
    None
):
    repository = FakeRepository(
        artifacts=(_artifact(section_id=None),),
        calls=[],
    )
    service = FaqWorkbenchLocalClaimGraphLoaderService(repository=repository)

    with pytest.raises(DomainInvariantError, match="section_id"):
        await service.load_document_local_claim_graphs(
            LoadDocumentLocalClaimGraphsCommand(
                project_id="project-1",
                document_id="document-1",
                processing_run_id="processing-run-1",
            )
        )


@pytest.mark.asyncio
async def test_load_document_local_claim_graphs_propagates_invalid_payload_error() -> (
    None
):
    repository = FakeRepository(
        artifacts=(
            _artifact(
                payload_json={
                    "claim_observations": [],
                }
            ),
        ),
        calls=[],
    )
    service = FaqWorkbenchLocalClaimGraphLoaderService(repository=repository)

    with pytest.raises(DomainInvariantError, match="non-empty claim_observations"):
        await service.load_document_local_claim_graphs(
            LoadDocumentLocalClaimGraphsCommand(
                project_id="project-1",
                document_id="document-1",
                processing_run_id="processing-run-1",
            )
        )


def test_load_document_local_claim_graphs_command_requires_ids() -> None:
    with pytest.raises(DomainInvariantError, match="project_id"):
        LoadDocumentLocalClaimGraphsCommand(
            project_id="",
            document_id="document-1",
            processing_run_id="processing-run-1",
        )

    with pytest.raises(DomainInvariantError, match="document_id"):
        LoadDocumentLocalClaimGraphsCommand(
            project_id="project-1",
            document_id="",
            processing_run_id="processing-run-1",
        )

    with pytest.raises(DomainInvariantError, match="processing_run_id"):
        LoadDocumentLocalClaimGraphsCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="",
        )
