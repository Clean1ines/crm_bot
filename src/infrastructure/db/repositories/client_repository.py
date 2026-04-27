"""Repository for project-scoped CRM clients/contacts."""

from collections.abc import Mapping
from uuid import UUID

from src.domain.project_plane.client_views import (
    ClientDetailView,
    ClientListItemView,
    ClientListView,
)


def _serialize_timestamp(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None else None


def _row_mapping(row: object) -> Mapping[str, object]:
    if isinstance(row, Mapping):
        return row
    return {}


def _search_filter(
    search: str | None, param_idx: int
) -> tuple[list[str], list[object], int]:
    if not search:
        return [], [], param_idx

    clause = f"""(
        c.full_name ILIKE ${param_idx}
        OR c.username ILIKE ${param_idx}
        OR c.email ILIKE ${param_idx}
        OR c.company ILIKE ${param_idx}
        OR c.phone ILIKE ${param_idx}
    )"""
    return [clause], [f"%{search}%"], param_idx + 1


def _list_where_clause(search: str | None) -> tuple[str, list[object], int]:
    where_parts = ["c.project_id = $1"]
    search_parts, search_params, param_idx = _search_filter(search, 2)
    where_parts.extend(search_parts)
    return " AND ".join(where_parts), search_params, param_idx


def _client_list_query(
    where_clause: str, *, limit_param: int, offset_param: int
) -> str:
    return f"""
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
        LIMIT ${limit_param} OFFSET ${offset_param}
    """


def _client_stats_query() -> str:
    return """
        SELECT
            COUNT(*) AS total_clients,
            COUNT(*) FILTER (
                WHERE created_at >= NOW() - INTERVAL '7 days'
            ) AS new_clients_7d,
            (
                SELECT COUNT(*)
                FROM threads t
                JOIN clients c2 ON c2.id = t.client_id
                WHERE c2.project_id = $1
                  AND t.status IN ('active', 'manual')
            ) AS active_dialogs
        FROM clients
        WHERE project_id = $1
    """


def _client_list_item_from_row(row: Mapping[str, object]) -> ClientListItemView:
    return ClientListItemView(
        id=str(row["id"]),
        user_id=_optional_text(row.get("user_id")),
        username=_optional_text(row.get("username")),
        full_name=_optional_text(row.get("full_name")),
        email=_optional_text(row.get("email")),
        company=_optional_text(row.get("company")),
        phone=_optional_text(row.get("phone")),
        metadata=dict(_row_mapping(row.get("metadata"))),
        chat_id=row.get("chat_id"),
        source=_optional_text(row.get("source")),
        created_at=_serialize_timestamp(row.get("created_at")),
        last_activity_at=_serialize_timestamp(row.get("last_activity_at")),
        threads_count=int(row.get("threads_count") or 0),
        latest_thread_id=_optional_text(row.get("latest_thread_id")),
    )


def _client_detail_from_row(row: Mapping[str, object]) -> ClientDetailView:
    return ClientDetailView(
        id=str(row["id"]),
        user_id=_optional_text(row.get("user_id")),
        username=_optional_text(row.get("username")),
        full_name=_optional_text(row.get("full_name")),
        email=_optional_text(row.get("email")),
        company=_optional_text(row.get("company")),
        phone=_optional_text(row.get("phone")),
        metadata=dict(_row_mapping(row.get("metadata"))),
        chat_id=row.get("chat_id"),
        source=_optional_text(row.get("source")),
        created_at=_serialize_timestamp(row.get("created_at")),
    )


def _client_list_from_rows(
    rows: list[Mapping[str, object]],
    stats_row: Mapping[str, object] | None,
) -> ClientListView:
    stats = stats_row or {}
    return ClientListView(
        clients=[_client_list_item_from_row(row) for row in rows],
        total_clients=int(stats.get("total_clients") or 0),
        new_clients_7d=int(stats.get("new_clients_7d") or 0),
        active_dialogs=int(stats.get("active_dialogs") or 0),
    )


class ClientRepository:
    def __init__(self, pool: object) -> None:
        self.pool = pool

    async def list_for_project_view(
        self,
        project_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
    ) -> ClientListView:
        project_uuid = UUID(project_id)
        where_clause, search_params, param_idx = _list_where_clause(search)

        query = _client_list_query(
            where_clause,
            limit_param=param_idx,
            offset_param=param_idx + 1,
        )
        params: list[object] = [project_uuid, *search_params, limit, offset]

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            stats_row = await conn.fetchrow(_client_stats_query(), project_uuid)

        return _client_list_from_rows(
            [_row_mapping(row) for row in rows],
            _row_mapping(stats_row) if stats_row else None,
        )

    async def get_by_id_view(
        self, project_id: str, client_id: str
    ) -> ClientDetailView | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, user_id, username, full_name, email, company, phone,
                       metadata, chat_id, source, created_at
                FROM clients
                WHERE id = $1 AND project_id = $2
                """,
                UUID(client_id),
                UUID(project_id),
            )

        if not row:
            return None

        return _client_detail_from_row(_row_mapping(row))
