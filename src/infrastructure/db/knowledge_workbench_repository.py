from __future__ import annotations

import json
from collections.abc import Awaitable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Protocol, cast

from src.application.ports.knowledge_workbench import (
    KnowledgeWorkbenchFreshUploadRepositoryPort,
    KnowledgeWorkbenchRegistryApplicationRepositoryPort,
    KnowledgeWorkbenchRuntimePublicationRepositoryPort,
    KnowledgeWorkbenchSectionBatchQueueRepositoryPort,
    KnowledgeWorkbenchClaimObservationsRepositoryPort,
)
from src.domain.project_plane.knowledge_workbench import (
    ProcessingNodeArtifactType,
    ProcessingNodeName,
    ProcessingExhaustionTransition,
    DocumentSection,
    DocumentSectionStatus,
    JsonValue,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeDocumentUploadActorType,
    KnowledgeProcessingRun,
    ProcessingMethod,
    ParallelSectionBatchPlan,
    SectionBatchQueueItem,
    SectionBatchQueueItemStatus,
    ProcessingNodeArtifact,
    ProcessingNodeRun,
    ProcessingRunStatus,
    ProcessingTrigger,
    RegistrySnapshot,
    ResumePolicy,
    SourceType,
    ProcessingLifecycleTransition,
    RegistryApplicationQueueItem,
    RegistryApplicationQueueItemStatus,
    ParallelDrainWorkCounts,
    ParallelProcessingIntegrityCounts,
    RegistryUpdateApplication,
)


def _publish_ready_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _publish_ready_text(value: object) -> str:
    text = _publish_ready_optional_text(value)
    return "" if text is None else text


def _publish_ready_text_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return (value,)
        return _publish_ready_text_tuple(loaded)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(str(item) for item in value if str(item).strip())
    return (str(value),)


