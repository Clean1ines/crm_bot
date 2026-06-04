from __future__ import annotations

import json
from collections.abc import Awaitable, Mapping, Sequence
from typing import Protocol

from src.application.workbench_commands.surface_curation import (
    SurfaceCurationRejectedError,
)


class WorkbenchSurfaceCurationTransaction(Protocol):
    async def __aenter__(self) -> object: ...

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> object: ...


class WorkbenchSurfaceCurationConnection(Protocol):
    def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> Awaitable[Mapping[str, object] | None]: ...

    def fetch(
        self,
        query: str,
        *args: object,
    ) -> Awaitable[Sequence[Mapping[str, object]]]: ...

    def execute(self, query: str, *args: object) -> Awaitable[str]: ...

    def transaction(self) -> WorkbenchSurfaceCurationTransaction: ...


class WorkbenchSurfaceCurationRepository:
    def __init__(self, connection: WorkbenchSurfaceCurationConnection) -> None:
        self._connection = connection

    async def approve_surface(
        self,
        *,
        project_id: str,
        document_id: str,
        surface_id: str,
    ) -> Mapping[str, object]:
        row = await self._connection.fetchrow(
            """
            UPDATE knowledge_workbench_surfaces
            SET status = 'ready',
                curation_state = 'approved',
                updated_at = now()
            WHERE project_id = $1::uuid
              AND document_id = $2
              AND surface_id = $3
              AND status <> 'deleted'
            RETURNING *
            """,
            project_id,
            document_id,
            surface_id,
        )
        return _required_row(row, "surface not found")

    async def reject_surface(
        self,
        *,
        project_id: str,
        document_id: str,
        surface_id: str,
        reason: str,
    ) -> Mapping[str, object]:
        row = await self._connection.fetchrow(
            """
            UPDATE knowledge_workbench_surfaces
            SET status = 'rejected',
                curation_state = 'rejected',
                updated_at = now()
            WHERE project_id = $1::uuid
              AND document_id = $2
              AND surface_id = $3
              AND status <> 'deleted'
            RETURNING *, $4::text AS curation_reason
            """,
            project_id,
            document_id,
            surface_id,
            reason,
        )
        return _required_row(row, "surface not found")

    async def edit_surface(
        self,
        *,
        project_id: str,
        document_id: str,
        surface_id: str,
        title: str | None,
        answer: str | None,
        short_answer: str | None,
        question_variants: tuple[str, ...] | None,
        retrieval_scope: str | None,
        exclusion_scope: str | None,
    ) -> Mapping[str, object]:
        row = await self._connection.fetchrow(
            """
            UPDATE knowledge_workbench_surfaces
            SET title = COALESCE($4, title),
                answer = COALESCE($5, answer),
                short_answer = COALESCE($6, short_answer),
                question_variants = CASE
                    WHEN $7::jsonb IS NULL THEN question_variants
                    ELSE $7::jsonb
                END,
                retrieval_scope = COALESCE($8, retrieval_scope),
                exclusion_scope = COALESCE($9, exclusion_scope),
                status = CASE
                    WHEN status = 'published' THEN status
                    ELSE 'ready'
                END,
                curation_state = 'edited',
                updated_at = now()
            WHERE project_id = $1::uuid
              AND document_id = $2
              AND surface_id = $3
              AND status <> 'deleted'
            RETURNING *
            """,
            project_id,
            document_id,
            surface_id,
            title,
            answer,
            short_answer,
            _json(list(question_variants)) if question_variants is not None else None,
            retrieval_scope,
            exclusion_scope,
        )
        return _required_row(row, "surface not found")

    async def merge_facts(
        self,
        *,
        project_id: str,
        document_id: str,
        target_fact_id: str,
        source_fact_ids: tuple[str, ...],
        reason: str,
    ) -> Mapping[str, object]:
        async with self._connection.transaction():
            target = await self._connection.fetchrow(
                """
                SELECT *
                FROM knowledge_workbench_surfaces
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND fact_id = $3
                  AND status <> 'deleted'
                ORDER BY updated_at DESC NULLS LAST, created_at DESC
                LIMIT 1
                """,
                project_id,
                document_id,
                target_fact_id,
            )
            target_row = _required_row(target, "target fact surface not found")

            source_rows = await self._connection.fetch(
                """
                SELECT *
                FROM knowledge_workbench_surfaces
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND fact_id = ANY($3::text[])
                  AND status <> 'deleted'
                ORDER BY created_at ASC, surface_id ASC
                """,
                project_id,
                document_id,
                list(source_fact_ids),
            )
            if len(source_rows) != len(source_fact_ids):
                raise SurfaceCurationRejectedError(
                    "one or more source fact surfaces were not found"
                )

            merged_question_variants = _merge_text_arrays(
                target_row.get("question_variants"),
                *(row.get("question_variants") for row in source_rows),
            )
            merged_evidence_quotes = _merge_text_arrays(
                target_row.get("evidence_quotes"),
                *(row.get("evidence_quotes") for row in source_rows),
            )
            merged_source_refs = _merge_text_arrays(
                target_row.get("source_refs"),
                *(row.get("source_refs") for row in source_rows),
            )
            merged_source_section_ids = _merge_text_arrays(
                target_row.get("source_section_ids"),
                *(row.get("source_section_ids") for row in source_rows),
            )

            updated = await self._connection.fetchrow(
                """
                UPDATE knowledge_workbench_surfaces
                SET question_variants = $4::jsonb,
                    evidence_quotes = $5::jsonb,
                    source_refs = $6::jsonb,
                    source_section_ids = $7::jsonb,
                    curation_state = 'merged',
                    updated_at = now()
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND fact_id = $3
                  AND surface_id = $8
                RETURNING *
                """,
                project_id,
                document_id,
                target_fact_id,
                _json(list(merged_question_variants)),
                _json(list(merged_evidence_quotes)),
                _json(list(merged_source_refs)),
                _json(list(merged_source_section_ids)),
                str(target_row["surface_id"]),
            )

            await self._connection.execute(
                """
                UPDATE knowledge_workbench_surfaces
                SET status = 'deleted',
                    curation_state = 'merged_into',
                    updated_at = now()
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND fact_id = ANY($3::text[])
                """,
                project_id,
                document_id,
                list(source_fact_ids),
            )

            await self._connection.execute(
                """
                UPDATE knowledge_workbench_canonical_facts
                SET status = 'merged',
                    updated_at = now()
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND fact_id = ANY($3::text[])
                """,
                project_id,
                document_id,
                list(source_fact_ids),
            )

            for source_fact_id in source_fact_ids:
                await self._connection.execute(
                    """
                    INSERT INTO knowledge_workbench_fact_relations (
                        relation_id,
                        registry_id,
                        source_fact_id,
                        target_fact_id,
                        relation,
                        reason
                    )
                    SELECT
                        $1,
                        registry_id,
                        $2,
                        $3,
                        'same_meaning',
                        $4
                    FROM knowledge_workbench_canonical_facts
                    WHERE project_id = $5::uuid
                      AND document_id = $6
                      AND fact_id = $3
                    ON CONFLICT (relation_id) DO NOTHING
                    """,
                    f"curation-merge:{project_id}:{document_id}:{source_fact_id}:{target_fact_id}",
                    source_fact_id,
                    target_fact_id,
                    reason,
                    project_id,
                    document_id,
                )

            return _required_row(updated, "target fact surface not found")

    async def delete_fact(
        self,
        *,
        project_id: str,
        document_id: str,
        fact_id: str,
        reason: str,
    ) -> Mapping[str, object]:
        async with self._connection.transaction():
            row = await self._connection.fetchrow(
                """
                UPDATE knowledge_workbench_surfaces
                SET status = 'deleted',
                    curation_state = 'deleted',
                    updated_at = now()
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND fact_id = $3
                  AND status <> 'deleted'
                RETURNING *, $4::text AS curation_reason
                """,
                project_id,
                document_id,
                fact_id,
                reason,
            )

            await self._connection.execute(
                """
                UPDATE knowledge_workbench_canonical_facts
                SET status = 'deleted',
                    updated_at = now()
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND fact_id = $3
                """,
                project_id,
                document_id,
                fact_id,
            )

            return _required_row(row, "fact surface not found")

    async def publish_selected_surfaces(
        self,
        *,
        project_id: str,
        document_id: str,
        surface_ids: tuple[str, ...],
    ) -> Mapping[str, object]:
        rows = await self._connection.fetch(
            """
            UPDATE knowledge_workbench_surfaces
            SET status = 'published',
                curation_state = 'published',
                updated_at = now()
            WHERE project_id = $1::uuid
              AND document_id = $2
              AND surface_id = ANY($3::text[])
              AND status <> 'deleted'
            RETURNING *
            """,
            project_id,
            document_id,
            list(surface_ids),
        )
        if not rows:
            raise SurfaceCurationRejectedError("no selected surfaces were published")
        return {"items": tuple(dict(row) for row in rows)}


def _required_row(
    row: Mapping[str, object] | None,
    message: str,
) -> Mapping[str, object]:
    if row is None:
        raise SurfaceCurationRejectedError(message)
    return dict(row)


def _merge_text_arrays(first: object, *rest: object) -> tuple[str, ...]:
    values: list[str] = []
    for value in (first, *rest):
        for item in _text_tuple(value):
            if item not in values:
                values.append(item)
    return tuple(values)


def _text_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    parsed = value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = value
        else:
            return (stripped,) if stripped else ()
    if isinstance(parsed, Sequence) and not isinstance(parsed, (str, bytes, bytearray)):
        return tuple(str(item).strip() for item in parsed if str(item).strip())
    text = str(parsed).strip()
    return (text,) if text else ()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


__all__ = [
    "WorkbenchSurfaceCurationConnection",
    "WorkbenchSurfaceCurationRepository",
]
