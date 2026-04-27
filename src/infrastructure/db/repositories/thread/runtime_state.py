import json
from uuid import UUID

from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown
from src.domain.project_plane.thread_views import (
    ThreadAnalyticsView,
    ThreadMessageCounts,
)
from src.infrastructure.logging.logger import get_logger
from src.utils.uuid_utils import ensure_uuid

logger = get_logger(__name__)


class ThreadRuntimeStateRepository:
    def __init__(self, pool):
        self.pool = pool

    async def update_summary(self, thread_id: str, summary: str) -> None:
        logger.info(f"Updating summary for thread {thread_id}")

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE threads
                SET context_summary = $1, updated_at = NOW()
                WHERE id = $2
            """,
                summary,
                ensure_uuid(thread_id),
            )

        logger.debug("Summary updated")

    async def get_state_json(self, thread_id: str) -> JsonObject | None:
        logger.debug(f"Fetching state_json for thread {thread_id}")

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT state_json
                FROM threads
                WHERE id = $1
            """,
                ensure_uuid(thread_id),
            )

        if row and row["state_json"] is not None:
            logger.debug(f"State_json retrieved for thread {thread_id}")
            return json_object_from_unknown(row["state_json"])

        logger.debug(f"No state_json found for thread {thread_id}")
        return None

    async def save_state_json(self, thread_id: str, state: JsonObject) -> None:
        logger.info(f"Saving state_json for thread {thread_id}")

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE threads
                SET state_json = $1, updated_at = NOW()
                WHERE id = $2
            """,
                json.dumps(state, ensure_ascii=False),
                ensure_uuid(thread_id),
            )

        logger.debug("State_json saved")

    async def update_analytics(
        self,
        thread_id: str,
        intent: str | None = None,
        lifecycle: str | None = None,
        cta: str | None = None,
        decision: str | None = None,
    ) -> None:
        thread_uuid = ensure_uuid(thread_id)

        updates: list[str] = []
        params: list[str | UUID] = []

        if intent is not None:
            updates.append("intent = $%d" % (len(params) + 1))
            params.append(intent)

        if lifecycle is not None:
            updates.append("lifecycle = $%d" % (len(params) + 1))
            params.append(lifecycle)

        if cta is not None:
            updates.append("cta = $%d" % (len(params) + 1))
            params.append(cta)

        if decision is not None:
            updates.append("decision = $%d" % (len(params) + 1))
            params.append(decision)

        if not updates:
            logger.debug(
                "No analytics fields to update", extra={"thread_id": thread_id}
            )
            return

        query = f"""
            UPDATE threads
            SET {", ".join(updates)}, updated_at = NOW()
            WHERE id = ${len(params) + 1}
        """
        params.append(thread_uuid)

        async with self.pool.acquire() as conn:
            await conn.execute(query, *params)

        logger.info(
            "Analytics updated",
            extra={
                "thread_id": thread_id,
                "intent": intent,
                "lifecycle": lifecycle,
                "cta": cta,
                "decision": decision,
            },
        )

    async def get_analytics_view(self, thread_id: str) -> ThreadAnalyticsView | None:
        logger.debug(f"Fetching analytics for thread {thread_id}")

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT intent, lifecycle, cta, decision
                FROM threads
                WHERE id = $1
            """,
                ensure_uuid(thread_id),
            )

        if not row:
            logger.warning(f"Thread {thread_id} not found for analytics fetch")
            return None

        logger.debug(f"Analytics retrieved for thread {thread_id}")
        return ThreadAnalyticsView.from_record(dict(row))

    async def get_message_counts_view(self, thread_id: str) -> ThreadMessageCounts:
        logger.debug(f"Fetching message counts for thread {thread_id}")

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(CASE WHEN role = 'assistant' THEN 1 END) AS ai,
                    COUNT(CASE WHEN role = 'user' THEN 1 END) AS manager
                FROM messages
                WHERE thread_id = $1
            """,
                ensure_uuid(thread_id),
            )

        return ThreadMessageCounts.from_record(dict(row) if row else None)