def _text_tuple_from_object(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    stripped = str(value).strip()
    return (stripped,) if stripped else ()


def _publish_ready_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    return datetime.fromisoformat(text)


class WorkbenchAsyncTransaction(Protocol):
    async def __aenter__(self) -> object: ...

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> object: ...


class _NoopAsyncTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


def _optional_workbench_transaction(connection: object) -> WorkbenchAsyncTransaction:
    transaction = getattr(connection, "transaction", None)
    if callable(transaction):
        return cast(WorkbenchAsyncTransaction, transaction())
    return _NoopAsyncTransaction()


class WorkbenchDbConnection(Protocol):
    def execute(self, query: str, *args: object) -> Awaitable[str]: ...

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


class KnowledgeWorkbenchRepository(
    KnowledgeWorkbenchFreshUploadRepositoryPort,
    KnowledgeWorkbenchRegistryApplicationRepositoryPort,
    KnowledgeWorkbenchRuntimePublicationRepositoryPort,
    KnowledgeWorkbenchSectionBatchQueueRepositoryPort,
    KnowledgeWorkbenchClaimObservationsRepositoryPort,
):
    def __init__(self, connection: WorkbenchDbConnection) -> None:
        self._connection = connection

    async def create_parallel_section_batch_plan(
        self,
        plan: ParallelSectionBatchPlan,
    ) -> None:
        lanes_payload = [
            {
                "lane_id": lane.lane_id,
                "lane_index": lane.lane_index,
                "section_ids": list(lane.section_ids),
            }
            for lane in plan.lanes
        ]

        async with _optional_workbench_transaction(self._connection):
            await self._connection.execute(
                """
                INSERT INTO knowledge_workbench_parallel_section_batch_plans (
                    batch_plan_id,
                    processing_run_id,
                    project_id,
                    document_id,
                    observed_registry_snapshot_id,
                    observed_registry_snapshot_sequence,
                    max_lanes,
                    lanes_payload,
                    queue_item_count
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
                ON CONFLICT (batch_plan_id) DO UPDATE SET
                    observed_registry_snapshot_id = EXCLUDED.observed_registry_snapshot_id,
                    observed_registry_snapshot_sequence = EXCLUDED.observed_registry_snapshot_sequence,
                    max_lanes = EXCLUDED.max_lanes,
                    lanes_payload = EXCLUDED.lanes_payload,
                    queue_item_count = EXCLUDED.queue_item_count
                """,
                plan.batch_plan_id,
                plan.processing_run_id,
                plan.project_id,
                plan.document_id,
                plan.observed_registry_snapshot_id,
                plan.observed_registry_snapshot_sequence,
                plan.max_lanes,
                self._json(self._json_value_from_db(lanes_payload)),
                len(plan.queue_items),
            )

            for item in plan.queue_items:
                await self._upsert_section_batch_queue_item(item)

    async def list_section_batch_queue_items(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> tuple[SectionBatchQueueItem, ...]:
        rows = await self._connection.fetch(
            """
            SELECT
                queue_item_id,
                batch_plan_id,
                processing_run_id,
                project_id,
                document_id,
                section_id,
                section_key,
                section_index,
                lane_id,
                lane_index,
                observed_registry_snapshot_id,
                observed_registry_snapshot_sequence,
                status,
                claimed_by_worker_id,
                lease_expires_at,
                claim_observations_node_run_id,
                registry_application_queue_item_id,
                error_kind,
                attempt_count,
                created_at,
                updated_at
            FROM knowledge_workbench_section_batch_queue_items
            WHERE project_id = $1
              AND document_id = $2
              AND processing_run_id = $3
            ORDER BY lane_index ASC, section_index ASC
            """,
            project_id,
            document_id,
            processing_run_id,
        )
        return tuple(self._section_batch_queue_item_from_row(row) for row in rows)

    async def restore_stale_registry_application_work_item_leases(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        now: datetime,
    ) -> int:
        result = await self._connection.execute(
            """
            UPDATE knowledge_workbench_fact_registry_application_queue
            SET status = 'ready',
                claimed_by_worker_id = NULL,
                lease_expires_at = NULL,
                updated_at = $4
            WHERE project_id = $1
              AND document_id = $2
              AND processing_run_id = $3
              AND status = 'leased'
              AND lease_expires_at <= $4
            """,
            project_id,
            document_id,
            processing_run_id,
            now,
        )
        parts = str(result).split()
        if len(parts) >= 2 and parts[-1].isdigit():
            return int(parts[-1])
        return 0

    async def lease_next_ready_registry_application_work_item(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        worker_id: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> RegistryApplicationQueueItem | None:
        async with _optional_workbench_transaction(self._connection):
            row = await self._connection.fetchrow(
                """
                WITH next_item AS (
                    SELECT queue_item_id
                    FROM knowledge_workbench_fact_registry_application_queue
                    WHERE project_id = $1
                      AND document_id = $2
                      AND processing_run_id = $3
                      AND status = 'ready'
                    ORDER BY observed_registry_snapshot_sequence ASC, created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE knowledge_workbench_fact_registry_application_queue AS item
                SET status = 'leased',
                    claimed_by_worker_id = $4,
                    lease_expires_at = $5,
                    attempt_count = item.attempt_count + 1,
                    updated_at = $6
                FROM next_item
                WHERE item.queue_item_id = next_item.queue_item_id
                RETURNING
                    item.queue_item_id,
                    item.processing_run_id,
                    item.project_id,
                    item.document_id,
                    item.section_id,
                    item.source_node_run_id,
                    item.observed_registry_snapshot_id,
                    item.observed_registry_snapshot_sequence,
                    item.claim_input_refs,
                    item.status,
                    item.claimed_by_worker_id,
                    item.lease_expires_at,
                    item.applied_registry_snapshot_id,
                    item.stale_at_registry_snapshot_id,
                    item.attempt_count,
                    item.created_at,
                    item.updated_at
                """,
                project_id,
                document_id,
                processing_run_id,
                worker_id,
                lease_expires_at,
                now,
            )
        if row is None:
            return None
        return self._registry_application_queue_item_from_row(row)

    async def update_registry_application_queue_item(
        self,
        item: RegistryApplicationQueueItem,
    ) -> None:
        await self._connection.execute(
            """
            UPDATE knowledge_workbench_fact_registry_application_queue
            SET status = $2,
                claimed_by_worker_id = $3,
                lease_expires_at = $4,
                applied_registry_snapshot_id = $5,
                stale_at_registry_snapshot_id = $6,
                attempt_count = $7,
                updated_at = $8
            WHERE queue_item_id = $1
            """,
            item.queue_item_id,
            item.status.value,
            item.claimed_by_worker_id,
            self._time(item.lease_expires_at),
            item.applied_registry_snapshot_id,
            item.stale_at_registry_snapshot_id,
            item.attempt_count,
            self._time(item.updated_at),
        )

    async def create_registry_application_queue_item(
        self,
        item: RegistryApplicationQueueItem,
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO knowledge_workbench_fact_registry_application_queue (
                queue_item_id,
                processing_run_id,
                project_id,
                document_id,
                section_id,
                source_node_run_id,
                observed_registry_snapshot_id,
                observed_registry_snapshot_sequence,
                claim_input_refs,
                status,
                claimed_by_worker_id,
                lease_expires_at,
                applied_registry_snapshot_id,
                stale_at_registry_snapshot_id,
                attempt_count,
                created_at,
                updated_at
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17
            )
            """,
            item.queue_item_id,
            item.processing_run_id,
            item.project_id,
            item.document_id,
            item.section_id,
            item.source_node_run_id,
            item.observed_registry_snapshot_id,
            item.observed_registry_snapshot_sequence,
            self._json(list(item.claim_input_refs)),
            item.status.value,
            item.claimed_by_worker_id,
            self._time(item.lease_expires_at),
            item.applied_registry_snapshot_id,
            item.stale_at_registry_snapshot_id,
            item.attempt_count,
            self._time(item.created_at),
            self._time(item.updated_at),
        )

    async def get_section_batch_queue_item_by_registry_application_queue_item_id(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        registry_application_queue_item_id: str,
    ) -> SectionBatchQueueItem | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                queue_item_id,
                batch_plan_id,
                processing_run_id,
                project_id,
                document_id,
                section_id,
                section_key,
                section_index,
                lane_id,
                lane_index,
                observed_registry_snapshot_id,
                observed_registry_snapshot_sequence,
                status,
                claimed_by_worker_id,
                lease_expires_at,
                claim_observations_node_run_id,
                registry_application_queue_item_id,
                error_kind,
                attempt_count,
                created_at,
                updated_at
            FROM knowledge_workbench_section_batch_queue_items
            WHERE project_id = $1
              AND document_id = $2
              AND processing_run_id = $3
              AND registry_application_queue_item_id = $4
            ORDER BY lane_index ASC, section_index ASC, queue_item_id ASC
            LIMIT 1
            """,
            project_id,
            document_id,
            processing_run_id,
            registry_application_queue_item_id,
        )
        if row is None:
            return None
        return self._section_batch_queue_item_from_row(row)

    async def update_section_batch_queue_item(
        self,
        item: SectionBatchQueueItem,
    ) -> None:
        await self._upsert_section_batch_queue_item(item)

    async def _upsert_section_batch_queue_item(
        self,
        item: SectionBatchQueueItem,
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO knowledge_workbench_section_batch_queue_items (
                queue_item_id,
                batch_plan_id,
                processing_run_id,
                project_id,
                document_id,
                section_id,
                section_key,
                section_index,
                lane_id,
                lane_index,
                observed_registry_snapshot_id,
                observed_registry_snapshot_sequence,
                status,
                claimed_by_worker_id,
                lease_expires_at,
                claim_observations_node_run_id,
                registry_application_queue_item_id,
                error_kind,
                attempt_count,
                created_at,
                updated_at
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19,
                COALESCE($20, now()), $21
            )
            ON CONFLICT (queue_item_id) DO UPDATE SET
                status = EXCLUDED.status,
                claimed_by_worker_id = EXCLUDED.claimed_by_worker_id,
                lease_expires_at = EXCLUDED.lease_expires_at,
                claim_observations_node_run_id = EXCLUDED.claim_observations_node_run_id,
                registry_application_queue_item_id = EXCLUDED.registry_application_queue_item_id,
                error_kind = EXCLUDED.error_kind,
                attempt_count = EXCLUDED.attempt_count,
                updated_at = COALESCE(EXCLUDED.updated_at, now())
            """,
            item.queue_item_id,
            item.batch_plan_id,
            item.processing_run_id,
            item.project_id,
            item.document_id,
            item.section_id,
            item.section_key,
            item.section_index,
            item.lane_id,
            item.lane_index,
            item.observed_registry_snapshot_id,
            item.observed_registry_snapshot_sequence,
            item.status.value,
            item.claimed_by_worker_id,
            item.lease_expires_at,
            item.claim_observations_node_run_id,
            item.registry_application_queue_item_id,
            item.error_kind,
            item.attempt_count,
            item.created_at,
            item.updated_at,
        )

    async def get_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> KnowledgeDocument | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                document_id,
                project_id,
                file_name,
                source_type,
                content_hash,
                upload_id,
                file_size_bytes,
                status,
                current_processing_run_id,
                uploaded_by_user_id,
                uploaded_by_actor_type,
                uploaded_by_actor_id,
                trusted_upload,
                last_error_kind,
                last_error_message,
                last_error_at,
                created_at,
                updated_at,
                deleted_at
            FROM knowledge_workbench_documents
            WHERE project_id = $1
              AND document_id = $2
            """,
            project_id,
            document_id,
        )
        if row is None:
            return None
        return KnowledgeDocument(
            document_id=str(row["document_id"]),
            project_id=str(row["project_id"]),
            file_name=str(row["file_name"]),
            source_type=SourceType(str(row["source_type"])),
            content_hash=_publish_ready_text(row["content_hash"]),
            upload_id=str(row["upload_id"]),
            file_size_bytes=self._int_from_db(row["file_size_bytes"]),
            status=KnowledgeDocumentStatus(str(row["status"])),
            current_processing_run_id=str(row["current_processing_run_id"])
            if row["current_processing_run_id"] is not None
            else None,
            uploaded_by_user_id=str(row["uploaded_by_user_id"])
            if row["uploaded_by_user_id"] is not None
            else None,
            uploaded_by_actor_type=KnowledgeDocumentUploadActorType(
                str(row["uploaded_by_actor_type"] or "unknown")
            ),
            uploaded_by_actor_id=str(row["uploaded_by_actor_id"])
            if row["uploaded_by_actor_id"] is not None
            else None,
            trusted_upload=bool(row["trusted_upload"]),
            last_error_kind=str(row["last_error_kind"])
            if row["last_error_kind"] is not None
            else None,
            last_error_message=str(row["last_error_message"])
            if row["last_error_message"] is not None
            else None,
            last_error_at=self._datetime_from_db(row["last_error_at"]),
            created_at=self._datetime_from_db(row["created_at"]),
            updated_at=self._datetime_from_db(row["updated_at"]),
            deleted_at=self._datetime_from_db(row["deleted_at"]),
        )

    async def get_document_section(
        self,
        *,
        project_id: str,
        document_id: str,
        section_id: str,
    ) -> DocumentSection | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                section_id,
                document_id,
                project_id,
                section_index,
                section_key,
                heading_path,
                title,
                raw_text,
                normalized_text,
                source_refs,
                source_chunk_indexes,
                parent_section_id,
                status,
                metadata
            FROM knowledge_workbench_document_sections
            WHERE project_id = $1
              AND document_id = $2
              AND section_id = $3
              AND status <> 'deleted'
            LIMIT 1
            """,
            project_id,
            document_id,
            section_id,
        )
        if row is None:
            return None
        return DocumentSection(
            section_id=str(row["section_id"]),
            document_id=str(row["document_id"]),
            project_id=str(row["project_id"]),
            section_index=self._int_from_db(row["section_index"]),
            section_key=str(row["section_key"]),
            heading_path=self._text_tuple_from_db(row["heading_path"]),
            title=str(row["title"]),
            raw_text=str(row["raw_text"]),
            normalized_text=str(row["normalized_text"]),
            source_refs=self._text_tuple_from_db(row["source_refs"]),
            source_chunk_indexes=self._int_tuple_from_db(row["source_chunk_indexes"]),
            parent_section_id=str(row["parent_section_id"])
            if row["parent_section_id"] is not None
            else None,
            status=DocumentSectionStatus(str(row["status"])),
            metadata=self._json_object_from_db(row["metadata"]),
        )

    async def list_document_sections(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> tuple[DocumentSection, ...]:
        rows = await self._connection.fetch(
            """
            SELECT
                section_id,
                document_id,
                project_id,
                section_index,
                section_key,
                heading_path,
                title,
                raw_text,
                normalized_text,
                source_refs,
                source_chunk_indexes,
                parent_section_id,
                status,
                metadata
            FROM knowledge_workbench_document_sections
            WHERE project_id = $1
              AND document_id = $2
              AND status <> 'deleted'
            ORDER BY section_index ASC
            """,
            project_id,
            document_id,
        )
        sections: list[DocumentSection] = []
        for row in rows:
            sections.append(
                DocumentSection(
                    section_id=str(row["section_id"]),
                    document_id=str(row["document_id"]),
                    project_id=str(row["project_id"]),
                    section_index=self._int_from_db(row["section_index"]),
                    section_key=str(row["section_key"]),
                    heading_path=self._text_tuple_from_db(row["heading_path"]),
                    title=str(row["title"]),
                    raw_text=str(row["raw_text"]),
                    normalized_text=str(row["normalized_text"]),
                    source_refs=self._text_tuple_from_db(row["source_refs"]),
                    source_chunk_indexes=self._int_tuple_from_db(
                        row["source_chunk_indexes"]
                    ),
                    parent_section_id=str(row["parent_section_id"])
                    if row["parent_section_id"] is not None
                    else None,
                    status=DocumentSectionStatus(str(row["status"])),
                    metadata=self._json_object_from_db(row["metadata"]),
                )
            )
        return tuple(sections)

    async def get_processing_run(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> KnowledgeProcessingRun | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                processing_run_id,
                project_id,
                document_id,
                processing_method,
                trigger,
                status,
                resume_policy,
                started_at,
                stopped_at,
                completed_at,
                deleted_at,
                active_elapsed_seconds,
                wall_elapsed_seconds,
                total_prompt_tokens,
                total_completion_tokens,
                total_tokens,
                total_llm_calls,
                last_error_kind,
                last_user_message,
                last_internal_error
            FROM knowledge_workbench_processing_runs
            WHERE project_id = $1
              AND document_id = $2
              AND processing_run_id = $3
            """,
            project_id,
            document_id,
            processing_run_id,
        )
        if row is None:
            return None
        return KnowledgeProcessingRun(
            processing_run_id=str(row["processing_run_id"]),
            project_id=str(row["project_id"]),
            document_id=str(row["document_id"]),
            processing_method=ProcessingMethod(str(row["processing_method"])),
            trigger=ProcessingTrigger(str(row["trigger"])),
            status=ProcessingRunStatus(str(row["status"])),
            resume_policy=ResumePolicy(str(row["resume_policy"])),
            started_at=self._datetime_from_db(row["started_at"]),
            stopped_at=self._datetime_from_db(row["stopped_at"]),
            completed_at=self._datetime_from_db(row["completed_at"]),
            deleted_at=self._datetime_from_db(row["deleted_at"]),
            active_elapsed_seconds=self._int_from_db(row["active_elapsed_seconds"]),
            wall_elapsed_seconds=self._int_from_db(row["wall_elapsed_seconds"]),
            total_prompt_tokens=self._int_from_db(row["total_prompt_tokens"]),
            total_completion_tokens=self._int_from_db(row["total_completion_tokens"]),
            total_tokens=self._int_from_db(row["total_tokens"]),
            total_llm_calls=self._int_from_db(row["total_llm_calls"]),
            last_error_kind=str(row["last_error_kind"])
            if row["last_error_kind"] is not None
            else None,
            last_user_message=str(row["last_user_message"])
            if row["last_user_message"] is not None
            else None,
            last_internal_error=str(row["last_internal_error"])
            if row["last_internal_error"] is not None
            else None,
        )

    async def get_latest_registry_snapshot(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> RegistrySnapshot | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                snapshot_id,
                registry_id,
                processing_run_id,
                project_id,
                document_id,
                after_section_id,
                after_node_run_id,
                sequence_number,
                entries_payload,
                relations_payload,
                entry_count,
                relation_count,
                claim_observation_count,
                update_count,
                created_at
            FROM knowledge_workbench_registry_snapshots
            WHERE project_id = $1
              AND document_id = $2
              AND processing_run_id = $3
            ORDER BY sequence_number DESC
            LIMIT 1
            """,
            project_id,
            document_id,
            processing_run_id,
        )
        if row is None:
            return None
        return RegistrySnapshot(
            snapshot_id=str(row["snapshot_id"]),
            registry_id=str(row["registry_id"]),
            processing_run_id=str(row["processing_run_id"]),
            project_id=str(row["project_id"]),
            document_id=str(row["document_id"]),
            after_section_id=str(row["after_section_id"])
            if row["after_section_id"] is not None
            else None,
            after_node_run_id=str(row["after_node_run_id"]),
            sequence_number=self._int_from_db(row["sequence_number"]),
            entries_payload=self._json_object_from_db(row["entries_payload"]),
            relations_payload=self._json_object_from_db(row["relations_payload"]),
            entry_count=self._int_from_db(row["entry_count"]),
            relation_count=self._int_from_db(row["relation_count"]),
            claim_observation_count=self._int_from_db(row["claim_observation_count"]),
            update_count=self._int_from_db(row["update_count"]),
            created_at=self._datetime_from_db(row["created_at"]),
        )

    async def persist_processing_cancellation_transition(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        transition: ProcessingLifecycleTransition,
    ) -> None:
        if not transition.may_proceed:
            raise ValueError("cannot persist rejected lifecycle transition")
        if transition.document_status_after is None:
            raise ValueError("cancellation transition missing document_status_after")
        if transition.processing_run_status_after is None:
            raise ValueError(
                "cancellation transition missing processing_run_status_after"
            )

        async with _optional_workbench_transaction(self._connection):
            await self._connection.execute(
                """
                UPDATE knowledge_workbench_documents
                SET status = $4,
                    updated_at = now()
                WHERE project_id = $1
                  AND document_id = $2
                  AND current_processing_run_id = $3
                """,
                project_id,
                document_id,
                processing_run_id,
                transition.document_status_after.value,
            )
            await self._connection.execute(
                """
                UPDATE knowledge_workbench_processing_runs
                SET status = $4,
                    resume_policy = $5,
                    last_error = $6,
                    updated_at = now()
                WHERE project_id = $1
                  AND document_id = $2
                  AND processing_run_id = $3
                """,
                project_id,
                document_id,
                processing_run_id,
                transition.processing_run_status_after.value,
                transition.resume_policy_after.value,
                transition.reason,
            )

    async def get_parallel_processing_integrity_counts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> ParallelProcessingIntegrityCounts:
        row = await self._connection.fetchrow(
            """
            SELECT
                (
                    SELECT COUNT(*)::int
                    FROM knowledge_workbench_document_sections AS section
                    WHERE section.project_id = $1
                      AND section.document_id = $2
                      AND section.status <> 'deleted'
                ) AS document_sections_total,
                (
                    SELECT COUNT(*)::int
                    FROM knowledge_workbench_section_batch_queue_items AS item
                    WHERE item.project_id = $1
                      AND item.document_id = $2
                      AND item.processing_run_id = $3
                ) AS section_queue_items_total,
                (
                    SELECT COUNT(*)::int
                    FROM knowledge_workbench_processing_node_artifacts AS artifact
                    JOIN knowledge_workbench_processing_node_runs AS node
                      ON node.node_run_id = artifact.node_run_id
                     AND node.processing_run_id = artifact.processing_run_id
                     AND node.project_id = artifact.project_id
                     AND node.document_id = artifact.document_id
                    WHERE artifact.project_id = $1
                      AND artifact.document_id = $2
                      AND artifact.processing_run_id = $3
                      AND artifact.artifact_type = 'parsed_llm_output'
                      AND node.node_name = 'faq_surface_claim_observations'
                ) AS claim_observation_artifacts_total,
                (
                    SELECT COUNT(*)::int
                    FROM knowledge_workbench_processing_node_artifacts AS artifact
                    JOIN knowledge_workbench_processing_node_runs AS node
                      ON node.node_run_id = artifact.node_run_id
                     AND node.processing_run_id = artifact.processing_run_id
                     AND node.project_id = artifact.project_id
                     AND node.document_id = artifact.document_id
                    WHERE artifact.project_id = $1
                      AND artifact.document_id = $2
                      AND artifact.processing_run_id = $3
                      AND artifact.artifact_type = 'parsed_llm_output'
                      AND node.node_name = 'faq_surface_registry_merge'
                ) AS canonicalization_artifacts_total
            """,
            project_id,
            document_id,
            processing_run_id,
        )
        if row is None:
            return ParallelProcessingIntegrityCounts(
                document_sections_total=0,
                section_queue_items_total=0,
                claim_observation_artifacts_total=0,
                canonicalization_artifacts_total=0,
            )

        return ParallelProcessingIntegrityCounts(
            document_sections_total=self._int_from_db(row["document_sections_total"]),
            section_queue_items_total=self._int_from_db(
                row["section_queue_items_total"]
            ),
            claim_observation_artifacts_total=self._int_from_db(
                row["claim_observation_artifacts_total"]
            ),
            canonicalization_artifacts_total=self._int_from_db(
                row["canonicalization_artifacts_total"]
            ),
        )

    async def restore_stale_section_work_item_leases(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        now: datetime,
    ) -> int:
        result = await self._connection.execute(
            """
            UPDATE knowledge_workbench_section_batch_queue_items
            SET status = 'ready',
                claimed_by_worker_id = NULL,
                lease_expires_at = NULL,
                updated_at = $4
            WHERE project_id = $1
              AND document_id = $2
              AND processing_run_id = $3
              AND status = 'leased'
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at <= $4
            """,
            project_id,
            document_id,
            processing_run_id,
            now,
        )
        return self._row_count_from_execute_result(result)

    async def lease_next_ready_section_work_item(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        worker_id: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> SectionBatchQueueItem | None:
        async with _optional_workbench_transaction(self._connection):
            row = await self._connection.fetchrow(
                """
                WITH next_item AS (
                    SELECT queue_item_id
                    FROM knowledge_workbench_section_batch_queue_items
                    WHERE project_id = $1
                      AND document_id = $2
                      AND processing_run_id = $3
                      AND status = 'ready'
                    ORDER BY lane_index ASC, section_index ASC, queue_item_id ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE knowledge_workbench_section_batch_queue_items AS item
                SET status = 'leased',
                    claimed_by_worker_id = $4,
                    lease_expires_at = $5,
                    attempt_count = item.attempt_count + 1,
                    updated_at = $6
                FROM next_item
                WHERE item.queue_item_id = next_item.queue_item_id
                RETURNING
                    item.queue_item_id,
                    item.batch_plan_id,
                    item.processing_run_id,
                    item.project_id,
                    item.document_id,
                    item.section_id,
                    item.section_key,
                    item.section_index,
                    item.lane_id,
                    item.lane_index,
                    item.observed_registry_snapshot_id,
                    item.observed_registry_snapshot_sequence,
                    item.status,
                    item.claimed_by_worker_id,
                    item.lease_expires_at,
                    item.claim_observations_node_run_id,
                    item.registry_application_queue_item_id,
                    item.error_kind,
                    item.attempt_count,
                    item.created_at,
                    item.updated_at
                """,
                project_id,
                document_id,
                processing_run_id,
                worker_id,
                lease_expires_at,
                now,
            )

        if row is None:
            return None

        return self._section_batch_queue_item_from_row(row)

    def _section_batch_queue_item_from_row(
        self,
        row: Mapping[str, object],
    ) -> SectionBatchQueueItem:
        return SectionBatchQueueItem(
            queue_item_id=str(row["queue_item_id"]),
            batch_plan_id=str(row["batch_plan_id"]),
            processing_run_id=str(row["processing_run_id"]),
            project_id=str(row["project_id"]),
            document_id=str(row["document_id"]),
            section_id=str(row["section_id"]),
            section_key=str(row["section_key"]),
            section_index=self._int_from_db(row["section_index"]),
            lane_id=str(row["lane_id"]),
            lane_index=self._int_from_db(row["lane_index"]),
            observed_registry_snapshot_id=str(row["observed_registry_snapshot_id"]),
            observed_registry_snapshot_sequence=self._int_from_db(
                row["observed_registry_snapshot_sequence"]
            ),
            status=SectionBatchQueueItemStatus(str(row["status"])),
            claimed_by_worker_id=self._optional_text(row["claimed_by_worker_id"]),
            lease_expires_at=self._datetime_from_db(row["lease_expires_at"]),
            claim_observations_node_run_id=self._optional_text(
                row["claim_observations_node_run_id"]
            ),
            registry_application_queue_item_id=self._optional_text(
                row["registry_application_queue_item_id"]
            ),
            error_kind=self._optional_text(row["error_kind"]),
            attempt_count=self._int_from_db(row["attempt_count"]),
            created_at=self._datetime_from_db(row["created_at"]),
            updated_at=self._datetime_from_db(row["updated_at"]),
        )

    def _row_count_from_execute_result(self, result: object) -> int:
        parts = str(result).split()
        if len(parts) >= 2 and parts[-1].isdigit():
            return int(parts[-1])
        return 0

    def _optional_text(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    async def create_document(self, document: KnowledgeDocument) -> None:
        await self._connection.execute(
            """
            INSERT INTO knowledge_workbench_documents (
                document_id,
                project_id,
                file_name,
                source_type,
                content_hash,
                upload_id,
                file_size_bytes,
                status,
                current_processing_run_id,
                uploaded_by_user_id,
                uploaded_by_actor_type,
                uploaded_by_actor_id,
                trusted_upload,
                last_error_kind,
                last_error_message,
                last_error_at,
                created_at,
                updated_at,
                deleted_at
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
            """,
            document.document_id,
            document.project_id,
            document.file_name,
            document.source_type.value,
            document.content_hash,
            document.upload_id,
            document.file_size_bytes,
            document.status.value,
            document.current_processing_run_id,
            document.uploaded_by_user_id,
            document.uploaded_by_actor_type.value,
            document.uploaded_by_actor_id,
            document.trusted_upload,
            document.last_error_kind,
            document.last_error_message,
            document.last_error_at,
            self._time(document.created_at),
            self._time(document.updated_at),
            document.deleted_at,
        )

    async def create_document_sections(
        self,
        sections: tuple[DocumentSection, ...],
    ) -> None:
        for section in sections:
            await self._connection.execute(
                """
                INSERT INTO knowledge_workbench_document_sections (
                    section_id,
                    document_id,
                    project_id,
                    section_index,
                    section_key,
                    heading_path,
                    title,
                    raw_text,
                    normalized_text,
                    source_refs,
                    source_chunk_indexes,
                    parent_section_id,
                    status,
                    metadata
                )
                VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9,$10::jsonb,$11::jsonb,$12,$13,$14::jsonb)
                """,
                section.section_id,
                section.document_id,
                section.project_id,
                section.section_index,
                section.section_key,
                self._json(list(section.heading_path)),
                section.title,
                section.raw_text,
                section.normalized_text,
                self._json(list(section.source_refs)),
                self._json(list(section.source_chunk_indexes)),
                section.parent_section_id,
                section.status.value,
                self._json(section.metadata),
            )

    async def persist_processing_exhaustion_transition(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        transition: ProcessingExhaustionTransition,
    ) -> None:
        async with _optional_workbench_transaction(self._connection):
            await self._connection.execute(
                """
                    UPDATE knowledge_workbench_documents
                    SET status = $4,
                        last_error_kind = $5,
                        last_error_message = $6,
                        last_error_at = now(),
                        updated_at = now()
                    WHERE project_id = $1::uuid
                      AND document_id = $2::uuid
                      AND current_processing_run_id = $3
                    """,
                project_id,
                document_id,
                processing_run_id,
                transition.document_status_after.value,
                transition.error_kind,
                transition.error_message_user,
            )

            await self._connection.execute(
                """
                UPDATE knowledge_workbench_processing_runs
                    SET status = $4,
                        resume_policy = $5,
                        last_error = $6,
                        last_error_kind = $7,
                        last_internal_error = $8,
                        updated_at = now()
                    WHERE project_id = $1::uuid
                      AND document_id = $2::uuid
                      AND processing_run_id = $3
                    """,
                project_id,
                document_id,
                processing_run_id,
                transition.processing_run_status_after.value,
                transition.resume_policy_after.value,
                transition.error_message_user,
                transition.error_kind,
                transition.error_message_internal,
            )

    async def create_processing_run(self, run: KnowledgeProcessingRun) -> None:
        await self._connection.execute(
            """
            INSERT INTO knowledge_workbench_processing_runs (
                processing_run_id,
                project_id,
                document_id,
                processing_method,
                trigger,
                status,
                resume_policy,
                started_at,
                stopped_at,
                completed_at,
                deleted_at,
                active_elapsed_seconds,
                wall_elapsed_seconds,
                total_prompt_tokens,
                total_completion_tokens,
                total_tokens,
                total_llm_calls,
                last_error_kind,
                last_error_report_id,
                last_user_message,
                last_internal_error
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)
            """,
            run.processing_run_id,
            run.project_id,
            run.document_id,
            run.processing_method.value,
            run.trigger.value,
            run.status.value,
            run.resume_policy.value,
            run.started_at,
            run.stopped_at,
            run.completed_at,
            run.deleted_at,
            run.active_elapsed_seconds,
            run.wall_elapsed_seconds,
            run.total_prompt_tokens,
            run.total_completion_tokens,
            run.total_tokens,
            run.total_llm_calls,
            run.last_error_kind,
            run.last_error_report_id,
            run.last_user_message,
            run.last_internal_error,
        )

    async def create_processing_node_run(self, node_run: ProcessingNodeRun) -> None:
        await self._connection.execute(
            """
            INSERT INTO knowledge_workbench_processing_node_runs (
                node_run_id,
                processing_run_id,
                project_id,
                document_id,
                section_id,
                node_name,
                node_kind,
                status,
                input_snapshot_id,
                output_snapshot_id,
                started_at,
                completed_at,
                duration_ms,
                model_name,
                model_provider,
                groq_key_slot,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                error_kind,
                error_message_user,
                error_message_internal
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22)
            """,
            node_run.node_run_id,
            node_run.processing_run_id,
            node_run.project_id,
            node_run.document_id,
            node_run.section_id,
            node_run.node_name.value,
            node_run.node_kind.value,
            node_run.status.value,
            node_run.input_snapshot_id,
            node_run.output_snapshot_id,
            node_run.started_at,
            node_run.completed_at,
            node_run.duration_ms,
            node_run.model_name,
            node_run.model_provider,
            node_run.groq_key_slot,
            node_run.prompt_tokens,
            node_run.completion_tokens,
            node_run.total_tokens,
            node_run.error_kind,
            node_run.error_message_user,
            node_run.error_message_internal,
        )

    async def replace_canonical_facts_for_snapshot(
        self,
        *,
        snapshot: RegistrySnapshot,
        canonical_facts: tuple[Mapping[str, object], ...],
    ) -> int:
        async with _optional_workbench_transaction(self._connection):
            await self._connection.execute(
                """
                DELETE FROM knowledge_workbench_canonical_facts
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND processing_run_id = $3
                  AND registry_id = $4
                """,
                snapshot.project_id,
                snapshot.document_id,
                snapshot.processing_run_id,
                snapshot.registry_id,
            )

            for fact in canonical_facts:
                await self._connection.execute(
                    """
                    INSERT INTO knowledge_workbench_canonical_facts (
                        fact_id,
                        registry_id,
                        project_id,
                        document_id,
                        processing_run_id,
                        claim,
                        claim_kind,
                        granularity,
                        possible_questions,
                        scope,
                        exclusion_scope,
                        derived_fact_notes,
                        status,
                        updated_at
                    )
                    VALUES (
                        $1, $2, $3::uuid, $4, $5, $6, $7, $8,
                        $9::jsonb, $10, $11, $12::jsonb, $13, now()
                    )
                    ON CONFLICT (fact_id) DO UPDATE SET
                        registry_id = EXCLUDED.registry_id,
                        project_id = EXCLUDED.project_id,
                        document_id = EXCLUDED.document_id,
                        processing_run_id = EXCLUDED.processing_run_id,
                        claim = EXCLUDED.claim,
                        claim_kind = EXCLUDED.claim_kind,
                        granularity = EXCLUDED.granularity,
                        possible_questions = EXCLUDED.possible_questions,
                        scope = EXCLUDED.scope,
                        exclusion_scope = EXCLUDED.exclusion_scope,
                        derived_fact_notes = EXCLUDED.derived_fact_notes,
                        status = EXCLUDED.status,
                        updated_at = now()
                    """,
                    fact["fact_id"],
                    fact["registry_id"],
                    fact["project_id"],
                    fact["document_id"],
                    fact["processing_run_id"],
                    fact["claim"],
                    fact["claim_kind"],
                    fact["granularity"],
                    self._json(
                        list(_text_tuple_from_object(fact["possible_questions"]))
                    ),
                    fact["scope"],
                    fact["exclusion_scope"],
                    self._json(self._json_value_from_db(fact["derived_fact_notes"])),
                    fact["status"],
                )

        return len(canonical_facts)

    async def replace_fact_mentions_for_snapshot(
        self,
        *,
        snapshot: RegistrySnapshot,
        fact_mentions: tuple[Mapping[str, object], ...],
    ) -> int:
        async with _optional_workbench_transaction(self._connection):
            await self._connection.execute(
                """
                DELETE FROM knowledge_workbench_fact_mentions
                WHERE registry_id = $1
                  AND fact_id IN (
                    SELECT fact_id
                    FROM knowledge_workbench_canonical_facts
                    WHERE project_id = $2::uuid
                      AND document_id = $3
                      AND processing_run_id = $4
                      AND registry_id = $1
                  )
                """,
                snapshot.registry_id,
                snapshot.project_id,
                snapshot.document_id,
                snapshot.processing_run_id,
            )

            for mention in fact_mentions:
                await self._connection.execute(
                    """
                    INSERT INTO knowledge_workbench_fact_mentions (
                        mention_id,
                        fact_id,
                        registry_id,
                        source_section_id,
                        source_section_ref,
                        source_local_ref,
                        evidence_block,
                        mention_relation
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (mention_id) DO UPDATE SET
                        fact_id = EXCLUDED.fact_id,
                        registry_id = EXCLUDED.registry_id,
                        source_section_id = EXCLUDED.source_section_id,
                        source_section_ref = EXCLUDED.source_section_ref,
                        source_local_ref = EXCLUDED.source_local_ref,
                        evidence_block = EXCLUDED.evidence_block,
                        mention_relation = EXCLUDED.mention_relation
                    """,
                    mention["mention_id"],
                    mention["fact_id"],
                    mention["registry_id"],
                    mention["source_section_id"],
                    mention["source_section_ref"],
                    mention["source_local_ref"],
                    mention["evidence_block"],
                    mention["mention_relation"],
                )

        return len(fact_mentions)

    async def replace_fact_relations_for_snapshot(
        self,
        *,
        snapshot: RegistrySnapshot,
        fact_relations: tuple[Mapping[str, object], ...],
    ) -> int:
        async with _optional_workbench_transaction(self._connection):
            await self._connection.execute(
                """
                DELETE FROM knowledge_workbench_fact_relations
                WHERE registry_id = $1
                """,
                snapshot.registry_id,
            )

            for relation in fact_relations:
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
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (relation_id) DO UPDATE SET
                        registry_id = EXCLUDED.registry_id,
                        source_fact_id = EXCLUDED.source_fact_id,
                        target_fact_id = EXCLUDED.target_fact_id,
                        relation = EXCLUDED.relation,
                        reason = EXCLUDED.reason
                    """,
                    relation["relation_id"],
                    relation["registry_id"],
                    relation["source_fact_id"],
                    relation["target_fact_id"],
                    relation["relation"],
                    relation["reason"],
                )

        return len(fact_relations)

    async def replace_surfaces_for_snapshot(
        self,
        *,
        snapshot: RegistrySnapshot,
        surfaces: tuple[Mapping[str, object], ...],
    ) -> int:
        async with _optional_workbench_transaction(self._connection):
            await self._connection.execute(
                """
                DELETE FROM knowledge_workbench_surfaces
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND fact_id IN (
                    SELECT fact_id
                    FROM knowledge_workbench_canonical_facts
                    WHERE project_id = $1::uuid
                      AND document_id = $2
                      AND processing_run_id = $3
                      AND registry_id = $4
                  )
                """,
                snapshot.project_id,
                snapshot.document_id,
                snapshot.processing_run_id,
                snapshot.registry_id,
            )

            for surface in surfaces:
                await self._connection.execute(
                    """
                    INSERT INTO knowledge_workbench_surfaces (
                        surface_id,
                        project_id,
                        document_id,
                        fact_id,
                        title,
                        claim,
                        question_variants,
                        answer,
                        short_answer,
                        answer_scope,
                        retrieval_scope,
                        exclusion_scope,
                        evidence_quotes,
                        source_refs,
                        source_section_ids,
                        claim_kind,
                        status,
                        curation_state,
                        updated_at
                    )
                    VALUES (
                        $1, $2::uuid, $3, $4, $5, $6, $7::jsonb, $8, $9,
                        $10, $11, $12, $13::jsonb, $14::jsonb, $15::jsonb,
                        $16, $17, $18, now()
                    )
                    ON CONFLICT (surface_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        claim = EXCLUDED.claim,
                        question_variants = EXCLUDED.question_variants,
                        answer = EXCLUDED.answer,
                        short_answer = EXCLUDED.short_answer,
                        answer_scope = EXCLUDED.answer_scope,
                        retrieval_scope = EXCLUDED.retrieval_scope,
                        exclusion_scope = EXCLUDED.exclusion_scope,
                        evidence_quotes = EXCLUDED.evidence_quotes,
                        source_refs = EXCLUDED.source_refs,
                        source_section_ids = EXCLUDED.source_section_ids,
                        claim_kind = EXCLUDED.claim_kind,
                        status = EXCLUDED.status,
                        curation_state = EXCLUDED.curation_state,
                        updated_at = now()
                    """,
                    surface["surface_id"],
                    surface["project_id"],
                    surface["document_id"],
                    surface["fact_id"],
                    surface["title"],
                    surface["claim"],
                    self._json(
                        list(_text_tuple_from_object(surface["question_variants"]))
                    ),
                    surface["answer"],
                    surface["short_answer"],
                    surface["answer_scope"],
                    surface["retrieval_scope"],
                    surface["exclusion_scope"],
                    self._json(
                        list(_text_tuple_from_object(surface["evidence_quotes"]))
                    ),
                    self._json(list(_text_tuple_from_object(surface["source_refs"]))),
                    self._json(
                        list(_text_tuple_from_object(surface["source_section_ids"]))
                    ),
                    surface["claim_kind"],
                    surface["status"],
                    surface["curation_state"],
                )

        return len(surfaces)

    async def create_processing_node_artifact(
        self,
        artifact: ProcessingNodeArtifact,
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO knowledge_workbench_processing_node_artifacts (
                artifact_id,
                node_run_id,
                processing_run_id,
                project_id,
                document_id,
                section_id,
                artifact_type,
                payload_json,
                schema_version,
                metadata,
                created_at
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10::jsonb,$11)
            """,
            artifact.artifact_id,
            artifact.node_run_id,
            artifact.processing_run_id,
            artifact.project_id,
            artifact.document_id,
            artifact.section_id,
            artifact.artifact_type.value,
            self._json(artifact.payload_json),
            artifact.schema_version,
            self._json(artifact.metadata),
            self._time(artifact.created_at),
        )

    async def get_processing_node_artifact_by_node_run_id_and_type(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        node_run_id: str,
        artifact_type: ProcessingNodeArtifactType,
    ) -> ProcessingNodeArtifact | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                artifact_id,
                node_run_id,
                processing_run_id,
                project_id,
                document_id,
                section_id,
                artifact_type,
                payload_json,
                schema_version,
                metadata,
                created_at
            FROM knowledge_workbench_processing_node_artifacts
            WHERE project_id = $1
              AND document_id = $2
              AND processing_run_id = $3
              AND node_run_id = $4
              AND artifact_type = $5
            ORDER BY created_at DESC
            LIMIT 1
            """,
            project_id,
            document_id,
            processing_run_id,
            node_run_id,
            artifact_type.value,
        )
        if row is None:
            return None

        return ProcessingNodeArtifact(
            artifact_id=str(row["artifact_id"]),
            node_run_id=str(row["node_run_id"]),
            processing_run_id=str(row["processing_run_id"]),
            project_id=str(row["project_id"]),
            document_id=str(row["document_id"]),
            section_id=(
                str(row["section_id"]) if row["section_id"] is not None else None
            ),
            artifact_type=ProcessingNodeArtifactType(str(row["artifact_type"])),
            payload_json=self._json_object_from_db(row["payload_json"]),
            schema_version=self._int_from_db(row["schema_version"]),
            created_at=self._datetime_from_db(row["created_at"]),
            metadata=self._json_object_from_db(row["metadata"]),
        )

    async def list_claim_observation_parsed_artifacts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> tuple[ProcessingNodeArtifact, ...]:
        rows = await self._connection.fetch(
            """
            SELECT
                artifact.artifact_id,
                artifact.node_run_id,
                artifact.processing_run_id,
                artifact.project_id,
                artifact.document_id,
                artifact.section_id,
                artifact.artifact_type,
                artifact.payload_json,
                artifact.schema_version,
                artifact.metadata,
                artifact.created_at
            FROM knowledge_workbench_processing_node_artifacts AS artifact
            JOIN knowledge_workbench_processing_node_runs AS node
              ON node.node_run_id = artifact.node_run_id
             AND node.processing_run_id = artifact.processing_run_id
             AND node.project_id = artifact.project_id
             AND node.document_id = artifact.document_id
            LEFT JOIN knowledge_workbench_document_sections AS section
              ON section.section_id = artifact.section_id
             AND section.document_id = artifact.document_id
             AND section.project_id = artifact.project_id
            WHERE artifact.project_id = $1::uuid
              AND artifact.document_id = $2
              AND artifact.processing_run_id = $3
              AND node.node_name = $4
              AND artifact.artifact_type = $5
            ORDER BY
                section.section_index NULLS LAST,
                artifact.created_at ASC,
                artifact.artifact_id ASC
            """,
            project_id,
            document_id,
            processing_run_id,
            ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS.value,
            ProcessingNodeArtifactType.PARSED_LLM_OUTPUT.value,
        )
        return tuple(
            ProcessingNodeArtifact(
                artifact_id=str(row["artifact_id"]),
                node_run_id=str(row["node_run_id"]),
                processing_run_id=str(row["processing_run_id"]),
                project_id=str(row["project_id"]),
                document_id=str(row["document_id"]),
                section_id=(
                    str(row["section_id"]) if row["section_id"] is not None else None
                ),
                artifact_type=ProcessingNodeArtifactType(str(row["artifact_type"])),
                payload_json=self._json_object_from_db(row["payload_json"]),
                schema_version=self._int_from_db(row["schema_version"]),
                metadata=self._json_object_from_db(row["metadata"]),
                created_at=self._datetime_from_db(row["created_at"]),
            )
            for row in rows
        )

    async def sync_processing_run_llm_usage_totals(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> None:
        await self._connection.execute(
            """
            UPDATE knowledge_workbench_processing_runs AS run
            SET
                total_prompt_tokens = usage.total_prompt_tokens,
                total_completion_tokens = usage.total_completion_tokens,
                total_tokens = usage.total_tokens,
                total_llm_calls = usage.total_llm_calls,
                updated_at = now()
            FROM (
                SELECT
                    COALESCE(SUM(node.prompt_tokens), 0)::int AS total_prompt_tokens,
                    COALESCE(SUM(node.completion_tokens), 0)::int AS total_completion_tokens,
                    COALESCE(SUM(node.total_tokens), 0)::int AS total_tokens,
                    COUNT(*) FILTER (
                        WHERE node.node_kind = 'llm_prompt'
                          AND node.status = 'completed'
                          AND (
                              node.model_provider IS NOT NULL
                              OR node.prompt_tokens > 0
                              OR node.completion_tokens > 0
                              OR node.total_tokens > 0
                          )
                    )::int AS total_llm_calls
                FROM knowledge_workbench_processing_node_runs AS node
                WHERE node.project_id = $1::uuid
                  AND node.document_id = $2
                  AND node.processing_run_id = $3
                  AND node.node_kind = 'llm_prompt'
                  AND node.status = 'completed'
            ) AS usage
            WHERE run.project_id = $1::uuid
              AND run.document_id = $2
              AND run.processing_run_id = $3
              AND run.deleted_at IS NULL
            """,
            project_id,
            document_id,
            processing_run_id,
        )

    async def persist_claim_observations_generation_error_lifecycle(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        document_status: object,
        processing_run_status: object,
        resume_policy: object,
        error_kind: str,
        error_report_id: str,
        user_message: str,
        internal_error: str,
        node_run_id: str | None = None,
    ) -> None:
        document_status_value = getattr(document_status, "value", str(document_status))
        processing_run_status_value = getattr(
            processing_run_status,
            "value",
            str(processing_run_status),
        )
        resume_policy_value = getattr(resume_policy, "value", str(resume_policy))

        async with _optional_workbench_transaction(self._connection):
            await self._connection.execute(
                """
                UPDATE knowledge_workbench_documents
                SET status = $4,
                    last_error_kind = $5,
                    last_error_message = $6,
                    last_error_at = now(),
                    updated_at = now()
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND current_processing_run_id = $3
                """,
                project_id,
                document_id,
                processing_run_id,
                document_status_value,
                error_kind,
                user_message,
            )
            await self._connection.execute(
                """
                UPDATE knowledge_workbench_processing_runs
                SET status = $4,
                    resume_policy = $5,
                    stopped_at = COALESCE(stopped_at, now()),
                    last_error_kind = $6,
                    last_error_report_id = $7,
                    last_user_message = $8,
                    last_internal_error = $9,
                    updated_at = now()
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND processing_run_id = $3
                  AND deleted_at IS NULL
                """,
                project_id,
                document_id,
                processing_run_id,
                processing_run_status_value,
                resume_policy_value,
                error_kind,
                error_report_id,
                user_message,
                internal_error,
            )

    async def persist_registry_merge_generation_error_lifecycle(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        node_run_id: str,
        document_status: KnowledgeDocumentStatus,
        processing_run_status: ProcessingRunStatus,
        resume_policy: ResumePolicy,
        error_kind: str,
        user_message: str,
        internal_error: str,
    ) -> None:
        await self.persist_claim_observations_generation_error_lifecycle(
            project_id=project_id,
            document_id=document_id,
            processing_run_id=processing_run_id,
            node_run_id=node_run_id,
            document_status=document_status,
            processing_run_status=processing_run_status,
            resume_policy=resume_policy,
            error_kind=error_kind,
            error_report_id=node_run_id,
            user_message=user_message,
            internal_error=internal_error,
        )

    async def persist_final_reconciliation_generation_error_lifecycle(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        node_run_id: str,
        document_status: KnowledgeDocumentStatus,
        processing_run_status: ProcessingRunStatus,
        resume_policy: ResumePolicy,
        error_kind: str,
        user_message: str,
        internal_error: str,
    ) -> None:
        await self.persist_claim_observations_generation_error_lifecycle(
            project_id=project_id,
            document_id=document_id,
            processing_run_id=processing_run_id,
            node_run_id=node_run_id,
            document_status=document_status,
            processing_run_status=processing_run_status,
            resume_policy=resume_policy,
            error_kind=error_kind,
            error_report_id=node_run_id,
            user_message=user_message,
            internal_error=internal_error,
        )

    async def create_registry_snapshot(self, snapshot: RegistrySnapshot) -> None:
        await self._connection.execute(
            """
            INSERT INTO knowledge_workbench_registry_snapshots (
                snapshot_id,
                registry_id,
                processing_run_id,
                project_id,
                document_id,
                after_section_id,
                after_node_run_id,
                sequence_number,
                entries_payload,
                relations_payload,
                entry_count,
                relation_count,
                claim_observation_count,
                update_count,
                created_at
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10::jsonb,$11,$12,$13,$14,$15)
            """,
            snapshot.snapshot_id,
            snapshot.registry_id,
            snapshot.processing_run_id,
            snapshot.project_id,
            snapshot.document_id,
            snapshot.after_section_id,
            snapshot.after_node_run_id,
            snapshot.sequence_number,
            self._json(snapshot.entries_payload),
            self._json(snapshot.relations_payload),
            snapshot.entry_count,
            snapshot.relation_count,
            snapshot.claim_observation_count,
            snapshot.update_count,
            self._time(snapshot.created_at),
        )

    async def create_registry_application_queue_items(
        self,
        items: tuple[RegistryApplicationQueueItem, ...],
    ) -> None:
        for item in items:
            await self._connection.execute(
                """
                INSERT INTO knowledge_workbench_fact_registry_application_queue (
                    queue_item_id,
                    processing_run_id,
                    project_id,
                    document_id,
                    section_id,
                    source_node_run_id,
                    observed_registry_snapshot_id,
                    observed_registry_snapshot_sequence,
                    claim_input_refs,
                    status,
                    claimed_by_worker_id,
                    lease_expires_at,
                    applied_registry_snapshot_id,
                    stale_at_registry_snapshot_id,
                    attempt_count,
                    created_at,
                    updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8,
                    $9, $10, $11, $12, $13, $14, $15, $16, $17
                )
                ON CONFLICT (queue_item_id) DO NOTHING
                """,
                item.queue_item_id,
                item.processing_run_id,
                item.project_id,
                item.document_id,
                item.section_id,
                item.source_node_run_id,
                item.observed_registry_snapshot_id,
                item.observed_registry_snapshot_sequence,
                self._json(list(item.claim_input_refs)),
                item.status.value,
                item.claimed_by_worker_id,
                item.lease_expires_at,
                item.applied_registry_snapshot_id,
                item.stale_at_registry_snapshot_id,
                item.attempt_count,
                self._time(item.created_at),
                self._time(item.updated_at),
            )

    async def lease_next_registry_application_queue_item(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        worker_id: str,
        lease_expires_at: object,
    ) -> RegistryApplicationQueueItem | None:
        row = await self._connection.fetchrow(
            """
            WITH candidate AS (
                SELECT queue_item_id
                FROM knowledge_workbench_fact_registry_application_queue
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND processing_run_id = $3
                  AND status = 'ready'
                ORDER BY observed_registry_snapshot_sequence ASC, created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE knowledge_workbench_fact_registry_application_queue AS queue
            SET status = 'leased',
                claimed_by_worker_id = $4,
                lease_expires_at = $5,
                attempt_count = queue.attempt_count + 1,
                updated_at = now()
            FROM candidate
            WHERE queue.queue_item_id = candidate.queue_item_id
            RETURNING
                queue.queue_item_id,
                queue.processing_run_id,
                queue.project_id,
                queue.document_id,
                queue.section_id,
                queue.source_node_run_id,
                queue.observed_registry_snapshot_id,
                queue.observed_registry_snapshot_sequence,
                queue.claim_input_refs,
                queue.status,
                queue.claimed_by_worker_id,
                queue.lease_expires_at,
                queue.applied_registry_snapshot_id,
                queue.stale_at_registry_snapshot_id,
                queue.attempt_count,
                queue.created_at,
                queue.updated_at
            """,
            project_id,
            document_id,
            processing_run_id,
            worker_id,
            lease_expires_at,
        )
        if row is None:
            return None
        return self._registry_application_queue_item_from_row(row)

    async def mark_registry_application_queue_item_waiting_for_fresh_registry(
        self,
        *,
        queue_item_id: str,
        stale_at_registry_snapshot_id: str,
    ) -> None:
        await self._connection.execute(
            """
            UPDATE knowledge_workbench_fact_registry_application_queue
            SET status = 'waiting_for_fresh_registry',
                stale_at_registry_snapshot_id = $2,
                claimed_by_worker_id = NULL,
                lease_expires_at = NULL,
                updated_at = now()
            WHERE queue_item_id = $1
            """,
            queue_item_id,
            stale_at_registry_snapshot_id,
        )

    async def mark_registry_application_queue_item_applied(
        self,
        *,
        queue_item_id: str,
        applied_registry_snapshot_id: str,
    ) -> None:
        await self._connection.execute(
            """
            UPDATE knowledge_workbench_fact_registry_application_queue
            SET status = 'applied',
                applied_registry_snapshot_id = $2,
                claimed_by_worker_id = NULL,
                lease_expires_at = NULL,
                updated_at = now()
            WHERE queue_item_id = $1
            """,
            queue_item_id,
            applied_registry_snapshot_id,
        )

    def _registry_application_queue_item_from_row(
        self,
        row: Mapping[str, object],
    ) -> RegistryApplicationQueueItem:
        return RegistryApplicationQueueItem(
            queue_item_id=str(row["queue_item_id"]),
            processing_run_id=str(row["processing_run_id"]),
            project_id=str(row["project_id"]),
            document_id=str(row["document_id"]),
            section_id=str(row["section_id"]),
            source_node_run_id=str(row["source_node_run_id"]),
            observed_registry_snapshot_id=str(row["observed_registry_snapshot_id"]),
            observed_registry_snapshot_sequence=self._int_from_db(
                row["observed_registry_snapshot_sequence"]
            ),
            claim_input_refs=self._text_tuple_from_db(row["claim_input_refs"]),
            status=RegistryApplicationQueueItemStatus(str(row["status"])),
            claimed_by_worker_id=(
                str(row["claimed_by_worker_id"])
                if row["claimed_by_worker_id"] is not None
                else None
            ),
            lease_expires_at=self._datetime_from_db(row["lease_expires_at"]),
            applied_registry_snapshot_id=(
                str(row["applied_registry_snapshot_id"])
                if row["applied_registry_snapshot_id"] is not None
                else None
            ),
            stale_at_registry_snapshot_id=(
                str(row["stale_at_registry_snapshot_id"])
                if row["stale_at_registry_snapshot_id"] is not None
                else None
            ),
            attempt_count=self._int_from_db(row["attempt_count"]),
            created_at=self._datetime_from_db(row["created_at"]),
            updated_at=self._datetime_from_db(row["updated_at"]),
        )

    async def create_registry_update_applications(
        self,
        applications: tuple[RegistryUpdateApplication, ...],
    ) -> None:
        for application in applications:
            await self._connection.execute(
                """
                INSERT INTO knowledge_workbench_registry_update_applications (
                    application_id,
                    processing_run_id,
                    project_id,
                    document_id,
                    section_id,
                    proposal_id,
                    applied_by,
                    operation,
                    target_fact_id,
                    before_snapshot_id,
                    after_snapshot_id,
                    payload,
                    applied_at
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,$13)
                """,
                application.application_id,
                application.processing_run_id,
                application.project_id,
                application.document_id,
                application.section_id,
                application.proposal_id,
                application.applied_by.value,
                application.operation.value,
                application.target_fact_id,
                application.before_snapshot_id,
                application.after_snapshot_id,
                self._json(application.payload),
                self._time(application.applied_at),
            )

    async def publish_latest_reconciled_fact_registry_snapshot(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> str | None:
        already_published = await self._connection.fetchrow(
            """
            SELECT snapshot_id
            FROM knowledge_workbench_registry_snapshots
            WHERE project_id = $1::uuid
              AND document_id = $2
              AND is_final_published IS TRUE
            ORDER BY created_at DESC, sequence_number DESC
            LIMIT 1
            """,
            project_id,
            document_id,
        )
        if already_published is not None:
            return str(already_published["snapshot_id"])

        row = await self._connection.fetchrow(
            """
            SELECT
                snapshot.snapshot_id,
                snapshot.processing_run_id
            FROM knowledge_workbench_registry_snapshots AS snapshot
            WHERE snapshot.project_id = $1::uuid
              AND snapshot.document_id = $2
              AND snapshot.processing_run_id IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM knowledge_workbench_processing_node_runs AS node
                  JOIN knowledge_workbench_processing_node_artifacts AS artifact
                    ON artifact.node_run_id = node.node_run_id
                   AND artifact.processing_run_id = node.processing_run_id
                   AND artifact.project_id = node.project_id
                   AND artifact.document_id = node.document_id
                  WHERE node.project_id = snapshot.project_id
                    AND node.document_id = snapshot.document_id
                    AND node.processing_run_id = snapshot.processing_run_id
                    AND node.node_name = 'faq_surface_final_reconciliation'
                    AND node.status = 'completed'
                    AND artifact.artifact_type = 'parsed_llm_output'
                    AND artifact.metadata ->> 'snapshot_id' = snapshot.snapshot_id
              )
            ORDER BY snapshot.sequence_number DESC, snapshot.created_at DESC
            LIMIT 1
            """,
            project_id,
            document_id,
        )
        if row is None:
            return None

        snapshot_id = str(row["snapshot_id"])
        processing_run_id = str(row["processing_run_id"])

        async with _optional_workbench_transaction(self._connection):
            await self._connection.execute(
                """
                UPDATE knowledge_workbench_registry_snapshots
                SET is_final_published = FALSE
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND is_final_published IS TRUE
                """,
                project_id,
                document_id,
            )

            await self._connection.execute(
                """
                UPDATE knowledge_workbench_registry_snapshots
                SET is_final_published = TRUE
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND snapshot_id = $3
                """,
                project_id,
                document_id,
                snapshot_id,
            )

            await self.purge_transient_processing_workspace_after_publication(
                project_id=project_id,
                document_id=document_id,
                processing_run_id=processing_run_id,
            )

        return snapshot_id

    async def purge_transient_processing_workspace_after_publication(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> None:
        """Delete processing workspace after successful publication.

        Final registry rows survive because migration 071 switches their
        processing_run FKs to ON DELETE SET NULL. Node runs/artifacts,
        findings, update applications and materialization results are deleted
        through the processing_run cascade.
        """

        async with _optional_workbench_transaction(self._connection):
            await self._connection.execute(
                """
                DELETE FROM execution_queue
                WHERE task_type = 'process_workbench_document'
                  AND payload::jsonb ->> 'project_id' = $1
                  AND payload::jsonb ->> 'document_id' = $2
                """,
                project_id,
                document_id,
            )

            await self._connection.execute(
                """
                DELETE FROM knowledge_workbench_registry_snapshots
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND processing_run_id = $3
                  AND is_final_published IS NOT TRUE
                """,
                project_id,
                document_id,
                processing_run_id,
            )

            await self._connection.execute(
                """
                DELETE FROM knowledge_workbench_processing_runs
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND processing_run_id = $3
                """,
                project_id,
                document_id,
                processing_run_id,
            )

            await self._connection.execute(
                """
                UPDATE knowledge_workbench_documents
                SET status = 'published',
                    retention_state = 'transient_purged',
                    current_processing_run_id = NULL,
                    updated_at = now()
                WHERE project_id = $1::uuid
                  AND document_id = $2
                """,
                project_id,
                document_id,
            )

    def _int_from_db(self, value: object, *, default: int = 0) -> int:
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        text = str(value).strip()
        if not text:
            return default
        return int(text)

    def _datetime_from_db(self, value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        return datetime.fromisoformat(text)

    def _json_value_from_db(self, value: object) -> JsonValue:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return value
            if stripped[0] not in '[{"0123456789tfn-':
                return value
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                return value
            return self._json_value_from_db(decoded)
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, Sequence) and not isinstance(
            value, str | bytes | bytearray
        ):
            return [self._json_value_from_db(item) for item in value]
        if isinstance(value, Mapping):
            return {
                str(key): self._json_value_from_db(item) for key, item in value.items()
            }
        return str(value)

    def _json_object_from_db(self, value: object) -> dict[str, JsonValue]:
        parsed = self._json_value_from_db(value)
        if not isinstance(parsed, dict):
            return {}
        return {str(key): item for key, item in parsed.items()}

    def _text_tuple_from_db(self, value: object) -> tuple[str, ...]:
        parsed = self._json_value_from_db(value)
        if not isinstance(parsed, list):
            return ()
        return tuple(str(item) for item in parsed)

    def _int_tuple_from_db(self, value: object) -> tuple[int, ...]:
        parsed = self._json_value_from_db(value)
        if not isinstance(parsed, list):
            return ()
        result: list[int] = []
        for item in parsed:
            if isinstance(item, bool):
                continue
            if isinstance(item, int):
                result.append(item)
            elif isinstance(item, str) and item.strip().isdigit():
                result.append(int(item.strip()))
        return tuple(result)

    def _json(self, value: JsonValue) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _time(self, value: datetime | None) -> datetime:
        return value if value is not None else datetime.now(timezone.utc)

    async def mark_parallel_processing_completed(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> None:
        async with _optional_workbench_transaction(self._connection):
            await self._connection.execute(
                """
                UPDATE knowledge_workbench_documents
                SET status = 'processed',
                    last_error_kind = NULL,
                    last_error_message = NULL,
                    last_error_at = NULL,
                    updated_at = now()
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND current_processing_run_id = $3
                  AND status NOT IN ('deleted', 'cancelled')
                """,
                project_id,
                document_id,
                processing_run_id,
            )
            await self._connection.execute(
                """
                UPDATE knowledge_workbench_processing_runs
                SET status = 'completed',
                    resume_policy = 'forbidden',
                    completed_at = COALESCE(completed_at, now()),
                    stopped_at = COALESCE(stopped_at, now()),
                    last_error_kind = NULL,
                    last_error_report_id = NULL,
                    last_user_message = NULL,
                    last_internal_error = NULL,
                    updated_at = now()
                WHERE project_id = $1::uuid
                  AND document_id = $2
                  AND processing_run_id = $3
                  AND deleted_at IS NULL
                  AND status NOT IN (
                      'deleted',
                      'cancelled_by_user',
                      'failed_validation',
                      'failed_fatal'
                  )
                """,
                project_id,
                document_id,
                processing_run_id,
            )

    async def has_completed_fact_registry_canonicalization(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> bool:
        row = await self._connection.fetchrow(
            """
            SELECT EXISTS (
                SELECT 1
                FROM knowledge_workbench_processing_node_artifacts AS marker
                JOIN knowledge_workbench_registry_snapshots AS snapshot
                  ON snapshot.snapshot_id = marker.metadata ->> 'final_snapshot_id'
                 AND snapshot.project_id = marker.project_id
                 AND snapshot.document_id = marker.document_id
                 AND snapshot.processing_run_id = marker.processing_run_id
                WHERE marker.project_id = $1::uuid
                  AND marker.document_id = $2
                  AND marker.processing_run_id = $3
                  AND marker.section_id IS NULL
                  AND marker.artifact_type = 'parsed_llm_output'
                  AND marker.metadata ->> 'contract' = 'fact_registry_canonicalization_barrier'
                  AND marker.metadata ->> 'status' = 'completed'
                  AND (marker.metadata ->> 'expected_unit_count')::int
                    = (marker.metadata ->> 'completed_unit_count')::int
                  AND snapshot.entries_payload ->> 'contract' = 'fact_registry'
                  AND snapshot.entry_count >= 0
                LIMIT 1
            ) AS completed
            """,
            project_id,
            document_id,
            processing_run_id,
        )
        if row is None:
            return False
        return bool(row["completed"])

    async def get_parallel_processing_drain_counts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> ParallelDrainWorkCounts:
        section_row = await self._connection.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'ready')::int AS section_ready,
                COUNT(*) FILTER (WHERE status = 'leased')::int AS section_leased,
                COUNT(*) FILTER (
                    WHERE status = 'claim_observations_persisted'
                )::int AS section_claim_observations_persisted,
                COUNT(*) FILTER (
                    WHERE status = 'registry_application_queued'
                )::int AS section_registry_application_queued,
                COUNT(*) FILTER (
                    WHERE status = 'waiting_for_fresh_registry'
                )::int AS section_waiting_for_fresh_registry,
                COUNT(*) FILTER (WHERE status = 'failed')::int AS section_failed,
                COUNT(*) FILTER (
                    WHERE status = 'registry_application_applied'
                )::int AS section_registry_application_applied,
                COUNT(*) FILTER (WHERE status = 'skipped')::int AS section_skipped
            FROM knowledge_workbench_section_batch_queue_items
            WHERE project_id = $1
              AND document_id = $2
              AND processing_run_id = $3
            """,
            project_id,
            document_id,
            processing_run_id,
        )
        registry_row = await self._connection.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'ready')::int AS registry_ready,
                COUNT(*) FILTER (WHERE status = 'leased')::int AS registry_leased,
                COUNT(*) FILTER (
                    WHERE status = 'waiting_for_fresh_registry'
                )::int AS registry_waiting_for_fresh_registry,
                COUNT(*) FILTER (WHERE status = 'failed')::int AS registry_failed,
                COUNT(*) FILTER (WHERE status = 'applied')::int AS registry_applied,
                COUNT(*) FILTER (
                    WHERE status = 'superseded'
                )::int AS registry_superseded
            FROM knowledge_workbench_fact_registry_application_queue
            WHERE project_id = $1
              AND document_id = $2
              AND processing_run_id = $3
            """,
            project_id,
            document_id,
            processing_run_id,
        )

        def count(row: Mapping[str, object] | None, key: str) -> int:
            if row is None:
                return 0
            return self._int_from_db(row.get(key, 0))

        return ParallelDrainWorkCounts(
            section_ready=count(section_row, "section_ready"),
            section_leased=count(section_row, "section_leased"),
            section_claim_observations_persisted=count(
                section_row,
                "section_claim_observations_persisted",
            ),
            section_registry_application_queued=count(
                section_row,
                "section_registry_application_queued",
            ),
            section_waiting_for_fresh_registry=count(
                section_row,
                "section_waiting_for_fresh_registry",
            ),
            section_failed=count(section_row, "section_failed"),
            section_registry_application_applied=count(
                section_row,
                "section_registry_application_applied",
            ),
            section_skipped=count(section_row, "section_skipped"),
            registry_ready=count(registry_row, "registry_ready"),
            registry_leased=count(registry_row, "registry_leased"),
            registry_waiting_for_fresh_registry=count(
                registry_row,
                "registry_waiting_for_fresh_registry",
            ),
            registry_failed=count(registry_row, "registry_failed"),
            registry_applied=count(registry_row, "registry_applied"),
            registry_superseded=count(registry_row, "registry_superseded"),
        )
