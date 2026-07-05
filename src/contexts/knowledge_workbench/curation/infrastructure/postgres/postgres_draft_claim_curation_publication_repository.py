from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import json
from typing import Protocol, cast

from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_publication import (
    DraftClaimCurationPublicationCandidate,
    DraftClaimCurationPublicationItem,
    DraftClaimCurationPublicationResult,
)
from src.contexts.knowledge_workbench.curation.application.ports.draft_claim_curation_publication_repository_port import (
    DraftClaimCurationPublicationRepositoryPort,
)


class DraftClaimCurationPublicationTransactionLike(Protocol):
    async def __aenter__(self) -> object: ...

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> bool | None: ...


class DraftClaimCurationRuntimeEntryIdRowLike(Protocol):
    def __getitem__(self, key: str) -> object: ...


class DraftClaimCurationPublicationConnectionLike(Protocol):
    async def fetch(
        self, query: str, *args: object
    ) -> list[DraftClaimCurationRuntimeEntryIdRowLike]: ...

    async def execute(self, query: str, *args: object) -> object: ...

    def transaction(self) -> DraftClaimCurationPublicationTransactionLike: ...


class DraftClaimCurationPublicationAcquireContextLike(Protocol):
    async def __aenter__(self) -> DraftClaimCurationPublicationConnectionLike: ...

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> bool | None: ...


class DraftClaimCurationPublicationPoolLike(Protocol):
    def acquire(self) -> DraftClaimCurationPublicationAcquireContextLike: ...


class PostgresDraftClaimCurationPublicationRepository(
    DraftClaimCurationPublicationRepositoryPort
):
    def __init__(self, connection_or_pool: object) -> None:
        self._connection_or_pool = connection_or_pool

    async def publish_curated_claims(
        self,
        *,
        publication: DraftClaimCurationPublicationCandidate,
    ) -> DraftClaimCurationPublicationResult:
        if _has_acquire(self._connection_or_pool):
            async with cast(
                DraftClaimCurationPublicationPoolLike,
                self._connection_or_pool,
            ).acquire() as connection:
                return await self._publish_with_connection(
                    connection=connection,
                    publication=publication,
                )

        return await self._publish_with_connection(
            connection=cast(
                DraftClaimCurationPublicationConnectionLike,
                self._connection_or_pool,
            ),
            publication=publication,
        )

    async def _publish_with_connection(
        self,
        *,
        connection: DraftClaimCurationPublicationConnectionLike,
        publication: DraftClaimCurationPublicationCandidate,
    ) -> DraftClaimCurationPublicationResult:
        async with connection.transaction():
            await _deactivate_existing_runtime_projection(connection, publication)
            await _upsert_publication(connection, publication)
            await _upsert_fact_registry(connection, publication)

            for item in publication.items:
                await _upsert_fact(connection, publication, item)
                await _replace_fact_triples(connection, publication, item)
                await _upsert_runtime_entry(connection, publication, item)
                await _replace_runtime_embedding(
                    connection, item, publication.published_at
                )

            await connection.execute(
                """
                UPDATE draft_claim_curation_workspaces
                SET status = 'published',
                    updated_at = $2
                WHERE workflow_run_id = $1
                """,
                publication.workflow_run_id,
                publication.published_at,
            )

        return DraftClaimCurationPublicationResult(
            status="published",
            publication_id=publication.publication_id,
            workflow_run_id=publication.workflow_run_id,
            project_id=publication.project_id,
            source_document_ref=publication.source_document_ref,
            published_item_count=len(publication.items),
            excluded_item_count=publication.excluded_item_count,
            runtime_entry_count=len(publication.items),
            embedding_count=len(publication.items),
            deleted_draft_embedding_count=0,
            automatic_processing_elapsed_seconds=None,
            published_at=publication.published_at,
        )


async def _deactivate_existing_runtime_projection(
    connection: DraftClaimCurationPublicationConnectionLike,
    publication: DraftClaimCurationPublicationCandidate,
) -> None:
    rows = await connection.fetch(
        """
        SELECT runtime_entry_id
        FROM knowledge_workbench_runtime_retrieval_entries
        WHERE workflow_run_id = $1
        """,
        publication.workflow_run_id,
    )
    runtime_entry_ids: list[str] = []
    for row in rows:
        try:
            runtime_entry_id = row["runtime_entry_id"]
        except KeyError:
            continue
        if runtime_entry_id:
            runtime_entry_ids.append(str(runtime_entry_id))

    if runtime_entry_ids:
        await connection.execute(
            """
            DELETE FROM knowledge_workbench_runtime_retrieval_entry_embeddings
            WHERE runtime_entry_id = ANY($1::text[])
            """,
            runtime_entry_ids,
        )

    await connection.execute(
        """
        UPDATE knowledge_workbench_runtime_retrieval_entries
        SET visibility = 'hidden',
            status = 'inactive',
            updated_at = $2
        WHERE workflow_run_id = $1
        """,
        publication.workflow_run_id,
        publication.published_at,
    )


