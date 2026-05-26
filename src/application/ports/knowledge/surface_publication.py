from __future__ import annotations

from typing import Protocol


class KnowledgeSurfacePublicationPort(Protocol):
    async def publish_surface(self, *, project_id: str, document_id: str, surface_id: str) -> str: ...

    async def create_runtime_entry_from_surface(self, *, project_id: str, document_id: str, surface_id: str) -> str: ...

    async def link_surface_publication(self, *, surface_id: str, runtime_entry_id: str) -> None: ...
