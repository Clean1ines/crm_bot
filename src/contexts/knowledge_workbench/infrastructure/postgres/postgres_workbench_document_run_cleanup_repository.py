from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast
from uuid import UUID

import asyncpg

from src.contexts.knowledge_workbench.application.sagas.delete_knowledge_extraction_document_run import (
    DeletedWorkbenchDocumentRunCounts,
    DocumentRunRefs,
    deleted_counts_from_mapping,
)


class WorkbenchDocumentRunCleanupPool(Protocol):
    async def acquire(self): ...


class PostgresWorkbenchDocumentRunCleanupRepository:
    def __init__(self, pool: WorkbenchDocumentRunCleanupPool) -> None:
        self._pool = pool

    async def collect_document_run_refs(
        self,
        *,
        project_id: UUID,
        source_document_ref: str,
    ) -> DocumentRunRefs:
        async with cast(asyncpg.Pool, self._pool).acquire() as connection:
            columns = await _load_columns(connection)
            project_id_text = str(project_id)

            exists = await _document_exists(
                connection=connection,
                columns=columns,
                project_id=project_id_text,
                source_document_ref=source_document_ref,
            )
            workflow_run_ids = await _workflow_run_ids(
                connection=connection,
                columns=columns,
                project_id=project_id_text,
                source_document_ref=source_document_ref,
            )
            processing_run_ids = await _processing_run_ids(
                connection=connection,
                columns=columns,
                project_id=project_id_text,
                source_document_ref=source_document_ref,
            )
            source_unit_refs = await _source_unit_refs(
                connection=connection,
                columns=columns,
                source_document_ref=source_document_ref,
            )
            observation_refs = await _observation_refs(
                connection=connection,
                columns=columns,
                source_unit_refs=source_unit_refs,
            )
            curation_workspace_refs = await _curation_workspace_refs(
                connection=connection,
                columns=columns,
                workflow_run_ids=workflow_run_ids,
                source_document_ref=source_document_ref,
            )
            work_item_ids = await _work_item_ids(
                connection=connection,
                columns=columns,
                workflow_run_ids=workflow_run_ids,
                source_document_ref=source_document_ref,
                source_unit_refs=source_unit_refs,
            )
            attempt_ids = await _attempt_ids(
                connection=connection,
                columns=columns,
                workflow_run_ids=workflow_run_ids,
                work_item_ids=work_item_ids,
            )
            llm_task_ids = await _llm_task_ids(
                connection=connection,
                columns=columns,
                workflow_run_ids=workflow_run_ids,
                source_unit_refs=source_unit_refs,
            )
            llm_attempt_ids = await _llm_attempt_ids(
                connection=connection,
                columns=columns,
                workflow_run_ids=workflow_run_ids,
                source_unit_refs=source_unit_refs,
            )

            return DocumentRunRefs(
                project_id=project_id_text,
                source_document_ref=source_document_ref,
                exists=exists,
                workflow_run_ids=workflow_run_ids,
                processing_run_ids=processing_run_ids,
                source_unit_refs=source_unit_refs,
                observation_refs=observation_refs,
                work_item_ids=work_item_ids,
                attempt_ids=attempt_ids,
                llm_task_ids=llm_task_ids,
                llm_attempt_ids=llm_attempt_ids,
                curation_workspace_refs=curation_workspace_refs,
            )

    async def delete_document_run(
        self,
        refs: DocumentRunRefs,
    ) -> DeletedWorkbenchDocumentRunCounts:
        async with cast(asyncpg.Pool, self._pool).acquire() as connection:
            async with connection.transaction():
                columns = await _load_columns(connection)
                counts: dict[str, int] = {}

                counts["runtime_embeddings"] = await _delete_runtime_embeddings(
                    connection, columns, refs
                )
                counts["runtime_entries"] = await _delete_runtime_entries(
                    connection, columns, refs
                )
                counts["publications"] = await _delete_runtime_publications(
                    connection, columns, refs
                )

                counts["curation_items"] = await _delete_curation_items(
                    connection, columns, refs
                )
                counts["curation_workspaces"] = await _delete_curation_workspaces(
                    connection, columns, refs
                )

                counts["compaction_items"] = await _delete_compaction_artifacts(
                    connection, columns, refs
                )
                counts["clusters"] = await _delete_cluster_artifacts(
                    connection, columns, refs
                )

                counts["draft_claim_embeddings"] = await _delete_by_source_or_workflow(
                    connection,
                    columns,
                    table_name="draft_claim_embeddings",
                    source_document_ref=refs.source_document_ref,
                    workflow_run_ids=refs.workflow_run_ids,
                )
                counts[
                    "draft_claim_possible_questions"
                ] = await _delete_possible_questions(connection, columns, refs)
                counts["draft_claim_provenance"] = await _delete_provenance(
                    connection, columns, refs
                )
                counts["draft_claims"] = await _delete_draft_claims(
                    connection, columns, refs
                )

                counts["llm_artifacts"] = await _delete_llm_artifacts(
                    connection, columns, refs
                )
                counts["capacity_rows"] = await _delete_capacity_rows(
                    connection, columns, refs
                )

                counts[
                    "execution_attempt_dispatches"
                ] = await _delete_execution_dispatches(connection, columns, refs)
                counts[
                    "execution_work_item_attempts"
                ] = await _delete_execution_attempts(connection, columns, refs)
                counts[
                    "execution_work_item_schedules"
                ] = await _delete_execution_schedules(connection, columns, refs)
                counts["execution_work_items"] = await _delete_execution_work_items(
                    connection, columns, refs
                )

                counts["workflow_outbox_events"] = await _delete_by_workflows(
                    connection,
                    columns,
                    "workflow_runtime_outbox_events",
                    refs.workflow_run_ids,
                )
                counts["workflow_commands"] = await _delete_by_workflows(
                    connection,
                    columns,
                    "workflow_runtime_command_log",
                    refs.workflow_run_ids,
                )
                counts["workflow_progress_snapshots"] = await _delete_by_workflows(
                    connection,
                    columns,
                    "workflow_runtime_progress_snapshots",
                    refs.workflow_run_ids,
                )
                counts["timeline_entries"] = await _delete_timeline_entries(
                    connection, columns, refs
                )
                counts["resource_usage_snapshots"] = await _delete_by_workflows(
                    connection,
                    columns,
                    "workflow_runtime_resource_usage_snapshots",
                    refs.workflow_run_ids,
                )

                counts["workflow_runs"] = await _delete_saga_runs(
                    connection, columns, refs
                )
                counts["workbench_child_rows"] = await _delete_workbench_children(
                    connection, columns, refs
                )
                counts["source_units"] = await _delete_source_units(
                    connection, columns, refs
                )
                counts["source_documents"] = await _delete_source_document(
                    connection, columns, refs
                )
                counts["workbench_documents"] = await _delete_workbench_document(
                    connection, columns, refs
                )

                return deleted_counts_from_mapping(counts)


