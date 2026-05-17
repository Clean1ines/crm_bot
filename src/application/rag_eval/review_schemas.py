from __future__ import annotations

from typing import Literal, TypedDict

from src.domain.project_plane.json_types import JsonObject


RagEvalQuestionReviewStatus = Literal[
    "candidate",
    "accepted",
    "rejected",
    "edited",
    "applied",
]

RagEvalRetrievalStatus = Literal[
    "reliable",
    "weak",
    "confused",
    "missing",
]

RagEvalReviewGroupStatus = Literal[
    "queued",
    "generating_questions",
    "checking_retrieval",
    "ready_for_review",
    "failed",
]


class RagEvalQuestionReviewState(TypedDict, total=False):
    id: str
    question_id: str
    run_id: str
    dataset_id: str
    project_id: str
    document_id: str
    source_chunk_id: str
    status: RagEvalQuestionReviewStatus
    original_question: str
    edited_question: str
    review_reason: str
    reviewed_by: str
    reviewed_at: str | None
    created_at: str
    updated_at: str


class RagEvalApplyAcceptedSummary(TypedDict):
    ok: bool
    run_id: str
    applied_questions: int
    failed_questions: int
    failures: list[JsonObject]
    queued_rerun_job_id: str | None


class RagEvalReviewRunPayload(TypedDict):
    id: str
    dataset_id: str
    project_id: str
    document_id: str
    status: str
    started_at: str
    finished_at: str | None
    retriever_version: str
    reranker_version: str
    generator_model: str
    result_count: int
