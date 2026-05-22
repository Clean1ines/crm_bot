from __future__ import annotations

from collections.abc import Sequence

import asyncpg

from src.application.ports.commercial_price import CommercialPriceKnowledgePort
from src.domain.commercial.price_knowledge import (
    PriceDocument,
    PriceDocumentStatus,
    PriceLookupQuery,
    PriceSourceRow,
    PriceSourceUnit,
    PublishedPriceFact,
)
from src.infrastructure.db.repositories.commercial_price_mappers import (
    jsonb_array_payload,
    jsonb_object_payload,
    price_conditions_payload,
    price_document_from_row,
    price_fact_aliases_payload,
    price_fact_amount,
    price_fact_currency,
    price_fact_from_row,
    price_fact_max_amount,
    price_fact_min_amount,
    price_fact_variant_payload,
    price_source_refs_payload,
    price_source_row_from_row,
    price_source_unit_from_row,
)
from src.utils.uuid_utils import ensure_uuid


def affected_row_count(command_result: str) -> int:
    try:
        return int(str(command_result).split()[-1])
    except (IndexError, ValueError):
        return 0


def _normalized_limit(limit: int, *, upper: int = 200) -> int:
    return max(1, min(int(limit), upper))


class CommercialPriceRepository(CommercialPriceKnowledgePort):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def create_price_document(self, document: PriceDocument) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO commercial_price_documents (
                    id,
                    project_id,
                    knowledge_document_id,
                    source_format,
                    input_kind,
                    status,
                    detected_currency,
                    detected_locale,
                    error
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, '')
                ON CONFLICT (id)
                DO UPDATE SET
                    source_format = EXCLUDED.source_format,
                    input_kind = EXCLUDED.input_kind,
                    status = EXCLUDED.status,
                    detected_currency = EXCLUDED.detected_currency,
                    detected_locale = EXCLUDED.detected_locale,
                    error = '',
                    updated_at = now()
                """,
                document.id,
                ensure_uuid(document.project_id),
                ensure_uuid(document.knowledge_document_id),
                document.source_format.value,
                document.input_kind.value,
                document.status.value,
                document.detected_currency,
                document.detected_locale,
            )

    async def get_price_document_by_knowledge_document(
        self,
        *,
        project_id: str,
        knowledge_document_id: str,
    ) -> PriceDocument | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id,
                    project_id,
                    knowledge_document_id,
                    source_format,
                    input_kind,
                    status,
                    detected_currency,
                    detected_locale
                FROM commercial_price_documents
                WHERE project_id = $1
                  AND knowledge_document_id = $2
                """,
                ensure_uuid(project_id),
                ensure_uuid(knowledge_document_id),
            )

        return price_document_from_row(dict(row)) if row is not None else None

    async def get_price_document(
        self,
        *,
        project_id: str,
        price_document_id: str,
    ) -> PriceDocument | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id,
                    project_id,
                    knowledge_document_id,
                    source_format,
                    input_kind,
                    status,
                    detected_currency,
                    detected_locale
                FROM commercial_price_documents
                WHERE project_id = $1
                  AND id = $2
                """,
                ensure_uuid(project_id),
                price_document_id,
            )

        return price_document_from_row(dict(row)) if row is not None else None

    async def list_price_documents_for_project(
        self,
        *,
        project_id: str,
    ) -> tuple[PriceDocument, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    project_id,
                    knowledge_document_id,
                    source_format,
                    input_kind,
                    status,
                    detected_currency,
                    detected_locale
                FROM commercial_price_documents
                WHERE project_id = $1
                ORDER BY updated_at DESC, id
                """,
                ensure_uuid(project_id),
            )

        return tuple(price_document_from_row(dict(row)) for row in rows)

    async def update_price_document_status(
        self,
        *,
        project_id: str,
        price_document_id: str,
        status: PriceDocumentStatus,
        error: str | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE commercial_price_documents
                SET status = $3,
                    error = $4,
                    updated_at = now()
                WHERE project_id = $1
                  AND id = $2
                """,
                ensure_uuid(project_id),
                price_document_id,
                status.value,
                error or "",
            )

    async def replace_price_source_units(
        self,
        *,
        project_id: str,
        price_document_id: str,
        units: Sequence[PriceSourceUnit],
    ) -> int:
        for unit in units:
            if unit.price_document_id != price_document_id:
                raise ValueError("price source unit document mismatch")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    DELETE FROM commercial_price_source_units
                    WHERE project_id = $1
                      AND price_document_id = $2
                    """,
                    ensure_uuid(project_id),
                    price_document_id,
                )

                for unit in units:
                    await conn.execute(
                        """
                        INSERT INTO commercial_price_source_units (
                            id,
                            project_id,
                            price_document_id,
                            source_index,
                            kind,
                            raw_text,
                            title,
                            metadata
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
                        """,
                        unit.id,
                        ensure_uuid(project_id),
                        price_document_id,
                        unit.source_index,
                        unit.kind.value,
                        unit.raw_text,
                        unit.title,
                        jsonb_object_payload(unit.metadata),
                    )

        return len(units)

    async def list_price_source_units(
        self,
        *,
        project_id: str,
        price_document_id: str,
    ) -> tuple[PriceSourceUnit, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    price_document_id,
                    source_index,
                    kind,
                    raw_text,
                    title,
                    metadata
                FROM commercial_price_source_units
                WHERE project_id = $1
                  AND price_document_id = $2
                ORDER BY source_index, id
                """,
                ensure_uuid(project_id),
                price_document_id,
            )

        return tuple(price_source_unit_from_row(dict(row)) for row in rows)

    async def replace_price_source_rows(
        self,
        *,
        project_id: str,
        price_document_id: str,
        source_unit_id: str,
        rows: Sequence[PriceSourceRow],
    ) -> int:
        for row in rows:
            if row.source_unit_id != source_unit_id:
                raise ValueError("price source row source_unit_id mismatch")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    DELETE FROM commercial_price_source_rows
                    WHERE project_id = $1
                      AND price_document_id = $2
                      AND source_unit_id = $3
                    """,
                    ensure_uuid(project_id),
                    price_document_id,
                    source_unit_id,
                )

                for row in rows:
                    await conn.execute(
                        """
                        INSERT INTO commercial_price_source_rows (
                            id,
                            project_id,
                            price_document_id,
                            source_unit_id,
                            row_index,
                            raw_cells,
                            normalized_cells
                        )
                        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb)
                        """,
                        row.id,
                        ensure_uuid(project_id),
                        price_document_id,
                        source_unit_id,
                        row.row_index,
                        jsonb_object_payload(row.raw_cells),
                        jsonb_object_payload(row.normalized_cells),
                    )

        return len(rows)

    async def list_price_source_rows(
        self,
        *,
        project_id: str,
        price_document_id: str,
        source_unit_id: str | None = None,
    ) -> tuple[PriceSourceRow, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    source_unit_id,
                    row_index,
                    raw_cells,
                    normalized_cells
                FROM commercial_price_source_rows
                WHERE project_id = $1
                  AND price_document_id = $2
                  AND ($3::text IS NULL OR source_unit_id = $3)
                ORDER BY source_unit_id, row_index, id
                """,
                ensure_uuid(project_id),
                price_document_id,
                source_unit_id,
            )

        return tuple(price_source_row_from_row(dict(row)) for row in rows)

    async def replace_price_facts_for_document(
        self,
        *,
        project_id: str,
        price_document_id: str,
        facts: Sequence[PublishedPriceFact],
    ) -> int:
        for fact in facts:
            if (
                fact.project_id != project_id
                or fact.price_document_id != price_document_id
            ):
                raise ValueError("price fact project/document mismatch")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    DELETE FROM commercial_price_facts
                    WHERE project_id = $1
                      AND price_document_id = $2
                    """,
                    ensure_uuid(project_id),
                    price_document_id,
                )

                for fact in facts:
                    await self._insert_price_fact(conn, fact)

        return len(facts)

    async def list_price_facts_for_document(
        self,
        *,
        project_id: str,
        price_document_id: str,
        include_non_runtime: bool = False,
    ) -> tuple[PublishedPriceFact, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    project_id,
                    price_document_id,
                    item_name,
                    value_kind,
                    status,
                    amount,
                    min_amount,
                    max_amount,
                    currency,
                    unit,
                    price_text,
                    variant,
                    aliases,
                    conditions,
                    source_refs,
                    confidence
                FROM commercial_price_facts
                WHERE project_id = $1
                  AND price_document_id = $2
                  AND ($3::boolean OR status = 'published')
                ORDER BY updated_at DESC, id
                """,
                ensure_uuid(project_id),
                price_document_id,
                include_non_runtime,
            )

        return tuple(price_fact_from_row(dict(row)) for row in rows)

    async def list_price_facts_for_documents(
        self,
        *,
        project_id: str,
        price_document_ids: Sequence[str],
        include_non_runtime: bool = False,
    ) -> tuple[PublishedPriceFact, ...]:
        cleaned_document_ids = tuple(
            price_document_id
            for price_document_id in price_document_ids
            if price_document_id.strip()
        )
        if not cleaned_document_ids:
            return ()

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    project_id,
                    price_document_id,
                    item_name,
                    value_kind,
                    status,
                    amount,
                    min_amount,
                    max_amount,
                    currency,
                    unit,
                    price_text,
                    variant,
                    aliases,
                    conditions,
                    source_refs,
                    confidence
                FROM commercial_price_facts
                WHERE project_id = $1
                  AND price_document_id = ANY($2::text[])
                  AND ($3::boolean OR status = 'published')
                ORDER BY updated_at DESC, id
                """,
                ensure_uuid(project_id),
                list(cleaned_document_ids),
                include_non_runtime,
            )

        return tuple(price_fact_from_row(dict(row)) for row in rows)

    async def publish_price_facts(
        self,
        *,
        project_id: str,
        price_document_id: str,
        fact_ids: Sequence[str],
    ) -> int:
        if not fact_ids:
            return 0

        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE commercial_price_facts
                SET status = 'published',
                    updated_at = now()
                WHERE project_id = $1
                  AND price_document_id = $2
                  AND id = ANY($3::text[])
                """,
                ensure_uuid(project_id),
                price_document_id,
                list(fact_ids),
            )

        return affected_row_count(result)

    async def reject_price_facts(
        self,
        *,
        project_id: str,
        price_document_id: str,
        fact_ids: Sequence[str],
        reason: str,
    ) -> int:
        if not fact_ids:
            return 0
        if not reason.strip():
            raise ValueError("price fact rejection reason must not be empty")

        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE commercial_price_facts
                SET status = 'rejected',
                    metadata = jsonb_set(
                        metadata,
                        '{rejection_reason}',
                        to_jsonb($4::text),
                        true
                    ),
                    updated_at = now()
                WHERE project_id = $1
                  AND price_document_id = $2
                  AND id = ANY($3::text[])
                """,
                ensure_uuid(project_id),
                price_document_id,
                list(fact_ids),
                reason.strip(),
            )

        return affected_row_count(result)

    async def list_published_price_facts_for_lookup(
        self,
        *,
        query: PriceLookupQuery,
        limit: int = 20,
    ) -> tuple[PublishedPriceFact, ...]:
        normalized_limit = _normalized_limit(limit)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    project_id,
                    price_document_id,
                    item_name,
                    value_kind,
                    status,
                    amount,
                    min_amount,
                    max_amount,
                    currency,
                    unit,
                    price_text,
                    variant,
                    aliases,
                    conditions,
                    source_refs,
                    confidence
                FROM commercial_price_facts
                WHERE project_id = $1
                  AND status = 'published'
                  AND (
                      lower(item_name) = lower($2)
                      OR EXISTS (
                          SELECT 1
                          FROM jsonb_array_elements_text(aliases) AS alias_value(value)
                          WHERE lower(alias_value.value) = lower($2)
                      )
                  )
                ORDER BY
                    CASE WHEN lower(item_name) = lower($2) THEN 0 ELSE 1 END,
                    updated_at DESC,
                    id
                LIMIT $3
                """,
                ensure_uuid(query.project_id),
                query.item_name,
                normalized_limit,
            )

        return tuple(price_fact_from_row(dict(row)) for row in rows)

    async def list_required_variant_slots(
        self,
        *,
        project_id: str,
        item_name: str,
    ) -> tuple[str, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT variant_key.value AS key
                FROM commercial_price_facts
                CROSS JOIN LATERAL jsonb_object_keys(variant) AS variant_key(value)
                WHERE project_id = $1
                  AND status = 'published'
                  AND (
                      lower(item_name) = lower($2)
                      OR EXISTS (
                          SELECT 1
                          FROM jsonb_array_elements_text(aliases) AS alias_value(value)
                          WHERE lower(alias_value.value) = lower($2)
                      )
                  )
                ORDER BY variant_key.value
                """,
                ensure_uuid(project_id),
                item_name,
            )

        return tuple(str(row["key"]) for row in rows if str(row["key"]).strip())

    async def list_price_item_names(
        self,
        *,
        project_id: str,
        query_text: str | None = None,
        limit: int = 50,
    ) -> tuple[str, ...]:
        normalized_limit = _normalized_limit(limit)
        search_pattern = (
            f"%{query_text.strip()}%" if query_text and query_text.strip() else None
        )

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT item_name
                FROM commercial_price_facts
                WHERE project_id = $1
                  AND status = 'published'
                  AND ($2::text IS NULL OR item_name ILIKE $2)
                ORDER BY item_name
                LIMIT $3
                """,
                ensure_uuid(project_id),
                search_pattern,
                normalized_limit,
            )

        return tuple(
            str(row["item_name"]) for row in rows if str(row["item_name"]).strip()
        )

    async def _insert_price_fact(
        self,
        conn: asyncpg.Connection,
        fact: PublishedPriceFact,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO commercial_price_facts (
                id,
                project_id,
                price_document_id,
                item_name,
                value_kind,
                status,
                amount,
                min_amount,
                max_amount,
                currency,
                unit,
                price_text,
                variant,
                aliases,
                conditions,
                source_refs,
                confidence
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                $7,
                $8,
                $9,
                $10,
                $11,
                $12,
                $13::jsonb,
                $14::jsonb,
                $15::jsonb,
                $16::jsonb,
                $17
            )
            ON CONFLICT (id)
            DO UPDATE SET
                item_name = EXCLUDED.item_name,
                value_kind = EXCLUDED.value_kind,
                status = EXCLUDED.status,
                amount = EXCLUDED.amount,
                min_amount = EXCLUDED.min_amount,
                max_amount = EXCLUDED.max_amount,
                currency = EXCLUDED.currency,
                unit = EXCLUDED.unit,
                price_text = EXCLUDED.price_text,
                variant = EXCLUDED.variant,
                aliases = EXCLUDED.aliases,
                conditions = EXCLUDED.conditions,
                source_refs = EXCLUDED.source_refs,
                confidence = EXCLUDED.confidence,
                updated_at = now()
            """,
            fact.id,
            ensure_uuid(fact.project_id),
            fact.price_document_id,
            fact.item_name,
            fact.value_kind.value,
            fact.status.value,
            price_fact_amount(fact),
            price_fact_min_amount(fact),
            price_fact_max_amount(fact),
            price_fact_currency(fact),
            fact.unit,
            fact.price_text,
            jsonb_object_payload(price_fact_variant_payload(fact)),
            jsonb_array_payload(price_fact_aliases_payload(fact)),
            jsonb_array_payload(price_conditions_payload(fact.conditions)),
            jsonb_array_payload(price_source_refs_payload(fact.source_refs)),
            float(fact.confidence),
        )
