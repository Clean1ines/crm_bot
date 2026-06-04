from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import pytest

import src.infrastructure.db.repositories.knowledge_repository as knowledge_repository_module
from src.application.services.faq_workbench_retrieval_surface_publication_service import (
    FaqWorkbenchRetrievalSurfacePublicationService,
    WorkbenchRetrievalSurfaceEmbeddingResult,
    WorkbenchRetrievalSurfaceEntry,
)
from src.application.services.faq_workbench_runtime_publication_service import (
    FaqWorkbenchRuntimePublicationService,
    PublishFactRegistryRuntimeCommand,
)
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository


PROJECT_ID = "00000000-0000-0000-0000-000000000001"
DOCUMENT_ID = "document-workbench-runtime-smoke"


@dataclass(slots=True)
class FakeEmbeddingTextResult:
    embedding: list[float]
    usage: object | None = None


@dataclass(slots=True)
class FakeDebugRuntimeRepository:
    calls: list[tuple[str, str, object]] = field(default_factory=list)

    async def publish_fact_registry_runtime_entries(
        self,
        *,
        project_id: str,
        document_id: str,
        fact_registry_payload: object,
    ) -> int:
        self.calls.append((project_id, document_id, fact_registry_payload))
        facts = _canonical_facts(fact_registry_payload)
        return len([fact for fact in facts if _fact_is_active(fact)])


@dataclass(slots=True)
class FakePassageEmbeddingService:
    texts: list[str] = field(default_factory=list)

    async def embed_passages(
        self,
        texts: list[str],
    ) -> WorkbenchRetrievalSurfaceEmbeddingResult:
        self.texts.extend(texts)
        return WorkbenchRetrievalSurfaceEmbeddingResult(
            embeddings=[
                [0.01 + index, 0.02 + index, 0.03 + index]
                for index, _text in enumerate(texts)
            ],
        )


@dataclass(slots=True)
class CapturingRetrievalSurfaceRepository:
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
    retrieval_surface_repository: CapturingRetrievalSurfaceRepository
    fetch_queries: list[str] = field(default_factory=list)

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.fetch_queries.append(" ".join(query.lower().split()))

        project_id = str(args[2]) if len(args) >= 3 else PROJECT_ID
        entry_kinds = _text_set(args[5]) if len(args) >= 6 else {"faq_workbench_fact"}

        rows: list[dict[str, object]] = []
        for entry in self.retrieval_surface_repository.entries:
            if entry.project_id != project_id:
                continue
            if entry.entry_kind not in entry_kinds:
                continue
            if entry.status != "published" or entry.visibility != "runtime":
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
                    "vector_score": 0.94,
                    "lexical_score": 0.12,
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
    retrieval_surface_repository: CapturingRetrievalSurfaceRepository
    connection: FakeSearchConnection | None = None

    def acquire(self) -> FakeAcquireContext:
        if self.connection is None:
            self.connection = FakeSearchConnection(self.retrieval_surface_repository)
        return FakeAcquireContext(self.connection)


def _text_set(value: object) -> set[str]:
    if isinstance(value, list):
        return {str(item) for item in value}
    if isinstance(value, tuple):
        return {str(item) for item in value}
    return set()


