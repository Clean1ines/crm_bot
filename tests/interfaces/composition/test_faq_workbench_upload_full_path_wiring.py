from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import pytest

from src.interfaces.composition.faq_workbench_upload import (
    upload_faq_workbench_knowledge_file,
)


@dataclass(slots=True)
class FakeLogger:
    warnings: list[str] = field(default_factory=list)

    def warning(self, message: str) -> None:
        self.warnings.append(message)


@dataclass(slots=True)
class FakePool:
    execute_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    fetchrow_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    fetch_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append((" ".join(query.lower().split()), args))
        return "OK"

    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> Mapping[str, object] | None:
        self.fetchrow_calls.append((" ".join(query.lower().split()), args))
        return None

    async def fetch(
        self,
        query: str,
        *args: object,
    ) -> Sequence[Mapping[str, object]]:
        self.fetch_calls.append((" ".join(query.lower().split()), args))
        return ()


@dataclass(slots=True)
class FakeQueueRepositoryWithoutExecute:
    marker: str = "queue repository intentionally has no execute method"


@pytest.mark.asyncio
async def test_upload_faq_workbench_uses_pool_for_parallel_queue_adapter_not_queue_repo() -> (
    None
):
    pool = FakePool()
    queue_repo = FakeQueueRepositoryWithoutExecute()

    result = await upload_faq_workbench_knowledge_file(
        pool=pool,
        queue_repo=queue_repo,
        project_id="00000000-0000-0000-0000-000000000001",
        file_name="knowledge.md",
        file_content=(
            b"# Product\n"
            b"Bot answers customers in Telegram.\n\n"
            b"## Handoff\n"
            b"Complex questions are handed off to a manager."
        ),
        logger=FakeLogger(),
    )

    assert result.document_id is not None
    assert result.chunks >= 1
    assert result.preprocessing_status == "processing"

    execute_queries = [query for query, _args in pool.execute_calls]
    assert any("insert into execution_queue" in query for query in execute_queries)


@dataclass(slots=True)
class FailingExecutePool(FakePool):
    async def execute(self, query: str, *args: object) -> str:
        normalized_query = " ".join(query.lower().split())
        self.execute_calls.append((normalized_query, args))
        if "insert into execution_queue" in normalized_query:
            raise RuntimeError("queue insert failed")
        return "OK"


@pytest.mark.asyncio
async def test_upload_queue_failure_is_now_pool_execute_failure_not_queue_repo_attribute_error() -> (
    None
):
    pool = FailingExecutePool()
    queue_repo = FakeQueueRepositoryWithoutExecute()

    with pytest.raises(RuntimeError, match="queue insert failed"):
        await upload_faq_workbench_knowledge_file(
            pool=pool,
            queue_repo=queue_repo,
            project_id="00000000-0000-0000-0000-000000000001",
            file_name="knowledge.md",
            file_content=(
                b"# Product\n"
                b"Bot answers customers in Telegram.\n\n"
                b"## Handoff\n"
                b"Complex questions are handed off to a manager."
            ),
            logger=FakeLogger(),
        )

    assert any(
        "insert into execution_queue" in query for query, _args in pool.execute_calls
    )
