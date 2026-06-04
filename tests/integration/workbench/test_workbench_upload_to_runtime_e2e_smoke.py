from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import src.infrastructure.db.repositories.knowledge_repository as knowledge_repository_module
from src.application.ports.faq_workbench_registry_merge_generator import (
    FaqWorkbenchRegistryMergeGenerationResult,
)
from src.application.services.faq_workbench_canonicalization_barrier_service import (
    FaqWorkbenchCanonicalizationBarrierService,
    ProcessDocumentCanonicalizationBarrierCommand,
)
from src.application.services.faq_workbench_fresh_upload_service import (
    MonotonicIdFactory,
)
from src.application.services.faq_workbench_local_claim_retrieval_service import (
    BuildDocumentLocalClaimRetrievalCommand,
    FaqWorkbenchLocalClaimRetrievalService,
    LoadIndexedLocalClaimRetrievalSurfaceCommand,
    LoadIndexedLocalClaimRetrievalSurfaceResult,
)
from src.application.services.faq_workbench_local_claim_retrieval_surface_indexing_service import (
    FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService,
    IndexDocumentLocalClaimRetrievalSurfaceCommand,
    LocalClaimRetrievalSurfaceEmbeddingResult,
    LocalClaimRetrievalSurfaceEntry,
)
from src.application.services.faq_workbench_registry_application_service import (
    ApplyFactRegistrySnapshotCommand,
    ApplyFactRegistrySnapshotResult,
)
from src.application.services.faq_workbench_registry_merge_service import (
    PersistRegistryMergeNodeOutputCommand,
    PersistRegistryMergeNodeOutputResult,
)
from src.application.services.faq_workbench_retrieval_surface_publication_service import (
    FaqWorkbenchRetrievalSurfacePublicationService,
    WorkbenchRetrievalSurfaceEmbeddingResult,
    WorkbenchRetrievalSurfaceEntry,
)
from src.application.services.faq_workbench_runtime_publication_service import (
    FaqWorkbenchRuntimePublicationService,
    PublishFactRegistryRuntimeCommand,
)
from src.application.workbench.upload_service import (
    FaqWorkbenchUploadCommand,
    FaqWorkbenchUploadService,
)
from src.domain.project_plane.knowledge_workbench import (
    FactRegistry,
    FactRegistryStatus,
    LocalClaimSearchDocument,
    RegistrySnapshot,
    SectionBatchQueueItemStatus,
)
from src.domain.project_plane.llm_routing import (
    LlmInvocationStatus,
    LlmJsonInvocationResult,
    LlmRouteAttempt,
    LlmRouteAttemptStatus,
    LlmTokenUsage,
)
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from tests.application.workbench.helpers import (
    InMemoryWorkbenchQueue,
    InMemoryWorkbenchRepository,
)


PROJECT_ID = "00000000-0000-0000-0000-000000000001"


@dataclass(slots=True)
class FakeEmbeddingTextResult:
    embedding: list[float]
    usage: object | None = None


@dataclass(slots=True)
class FakeGraphLoader:
    async def load_document_local_claim_graphs(self, command: object) -> object:
        raise AssertionError(
            f"graph loader should not be used in this E2E smoke: {command}"
        )


@dataclass(slots=True)
class FakeLocalClaimEmbeddingService:
    texts: list[str] = field(default_factory=list)

    async def embed_passages(
        self,
        texts: list[str],
    ) -> LocalClaimRetrievalSurfaceEmbeddingResult:
        self.texts.extend(texts)
        return LocalClaimRetrievalSurfaceEmbeddingResult(
            embeddings=[
                [1.0, 0.0, 0.0],
                [0.98, 0.02, 0.0],
                [0.0, 1.0, 0.0],
            ][: len(texts)]
        )


