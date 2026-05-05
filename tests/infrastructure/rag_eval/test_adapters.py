from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from collections.abc import Mapping

import pytest

from src.application.rag_eval.schemas import RagEvalChunk
from src.interfaces.composition.rag_eval_answerer import ProductionRagEvalAnswerer
from src.infrastructure.rag_eval.adapters import (
    LocalRagEvalReportSink,
    RagServiceRagEvalRetriever,
    _extract_json_object,
)


class FakeRagService:
    async def search_with_expansion(
        self,
        *,
        project_id: str,
        query: str,
        final_limit: int,
    ) -> list[dict[str, object]]:
        assert project_id == "project_1"
        assert query == "question?"
        assert final_limit == 3
        return [
            {
                "id": "chunk_1",
                "content": "Evidence text",
                "score": 0.91,
                "method": "hybrid",
                "source": "kb.md",
                "document_id": "doc_1",
            },
            {
                "id": "empty",
                "content": "",
            },
        ]


@pytest.mark.asyncio
async def test_rag_service_retriever_maps_production_rag_results() -> None:
    retriever = RagServiceRagEvalRetriever(FakeRagService())

    chunks = await retriever.retrieve(
        project_id="project_1",
        question="question?",
        limit=3,
    )

    assert len(chunks) == 1
    assert chunks[0].id == "chunk_1"
    assert chunks[0].content == "Evidence text"
    assert chunks[0].source == "kb.md"
    assert chunks[0].metadata["score"] == 0.91
    assert chunks[0].metadata["method"] == "hybrid"


@pytest.mark.asyncio
async def test_production_answerer_uses_response_generator_state_contract() -> None:
    seen_state: dict[str, object] = {}

    def node_factory():
        async def node(state: Mapping[str, object]) -> dict[str, object]:
            seen_state.update(dict(state))
            return {"response_text": "Ответ по evidence."}

        return node

    answerer = ProductionRagEvalAnswerer(node_factory=node_factory)

    answer = await answerer.answer(
        project_id="project_1",
        question="Что известно?",
        evidence=[
            RagEvalChunk(
                id="chunk_1",
                content="Evidence text",
                document_id="doc_1",
                source="kb.md",
                metadata={"score": 0.9},
            )
        ],
    )

    assert answer == "Ответ по evidence."
    assert seen_state["decision"] == "RESPOND_KB"
    assert seen_state["user_input"] == "Что известно?"
    prompt_chunks = seen_state["knowledge_chunks"]
    assert isinstance(prompt_chunks, list)
    assert prompt_chunks[0]["id"] == "chunk_1"
    assert prompt_chunks[0]["content"] == "Evidence text"


@pytest.mark.asyncio
async def test_local_report_sink_writes_markdown_and_json() -> None:
    with TemporaryDirectory() as tmp:
        sink = LocalRagEvalReportSink(reports_dir=tmp)

        await sink.write_markdown_report(run_id="run_1", markdown="# Report")
        await sink.write_json_report(run_id="run_1", payload={"score": 91})

        md_path = Path(tmp) / "rag-eval-run_1.md"
        json_path = Path(tmp) / "rag-eval-run_1.json"

        assert md_path.read_text(encoding="utf-8") == "# Report"
        assert json.loads(json_path.read_text(encoding="utf-8")) == {"score": 91}


def test_extract_json_object_accepts_plain_and_fenced_json() -> None:
    assert _extract_json_object('{"ok": true}')["ok"] is True
    assert _extract_json_object('```json\n{"ok": true}\n```')["ok"] is True
    assert _extract_json_object('prefix {"ok": true} suffix')["ok"] is True