async def _upsert_publication(
    connection: DraftClaimCurationPublicationConnectionLike,
    publication: DraftClaimCurationPublicationCandidate,
) -> None:
    await connection.execute(
        """
        INSERT INTO knowledge_workbench_runtime_publications (
            publication_id, project_id, source, status, created_at, published_at
        )
        VALUES ($1, $2::uuid, $3, 'published', $4, $4)
        ON CONFLICT (publication_id) DO UPDATE
        SET status = 'published',
            published_at = EXCLUDED.published_at
        """,
        publication.publication_id,
        publication.project_id,
        "draft_claim_curation_workspace",
        publication.published_at,
    )


async def _upsert_fact_registry(
    connection: DraftClaimCurationPublicationConnectionLike,
    publication: DraftClaimCurationPublicationCandidate,
) -> None:
    await connection.execute(
        """
        INSERT INTO knowledge_workbench_fact_registries (
            registry_id, project_id, document_id, processing_run_id,
            status, version, retention_state, created_at, updated_at
        )
        VALUES ($1, $2::uuid, $3, NULL, 'published', 1, 'runtime_published', $4, $4)
        ON CONFLICT (registry_id) DO UPDATE
        SET status = 'published',
            retention_state = 'runtime_published',
            updated_at = EXCLUDED.updated_at
        """,
        publication.fact_registry_id,
        publication.project_id,
        publication.source_document_ref,
        publication.published_at,
    )


async def _upsert_fact(
    connection: DraftClaimCurationPublicationConnectionLike,
    publication: DraftClaimCurationPublicationCandidate,
    item: DraftClaimCurationPublicationItem,
) -> None:
    await connection.execute(
        """
        INSERT INTO knowledge_workbench_canonical_facts (
            fact_id, registry_id, project_id, document_id, processing_run_id,
            claim, claim_kind, granularity, possible_questions, scope,
            exclusion_scope, derived_fact_notes, status, retention_state,
            created_at, updated_at
        )
        VALUES (
            $1, $2, $3::uuid, $4, NULL, $5, $6, $7, $8::jsonb, '',
            $9, '[]'::jsonb, 'published', 'runtime_published', $10, $10
        )
        ON CONFLICT (fact_id) DO UPDATE
        SET claim = EXCLUDED.claim,
            claim_kind = EXCLUDED.claim_kind,
            granularity = EXCLUDED.granularity,
            possible_questions = EXCLUDED.possible_questions,
            exclusion_scope = EXCLUDED.exclusion_scope,
            status = 'published',
            retention_state = 'runtime_published',
            updated_at = EXCLUDED.updated_at
        """,
        item.fact_id,
        publication.fact_registry_id,
        publication.project_id,
        publication.source_document_ref,
        item.claim,
        item.claim_kind,
        item.granularity,
        json.dumps(list(item.possible_questions), ensure_ascii=False),
        item.exclusion_scope,
        publication.published_at,
    )


async def _replace_fact_triples(
    connection: DraftClaimCurationPublicationConnectionLike,
    publication: DraftClaimCurationPublicationCandidate,
    item: DraftClaimCurationPublicationItem,
) -> None:
    await connection.execute(
        "DELETE FROM knowledge_workbench_fact_triples WHERE fact_id = $1",
        item.fact_id,
    )
    for index, triple in enumerate(item.triples):
        await connection.execute(
            """
            INSERT INTO knowledge_workbench_fact_triples (
                triple_id, fact_id, registry_id, subject,
                predicate, object, qualifiers, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
            """,
            f"{item.fact_id}:triple:{index}",
            item.fact_id,
            publication.fact_registry_id,
            _triple_text(triple, "subject"),
            _triple_text(triple, "predicate"),
            _triple_text(triple, "object"),
            json.dumps(_triple_qualifiers(triple), ensure_ascii=False),
            publication.published_at,
        )


