from __future__ import annotations

from typing import Any


class PostgresCapacityAdmissionProjectionWriter:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def persist_candidates(self, *args: Any, **kwargs: Any) -> int:
        return 0

    async def upsert_candidates(self, *args: Any, **kwargs: Any) -> int:
        return 0

    async def write_candidates(self, *args: Any, **kwargs: Any) -> int:
        return 0

    async def execute(self, *args: Any, **kwargs: Any) -> int:
        return 0
