from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from src.domain.project_plane.knowledge_workbench import DomainInvariantError


class WorkbenchRetrievalSurfaceEmbeddingPort(Protocol):
    async def embed_passages(
        self,
        texts: list[str],
    ) -> WorkbenchRetrievalSurfaceEmbeddingResult: ...


class WorkbenchRetrievalSurfaceRepositoryPort(Protocol):
    async def replace_workbench_fact_runtime_surface_entries(
        self,
        *,
        project_id: str,
        document_id: str,
        entries: tuple[WorkbenchRetrievalSurfaceEntry, ...],
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class WorkbenchRetrievalSurfaceEmbeddingResult:
    embeddings: list[list[float]]


@dataclass(frozen=True, slots=True)
class WorkbenchRetrievalSurfaceEntry:
    entry_id: str
    project_id: str
    document_id: str
    fact_id: str
    title: str
    answer: str
    search_text: str
    embedding_text: str
    embedding: tuple[float, ...]
    source_refs: tuple[str, ...]
    enrichment: Mapping[str, object]
    entry_kind: str = "faq_workbench_fact"
    status: str = "published"
    visibility: str = "runtime"


@dataclass(frozen=True, slots=True)
class PublishWorkbenchFactRetrievalSurfaceCommand:
    project_id: str
    document_id: str
    fact_registry_payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class PublishWorkbenchFactRetrievalSurfaceResult:
    built_entry_count: int
    published_entry_count: int


class FaqWorkbenchRetrievalSurfacePublicationService:
    def __init__(
        self,
        *,
        repository: WorkbenchRetrievalSurfaceRepositoryPort,
        embedding_service: WorkbenchRetrievalSurfaceEmbeddingPort,
    ) -> None:
        self._repository = repository
        self._embedding_service = embedding_service

    async def publish_workbench_fact_retrieval_surface(
        self,
        command: PublishWorkbenchFactRetrievalSurfaceCommand,
    ) -> PublishWorkbenchFactRetrievalSurfaceResult:
        project_id = _required(command.project_id, "project_id")
        document_id = _required(command.document_id, "document_id")
        facts = _canonical_facts(command.fact_registry_payload)

        draft_entries = tuple(
            entry
            for fact in facts
            if (entry := _draft_entry(project_id, document_id, fact)) is not None
        )

        if not draft_entries:
            published_count = (
                await self._repository.replace_workbench_fact_runtime_surface_entries(
                    project_id=project_id,
                    document_id=document_id,
                    entries=(),
                )
            )
            return PublishWorkbenchFactRetrievalSurfaceResult(
                built_entry_count=0,
                published_entry_count=published_count,
            )

        embedding_result = await self._embedding_service.embed_passages(
            [entry.embedding_text for entry in draft_entries]
        )

        if len(embedding_result.embeddings) != len(draft_entries):
            raise DomainInvariantError(
                "Workbench retrieval surface embedding count does not match entries"
            )

        entries = tuple(
            WorkbenchRetrievalSurfaceEntry(
                entry_id=draft.entry_id,
                project_id=draft.project_id,
                document_id=draft.document_id,
                fact_id=draft.fact_id,
                title=draft.title,
                answer=draft.answer,
                search_text=draft.search_text,
                embedding_text=draft.embedding_text,
                embedding=tuple(float(value) for value in vector),
                source_refs=draft.source_refs,
                enrichment=draft.enrichment,
                entry_kind=draft.entry_kind,
                status=draft.status,
                visibility=draft.visibility,
            )
            for draft, vector in zip(
                draft_entries, embedding_result.embeddings, strict=True
            )
        )

        published_count = (
            await self._repository.replace_workbench_fact_runtime_surface_entries(
                project_id=project_id,
                document_id=document_id,
                entries=entries,
            )
        )

        return PublishWorkbenchFactRetrievalSurfaceResult(
            built_entry_count=len(entries),
            published_entry_count=published_count,
        )


def _canonical_facts(payload: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw_facts = payload.get("canonical_facts")
    if not isinstance(raw_facts, Sequence) or isinstance(
        raw_facts,
        (str, bytes, bytearray),
    ):
        return ()
    return tuple(item for item in raw_facts if isinstance(item, Mapping))


def _draft_entry(
    project_id: str,
    document_id: str,
    fact: Mapping[str, object],
) -> WorkbenchRetrievalSurfaceEntry | None:
    status = _text(fact.get("status")) or "active"
    if status in {"deleted", "inactive", "merged"}:
        return None

    fact_id = _text(fact.get("fact_id"))
    claim = _text(fact.get("claim"))
    answer = _text(fact.get("answer")) or _text(fact.get("short_answer")) or claim

    if not fact_id or not claim or not answer:
        return None

    questions = _text_tuple(fact.get("question_variants"))
    source_refs = _text_tuple(fact.get("source_refs"))
    evidence_quotes = _text_tuple(fact.get("evidence_quotes")) or _evidence_texts(
        fact.get("evidence")
    )
    triples = _triple_texts(fact.get("triples"))
    scope = _text(fact.get("scope")) or _text(fact.get("answer_scope"))
    exclusion_scope = _text(fact.get("exclusion_scope"))

    search_text_parts = (
        claim,
        answer,
        scope,
        exclusion_scope,
        " ".join(questions),
        " ".join(triples),
        " ".join(source_refs),
        " ".join(evidence_quotes),
    )
    search_text = "\n".join(part for part in search_text_parts if part.strip())

    enrichment: dict[str, object] = {
        "contract": "faq_workbench_fact_retrieval_surface",
        "fact_id": fact_id,
        "claim_kind": _text(fact.get("claim_kind")),
        "granularity": _text(fact.get("granularity")),
        "questions": list(questions),
        "source_refs": list(source_refs),
        "evidence_quotes": list(evidence_quotes),
        "triples": list(triples),
        "scope": scope,
        "exclusion_scope": exclusion_scope,
    }

    return WorkbenchRetrievalSurfaceEntry(
        entry_id=f"workbench_fact:{project_id}:{document_id}:{fact_id}",
        project_id=project_id,
        document_id=document_id,
        fact_id=fact_id,
        title=claim,
        answer=answer,
        search_text=search_text,
        embedding_text=search_text,
        embedding=(),
        source_refs=source_refs,
        enrichment=enrichment,
    )


def _triple_texts(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()

    texts: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            subject = _text(item.get("subject"))
            predicate = _text(item.get("predicate"))
            object_value = _text(item.get("object"))
            text = " ".join(part for part in (subject, predicate, object_value) if part)
        else:
            text = _text(item)
        if text:
            texts.append(text)
    return tuple(dict.fromkeys(texts))


def _evidence_texts(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()

    texts: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            text = (
                _text(item.get("evidence_block"))
                or _text(item.get("quote"))
                or _text(item.get("text"))
            )
        else:
            text = _text(item)
        if text:
            texts.append(text)
    return tuple(dict.fromkeys(texts))


def _text_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        return (text,) if text else ()
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(text for item in value if (text := _text(item)))
    text = _text(value)
    return (text,) if text else ()


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _required(value: str, name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise DomainInvariantError(f"{name} is required")
    return cleaned


__all__ = [
    "FaqWorkbenchRetrievalSurfacePublicationService",
    "PublishWorkbenchFactRetrievalSurfaceCommand",
    "PublishWorkbenchFactRetrievalSurfaceResult",
    "WorkbenchRetrievalSurfaceEmbeddingPort",
    "WorkbenchRetrievalSurfaceEmbeddingResult",
    "WorkbenchRetrievalSurfaceEntry",
    "WorkbenchRetrievalSurfaceRepositoryPort",
]
