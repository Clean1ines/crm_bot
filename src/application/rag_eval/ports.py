from __future__ import annotations

from collections.abc import Awaitable, Callable
from collections.abc import Mapping
from typing import Protocol

from src.application.rag_eval.schemas import (
    JsonObject,
    RagEvalAnswerJudgeResult,
    RagEvalChunk,
    RagEvalDataset,
    RagEvalQuestion,
    RagEvalResult,
    RagEvalRun,
    RagQualityReport,
)


RagEvalDatasetProgressCallback = Callable[[int, int, int], Awaitable[None]]
RagEvalDatasetControlCallback = Callable[[], Awaitable[None]]


class RagEvalJsonLlmPort(Protocol):
    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
    ) -> Mapping[str, object]: ...


class RagEvalChunkSourcePort(Protocol):
    async def load_document_chunks(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[RagEvalChunk]: ...


class RagEvalDatasetGeneratorPort(Protocol):
    async def generate_dataset(
        self,
        *,
        project_id: str,
        document_id: str,
        chunks: list[RagEvalChunk],
        max_questions: int,
        progress_callback: RagEvalDatasetProgressCallback | None = None,
        control_callback: RagEvalDatasetControlCallback | None = None,
    ) -> RagEvalDataset: ...


class RagEvalRetrieverPort(Protocol):
    async def retrieve(
        self,
        *,
        project_id: str,
        question: str,
        limit: int,
    ) -> list[RagEvalChunk]: ...


class RagEvalAnswererPort(Protocol):
    async def answer(
        self,
        *,
        project_id: str,
        question: str,
        evidence: list[RagEvalChunk],
    ) -> str: ...


class RagEvalAnswerJudgePort(Protocol):
    async def judge_answer(
        self,
        *,
        question: RagEvalQuestion,
        retrieved_chunks: list[RagEvalChunk],
        answer_text: str,
    ) -> RagEvalAnswerJudgeResult: ...


class RagEvalStorePort(Protocol):
    async def save_dataset(self, *, dataset: RagEvalDataset) -> None: ...

    async def create_run(self, *, run: RagEvalRun) -> None: ...

    async def save_result(self, *, result: RagEvalResult) -> None: ...

    async def save_report(self, *, report: RagQualityReport) -> None: ...

    async def finish_run(self, *, run: RagEvalRun) -> None: ...


class RagEvalReportSinkPort(Protocol):
    async def write_json_report(
        self,
        *,
        run_id: str,
        payload: JsonObject,
    ) -> None: ...

    async def write_markdown_report(
        self,
        *,
        run_id: str,
        markdown: str,
    ) -> None: ...
