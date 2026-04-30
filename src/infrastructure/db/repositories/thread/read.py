from uuid import UUID

from src.domain.project_plane.thread_status import ThreadStatus
from src.domain.project_plane.thread_views import (
    ThreadDialogClientView,
    ThreadDialogView,
    ThreadLastMessageView,
    ThreadStatusSummaryView,
    ThreadWithProjectView,
)
from src.utils.uuid_utils import ensure_uuid
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

ThreadDialogQueryParam = UUID | str | int | None | list[str]


def _status_filter_values(status_filter: str | None) -> list[str] | None:
    if status_filter is None:
        return None
    if status_filter == ThreadStatus.ACTIVE.value:
        return [ThreadStatus.ACTIVE.value]
    if status_filter == ThreadStatus.MANUAL.value:
        return [ThreadStatus.MANUAL.value]
    if status_filter == ThreadStatus.WAITING_MANAGER.value:
        return [ThreadStatus.WAITING_MANAGER.value]
    if status_filter == ThreadStatus.CLOSED.value:
        return [ThreadStatus.CLOSED.value]
    return [status_filter]


class ThreadReadRepository:
    def __init__(self, pool):
        self.pool = pool

    async def get_thread_with_project_view(
        self, thread_id: str
    ) -> ThreadWithProjectView | None:
        logger.debug(f"Fetching thread with project for thread {thread_id}")

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    t.id,
                    t.client_id,
                    t.status,
                    t.manager_user_id,
                    t.manager_chat_id,
                    t.context_summary,
                    t.created_at,
                    t.updated_at,
                    c.project_id,
                    c.full_name,
                    c.username,
                    c.email,
                    c.chat_id
                FROM threads t
                JOIN clients c ON t.client_id = c.id
                WHERE t.id = $1
            """,
                ensure_uuid(thread_id),
            )

        if not row:
            logger.warning(f"Thread {thread_id} not found")
            return None

        logger.debug(f"Thread data retrieved for {thread_id}")
        return ThreadWithProjectView.from_record(dict(row))

    async def get_dialogs(
        self,
        project_id: str,
        limit: int = 20,
        offset: int = 0,
        status_filter: str | None = None,
        search: str | None = None,
        client_id: str | None = None,
    ) -> list[ThreadDialogView]:
        logger.info(
            "Fetching dialogs",
            extra={"project_id": project_id, "limit": limit, "offset": offset},
        )

        if status_filter == "manager":
            params = self._manager_dialog_params(
                project_id=project_id,
                search=search,
                client_id=client_id,
                limit=limit,
                offset=offset,
            )
            query = self._manager_dialogs_query()
        else:
            params = self._default_dialog_params(
                project_id=project_id,
                status_filter=status_filter,
                search=search,
                client_id=client_id,
                limit=limit,
                offset=offset,
            )
            query = self._default_dialogs_query()

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        dialogs = []
        for row in rows:
            thread_created_at = row["thread_created_at"]
            if thread_created_at:
                thread_created_at = thread_created_at.isoformat()

            thread_updated_at = row["thread_updated_at"]
            if thread_updated_at:
                thread_updated_at = thread_updated_at.isoformat()

            last_msg_created_at = row["last_message_created_at"]
            if last_msg_created_at:
                last_msg_created_at = last_msg_created_at.isoformat()

            dialogs.append(
                ThreadDialogView(
                    thread_id=str(row["thread_id"]),
                    status=row["status"],
                    interaction_mode=row["interaction_mode"],
                    thread_created_at=thread_created_at,
                    thread_updated_at=thread_updated_at,
                    client=ThreadDialogClientView(
                        id=str(row["client_id"]),
                        full_name=row["full_name"],
                        username=row["username"],
                        email=row["email"],
                        chat_id=row["chat_id"],
                    ),
                    last_message=ThreadLastMessageView(
                        content=row["last_message_content"],
                        created_at=last_msg_created_at,
                    )
                    if row["last_message_content"]
                    else None,
                    unread_count=0,
                )
            )

        logger.debug(f"Retrieved {len(dialogs)} dialogs")
        return dialogs

    def _default_dialog_params(
        self,
        *,
        project_id: str,
        status_filter: str | None,
        search: str | None,
        client_id: str | None,
        limit: int,
        offset: int,
    ) -> list[ThreadDialogQueryParam]:
        return [
            ensure_uuid(project_id),
            _status_filter_values(status_filter),
            f"%{search}%" if search else None,
            ensure_uuid(client_id) if client_id else None,
            limit,
            offset,
        ]

    def _manager_dialog_params(
        self,
        *,
        project_id: str,
        search: str | None,
        client_id: str | None,
        limit: int,
        offset: int,
    ) -> list[ThreadDialogQueryParam]:
        return [
            ensure_uuid(project_id),
            f"%{search}%" if search else None,
            ensure_uuid(client_id) if client_id else None,
            limit,
            offset,
        ]

    def _default_dialogs_query(self) -> str:
        return """
            SELECT
                t.id AS thread_id,
                t.status,
                t.interaction_mode,
                t.created_at AS thread_created_at,
                t.updated_at AS thread_updated_at,
                c.id AS client_id,
                c.full_name,
                c.username,
                c.email,
                c.chat_id,
                lm.content AS last_message_content,
                lm.created_at AS last_message_created_at
            FROM threads t
            JOIN clients c ON t.client_id = c.id
            LEFT JOIN LATERAL (
                SELECT content, created_at
                FROM messages m
                WHERE m.thread_id = t.id
                ORDER BY m.created_at DESC
                LIMIT 1
            ) lm ON true
            WHERE c.project_id = $1
              AND ($2::text[] IS NULL OR t.status = ANY($2))
              AND (
                  $3::text IS NULL
                  OR (
                      c.full_name ILIKE $3
                      OR c.username ILIKE $3
                      OR c.email ILIKE $3
                  )
              )
              AND ($4::uuid IS NULL OR c.id = $4)
            ORDER BY t.updated_at DESC
            LIMIT $5 OFFSET $6
        """

    def _manager_dialogs_query(self) -> str:
        return """
            SELECT
                t.id AS thread_id,
                t.status,
                t.interaction_mode,
                t.created_at AS thread_created_at,
                t.updated_at AS thread_updated_at,
                c.id AS client_id,
                c.full_name,
                c.username,
                c.email,
                c.chat_id,
                lm.content AS last_message_content,
                lm.created_at AS last_message_created_at
            FROM threads t
            JOIN clients c ON t.client_id = c.id
            LEFT JOIN LATERAL (
                SELECT MAX(m.created_at) AS last_manager_message_at
                FROM messages m
                WHERE m.thread_id = t.id
                  AND m.role = 'manager'
            ) manager_reply ON true
            LEFT JOIN LATERAL (
                SELECT MAX(e.created_at) AS last_ticket_event_at
                FROM threads related
                JOIN events e ON e.stream_id = related.id
                WHERE related.client_id = t.client_id
                  AND e.event_type IN ('ticket_created', 'manager_replied', 'ticket_closed')
            ) manager_history ON true
            LEFT JOIN LATERAL (
                SELECT content, created_at
                FROM messages m
                WHERE m.thread_id = t.id
                ORDER BY m.created_at DESC
                LIMIT 1
            ) lm ON true
            WHERE c.project_id = $1
              AND (
                  manager_reply.last_manager_message_at IS NOT NULL
                  OR
                  t.status IN ('manual', 'waiting_manager', 'closed')
                  OR EXISTS (
                      SELECT 1
                      FROM threads related
                      JOIN events e ON e.stream_id = related.id
                      WHERE related.client_id = t.client_id
                        AND e.event_type IN ('ticket_created', 'manager_replied', 'ticket_closed')
                        AND t.updated_at BETWEEN e.created_at - INTERVAL '30 minutes' AND e.created_at
                  )
              )
              AND (
                  $2::text IS NULL
                  OR (
                      c.full_name ILIKE $2
                      OR c.username ILIKE $2
                      OR c.email ILIKE $2
                  )
              )
              AND ($3::uuid IS NULL OR c.id = $3)
            ORDER BY GREATEST(
                COALESCE(manager_reply.last_manager_message_at, TO_TIMESTAMP(0)),
                COALESCE(manager_history.last_ticket_event_at, TO_TIMESTAMP(0)),
                t.updated_at
            ) DESC,
            t.updated_at DESC
            LIMIT $4 OFFSET $5
        """

    async def find_by_status(self, status: str) -> list[ThreadStatusSummaryView]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT t.*, c.full_name AS client_name
                FROM threads t
                JOIN clients c ON t.client_id = c.id
                WHERE t.status = $1
                ORDER BY t.updated_at DESC
            """,
                status,
            )

        return [ThreadStatusSummaryView.from_record(dict(row)) for row in rows]