async def _upsert_runtime_entry(
    connection: DraftClaimCurationPublicationConnectionLike,
    publication: DraftClaimCurationPublicationCandidate,
    item: DraftClaimCurationPublicationItem,
) -> None:
    # answer_text is a deprecated runtime table compatibility column.
    # Published Workbench retrieval uses claim + embedding_text as semantic units.
    await connection.execute(
        """
        INSERT INTO knowledge_workbench_runtime_retrieval_entries (
            runtime_entry_id, project_id, fact_id, publication_id, workflow_run_id,
            source_document_ref, curation_item_ref, claim, claim_kind, granularity,
            possible_questions, exclusion_scope, evidence_block, triples,
            source_claim_refs, answer_text, embedding_text, source_refs,
            visibility, status, created_at, updated_at
        )
        VALUES (
            $1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10,
            $11::jsonb, $12, $13, $14::jsonb, $15::jsonb, $16,
            $17, $18::jsonb, 'published', 'active', $19, $19
        )
        ON CONFLICT (runtime_entry_id) DO UPDATE
        SET publication_id = EXCLUDED.publication_id,
            workflow_run_id = EXCLUDED.workflow_run_id,
            source_document_ref = EXCLUDED.source_document_ref,
            curation_item_ref = EXCLUDED.curation_item_ref,
            claim = EXCLUDED.claim,
            claim_kind = EXCLUDED.claim_kind,
            granularity = EXCLUDED.granularity,
            possible_questions = EXCLUDED.possible_questions,
            exclusion_scope = EXCLUDED.exclusion_scope,
            evidence_block = EXCLUDED.evidence_block,
            triples = EXCLUDED.triples,
            source_claim_refs = EXCLUDED.source_claim_refs,
            answer_text = EXCLUDED.answer_text,
            embedding_text = EXCLUDED.embedding_text,
            source_refs = EXCLUDED.source_refs,
            visibility = 'published',
            status = 'active',
            updated_at = EXCLUDED.updated_at
        """,
        item.runtime_entry_id,
        publication.project_id,
        item.fact_id,
        publication.publication_id,
        publication.workflow_run_id,
        publication.source_document_ref,
        item.item_ref,
        item.claim,
        item.claim_kind,
        item.granularity,
        json.dumps(list(item.possible_questions), ensure_ascii=False),
        item.exclusion_scope,
        item.evidence_block,
        json.dumps(list(item.triples), ensure_ascii=False),
        json.dumps(list(item.source_claim_refs), ensure_ascii=False),
        item.claim,
        item.embedding_text,
        json.dumps(
            {
                "publication_id": publication.publication_id,
                "workflow_run_id": publication.workflow_run_id,
                "source_document_ref": publication.source_document_ref,
                "curation_item_ref": item.item_ref,
                "source_claim_refs": list(item.source_claim_refs),
            },
            ensure_ascii=False,
        ),
        publication.published_at,
    )


async def _replace_runtime_embedding(
    connection: DraftClaimCurationPublicationConnectionLike,
    item: DraftClaimCurationPublicationItem,
    created_at: datetime,
) -> None:
    await connection.execute(
        """
        DELETE FROM knowledge_workbench_runtime_retrieval_entry_embeddings
        WHERE runtime_entry_id = $1
          AND embedding_model_id = $2
        """,
        item.runtime_entry_id,
        item.embedding_model_id,
    )
    await connection.execute(
        """
        INSERT INTO knowledge_workbench_runtime_retrieval_entry_embeddings (
            runtime_entry_id, embedding_model_id, dimensions,
            embedding, embedding_text_hash, created_at
        )
        VALUES ($1, $2, $3, $4::vector, $5, $6)
        """,
        item.runtime_entry_id,
        item.embedding_model_id,
        item.embedding_dimensions,
        _pg_vector_text(item.vector),
        item.embedding_text_hash,
        created_at,
    )


def _has_acquire(value: object) -> bool:
    return callable(getattr(value, "acquire", None))


def _affected_count(status: object) -> int:
    parts = str(status).split()
    if not parts:
        return 0
    try:
        return int(parts[-1])
    except ValueError:
        return 0


def _pg_vector_text(vector: tuple[float, ...]) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def _triple_text(triple: Mapping[str, object], key: str) -> str:
    value = triple.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"triple {key} must be non-empty")
    return value.strip()


def _triple_qualifiers(triple: Mapping[str, object]) -> list[object]:
    value = triple.get("qualifiers")
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError("triple qualifiers must be list")
    return list(value)
