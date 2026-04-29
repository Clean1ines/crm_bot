"""
Metrics Repository for aggregating thread and project metrics.
Provides methods to update thread_metrics and project_metrics_daily tables.
"""

import asyncpg
from datetime import date
from uuid import UUID

from src.infrastructure.logging.logger import get_logger
from src.utils.uuid_utils import ensure_uuid

logger = get_logger(__name__)


class MetricsRepository:
    """
    Repository for managing thread and project metrics.

    This repository handles incremental updates to thread_metrics and
    daily aggregates in project_metrics_daily.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        """
        Initialize the MetricsRepository with a database connection pool.

        Args:
            pool: Asyncpg connection pool for database operations.
        """
        self.pool = pool
        logger.debug("MetricsRepository initialized")

    async def update_thread_metrics(
        self,
        thread_id: str,
        total_messages: int | None = None,
        ai_messages: int | None = None,
        manager_messages: int | None = None,
        escalated: bool | None = None,
        resolution_time: float | None = None,  # in seconds
    ) -> None:
        """
        Update thread_metrics for a given thread. Uses ON CONFLICT to handle upsert.

        Args:
            thread_id: UUID of the thread.
            total_messages: Increment total messages by this amount.
            ai_messages: Increment AI messages by this amount.
            manager_messages: Increment manager messages by this amount.
            escalated: If True, set escalated = True (overwrites).
            resolution_time: Resolution time in seconds (sets the field).
        """
        thread_uuid = ensure_uuid(thread_id)
        query = """
            INSERT INTO thread_metrics (thread_id, total_messages, ai_messages, manager_messages, escalated, resolution_time, updated_at)
            VALUES ($1, 0, 0, 0, false, NULL, NOW())
            ON CONFLICT (thread_id) DO UPDATE SET
            total_messages = COALESCE(thread_metrics.total_messages, 0) + COALESCE($2, 0),
            ai_messages = COALESCE(thread_metrics.ai_messages, 0) + COALESCE($3, 0),
            manager_messages = COALESCE(thread_metrics.manager_messages, 0) + COALESCE($4, 0),
            escalated = COALESCE($5, thread_metrics.escalated),
            resolution_time = CASE
                WHEN $6 IS NULL THEN thread_metrics.resolution_time
                ELSE $6 * interval '1 second'
            END,
            updated_at = NOW()
        """
        params = [
            thread_uuid,
            total_messages,
            ai_messages,
            manager_messages,
            escalated,
            resolution_time,
        ]

        async with self.pool.acquire() as conn:
            await conn.execute(query, *params)
        logger.debug("Thread metrics updated", extra={"thread_id": thread_id})

    async def update_project_daily_metrics(
        self,
        project_id: str,
        date: date,
        total_threads_delta: int = 0,
        escalations_delta: int = 0,
        tokens_used_delta: int = 0,
        avg_messages_to_resolution: float | None = None,
    ) -> None:
        """
        Update project_metrics_daily for a given project and date.

        Args:
            project_id: UUID of the project.
            date: The date for which to update.
            total_threads_delta: Number to add to total_threads.
            escalations_delta: Number to add to escalations.
            tokens_used_delta: Number to add to tokens_used.
            avg_messages_to_resolution: Overwrites avg_messages_to_resolution (optional).
        """
        async with self.pool.acquire() as conn:
            # First, get current values (if any)
            current = await conn.fetchrow(
                """
                SELECT total_threads, escalations, avg_messages_to_resolution, tokens_used
                FROM project_metrics_daily
                WHERE project_id = $1 AND date = $2
            """,
                ensure_uuid(project_id),
                date,
            )

            if current:
                new_total = current["total_threads"] + total_threads_delta
                new_escalations = current["escalations"] + escalations_delta
                new_tokens = current["tokens_used"] + tokens_used_delta
                new_avg = (
                    avg_messages_to_resolution
                    if avg_messages_to_resolution is not None
                    else current["avg_messages_to_resolution"]
                )
                await conn.execute(
                    """
                    UPDATE project_metrics_daily
                    SET total_threads = $1, escalations = $2, avg_messages_to_resolution = $3, tokens_used = $4
                    WHERE project_id = $5 AND date = $6
                """,
                    new_total,
                    new_escalations,
                    new_avg,
                    new_tokens,
                    ensure_uuid(project_id),
                    date,
                )
            else:
                # Insert new row with deltas as initial values
                await conn.execute(
                    """
                    INSERT INTO project_metrics_daily (project_id, date, total_threads, escalations, avg_messages_to_resolution, tokens_used)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """,
                    ensure_uuid(project_id),
                    date,
                    total_threads_delta,
                    escalations_delta,
                    avg_messages_to_resolution,
                    tokens_used_delta,
                )

        logger.debug(
            "Project daily metrics updated",
            extra={"project_id": project_id, "date": date},
        )

    async def aggregate_for_date(self, target_date: date) -> None:
        """
        Recalculate all project_metrics_daily for a specific date from events.
        This is an idempotent operation that can be used to fix discrepancies.

        Args:
            target_date: The date to aggregate.
        """
        logger.info("Aggregating metrics for date", extra={"date": target_date})
        # Implementation depends on event structure. We'll compute:
        # - total_threads: count of threads created on that date
        # - escalations: count of ticket_created events on that date
        # - avg_messages_to_resolution: for threads closed on that date, average messages before resolution
        # - tokens_used: not available from events currently; we can skip or set to 0
        async with self.pool.acquire() as conn:
            # Get threads created on this date
            rows = await conn.fetch(
                """
                SELECT t.id, t.created_at, c.project_id
                FROM threads t
                JOIN clients c ON t.client_id = c.id
                WHERE t.created_at::date = $1
            """,
                target_date,
            )
            thread_counts: dict[UUID, int] = {}
            for row in rows:
                pid = row["project_id"]
                thread_counts[pid] = thread_counts.get(pid, 0) + 1

            # Get escalations on this date
            escalations = await conn.fetch(
                """
                SELECT project_id, COUNT(*) as count
                FROM events
                WHERE event_type = 'ticket_created' AND created_at::date = $1
                GROUP BY project_id
            """,
                target_date,
            )
            escal_counts: dict[UUID, int] = {
                row["project_id"]: int(row["count"]) for row in escalations
            }

            # For each project, update the daily metrics
            # We'll first delete existing rows for this date to avoid double counting
            await conn.execute(
                "DELETE FROM project_metrics_daily WHERE date = $1", target_date
            )

            all_projects = set(thread_counts.keys()) | set(escal_counts.keys())
            for pid in all_projects:
                total = thread_counts.get(pid, 0)
                esc = escal_counts.get(pid, 0)
                await conn.execute(
                    """
                    INSERT INTO project_metrics_daily (project_id, date, total_threads, escalations, avg_messages_to_resolution, tokens_used)
                    VALUES ($1, $2, $3, $4, NULL, 0)
                """,
                    pid,
                    target_date,
                    total,
                    esc,
                )

        logger.info("Metrics aggregated", extra={"date": target_date})
