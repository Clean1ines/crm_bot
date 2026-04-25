"""Repository for project-scoped CRM clients/contacts."""

from typing import Any, Dict, Optional
from uuid import UUID

from src.domain.project_plane.client_views import ClientDetailView, ClientListItemView, ClientListView

def _serialize_timestamp(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class ClientRepository:
    def __init__(self, pool) -> None:
        self.pool = pool

    async def list_for_project_view(
        self,
        project_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
    ) -> ClientListView:
        async with self.pool.acquire() as conn:
            where_parts = ["c.project_id = $1"]
            params: list[Any] = [UUID(project_id)]
            param_idx = 2
            if search:
                where_parts.append(
                    f"""(
                        c.full_name ILIKE ${param_idx}
                        OR c.username ILIKE ${param_idx}
                        OR c.email ILIKE ${param_idx}
                        OR c.company ILIKE ${param_idx}
                        OR c.phone ILIKE ${param_idx}
                    )"""
                )
                params.append(f"%{search}%")
                param_idx += 1

            where_clause = " AND ".join(where_parts)
            query = f"""
                SELECT
                    c.id,
                    c.user_id,
                    c.username,
                    c.full_name,
                    c.email,
                    c.company,
                    c.phone,
                    c.metadata,
                    c.chat_id,
                    c.source,
                    c.created_at,
                    MAX(t.updated_at) AS last_activity_at,
                    COUNT(t.id) AS threads_count,
                    (
                        SELECT t2.id
                        FROM threads t2
                        WHERE t2.client_id = c.id
                        ORDER BY t2.updated_at DESC
                        LIMIT 1
                    ) AS latest_thread_id
                FROM clients c
                LEFT JOIN threads t ON t.client_id = c.id
                WHERE {where_clause}
                GROUP BY c.id, c.user_id, c.username, c.full_name, c.email,
                         c.company, c.phone, c.metadata, c.chat_id, c.source, c.created_at
                ORDER BY COALESCE(MAX(t.updated_at), c.created_at) DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            params.extend([limit, offset])
            rows = await conn.fetch(query, *params)

            total_clients = await conn.fetchval(
                "SELECT COUNT(*) FROM clients WHERE project_id = $1",
                UUID(project_id),
            )
            new_clients_7d = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM clients
                WHERE project_id = $1
                  AND created_at >= NOW() - INTERVAL '7 days'
                """,
                UUID(project_id),
            )
            active_dialogs = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM threads t
                JOIN clients c ON c.id = t.client_id
                WHERE c.project_id = $1
                  AND t.status IN ('active', 'manual')
                """,
                UUID(project_id),
            )

            clients: list[ClientListItemView] = []
            for row in rows:
                clients.append(ClientListItemView(
                    id=str(row["id"]),
                    user_id=str(row["user_id"]) if row.get("user_id") else None,
                    username=row["username"],
                    full_name=row["full_name"],
                    email=row["email"],
                    company=row["company"],
                    phone=row["phone"],
                    metadata=row["metadata"] or {},
                    chat_id=row["chat_id"],
                    source=row["source"],
                    created_at=_serialize_timestamp(row.get("created_at")),
                    last_activity_at=_serialize_timestamp(row.get("last_activity_at")),
                    threads_count=int(row.get("threads_count") or 0),
                    latest_thread_id=str(row["latest_thread_id"]) if row.get("latest_thread_id") else None,
                ))

            return ClientListView(
                clients=clients,
                total_clients=int(total_clients or 0),
                new_clients_7d=int(new_clients_7d or 0),
                active_dialogs=int(active_dialogs or 0),
            )


    async def get_by_id_view(self, project_id: str, client_id: str) -> Optional[ClientDetailView]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, user_id, username, full_name, email, company, phone,
                       metadata, chat_id, source, created_at
                FROM clients
                WHERE id = $1 AND project_id = $2
            """, UUID(client_id), UUID(project_id))

        if not row:
            return None

        return ClientDetailView(
            id=str(row["id"]),
            user_id=str(row["user_id"]) if row.get("user_id") else None,
            username=row["username"],
            full_name=row["full_name"],
            email=row["email"],
            company=row["company"],
            phone=row["phone"],
            metadata=row["metadata"] or {},
            chat_id=row["chat_id"],
            source=row["source"],
            created_at=_serialize_timestamp(row["created_at"]),
        )

