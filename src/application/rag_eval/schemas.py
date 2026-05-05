from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Mapping, TypeAlias
from uuid import uuid4

JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
JsonObject: TypeAlias = dict[str, JsonValue]

RagEvalQuestionType: TypeAlias = Literal[
    "direct",
    "paraphrase",
    "short_vague",
    "similar_wrong",
    "unknown",
    "risky",
    "contradiction",
]

RagEvalStatus: TypeAlias = Literal[
    "created",
    "generating",
    "ready",
    "running",
    "completed",
    "failed",
]

RagEvalSeverity: TypeAlias = Literal["low", "medium", "high", "critical"]

RagEvalReadiness: TypeAlias = Literal[
    "ready",
    "needs_review",
    "not_ready",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_eval_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [json_value(item) for item in value]
    return str(value)


@dataclass(frozen=True, slots=True)
class RagEvalChunk:
    id: str
    content: str
    document_id: str | None = None
    source: str | None = None
    score: float = 0.0
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_json(self) -> JsonObject:
        return {
            "id": self.id,
            "content": self.content,
            "document_id": self.document_id,
            "source": self.source,
            "score": self.score,
            "metadata": json_value(dict(self.metadata)),
        }


@dataclass(frozen=True, slots=True)
class RagEvalQuestion:
    id: str
    dataset_id: str
    project_id: str
    document_id: str
    question: str
    question_type: RagEvalQuestionType
    expected_chunk_ids: list[str]
    expected_answer_summary: str
    should_answer: bool
    should_escalate: bool = False
    difficulty: int = 1
    severity: RagEvalSeverity = "medium"
    source: str = "llm_generated"
    metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def to_json(self) -> JsonObject:
        return {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "project_id": self.project_id,
            "document_id": self.document_id,
            "question": self.question,
            "question_type": self.question_type,
            "expected_chunk_ids": list(self.expected_chunk_ids),
            "expected_answer_summary": self.expected_answer_summary,
            "should_answer": self.should_answer,
            "should_escalate": self.should_escalate,
            "difficulty": self.difficulty,
            "severity": self.severity,
            "source": self.source,
            "metadata": json_value(dict(self.metadata)),
            "created_at": self.created_at.isoformat(),
        }


@dataclass(slots=True)
class RagEvalDataset:
    id: str
    project_id: str
    document_id: str
    status: RagEvalStatus = "created"
    model_used: str = ""
    total_questions: int = 0
    questions: list[RagEvalQuestion] = field(default_factory=list)
    generated_at: datetime = field(default_factory=utc_now)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_json(self) -> JsonObject:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "document_id": self.document_id,
            "status": self.status,
            "model_used": self.model_used,
            "total_questions": self.total_questions,
            "questions": [question.to_json() for question in self.questions],
            "generated_at": self.generated_at.isoformat(),
            "metadata": json_value(dict(self.metadata)),
        }


@dataclass(frozen=True, slots=True)
class RagEvalAnswerJudgeResult:
    answer_supported: bool
    hallucination_risk: Literal["low", "medium", "high"]
    missing_important_info: bool
    client_friendly: bool
    should_answer_passed: bool
    notes: str
    score: float
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_json(self) -> JsonObject:
        return {
            "answer_supported": self.answer_supported,
            "hallucination_risk": self.hallucination_risk,
            "missing_important_info": self.missing_important_info,
            "client_friendly": self.client_friendly,
            "should_answer_passed": self.should_answer_passed,
            "notes": self.notes,
            "score": self.score,
            "metadata": json_value(dict(self.metadata)),
        }


@dataclass(frozen=True, slots=True)
class RagEvalResult:
    id: str
    run_id: str
    question_id: str
    question: RagEvalQuestion
    retrieved_chunks: list[RagEvalChunk]
    answer_text: str
    top1_hit: bool
    top3_hit: bool
    top5_hit: bool
    expected_chunk_found: bool
    wrong_chunk_top1: bool
    answer_supported: bool
    hallucination_risk: Literal["low", "medium", "high"]
    should_answer_passed: bool
    score: float
    notes: str = ""
    latency_ms: int = 0
    judge_json: JsonObject = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def to_json(self) -> JsonObject:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "question_id": self.question_id,
            "question": self.question.to_json(),
            "retrieved_chunk_ids": [chunk.id for chunk in self.retrieved_chunks],
            "retrieved_chunks": [chunk.to_json() for chunk in self.retrieved_chunks],
            "answer_text": self.answer_text,
            "top1_hit": self.top1_hit,
            "top3_hit": self.top3_hit,
            "top5_hit": self.top5_hit,
            "expected_chunk_found": self.expected_chunk_found,
            "wrong_chunk_top1": self.wrong_chunk_top1,
            "answer_supported": self.answer_supported,
            "hallucination_risk": self.hallucination_risk,
            "should_answer_passed": self.should_answer_passed,
            "score": self.score,
            "notes": self.notes,
            "latency_ms": self.latency_ms,
            "judge_json": self.judge_json,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(slots=True)
class RagEvalRun:
    id: str
    dataset_id: str
    project_id: str
    document_id: str
    status: RagEvalStatus = "created"
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    retriever_version: str = "production_rag"
    reranker_version: str = "production_rag"
    generator_model: str = ""
    results: list[RagEvalResult] = field(default_factory=list)

    def to_json(self) -> JsonObject:
        return {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "project_id": self.project_id,
            "document_id": self.document_id,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "retriever_version": self.retriever_version,
            "reranker_version": self.reranker_version,
            "generator_model": self.generator_model,
            "results": [result.to_json() for result in self.results],
        }


@dataclass(frozen=True, slots=True)
class RagQualityReport:
    id: str
    run_id: str
    dataset_id: str
    project_id: str
    document_id: str
    score: float
    readiness: RagEvalReadiness
    strengths: list[str]
    problems: list[str]
    recommendations: list[str]
    metrics: JsonObject
    markdown: str
    created_at: datetime = field(default_factory=utc_now)

    def to_json(self) -> JsonObject:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "dataset_id": self.dataset_id,
            "project_id": self.project_id,
            "document_id": self.document_id,
            "score": self.score,
            "readiness": self.readiness,
            "strengths": list(self.strengths),
            "problems": list(self.problems),
            "recommendations": list(self.recommendations),
            "metrics": self.metrics,
            "markdown": self.markdown,
            "created_at": self.created_at.isoformat(),
        }
