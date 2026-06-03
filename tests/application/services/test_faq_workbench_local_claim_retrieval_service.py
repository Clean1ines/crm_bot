from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from src.application.services.faq_workbench_local_claim_graph_loader_service import (
    FaqWorkbenchLocalClaimGraphLoaderService,
)
from src.application.services.faq_workbench_local_claim_retrieval_service import (
    BuildDocumentLocalClaimRetrievalCommand,
    FaqWorkbenchLocalClaimRetrievalService,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
)


def _payload(
    *,
    local_ref: str,
    claim: str,
    triple: dict[str, object],
    questions: tuple[str, ...] = (),
    scope: str = "",
    exclusion_scope: str = "",
) -> dict[str, object]:
    return {
        "claim_observations": [
            {
                "local_ref": local_ref,
                "claim": claim,
                "claim_kind": "capability",
                "granularity": "atomic",
                "triples": [
                    {
                        "subject": triple["subject"],
                        "predicate": triple["predicate"],
                        "object": triple["object"],
                        "qualifiers": [],
                    }
                ],
                "evidence_block": claim,
                "possible_questions": list(questions),
                "scope": scope,
                "exclusion_scope": exclusion_scope,
                "local_relations": [],
                "confidence": 0.91,
            }
        ],
        "metadata": {"claim_observation_count": 1},
    }


def _artifact(
    *,
    artifact_id: str,
    node_run_id: str,
    section_id: str,
    payload_json: dict[str, object],
) -> ProcessingNodeArtifact:
    return ProcessingNodeArtifact(
        artifact_id=artifact_id,
        node_run_id=node_run_id,
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        section_id=section_id,
        artifact_type=ProcessingNodeArtifactType.PARSED_LLM_OUTPUT,
        payload_json=payload_json,
        schema_version=1,
        metadata={"section_id": section_id},
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


def _service(repository: FakeRepository) -> FaqWorkbenchLocalClaimRetrievalService:
    return FaqWorkbenchLocalClaimRetrievalService(
        graph_loader=FaqWorkbenchLocalClaimGraphLoaderService(
            repository=repository,
        )
    )


@pytest.mark.asyncio
async def test_build_document_local_claim_retrieval_returns_empty_package_for_no_artifacts() -> None:
    repository = FakeRepository(artifacts=(), calls=[])
    service = _service(repository)

    result = await service.build_document_local_claim_retrieval(
        BuildDocumentLocalClaimRetrievalCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
        )
    )

    assert result.search_documents == ()
    assert result.similarity_edges == ()
    assert result.candidate_groups == ()
    assert result.canonicalization_units == ()
    assert result.claim_count == 0
    assert result.edge_count == 0
    assert result.group_count == 0
    assert result.unit_count == 0
    assert result.singleton_group_count == 0
    assert repository.calls == [("project-1", "document-1", "processing-run-1")]