@dataclass(slots=True)
class InMemoryLocalClaimRetrievalSurfaceRepository:
    entries: tuple[LocalClaimRetrievalSurfaceEntry, ...] = ()

    async def has_indexed_local_claim_retrieval_entries_for_node_run(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        node_run_id: str,
    ) -> bool:
        return any(
            entry.project_id == project_id
            and entry.document_id == document_id
            and entry.processing_run_id == processing_run_id
            and entry.node_run_id == node_run_id
            and entry.status == "indexed"
            for entry in self.entries
        )

    async def replace_local_claim_retrieval_entries(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        entries: tuple[LocalClaimRetrievalSurfaceEntry, ...],
    ) -> int:
        self.entries = entries
        return len(entries)

    async def load_indexed_local_claim_retrieval_surface(
        self,
        command: LoadIndexedLocalClaimRetrievalSurfaceCommand,
    ) -> LoadIndexedLocalClaimRetrievalSurfaceResult:
        documents = tuple(
            LocalClaimSearchDocument(
                search_document_id=entry.search_document_id,
                project_id=entry.project_id,
                document_id=entry.document_id,
                section_id=entry.section_id,
                node_run_id=entry.node_run_id,
                local_ref=entry.local_ref,
                claim=entry.claim,
                claim_kind=entry.claim_kind,
                granularity=entry.granularity,
                triple_texts=entry.triple_texts,
                possible_questions=entry.possible_questions,
                scope=entry.scope,
                exclusion_scope=entry.exclusion_scope,
                evidence_block=entry.evidence_block,
                relation_texts=entry.relation_texts,
                search_text=entry.search_text,
            )
            for entry in self.entries
            if entry.project_id == command.project_id
            and entry.document_id == command.document_id
            and entry.processing_run_id == command.processing_run_id
            and entry.status == "indexed"
        )
        vector_edges = FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService(
            graph_loader=FakeGraphLoader(),
            repository=self,
            embedding_service=FakeLocalClaimEmbeddingService(),
        )._vector_similarity_edges_for_smoke(documents)
        return LoadIndexedLocalClaimRetrievalSurfaceResult(
            search_documents=documents,
            vector_similarity_edges=vector_edges,
        )


def _vector_similarity_edges_for_smoke(
    self: FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService,
    documents: tuple[LocalClaimSearchDocument, ...],
):
    from src.domain.project_plane.knowledge_workbench import (
        LocalClaimSimilarityEdge,
        LocalClaimSimilaritySignal,
    )

    if len(documents) < 2:
        return ()

    return (
        LocalClaimSimilarityEdge(
            source_search_document_id=documents[0].search_document_id,
            target_search_document_id=documents[1].search_document_id,
            score=0.93,
            signals=(
                LocalClaimSimilaritySignal(
                    signal_type="embedding_similarity",
                    score=0.93,
                ),
            ),
        ),
    )


setattr(
    FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService,
    "_vector_similarity_edges_for_smoke",
    _vector_similarity_edges_for_smoke,
)


@dataclass(slots=True)
class BarrierRepository:
    registry: FactRegistry
    latest_snapshot: RegistrySnapshot | None
    created_node_runs: list[object] = field(default_factory=list)
    created_artifacts: list[object] = field(default_factory=list)

    async def has_completed_fact_registry_canonicalization(
        self, **kwargs: object
    ) -> bool:
        return False

    async def get_fact_registry_for_run(self, **kwargs: object) -> FactRegistry:
        return self.registry

    async def get_latest_registry_snapshot(
        self, **kwargs: object
    ) -> RegistrySnapshot | None:
        return self.latest_snapshot

    async def list_canonical_facts(self, **kwargs: object) -> tuple[object, ...]:
        return ()

    async def create_processing_node_run(self, node_run: object) -> None:
        self.created_node_runs.append(node_run)

    async def create_processing_node_artifact(self, artifact: object) -> None:
        self.created_artifacts.append(artifact)


