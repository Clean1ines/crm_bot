from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.application.services.faq_workbench_retrieval_surface_publication_service import (
    FaqWorkbenchRetrievalSurfacePublicationService,
    PublishWorkbenchFactRetrievalSurfaceCommand,
    WorkbenchRetrievalSurfaceEmbeddingResult,
    WorkbenchRetrievalSurfaceEntry,
)


@dataclass(slots=True)
class FakeEmbeddingService:
    texts: list[str] = field(default_factory=list)

    async def embed_passages(
        self,
        texts: list[str],
    ) -> WorkbenchRetrievalSurfaceEmbeddingResult:
        self.texts.extend(texts)
        return WorkbenchRetrievalSurfaceEmbeddingResult(
            embeddings=[
                [float(index + 1), float(index + 2), float(index + 3)]
                for index, _text in enumerate(texts)
            ]
        )


@dataclass(slots=True)
class FakeRepository:
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


def _payload() -> dict[str, object]:
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
                "scope": "Telegram support",
                "exclusion_scope": "",
                "source_refs": ["section-1"],
                "evidence": ["Бот отвечает клиентам в Telegram."],
                "triples": [
                    {
                        "subject": "бот",
                        "predicate": "отвечает",
                        "object": "клиентам",
                    }
                ],
                "status": "active",
            },
            {
                "fact_id": "fact-deleted",
                "claim": "Удалённый факт.",
                "answer": "Удалённый факт.",
                "status": "deleted",
            },
        ],
        "fact_relations": [],
    }


@pytest.mark.asyncio
async def test_publishes_active_workbench_facts_as_embedding_backed_retrieval_surface_entries() -> (
    None
):
    repository = FakeRepository()
    embedding_service = FakeEmbeddingService()
    service = FaqWorkbenchRetrievalSurfacePublicationService(
        repository=repository,
        embedding_service=embedding_service,
    )

    result = await service.publish_workbench_fact_retrieval_surface(
        PublishWorkbenchFactRetrievalSurfaceCommand(
            project_id="00000000-0000-0000-0000-000000000001",
            document_id="document-1",
            fact_registry_payload=_payload(),
        )
    )

    assert result.built_entry_count == 1
    assert result.published_entry_count == 1
    assert len(embedding_service.texts) == 1
    assert "Telegram" in embedding_service.texts[0]
    assert "Может ли бот отвечать клиентам?" in embedding_service.texts[0]

    entry = repository.entries[0]
    assert entry.entry_kind == "faq_workbench_fact"
    assert entry.status == "published"
    assert entry.visibility == "runtime"
    assert entry.fact_id == "fact-telegram"
    assert entry.embedding == (1.0, 2.0, 3.0)
    assert entry.entry_id.endswith(":fact-telegram")
    assert entry.enrichment["contract"] == "faq_workbench_fact_retrieval_surface"


@pytest.mark.asyncio
async def test_empty_fact_registry_replaces_existing_workbench_projection_with_empty_set() -> (
    None
):
    repository = FakeRepository()
    embedding_service = FakeEmbeddingService()
    service = FaqWorkbenchRetrievalSurfacePublicationService(
        repository=repository,
        embedding_service=embedding_service,
    )

    result = await service.publish_workbench_fact_retrieval_surface(
        PublishWorkbenchFactRetrievalSurfaceCommand(
            project_id="00000000-0000-0000-0000-000000000001",
            document_id="document-1",
            fact_registry_payload={"canonical_facts": []},
        )
    )

    assert result.built_entry_count == 0
    assert result.published_entry_count == 0
    assert embedding_service.texts == []
    assert repository.entries == ()
