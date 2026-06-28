from __future__ import annotations

from typing import Protocol, Any


class CapacityAdmissionProjectionWriterPort(Protocol):
    async def persist_candidates(self, *args: Any, **kwargs: Any) -> object: ...

    async def upsert_candidates(self, *args: Any, **kwargs: Any) -> object: ...

    async def write_candidates(self, *args: Any, **kwargs: Any) -> object: ...