@dataclass(slots=True)
class FakeRegistryMergeGenerator:
    commands: list[object] = field(default_factory=list)

    async def generate_registry_updates(
        self,
        command: object,
    ) -> FaqWorkbenchRegistryMergeGenerationResult:
        self.commands.append(command)
        fact_registry = {
            "version": 1,
            "canonical_facts": [
                {
                    "fact_id": "fact-telegram",
                    "claim": "Бот автоматически отвечает клиентам в Telegram.",
                    "claim_kind": "capability",
                    "granularity": "atomic",
                    "triples": [
                        {
                            "subject": "бот",
                            "predicate": "отвечает",
                            "object": "клиентам в Telegram",
                        }
                    ],
                    "mentions": [],
                    "question_variants": [
                        "Может ли бот отвечать клиентам?",
                        "Где бот отвечает клиентам?",
                    ],
                    "answer": "Да, бот автоматически отвечает клиентам в Telegram.",
                    "source_refs": ["section-1", "section-2"],
                    "evidence": ["Бот отвечает клиентам в Telegram."],
                    "status": "active",
                }
            ],
            "fact_relations": [],
        }
        registry_update_summary = {
            "created_fact_count": 1,
            "updated_fact_count": 0,
            "created_relation_count": 0,
            "notes": [],
        }
        return FaqWorkbenchRegistryMergeGenerationResult(
            fact_registry=fact_registry,
            registry_update_summary=registry_update_summary,
            invocation=LlmJsonInvocationResult(
                status=LlmInvocationStatus.SUCCESS,
                parsed_json={
                    "fact_registry": fact_registry,
                    "registry_update_summary": registry_update_summary,
                },
                raw_text="{}",
                token_usage=LlmTokenUsage(prompt_tokens=1, completion_tokens=1),
                attempts=(
                    LlmRouteAttempt(
                        provider_id="fake",
                        model="fake-model",
                        api_key_slot="slot-1",
                        attempt_index=0,
                        status=LlmRouteAttemptStatus.SUCCESS,
                    ),
                ),
            ),
            raw_output_artifact_payload={"raw": 1},
            parsed_output_artifact_payload={
                "fact_registry": fact_registry,
                "registry_update_summary": registry_update_summary,
            },
        )


@dataclass(slots=True)
class FakeRegistryMergeService:
    commands: list[PersistRegistryMergeNodeOutputCommand] = field(default_factory=list)

    async def persist_registry_merge_output(
        self,
        command: PersistRegistryMergeNodeOutputCommand,
    ) -> PersistRegistryMergeNodeOutputResult:
        self.commands.append(command)
        return PersistRegistryMergeNodeOutputResult(
            node_run=SimpleNamespace(node_run_id=command.node_run_id),
            raw_llm_artifact=SimpleNamespace(),
            parsed_llm_artifact=SimpleNamespace(),
            fact_registry=command.generation_result.fact_registry,
            registry_update_summary=command.generation_result.registry_update_summary,
        )

    async def persist_registry_merge_generation_error(self, command: object) -> object:
        raise AssertionError(f"Prompt C should not fail in this smoke: {command}")