async def _load_columns(
    connection: asyncpg.Connection,
) -> dict[str, frozenset[str]]:
    rows = await connection.fetch(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
        """
    )
    result: dict[str, set[str]] = {}
    for row in rows:
        values = dict(row)
        table_name = values.get("table_name")
        column_name = values.get("column_name")
        if isinstance(table_name, str) and isinstance(column_name, str):
            result.setdefault(table_name, set()).add(column_name)
    return {table: frozenset(names) for table, names in result.items()}


def _has(
    columns: Mapping[str, frozenset[str]],
    table_name: str,
    *column_names: str,
) -> bool:
    table_columns = columns.get(table_name)
    return table_columns is not None and all(
        name in table_columns for name in column_names
    )


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _delete_count(status: object) -> int:
    if not isinstance(status, str):
        return 0
    parts = status.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return 0
    return int(parts[1])


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value.strip()))


async def _document_exists(
    *,
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    project_id: str,
    source_document_ref: str,
) -> bool:
    if _has(columns, "knowledge_workbench_documents", "project_id", "document_id"):
        row = await connection.fetchrow(
            """
            SELECT 1
            FROM knowledge_workbench_documents
            WHERE project_id = $1::uuid
              AND document_id = $2
            """,
            project_id,
            source_document_ref,
        )
        if row is not None:
            return True

    if _has(columns, "source_documents", "project_id", "document_ref"):
        row = await connection.fetchrow(
            """
            SELECT 1
            FROM source_documents
            WHERE project_id = $1
              AND document_ref = $2
            """,
            project_id,
            source_document_ref,
        )
        return row is not None

    return False


async def _fetch_text_column(
    connection: asyncpg.Connection,
    query: str,
    *args: object,
    column_name: str,
) -> tuple[str, ...]:
    rows = await connection.fetch(query, *args)
    values: list[str] = []
    for row in rows:
        value = dict(row).get(column_name)
        if isinstance(value, str) and value.strip():
            values.append(value)
    return _unique(values)


async def _workflow_run_ids(
    *,
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    project_id: str,
    source_document_ref: str,
) -> tuple[str, ...]:
    if not _has(
        columns,
        "knowledge_extraction_workflow_runs",
        "project_id",
        "source_document_ref",
        "workflow_run_id",
    ):
        return ()
    return await _fetch_text_column(
        connection,
        """
        SELECT workflow_run_id
        FROM knowledge_extraction_workflow_runs
        WHERE project_id = $1
          AND source_document_ref = $2
        ORDER BY created_at ASC
        """,
        project_id,
        source_document_ref,
        column_name="workflow_run_id",
    )


async def _processing_run_ids(
    *,
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    project_id: str,
    source_document_ref: str,
) -> tuple[str, ...]:
    if not _has(
        columns,
        "knowledge_workbench_processing_runs",
        "project_id",
        "document_id",
        "processing_run_id",
    ):
        return ()
    return await _fetch_text_column(
        connection,
        """
        SELECT processing_run_id
        FROM knowledge_workbench_processing_runs
        WHERE project_id = $1::uuid
          AND document_id = $2
        ORDER BY created_at ASC
        """,
        project_id,
        source_document_ref,
        column_name="processing_run_id",
    )


async def _source_unit_refs(
    *,
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    source_document_ref: str,
) -> tuple[str, ...]:
    if not _has(columns, "source_units", "document_ref", "unit_ref"):
        return ()
    return await _fetch_text_column(
        connection,
        """
        SELECT unit_ref
        FROM source_units
        WHERE document_ref = $1
        ORDER BY ordinal ASC, unit_ref ASC
        """,
        source_document_ref,
        column_name="unit_ref",
    )


async def _observation_refs(
    *,
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    source_unit_refs: tuple[str, ...],
) -> tuple[str, ...]:
    if not source_unit_refs or not _has(
        columns, "draft_claim_observations", "source_unit_ref", "observation_ref"
    ):
        return ()
    return await _fetch_text_column(
        connection,
        """
        SELECT observation_ref
        FROM draft_claim_observations
        WHERE source_unit_ref = ANY($1::text[])
        ORDER BY created_at ASC, observation_ref ASC
        """,
        source_unit_refs,
        column_name="observation_ref",
    )


async def _curation_workspace_refs(
    *,
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    workflow_run_ids: tuple[str, ...],
    source_document_ref: str,
) -> tuple[str, ...]:
    if not _has(columns, "draft_claim_curation_workspaces", "workspace_ref"):
        return ()
    clauses: list[str] = []
    args: list[object] = []
    if (
        _has(columns, "draft_claim_curation_workspaces", "workflow_run_id")
        and workflow_run_ids
    ):
        clauses.append("workflow_run_id = ANY($1::text[])")
        args.append(workflow_run_ids)
    if _has(columns, "draft_claim_curation_workspaces", "source_document_ref"):
        clauses.append(f"source_document_ref = ${len(args) + 1}")
        args.append(source_document_ref)
    if not clauses:
        return ()
    return await _fetch_text_column(
        connection,
        f"""
        SELECT workspace_ref
        FROM draft_claim_curation_workspaces
        WHERE {" OR ".join(clauses)}
        """,
        *args,
        column_name="workspace_ref",
    )


async def _work_item_ids(
    *,
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    workflow_run_ids: tuple[str, ...],
    source_document_ref: str,
    source_unit_refs: tuple[str, ...],
) -> tuple[str, ...]:
    values: list[str] = []
    if workflow_run_ids and _has(
        columns,
        "draft_claim_observation_provenance",
        "workflow_run_id",
        "work_item_id",
    ):
        values.extend(
            await _fetch_text_column(
                connection,
                """
                SELECT work_item_id
                FROM draft_claim_observation_provenance
                WHERE workflow_run_id = ANY($1::text[])
                """,
                workflow_run_ids,
                column_name="work_item_id",
            )
        )
    if source_unit_refs and _has(
        columns,
        "draft_claim_observation_provenance",
        "source_unit_ref",
        "work_item_id",
    ):
        values.extend(
            await _fetch_text_column(
                connection,
                """
                SELECT work_item_id
                FROM draft_claim_observation_provenance
                WHERE source_unit_ref = ANY($1::text[])
                """,
                source_unit_refs,
                column_name="work_item_id",
            )
        )
    if workflow_run_ids and _has(
        columns,
        "workflow_runtime_timeline_entries",
        "workflow_run_id",
        "work_item_id",
    ):
        values.extend(
            await _fetch_text_column(
                connection,
                """
                SELECT work_item_id
                FROM workflow_runtime_timeline_entries
                WHERE workflow_run_id = ANY($1::text[])
                  AND work_item_id IS NOT NULL
                """,
                workflow_run_ids,
                column_name="work_item_id",
            )
        )
    if _has(
        columns,
        "claim_extraction_stage_work_items",
        "source_document_ref",
        "work_item_id",
    ):
        values.extend(
            await _fetch_text_column(
                connection,
                """
                SELECT work_item_id
                FROM claim_extraction_stage_work_items
                WHERE source_document_ref = $1
                """,
                source_document_ref,
                column_name="work_item_id",
            )
        )

    if _has(columns, "execution_work_item_schedules", "work_item_id", "payload"):
        schedule_clauses: list[str] = ["payload->>'source_document_ref' = $1"]
        schedule_args: list[object] = [source_document_ref]

        if workflow_run_ids:
            schedule_clauses.append(
                f"payload->>'workflow_run_id' = ANY(${len(schedule_args) + 1}::text[])"
            )
            schedule_args.append(workflow_run_ids)

        if source_unit_refs:
            schedule_clauses.append(
                f"payload->>'source_unit_ref' = ANY(${len(schedule_args) + 1}::text[])"
            )
            schedule_args.append(source_unit_refs)

        values.extend(
            await _fetch_text_column(
                connection,
                f"""
                SELECT work_item_id
                FROM execution_work_item_schedules
                WHERE {" OR ".join(schedule_clauses)}
                """,
                *schedule_args,
                column_name="work_item_id",
            )
        )

    return _unique(values)


async def _attempt_ids(
    *,
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    workflow_run_ids: tuple[str, ...],
    work_item_ids: tuple[str, ...],
) -> tuple[str, ...]:
    values: list[str] = []
    if workflow_run_ids and _has(
        columns,
        "workflow_runtime_timeline_entries",
        "workflow_run_id",
        "attempt_id",
    ):
        values.extend(
            await _fetch_text_column(
                connection,
                """
                SELECT attempt_id
                FROM workflow_runtime_timeline_entries
                WHERE workflow_run_id = ANY($1::text[])
                  AND attempt_id IS NOT NULL
                """,
                workflow_run_ids,
                column_name="attempt_id",
            )
        )
    if work_item_ids and _has(
        columns,
        "execution_work_item_attempts",
        "work_item_id",
        "attempt_id",
    ):
        values.extend(
            await _fetch_text_column(
                connection,
                """
                SELECT attempt_id
                FROM execution_work_item_attempts
                WHERE work_item_id = ANY($1::text[])
                """,
                work_item_ids,
                column_name="attempt_id",
            )
        )
    return _unique(values)


async def _llm_task_ids(
    *,
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    workflow_run_ids: tuple[str, ...],
    source_unit_refs: tuple[str, ...],
) -> tuple[str, ...]:
    values: list[str] = []
    if workflow_run_ids and _has(
        columns,
        "draft_claim_observation_provenance",
        "workflow_run_id",
        "llm_task_id",
    ):
        values.extend(
            await _fetch_text_column(
                connection,
                """
                SELECT llm_task_id
                FROM draft_claim_observation_provenance
                WHERE workflow_run_id = ANY($1::text[])
                """,
                workflow_run_ids,
                column_name="llm_task_id",
            )
        )
    if source_unit_refs and _has(
        columns,
        "draft_claim_observation_provenance",
        "source_unit_ref",
        "llm_task_id",
    ):
        values.extend(
            await _fetch_text_column(
                connection,
                """
                SELECT llm_task_id
                FROM draft_claim_observation_provenance
                WHERE source_unit_ref = ANY($1::text[])
                """,
                source_unit_refs,
                column_name="llm_task_id",
            )
        )
    return _unique(values)


async def _llm_attempt_ids(
    *,
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    workflow_run_ids: tuple[str, ...],
    source_unit_refs: tuple[str, ...],
) -> tuple[str, ...]:
    values: list[str] = []
    if workflow_run_ids and _has(
        columns,
        "draft_claim_observation_provenance",
        "workflow_run_id",
        "llm_attempt_id",
    ):
        values.extend(
            await _fetch_text_column(
                connection,
                """
                SELECT llm_attempt_id
                FROM draft_claim_observation_provenance
                WHERE workflow_run_id = ANY($1::text[])
                """,
                workflow_run_ids,
                column_name="llm_attempt_id",
            )
        )
    if source_unit_refs and _has(
        columns,
        "draft_claim_observation_provenance",
        "source_unit_ref",
        "llm_attempt_id",
    ):
        values.extend(
            await _fetch_text_column(
                connection,
                """
                SELECT llm_attempt_id
                FROM draft_claim_observation_provenance
                WHERE source_unit_ref = ANY($1::text[])
                """,
                source_unit_refs,
                column_name="llm_attempt_id",
            )
        )
    return _unique(values)


async def _delete_by_workflows(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    table_name: str,
    workflow_run_ids: tuple[str, ...],
) -> int:
    if not workflow_run_ids or not _has(columns, table_name, "workflow_run_id"):
        return 0
    status = await connection.execute(
        f"""
        DELETE FROM {_quote(table_name)}
        WHERE workflow_run_id = ANY($1::text[])
        """,
        workflow_run_ids,
    )
    return _delete_count(status)


async def _delete_by_source_or_workflow(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    *,
    table_name: str,
    source_document_ref: str,
    workflow_run_ids: tuple[str, ...],
) -> int:
    if table_name not in columns:
        return 0
    clauses: list[str] = []
    args: list[object] = []
    if _has(columns, table_name, "source_document_ref"):
        clauses.append(f"source_document_ref = ${len(args) + 1}")
        args.append(source_document_ref)
    if workflow_run_ids and _has(columns, table_name, "workflow_run_id"):
        clauses.append(f"workflow_run_id = ANY(${len(args) + 1}::text[])")
        args.append(workflow_run_ids)
    if not clauses:
        return 0
    status = await connection.execute(
        f"""
        DELETE FROM {_quote(table_name)}
        WHERE {" OR ".join(clauses)}
        """,
        *args,
    )
    return _delete_count(status)


async def _delete_runtime_embeddings(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if (
        not _has(
            columns,
            "knowledge_workbench_runtime_retrieval_entry_embeddings",
            "runtime_entry_id",
        )
        or not _has(
            columns,
            "knowledge_workbench_runtime_retrieval_entries",
            "runtime_entry_id",
            "fact_id",
        )
        or not _has(
            columns,
            "knowledge_workbench_canonical_facts",
            "fact_id",
            "project_id",
            "document_id",
        )
    ):
        return 0
    status = await connection.execute(
        """
        DELETE FROM knowledge_workbench_runtime_retrieval_entry_embeddings
        WHERE runtime_entry_id IN (
            SELECT re.runtime_entry_id
            FROM knowledge_workbench_runtime_retrieval_entries AS re
            JOIN knowledge_workbench_canonical_facts AS f
              ON f.fact_id = re.fact_id
            WHERE f.project_id = $1::uuid
              AND f.document_id = $2
        )
        """,
        refs.project_id,
        refs.source_document_ref,
    )
    return _delete_count(status)


async def _delete_runtime_entries(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if not _has(
        columns,
        "knowledge_workbench_runtime_retrieval_entries",
        "fact_id",
    ) or not _has(
        columns,
        "knowledge_workbench_canonical_facts",
        "fact_id",
        "project_id",
        "document_id",
    ):
        return 0
    status = await connection.execute(
        """
        DELETE FROM knowledge_workbench_runtime_retrieval_entries
        WHERE fact_id IN (
            SELECT fact_id
            FROM knowledge_workbench_canonical_facts
            WHERE project_id = $1::uuid
              AND document_id = $2
        )
        """,
        refs.project_id,
        refs.source_document_ref,
    )
    return _delete_count(status)


async def _delete_runtime_publications(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if not _has(
        columns, "knowledge_workbench_runtime_publications", "project_id", "source"
    ):
        return 0
    source_refs = _unique(
        [refs.source_document_ref, *refs.workflow_run_ids, *refs.processing_run_ids]
    )
    if not source_refs:
        return 0
    status = await connection.execute(
        """
        DELETE FROM knowledge_workbench_runtime_publications
        WHERE project_id = $1::uuid
          AND source = ANY($2::text[])
        """,
        refs.project_id,
        source_refs,
    )
    return _delete_count(status)


async def _delete_curation_items(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if not _has(columns, "draft_claim_curation_items", "workspace_ref"):
        return 0
    if refs.curation_workspace_refs:
        status = await connection.execute(
            """
            DELETE FROM draft_claim_curation_items
            WHERE workspace_ref = ANY($1::text[])
            """,
            refs.curation_workspace_refs,
        )
        return _delete_count(status)
    return await _delete_by_workflows(
        connection,
        columns,
        "draft_claim_curation_items",
        refs.workflow_run_ids,
    )


async def _delete_curation_workspaces(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    return await _delete_by_source_or_workflow(
        connection,
        columns,
        table_name="draft_claim_curation_workspaces",
        source_document_ref=refs.source_document_ref,
        workflow_run_ids=refs.workflow_run_ids,
    )


async def _delete_compaction_artifacts(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    total = 0
    for table_name in (
        "draft_claim_compaction_component_incompatibilities",
        "draft_claim_compaction_components",
        "draft_claim_compaction_comparisons",
        "draft_claim_compaction_rounds",
        "draft_claim_compaction_node_sources",
        "draft_claim_compaction_nodes",
        "draft_claim_compaction_batches",
        "draft_claim_compaction_group_members",
        "draft_claim_compaction_candidate_edges",
        "draft_claim_compaction_groups",
    ):
        if table_name == "draft_claim_compaction_node_sources":
            if not _has(columns, table_name, "node_ref") or not _has(
                columns, "draft_claim_compaction_nodes", "node_ref", "workflow_run_id"
            ):
                continue
            status = await connection.execute(
                """
                DELETE FROM draft_claim_compaction_node_sources
                WHERE node_ref IN (
                    SELECT node_ref
                    FROM draft_claim_compaction_nodes
                    WHERE workflow_run_id = ANY($1::text[])
                )
                """,
                refs.workflow_run_ids,
            )
            total += _delete_count(status)
            continue

        if table_name == "draft_claim_compaction_group_members":
            if not _has(columns, table_name, "group_ref") or not _has(
                columns, "draft_claim_compaction_groups", "group_ref"
            ):
                continue
            status = await connection.execute(
                """
                DELETE FROM draft_claim_compaction_group_members
                WHERE group_ref IN (
                    SELECT group_ref
                    FROM draft_claim_compaction_groups
                    WHERE workflow_run_id = ANY($1::text[])
                       OR source_document_ref = $2
                )
                """,
                refs.workflow_run_ids,
                refs.source_document_ref,
            )
            total += _delete_count(status)
            continue

        total += await _delete_by_source_or_workflow(
            connection,
            columns,
            table_name=table_name,
            source_document_ref=refs.source_document_ref,
            workflow_run_ids=refs.workflow_run_ids,
        )
    return total


async def _delete_cluster_artifacts(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    total = 0
    for table_name in (
        "draft_claim_cluster_previews",
        "draft_claim_clusters",
        "draft_claim_cluster_members",
    ):
        total += await _delete_by_source_or_workflow(
            connection,
            columns,
            table_name=table_name,
            source_document_ref=refs.source_document_ref,
            workflow_run_ids=refs.workflow_run_ids,
        )
    return total


async def _delete_possible_questions(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if not refs.observation_refs or not _has(
        columns, "draft_claim_observation_possible_questions", "observation_ref"
    ):
        return 0
    status = await connection.execute(
        """
        DELETE FROM draft_claim_observation_possible_questions
        WHERE observation_ref = ANY($1::text[])
        """,
        refs.observation_refs,
    )
    return _delete_count(status)


async def _delete_provenance(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if not _has(columns, "draft_claim_observation_provenance", "observation_ref"):
        return 0
    clauses: list[str] = []
    args: list[object] = []
    if refs.observation_refs:
        clauses.append(f"observation_ref = ANY(${len(args) + 1}::text[])")
        args.append(refs.observation_refs)
    if refs.workflow_run_ids and _has(
        columns, "draft_claim_observation_provenance", "workflow_run_id"
    ):
        clauses.append(f"workflow_run_id = ANY(${len(args) + 1}::text[])")
        args.append(refs.workflow_run_ids)
    if not clauses:
        return 0
    status = await connection.execute(
        f"""
        DELETE FROM draft_claim_observation_provenance
        WHERE {" OR ".join(clauses)}
        """,
        *args,
    )
    return _delete_count(status)


async def _delete_draft_claims(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if not _has(columns, "draft_claim_observations", "source_unit_ref"):
        return 0
    if refs.observation_refs:
        status = await connection.execute(
            """
            DELETE FROM draft_claim_observations
            WHERE observation_ref = ANY($1::text[])
            """,
            refs.observation_refs,
        )
        return _delete_count(status)
    if refs.source_unit_refs:
        status = await connection.execute(
            """
            DELETE FROM draft_claim_observations
            WHERE source_unit_ref = ANY($1::text[])
            """,
            refs.source_unit_refs,
        )
        return _delete_count(status)
    return 0


async def _delete_llm_artifacts(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    total = 0
    for table_name in (
        "llm_dispatch_attempt_artifacts",
        "llm_dispatch_attempt_outputs",
        "llm_dispatch_attempts",
        "llm_dispatch_tasks",
        "llm_runtime_provider_responses",
        "llm_runtime_dispatch_attempts",
        "llm_runtime_dispatch_tasks",
    ):
        if table_name not in columns:
            continue
        clauses: list[str] = []
        args: list[object] = []
        if refs.llm_attempt_ids and _has(columns, table_name, "llm_attempt_id"):
            clauses.append(f"llm_attempt_id = ANY(${len(args) + 1}::text[])")
            args.append(refs.llm_attempt_ids)
        if refs.llm_task_ids and _has(columns, table_name, "llm_task_id"):
            clauses.append(f"llm_task_id = ANY(${len(args) + 1}::text[])")
            args.append(refs.llm_task_ids)
        if refs.workflow_run_ids and _has(columns, table_name, "workflow_run_id"):
            clauses.append(f"workflow_run_id = ANY(${len(args) + 1}::text[])")
            args.append(refs.workflow_run_ids)
        if refs.attempt_ids and _has(columns, table_name, "attempt_id"):
            clauses.append(f"attempt_id = ANY(${len(args) + 1}::text[])")
            args.append(refs.attempt_ids)
        if clauses:
            status = await connection.execute(
                f"""
                DELETE FROM {_quote(table_name)}
                WHERE {" OR ".join(clauses)}
                """,
                *args,
            )
            total += _delete_count(status)
    return total


async def _delete_capacity_rows(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    total = 0
    for table_name in (
        "llm_capacity_observations",
        "llm_capacity_snapshots",
        "capacity_observations",
        "capacity_snapshots",
    ):
        total += await _delete_by_workflows(
            connection, columns, table_name, refs.workflow_run_ids
        )
    return total


async def _delete_execution_dispatches(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if not _has(columns, "execution_work_item_attempt_dispatches", "attempt_id"):
        return 0
    clauses: list[str] = []
    args: list[object] = []
    if refs.attempt_ids:
        clauses.append(f"attempt_id = ANY(${len(args) + 1}::text[])")
        args.append(refs.attempt_ids)
    if refs.work_item_ids and _has(
        columns, "execution_work_item_attempt_dispatches", "work_item_id"
    ):
        clauses.append(f"work_item_id = ANY(${len(args) + 1}::text[])")
        args.append(refs.work_item_ids)
    if not clauses:
        return 0
    status = await connection.execute(
        f"""
        DELETE FROM execution_work_item_attempt_dispatches
        WHERE {" OR ".join(clauses)}
        """,
        *args,
    )
    return _delete_count(status)


async def _delete_execution_attempts(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if not _has(columns, "execution_work_item_attempts", "attempt_id", "work_item_id"):
        return 0
    clauses: list[str] = []
    args: list[object] = []
    if refs.attempt_ids:
        clauses.append(f"attempt_id = ANY(${len(args) + 1}::text[])")
        args.append(refs.attempt_ids)
    if refs.work_item_ids:
        clauses.append(f"work_item_id = ANY(${len(args) + 1}::text[])")
        args.append(refs.work_item_ids)
    if not clauses:
        return 0
    status = await connection.execute(
        f"""
        DELETE FROM execution_work_item_attempts
        WHERE {" OR ".join(clauses)}
        """,
        *args,
    )
    return _delete_count(status)


async def _delete_execution_schedules(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if not refs.work_item_ids or not _has(
        columns, "execution_work_item_schedules", "work_item_id"
    ):
        return 0
    status = await connection.execute(
        """
        DELETE FROM execution_work_item_schedules
        WHERE work_item_id = ANY($1::text[])
        """,
        refs.work_item_ids,
    )
    return _delete_count(status)


async def _delete_execution_work_items(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if not refs.work_item_ids or not _has(
        columns, "execution_work_items", "work_item_id"
    ):
        return 0
    status = await connection.execute(
        """
        DELETE FROM execution_work_items
        WHERE work_item_id = ANY($1::text[])
        """,
        refs.work_item_ids,
    )
    return _delete_count(status)


async def _delete_timeline_entries(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if not _has(columns, "workflow_runtime_timeline_entries", "workflow_run_id"):
        return 0
    clauses: list[str] = []
    args: list[object] = []
    if refs.workflow_run_ids:
        clauses.append(f"workflow_run_id = ANY(${len(args) + 1}::text[])")
        args.append(refs.workflow_run_ids)
    if _has(columns, "workflow_runtime_timeline_entries", "source_ref"):
        clauses.append(f"source_ref = ${len(args) + 1}")
        args.append(refs.source_document_ref)
    if not clauses:
        return 0
    status = await connection.execute(
        f"""
        DELETE FROM workflow_runtime_timeline_entries
        WHERE {" OR ".join(clauses)}
        """,
        *args,
    )
    return _delete_count(status)


async def _delete_frontend_workflow_events(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if not _has(columns, "frontend_workflow_events", "project_id", "document_id"):
        return 0

    clauses: list[str] = ["(project_id = $1 AND document_id = $2)"]
    args: list[object] = [refs.project_id, refs.source_document_ref]

    if refs.workflow_run_ids and _has(
        columns,
        "frontend_workflow_events",
        "workflow_run_id",
    ):
        clauses.append(f"workflow_run_id = ANY(${len(args) + 1}::text[])")
        args.append(refs.workflow_run_ids)

    status = await connection.execute(
        f"""
        DELETE FROM frontend_workflow_events
        WHERE {" OR ".join(clauses)}
        """,
        *args,
    )
    return _delete_count(status)


async def _delete_saga_runs(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if not _has(
        columns,
        "knowledge_extraction_workflow_runs",
        "project_id",
        "source_document_ref",
    ):
        return 0
    status = await connection.execute(
        """
        DELETE FROM knowledge_extraction_workflow_runs
        WHERE project_id = $1
          AND source_document_ref = $2
        """,
        refs.project_id,
        refs.source_document_ref,
    )
    return _delete_count(status)


async def _delete_workbench_children(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    total = 0
    ordered_tables = (
        "knowledge_workbench_runtime_retrieval_entry_embeddings",
        "knowledge_workbench_runtime_retrieval_entries",
        "knowledge_workbench_registry_update_applications",
        "knowledge_workbench_fact_registry_applications",
        "knowledge_workbench_fact_relations",
        "knowledge_workbench_fact_mentions",
        "knowledge_workbench_fact_triples",
        "knowledge_workbench_canonical_facts",
        "knowledge_workbench_registry_snapshots",
        "knowledge_workbench_fact_registries",
        "knowledge_workbench_processing_node_artifacts",
        "knowledge_workbench_processing_node_runs",
        "knowledge_workbench_registry_application_queue",
        "knowledge_workbench_fact_registry_application_queue",
        "knowledge_workbench_section_batch_queue_items",
        "knowledge_workbench_parallel_section_batch_plans",
        "knowledge_workbench_processing_runs",
        "knowledge_workbench_document_sections",
    )
    for table_name in ordered_tables:
        if _has(columns, table_name, "project_id", "document_id"):
            status = await connection.execute(
                f"""
                DELETE FROM {_quote(table_name)}
                WHERE project_id = $1::uuid
                  AND document_id = $2
                """,
                refs.project_id,
                refs.source_document_ref,
            )
            total += _delete_count(status)
    return total


async def _delete_source_units(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if not _has(columns, "source_units", "document_ref"):
        return 0
    status = await connection.execute(
        """
        DELETE FROM source_units
        WHERE document_ref = $1
        """,
        refs.source_document_ref,
    )
    return _delete_count(status)


async def _delete_source_document(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if not _has(columns, "source_documents", "document_ref"):
        return 0
    status = await connection.execute(
        """
        DELETE FROM source_documents
        WHERE document_ref = $1
        """,
        refs.source_document_ref,
    )
    return _delete_count(status)


async def _delete_workbench_document(
    connection: asyncpg.Connection,
    columns: Mapping[str, frozenset[str]],
    refs: DocumentRunRefs,
) -> int:
    if not _has(columns, "knowledge_workbench_documents", "project_id", "document_id"):
        return 0
    status = await connection.execute(
        """
        DELETE FROM knowledge_workbench_documents
        WHERE project_id = $1::uuid
          AND document_id = $2
        """,
        refs.project_id,
        refs.source_document_ref,
    )
    return _delete_count(status)