@pytest.mark.asyncio
async def test_build_document_local_claim_retrieval_builds_search_docs_edges_and_groups() -> None:
    repository = FakeRepository(
        artifacts=(
            _artifact(
                artifact_id="artifact-1",
                node_run_id="node-run-1",
                section_id="section-1",
                payload_json=_payload(
                    local_ref="c1",
                    claim="Бот автоматически отвечает клиентам в Telegram.",
                    triple={
                        "subject": "бот",
                        "predicate": "has_capability",
                        "object": "автоматически отвечать клиентам telegram",
                    },
                    questions=("Может ли бот отвечать клиентам в Telegram?",),
                    scope="автоматические ответы telegram",
                    exclusion_scope="не ручные ответы менеджера",
                ),
            ),
            _artifact(
                artifact_id="artifact-2",
                node_run_id="node-run-2",
                section_id="section-2",
                payload_json=_payload(
                    local_ref="c2",
                    claim="Telegram-бот отвечает клиентам автоматически.",
                    triple={
                        "subject": "telegram бот",
                        "predicate": "has_capability",
                        "object": "отвечать клиентам автоматически",
                    },
                    questions=("Отвечает ли бот клиентам автоматически?",),
                    scope="автоматические ответы telegram",
                    exclusion_scope="не работа менеджера вручную",
                ),
            ),
            _artifact(
                artifact_id="artifact-3",
                node_run_id="node-run-3",
                section_id="section-3",
                payload_json=_payload(
                    local_ref="c3",
                    claim="Оплата производится банковской картой.",
                    triple={
                        "subject": "оплата",
                        "predicate": "uses",
                        "object": "банковская карта",
                    },
                    questions=("Как оплатить заказ?",),
                    scope="оплата заказа",
                ),
            ),
        ),
        calls=[],
    )
    service = _service(repository)

    result = await service.build_document_local_claim_retrieval(
        BuildDocumentLocalClaimRetrievalCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            min_similarity_score=0.1,
        )
    )

    assert result.claim_count == 3
    assert tuple(document.local_ref for document in result.search_documents) == (
        "c1",
        "c2",
        "c3",
    )

    assert result.edge_count >= 1
    assert result.similarity_edges[0].source_search_document_id == (
        "section-1:node-run-1:c1"
    )
    assert result.similarity_edges[0].target_search_document_id == (
        "section-2:node-run-2:c2"
    )

    assert result.group_count >= 1
    assert result.candidate_groups[0].search_document_ids == (
        "section-1:node-run-1:c1",
        "section-2:node-run-2:c2",
    )
    assert result.candidate_groups[1].search_document_ids == (
        "section-3:node-run-3:c3",
    )
    assert result.unit_count == 2
    assert result.canonicalization_units[0].member_count == 2
    assert result.canonicalization_units[0].edge_count == 1
    assert tuple(
        member.local_ref for member in result.canonicalization_units[0].members
    ) == ("c1", "c2")
    assert result.canonicalization_units[1].member_count == 1
    assert result.canonicalization_units[1].edge_count == 0
    assert result.canonicalization_units[1].members[0].local_ref == "c3"
    assert result.singleton_group_count == 1


@pytest.mark.asyncio
async def test_build_document_local_claim_retrieval_respects_min_similarity_score() -> None:
    repository = FakeRepository(
        artifacts=(
            _artifact(
                artifact_id="artifact-1",
                node_run_id="node-run-1",
                section_id="section-1",
                payload_json=_payload(
                    local_ref="c1",
                    claim="Бот отвечает клиентам.",
                    triple={
                        "subject": "бот",
                        "predicate": "has_capability",
                        "object": "отвечать клиентам",
                    },
                ),
            ),
            _artifact(
                artifact_id="artifact-2",
                node_run_id="node-run-2",
                section_id="section-2",
                payload_json=_payload(
                    local_ref="c2",
                    claim="Бот отвечает клиентам в Telegram.",
                    triple={
                        "subject": "бот",
                        "predicate": "has_capability",
                        "object": "отвечать клиентам telegram",
                    },
                ),
            ),
        ),
        calls=[],
    )
    service = _service(repository)

    loose = await service.build_document_local_claim_retrieval(
        BuildDocumentLocalClaimRetrievalCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            min_similarity_score=0.1,
        )
    )
    strict = await service.build_document_local_claim_retrieval(
        BuildDocumentLocalClaimRetrievalCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            min_similarity_score=1.0,
        )
    )

    assert loose.edge_count == 1
    assert loose.unit_count == 1
    assert strict.edge_count == 0
    assert strict.group_count == 2
    assert strict.unit_count == 2
    assert all(unit.member_count == 1 for unit in strict.canonicalization_units)


def test_build_document_local_claim_retrieval_command_validates_ids_and_score() -> None:
    with pytest.raises(DomainInvariantError, match="project_id"):
        BuildDocumentLocalClaimRetrievalCommand(
            project_id="",
            document_id="document-1",
            processing_run_id="processing-run-1",
        )

    with pytest.raises(DomainInvariantError, match="document_id"):
        BuildDocumentLocalClaimRetrievalCommand(
            project_id="project-1",
            document_id="",
            processing_run_id="processing-run-1",
        )

    with pytest.raises(DomainInvariantError, match="processing_run_id"):
        BuildDocumentLocalClaimRetrievalCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="",
        )

    with pytest.raises(DomainInvariantError, match="min_similarity_score"):
        BuildDocumentLocalClaimRetrievalCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            min_similarity_score=1.1,
        )