@dataclass(slots=True)
class FakeRegistryApplicationService:
    snapshots: list[RegistrySnapshot] = field(default_factory=list)

    async def apply_fact_registry_snapshot(
        self,
        command: ApplyFactRegistrySnapshotCommand,
    ) -> ApplyFactRegistrySnapshotResult:
        snapshot = RegistrySnapshot(
            snapshot_id=f"snapshot-{len(self.snapshots) + 1}",
            registry_id=command.registry.registry_id,
            processing_run_id=command.registry.processing_run_id,
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            after_section_id=command.after_section_id,
            after_node_run_id=command.after_node_run_id,
            sequence_number=command.previous_snapshot_sequence_number + 1,
            entries_payload={
                "contract": "fact_registry",
                "fact_registry": command.fact_registry,
                "registry_update_summary": command.registry_update_summary,
            },
            relations_payload={
                "contract": "fact_registry_relations",
                "fact_relations": command.fact_registry["fact_relations"],
            },
            entry_count=len(command.fact_registry["canonical_facts"]),
            relation_count=len(command.fact_registry["fact_relations"]),
            claim_observation_count=3,
            update_count=1,
            created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        self.snapshots.append(snapshot)
        return ApplyFactRegistrySnapshotResult(
            snapshot=snapshot,
            fact_registry=command.fact_registry,
            registry_update_summary=command.registry_update_summary,
        )


@dataclass(slots=True)
class FakeRegistryMaterializationService:
    snapshots: list[RegistrySnapshot] = field(default_factory=list)

    async def materialize_fact_registry_snapshot(self, command: object) -> object:
        snapshot = command.snapshot
        self.snapshots.append(snapshot)
        return SimpleNamespace(
            canonical_fact_count=snapshot.entry_count,
            fact_mention_count=1,
            fact_relation_count=snapshot.relation_count,
            surface_count=snapshot.entry_count,
        )


@dataclass(slots=True)
class FakeRuntimeDebugRepository:
    payloads: list[object] = field(default_factory=list)

    async def publish_fact_registry_runtime_entries(
        self,
        *,
        project_id: str,
        document_id: str,
        fact_registry_payload: object,
    ) -> int:
        self.payloads.append(fact_registry_payload)
        facts = _canonical_facts(fact_registry_payload)
        return len([fact for fact in facts if _fact_is_active(fact)])


@dataclass(slots=True)
class FakeRuntimeEmbeddingService:
    texts: list[str] = field(default_factory=list)

    async def embed_passages(
        self,
        texts: list[str],
    ) -> WorkbenchRetrievalSurfaceEmbeddingResult:
        self.texts.extend(texts)
        return WorkbenchRetrievalSurfaceEmbeddingResult(
            embeddings=[[0.1, 0.2, 0.3] for _text in texts],
        )


@dataclass(slots=True)
class CapturingRuntimeSurfaceRepository:
    entries: tuple[WorkbenchRetrievalSurfaceEntry, ...] = ()

    async def replace_workbench_fact_runtime_surface_entries(
        self,
        *,
        project_id: str,
        document_id: str,
        entries: tuple[WorkbenchRetrievalSurfaceEntry, ...],
    ) -> int:
        self.entries = entries
        return len(entries)


@dataclass(slots=True)
class FakeSearchConnection:
    runtime_surface_repository: CapturingRuntimeSurfaceRepository

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        project_id = str(args[2])
        entry_kinds = _text_set(args[5])
        rows: list[dict[str, object]] = []
        for entry in self.runtime_surface_repository.entries:
            if entry.project_id != project_id:
                continue
            if entry.entry_kind not in entry_kinds:
                continue
            rows.append(
                {
                    "id": entry.entry_id,
                    "content": entry.answer,
                    "document_id": None,
                    "source": None,
                    "document_status": None,
                    "entry_kind": entry.entry_kind,
                    "title": entry.title,
                    "source_refs": list(entry.source_refs),
                    "embedding_text": entry.embedding_text,
                    "questions": entry.enrichment.get("questions"),
                    "synonyms": [],
                    "tags": ["workbench"],
                    "search_text": entry.search_text,
                    "vector_score": 0.99,
                    "lexical_score": 0.5,
                    "exact_score": 0.0,
                }
            )
        return rows


@dataclass(slots=True)
class FakeAcquireContext:
    connection: FakeSearchConnection

    async def __aenter__(self) -> FakeSearchConnection:
        return self.connection

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


@dataclass(slots=True)
class FakeSearchPool:
    runtime_surface_repository: CapturingRuntimeSurfaceRepository

    def acquire(self) -> FakeAcquireContext:
        return FakeAcquireContext(FakeSearchConnection(self.runtime_surface_repository))


@dataclass(slots=True)
class FakeSearchEmbeddingResult:
    embedding: list[float]
    usage: object | None = None


def _text_set(value: object) -> set[str]:
    if isinstance(value, list):
        return {str(item) for item in value}
    if isinstance(value, tuple):
        return {str(item) for item in value}
    return set()


def _canonical_facts(payload: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(payload, Mapping):
        return ()
    facts = payload.get("canonical_facts")
    if not isinstance(facts, Sequence) or isinstance(facts, (str, bytes, bytearray)):
        return ()
    return tuple(item for item in facts if isinstance(item, Mapping))


def _fact_is_active(fact: Mapping[str, object]) -> bool:
    return str(fact.get("status") or "active") not in {"deleted", "inactive", "merged"}


def _local_claim_documents_from_upload(
    *,
    upload_result: object,
) -> tuple[LocalClaimSearchDocument, ...]:
    sections = upload_result.upload.sections
    processing_run_id = upload_result.upload.processing_run.processing_run_id

    documents: list[LocalClaimSearchDocument] = []
    for index, section in enumerate(sections, start=1):
        local_ref = f"c{index}"
        node_run_id = f"prompt-a-node-{index}"
        claim = (
            "Бот отвечает клиентам в Telegram."
            if index < 3
            else "Сложный вопрос передаётся менеджеру."
        )
        documents.append(
            LocalClaimSearchDocument(
                search_document_id=f"{section.section_id}:{node_run_id}:{local_ref}",
                project_id=section.project_id,
                document_id=section.document_id,
                section_id=section.section_id,
                node_run_id=node_run_id,
                local_ref=local_ref,
                claim=claim,
                claim_kind="capability",
                granularity="atomic",
                triple_texts=("бот отвечает клиентам",),
                possible_questions=("Может ли бот отвечать клиентам?",),
                scope="Telegram support",
                exclusion_scope="",
                evidence_block=section.normalized_text,
                relation_texts=(),
                search_text=f"{claim}\n{section.normalized_text}",
            )
        )

    assert processing_run_id
    return tuple(documents)


@pytest.mark.asyncio
async def test_workbench_upload_to_runtime_vector_retrieval_e2e_smoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search_embed_text(text: str) -> FakeSearchEmbeddingResult:
        assert text == "Telegram клиенты"
        return FakeSearchEmbeddingResult(embedding=[0.1, 0.2, 0.3])

    monkeypatch.setattr(
        knowledge_repository_module,
        "embed_text",
        fake_search_embed_text,
    )

    upload_repository = InMemoryWorkbenchRepository()
    upload_queue = InMemoryWorkbenchQueue()
    upload_service = FaqWorkbenchUploadService(
        upload_repository,
        upload_queue,
        id_factory=MonotonicIdFactory.create(),
    )

    upload_result = await upload_service.upload_markdown(
        FaqWorkbenchUploadCommand(
            project_id=PROJECT_ID,
            file_name="knowledge.md",
            upload_id="upload-1",
            raw_text=(
                "# Product\n"
                "Бот отвечает клиентам в Telegram.\n\n"
                "## Telegram\n"
                "AI-ассистент отвечает покупателям в Telegram.\n\n"
                "## Handoff\n"
                "Сложный вопрос передаётся менеджеру."
            ),
            file_size_bytes=180,
            content_hash="hash-e2e",
        )
    )

    assert len(upload_repository.documents) == 1
    assert len(upload_repository.sections) == 3
    assert len(upload_repository.registry_snapshots) == 1
    assert len(upload_repository.parallel_section_batch_plans) == 1
    assert len(upload_repository.section_batch_queue_items) == 3
    assert all(
        item.status is SectionBatchQueueItemStatus.READY
        for item in upload_repository.section_batch_queue_items
    )
    assert len(upload_queue.payloads) == 1

    local_claim_surface_repository = InMemoryLocalClaimRetrievalSurfaceRepository()
    local_claim_embedding_service = FakeLocalClaimEmbeddingService()
    local_claim_indexing_service = (
        FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService(
            graph_loader=FakeGraphLoader(),
            repository=local_claim_surface_repository,
            embedding_service=local_claim_embedding_service,
        )
    )

    local_claim_documents = _local_claim_documents_from_upload(
        upload_result=upload_result
    )
    indexing_result = (
        await local_claim_indexing_service.index_document_local_claim_retrieval_surface(
            IndexDocumentLocalClaimRetrievalSurfaceCommand(
                project_id=PROJECT_ID,
                document_id=upload_result.upload.document.document_id,
                processing_run_id=upload_result.upload.processing_run.processing_run_id,
                search_documents=local_claim_documents,
                min_vector_similarity_score=0.9,
            )
        )
    )

    assert indexing_result.indexed_entry_count == 3
    assert indexing_result.indexed_node_run_count == 3
    assert indexing_result.vector_edge_count >= 1
    assert len(local_claim_embedding_service.texts) == 3

    local_claim_retrieval_service = FaqWorkbenchLocalClaimRetrievalService(
        graph_loader=FakeGraphLoader(),
        retrieval_surface_indexing_service=local_claim_indexing_service,
        retrieval_surface_reader=local_claim_surface_repository,
    )

    retrieval_result = (
        await local_claim_retrieval_service.build_document_local_claim_retrieval(
            BuildDocumentLocalClaimRetrievalCommand(
                project_id=PROJECT_ID,
                document_id=upload_result.upload.document.document_id,
                processing_run_id=upload_result.upload.processing_run.processing_run_id,
            )
        )
    )

    assert retrieval_result.claim_count == 3
    assert retrieval_result.edge_count >= 1
    assert retrieval_result.unit_count >= 1

    registry = FactRegistry(
        registry_id=upload_result.upload.registry.registry_id,
        project_id=PROJECT_ID,
        document_id=upload_result.upload.document.document_id,
        processing_run_id=upload_result.upload.processing_run.processing_run_id,
        status=FactRegistryStatus.BUILDING,
        version=1,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    barrier_repository = BarrierRepository(
        registry=registry,
        latest_snapshot=upload_result.upload.initial_snapshot,
    )
    registry_application_service = FakeRegistryApplicationService()
    materialization_service = FakeRegistryMaterializationService()
    barrier_service = FaqWorkbenchCanonicalizationBarrierService(
        repository=barrier_repository,
        local_claim_retrieval_service=local_claim_retrieval_service,
        registry_merge_generator=FakeRegistryMergeGenerator(),
        registry_merge_service=FakeRegistryMergeService(),
        registry_application_service=registry_application_service,
        registry_materialization_service=materialization_service,
        id_factory=MonotonicIdFactory.create(),
    )

    barrier_result = await barrier_service.process_document_canonicalization_barrier(
        ProcessDocumentCanonicalizationBarrierCommand(
            project_id=PROJECT_ID,
            document_id=upload_result.upload.document.document_id,
            processing_run_id=upload_result.upload.processing_run.processing_run_id,
            worker_id="worker-e2e",
        )
    )

    assert barrier_result.outcome == "canonicalized"
    assert barrier_result.prompt_c_success_count >= 1
    assert barrier_result.latest_snapshot_id is not None
    assert len(barrier_repository.created_artifacts) == 1
    assert (
        barrier_repository.created_artifacts[0].metadata["contract"]
        == "fact_registry_canonicalization_barrier"
    )
    assert len(registry_application_service.snapshots) >= 1
    assert len(materialization_service.snapshots) == 1

    final_snapshot = registry_application_service.snapshots[-1]
    fact_registry_payload = final_snapshot.entries_payload["fact_registry"]

    runtime_debug_repository = FakeRuntimeDebugRepository()
    runtime_surface_repository = CapturingRuntimeSurfaceRepository()
    runtime_publication = FaqWorkbenchRuntimePublicationService(
        runtime_debug_repository,
        FaqWorkbenchRetrievalSurfacePublicationService(
            repository=runtime_surface_repository,
            embedding_service=FakeRuntimeEmbeddingService(),
        ),
    )

    runtime_result = await runtime_publication.publish_fact_registry_runtime_entries(
        PublishFactRegistryRuntimeCommand(
            project_id=PROJECT_ID,
            document_id=upload_result.upload.document.document_id,
            fact_registry_payload=fact_registry_payload,
        )
    )

    assert runtime_result.published_entry_count == 1
    assert runtime_result.published_retrieval_surface_entry_count == 1
    assert len(runtime_surface_repository.entries) == 1
    assert runtime_surface_repository.entries[0].entry_kind == "faq_workbench_fact"

    knowledge_repository = KnowledgeRepository(
        FakeSearchPool(runtime_surface_repository)
    )
    search_results = await knowledge_repository.search(
        project_id=PROJECT_ID,
        query="Telegram клиенты",
        limit=5,
    )

    assert search_results
    assert search_results[0].entry_kind == "faq_workbench_fact"
    assert "Telegram" in search_results[0].content
    assert search_results[0].embedding_text is not None
    assert "Может ли бот отвечать клиентам?" in search_results[0].embedding_text
