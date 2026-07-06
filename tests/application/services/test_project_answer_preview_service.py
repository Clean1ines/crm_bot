from __future__ import annotations

import pytest

from src.application.services.project_answer_preview_service import (
    ProjectAnswerPreviewService,
    ProjectAnswerPreviewValidationError,
)


class FakeRagService:
    def __init__(self, chunks: list[dict[str, object]]) -> None:
        self.chunks = chunks
        self.calls: list[dict[str, object]] = []

    async def search_with_expansion(self, **kwargs):
        self.calls.append(kwargs)
        return self.chunks


class FakeRuntimeLoader:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def load_project_configuration(self, project_id: str):
        self.calls.append(project_id)
        return {"settings": {"target_language": "ru"}}


class FakePromptBuilder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs) -> str:
        self.calls.append(kwargs)
        chunks = kwargs["knowledge_chunks"]
        assert isinstance(chunks, list)
        return f"prompt: {chunks[0]['content']}" if chunks else "prompt: no facts"


class FakeAnswerCompletion:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: list[dict[str, object]] = []

    async def complete(self, prompt: str, *, project_configuration=None) -> str:
        self.calls.append(
            {"prompt": prompt, "project_configuration": project_configuration}
        )
        return self.answer


@pytest.mark.asyncio
async def test_preview_service_calls_runtime_rag_and_returns_answer_first() -> None:
    rag = FakeRagService(
        [
            {
                "id": "runtime-entry-1",
                "content": "Полный опубликованный факт о доставке.",
                "score": 0.91,
                "method": "runtime_hybrid",
                "source": "runtime",
                "entry_kind": "faq_workbench_fact",
            }
        ]
    )
    loader = FakeRuntimeLoader()
    prompt_builder = FakePromptBuilder()
    completion = FakeAnswerCompletion("Доставка занимает два дня.")
    service = ProjectAnswerPreviewService(
        rag_service=rag,
        runtime_loader=loader,
        prompt_builder=prompt_builder,
        answer_completion=completion,
    )

    result = await service.execute(
        project_id="project-1",
        question="  Когда доставка? ",
        limit=5,
    )

    assert rag.calls == [
        {
            "project_id": "project-1",
            "query": "Когда доставка?",
            "thread_id": None,
            "final_limit": 5,
        }
    ]
    assert loader.calls == ["project-1"]
    assert "Полный опубликованный факт о доставке." in completion.calls[0]["prompt"]
    assert result.answer == "Доставка занимает два дня."
    assert result.to_dict()["answer"] == "Доставка занимает два дня."
    assert result.to_dict()["debug_context"]["facts"][0]["id"] == "runtime-entry-1"


@pytest.mark.asyncio
async def test_preview_service_rejects_empty_question() -> None:
    service = ProjectAnswerPreviewService(
        rag_service=FakeRagService([]),
        runtime_loader=FakeRuntimeLoader(),
        prompt_builder=FakePromptBuilder(),
        answer_completion=FakeAnswerCompletion(""),
    )

    with pytest.raises(ProjectAnswerPreviewValidationError):
        await service.execute(project_id="project-1", question="   ")


@pytest.mark.asyncio
async def test_preview_service_empty_retrieval_returns_honest_answer() -> None:
    service = ProjectAnswerPreviewService(
        rag_service=FakeRagService([]),
        runtime_loader=FakeRuntimeLoader(),
        prompt_builder=FakePromptBuilder(),
        answer_completion=FakeAnswerCompletion(""),
    )

    result = await service.execute(
        project_id="project-1",
        question="Есть ли самовывоз?",
    )

    assert result.is_empty is True
    assert "достаточного контекста" in result.answer