def _canonical_facts(payload: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(payload, Mapping):
        return ()
    raw_facts = payload.get("canonical_facts")
    if not isinstance(raw_facts, Sequence) or isinstance(
        raw_facts,
        (str, bytes, bytearray),
    ):
        return ()
    return tuple(item for item in raw_facts if isinstance(item, Mapping))


def _fact_is_active(fact: Mapping[str, object]) -> bool:
    return str(fact.get("status") or "active") not in {"deleted", "inactive", "merged"}


def _fact_registry_payload() -> dict[str, object]:
    return {
        "version": 1,
        "canonical_facts": [
            {
                "fact_id": "fact-telegram",
                "claim": "Бот отвечает клиентам в Telegram.",
                "claim_kind": "capability",
                "granularity": "atomic",
                "question_variants": [
                    "Может ли бот отвечать клиентам?",
                    "Где бот отвечает клиентам?",
                ],
                "answer": "Да, бот автоматически отвечает клиентам в Telegram.",
                "scope": "Telegram customer support",
                "exclusion_scope": "",
                "source_refs": ["section-1"],
                "evidence": ["Бот отвечает клиентам в Telegram."],
                "triples": [
                    {
                        "subject": "бот",
                        "predicate": "отвечает",
                        "object": "клиентам в Telegram",
                    },
                ],
                "status": "active",
            },
            {
                "fact_id": "fact-manager",
                "claim": "Сложный вопрос передаётся менеджеру.",
                "claim_kind": "handoff",
                "granularity": "atomic",
                "question_variants": [
                    "Когда диалог передаётся менеджеру?",
                ],
                "answer": "Сложный вопрос передаётся менеджеру.",
                "scope": "handoff policy",
                "exclusion_scope": "",
                "source_refs": ["section-2"],
                "evidence": ["Сложный вопрос передаётся менеджеру."],
                "triples": [],
                "status": "active",
            },
        ],
        "fact_relations": [
            {
                "source_fact_id": "fact-manager",
                "target_fact_id": "fact-telegram",
                "relation": "sets_boundary_for",
                "reason": "handoff limits automated answers",
            },
        ],
    }


@pytest.mark.asyncio
async def test_publish_ready_projection_is_visible_to_production_knowledge_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_embed_text(text: str) -> FakeEmbeddingTextResult:
        assert text == "Telegram клиенты"
        return FakeEmbeddingTextResult(embedding=[0.01, 0.02, 0.03])

    monkeypatch.setattr(
        knowledge_repository_module,
        "embed_text",
        fake_embed_text,
    )

    debug_repository = FakeDebugRuntimeRepository()
    retrieval_surface_repository = CapturingRetrievalSurfaceRepository()
    passage_embedding_service = FakePassageEmbeddingService()

    retrieval_surface_publication = FaqWorkbenchRetrievalSurfacePublicationService(
        repository=retrieval_surface_repository,
        embedding_service=passage_embedding_service,
    )
    runtime_publication = FaqWorkbenchRuntimePublicationService(
        debug_repository,
        retrieval_surface_publication,
    )

    runtime_result = await runtime_publication.publish_fact_registry_runtime_entries(
        PublishFactRegistryRuntimeCommand(
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            fact_registry_payload=_fact_registry_payload(),
        )
    )

    assert runtime_result.published_entry_count == 2
    assert runtime_result.published_retrieval_surface_entry_count == 2
    assert len(debug_repository.calls) == 1
    assert len(passage_embedding_service.texts) == 2
    assert len(retrieval_surface_repository.entries) == 2

    search_pool = FakeSearchPool(retrieval_surface_repository)
    knowledge_repository = KnowledgeRepository(search_pool)

    results = await knowledge_repository.search(
        project_id=PROJECT_ID,
        query="Telegram клиенты",
        limit=5,
    )

    assert results
    assert results[0].entry_kind == "faq_workbench_fact"
    assert results[0].document_status is None
    assert "Telegram" in results[0].content
    assert results[0].embedding_text is not None
    assert "Может ли бот отвечать клиентам?" in results[0].embedding_text

    assert search_pool.connection is not None
    assert search_pool.connection.fetch_queries
    assert "knowledge_retrieval_surface" in search_pool.connection.fetch_queries[0]
    assert "entry_kind = any" in search_pool.connection.fetch_queries[0]


@pytest.mark.asyncio
async def test_workbench_fact_runtime_projection_skips_deleted_facts() -> None:
    debug_repository = FakeDebugRuntimeRepository()
    retrieval_surface_repository = CapturingRetrievalSurfaceRepository()
    passage_embedding_service = FakePassageEmbeddingService()

    payload = _fact_registry_payload()
    facts = payload["canonical_facts"]
    assert isinstance(facts, list)
    facts.append(
        {
            "fact_id": "fact-deleted",
            "claim": "Удалённый факт не должен попасть в runtime.",
            "answer": "Удалённый факт не должен попасть в runtime.",
            "status": "deleted",
        },
    )

    retrieval_surface_publication = FaqWorkbenchRetrievalSurfacePublicationService(
        repository=retrieval_surface_repository,
        embedding_service=passage_embedding_service,
    )
    runtime_publication = FaqWorkbenchRuntimePublicationService(
        debug_repository,
        retrieval_surface_publication,
    )

    runtime_result = await runtime_publication.publish_fact_registry_runtime_entries(
        PublishFactRegistryRuntimeCommand(
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            fact_registry_payload=payload,
        )
    )

    assert runtime_result.published_entry_count == 2
    assert runtime_result.published_retrieval_surface_entry_count == 2
    assert {entry.fact_id for entry in retrieval_surface_repository.entries} == {
        "fact-telegram",
        "fact-manager",
    }
