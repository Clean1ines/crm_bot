from typing import Protocol

from src.domain.project_plane.client_views import ClientDetailView, ClientListView


class ClientReaderPort(Protocol):
    async def list_for_project_view(
        self,
        project_id: str,
        *,
        limit: int,
        offset: int,
        search: str | None,
    ) -> ClientListView: ...

    async def get_by_id_view(
        self, project_id: str, client_id: str
    ) -> ClientDetailView | None: ...
