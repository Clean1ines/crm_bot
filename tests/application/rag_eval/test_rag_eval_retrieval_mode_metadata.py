from __future__ import annotations

import asyncio

from src.application.rag_eval.runner import RagEvalRunner
from src.application.rag_eval.schemas import RagEvalEvidenceEntry, RagEvalQuestion


class OrderedRetriever:
    def __init__(self, ids: list[str]) -> None:
        self.ids = ids

    async def retrieve(
        self,
        *,
        project_id: str,
        question: str,
        limit: int,
    ) -> list[RagEvalEvidenceEntry]:
        return [
            RagEvalEvidenceEntry(id=item, content=f"content {item}")
            for item in self.ids[:limit]
        ]


def question() -> RagEvalQuestion:
    return RagEvalQuestion(
        id="question-1",
        dataset_id="dataset-1",
        project_id="project-1",
        document_id="doc-1",
        question="delivery",
        question_type="direct",
        expected_entry_ids=["expected"],
        expected_answer_summary="expected answer",
        should_answer=True,
    )


def test_top_hits_use_selected_retrieval_ordering_and_metadata() -> None:
    production = asyncio.run(
        RagEvalRunner(
            retriever=OrderedRetriever(["expected", "other"]),
            retrieval_limit=5,
            retrieval_metadata={
                "retrieval_mode": "production_equivalent",
                "retrieval_path": "production_rag_service.search_with_expansion",
                "query_expansion_enabled": True,
                "runtime_equivalent": True,
                "diagnostic": False,
            },
        ).run_question(
            run_id="run-1",
            project_id="project-1",
            question=question(),
        )
    )

    vector = asyncio.run(
        RagEvalRunner(
            retriever=OrderedRetriever(["other", "expected"]),
            retrieval_limit=5,
            retrieval_metadata={
                "retrieval_mode": "vector_debug",
                "retrieval_path": "knowledge_retrieval_surface.vector_only",
                "query_expansion_enabled": False,
                "runtime_equivalent": False,
                "diagnostic": True,
            },
        ).run_question(
            run_id="run-1",
            project_id="project-1",
            question=question(),
        )
    )

    assert production.top1_hit is True
    assert vector.top1_hit is False
    assert vector.top3_hit is True
    assert production.judge_json["retrieval_mode"] == "production_equivalent"
    assert vector.judge_json["retrieval_mode"] == "vector_debug"
    assert vector.judge_json["query_expansion_enabled"] is False
