from src.domain.project_plane.manager_assignments import ManagerActor
from src.domain.project_plane.thread_status import ThreadStatus
from src.utils.uuid_utils import ensure_uuid
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class ThreadLifecycleRepository:
    def __init__(self, pool):
        self.pool = pool

    async def get_or_create_client(
        self,
        project_id: str,
        chat_id: int,
        username: str | None = None,
        source: str = "telegram",
        full_name: str | None = None,
    ) -> str:
        username_value = username.strip() if username and username.strip() else None
        full_name_value = full_name.strip() if full_name and full_name.strip() else None
        logger.info(
            f"Getting or creating client for project {project_id}, chat {chat_id}"
        )
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO clients (project_id, chat_id, username, source, user_id, full_name)
                VALUES (
                    $1,
                    $2,
                    $3,
                    $4,
                    (SELECT id FROM users WHERE telegram_id = $2 LIMIT 1),
                    $5
                )
                ON CONFLICT (project_id, chat_id) DO UPDATE
                SET
                    username = COALESCE(NULLIF(EXCLUDED.username, ''), clients.username),
                    full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), clients.full_name),
                    user_id = COALESCE(clients.user_id, EXCLUDED.user_id)
                RETURNING id
            """,
                ensure_uuid(project_id),
                chat_id,
                username_value,
                source,
                full_name_value,
            )
            client_id = str(row["id"])
            logger.info(f"Client {client_id} ensured")
            return client_id

    async def get_active_thread(self, client_id: str) -> str | None:
        logger.debug(f"Looking for thread for client {client_id}")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id FROM threads
                WHERE client_id = $1
                ORDER BY updated_at DESC
                LIMIT 1
            """,
                ensure_uuid(client_id),
            )

        if row:
            thread_id = str(row["id"])
            logger.debug(f"Thread found: {thread_id}")
            return thread_id

        logger.debug("No thread found")
        return None

    async def create_thread(self, client_id: str) -> str:
        logger.info(f"Creating new thread for client {client_id}")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO threads (client_id, status)
                VALUES ($1, $2)
                RETURNING id
            """,
                ensure_uuid(client_id),
                ThreadStatus.ACTIVE.value,
            )

        thread_id = str(row["id"])
        logger.info(f"Thread {thread_id} created")
        return thread_id

    async def update_status(self, thread_id: str, status: ThreadStatus | str) -> None:
        status_value = status.value if isinstance(status, ThreadStatus) else status
        logger.info(f"Updating thread {thread_id} status to {status_value}")

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE threads
                SET status = $1, updated_at = NOW()
                WHERE id = $2
            """,
                status_value,
                ensure_uuid(thread_id),
            )

    async def archive_thread(self, thread_id: str) -> None:
        await self.update_status(thread_id, "archived")

    async def update_interaction_mode(self, thread_id: str, mode: str) -> None:
        logger.info(f"Updating interaction mode for thread {thread_id} to {mode}")

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE threads
                SET interaction_mode = $1, updated_at = NOW()
                WHERE id = $2
            """,
                mode,
                ensure_uuid(thread_id),
            )

    async def claim_for_manager(
        self,
        thread_id: str,
        *,
        manager: ManagerActor | None = None,
        manager_user_id: str | None = None,
        manager_chat_id: str | None = None,
    ) -> None:
        if manager is not None:
            manager_user_id = manager.user_id
            manager_chat_id = manager.telegram_chat_id

        logger.info(
            "Claiming thread for manager",
            extra={
                "thread_id": thread_id,
                "manager_user_id": manager_user_id,
                "has_manager_chat_id": bool(manager_chat_id),
            },
        )

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE threads
                SET
                    status = $1,
                    manager_user_id = $2,
                    manager_chat_id = $3,
                    updated_at = NOW()
                WHERE id = $4
            """,
                ThreadStatus.MANUAL.value,
                ensure_uuid(manager_user_id) if manager_user_id else None,
                manager_chat_id,
                ensure_uuid(thread_id),
            )

    async def release_manager_assignment(self, thread_id: str) -> None:
        logger.info("Releasing manager assignment", extra={"thread_id": thread_id})

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE threads
                SET
                    status = $1,
                    manager_user_id = NULL,
                    manager_chat_id = NULL,
                    updated_at = NOW()
                WHERE id = $2
            """,
                ThreadStatus.ACTIVE.value,
                ensure_uuid(thread_id),
            )
